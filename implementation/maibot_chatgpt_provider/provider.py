import asyncio
import json
import random
import time
from dataclasses import dataclass
import httpx
from openai import APIStatusError, OpenAIError
from .wire import DirectSDK, private_wire, network_client

from .adapter import adapt
from .errors import Error, classify
from .oauth import RESOURCE, text
from .responses import consume


@dataclass(frozen=True)
class Settings:
    connect_timeout_seconds: int = 10
    read_idle_timeout_seconds: int = 90
    total_timeout_seconds: int = 180
    max_concurrent_requests: int = 1
    max_buffered_text_bytes: int = 1048576
    pre_admission_retry_limit: int = 0
    temporary_cooldown_seconds: int = 30


def catalog(obj):
    items = obj.get("models") if isinstance(obj, dict) else None
    if not isinstance(items, list):
        raise Error("upstream")
    out = []
    for m in items:
        if not isinstance(m, dict) or not text(m.get("visibility")):
            raise Error("upstream")
        if m["visibility"] == "list":
            if not text(m.get("slug")) or not text(m.get("display_name")):
                raise Error("upstream")
            out.append({k: m[k] for k in ("slug", "display_name")})
    if not out:
        raise Error("upstream")
    return out


async def bounded_json(response, limit):
    buf = bytearray()
    async for chunk in response.aiter_bytes():
        if len(buf) + len(chunk) > limit:
            return None
        buf.extend(chunk)
    try:
        return json.loads(buf)
    except (ValueError, RecursionError):
        return None


class Provider:
    def __init__(self, manager, settings=Settings(), transport=None):
        self.manager = manager
        self.cfg = settings
        self.slots = asyncio.Semaphore(settings.max_concurrent_requests)
        self.http = network_client(
            httpx.AsyncClient,
            "api.openai.com",
            transport=transport,
            timeout=httpx.Timeout(
                settings.read_idle_timeout_seconds,
                connect=settings.connect_timeout_seconds,
            ),
        )
        self.tasks = set()
        self.closed = False
        self.cool_until = 0.0
        self.probing = False

    async def dispatch(self, operation, request):
        return await self._run(adapt(operation, request))

    async def models(self):
        return await self._run(None)

    async def _send(self, body, token):
        method, path = ("GET", "/models") if body is None else ("POST", "/responses")
        headers = {
            "Authorization": "Bearer " + token,
            "Accept": "application/json" if body is None else "text/event-stream",
            "Accept-Encoding": "identity",
        }
        started = False
        try:
            with private_wire():
                if body is None:
                    async with self.http.stream(
                        method, RESOURCE + path, headers=headers
                    ) as r:
                        if r.status_code != 200:
                            raise classify(
                                r.status_code, await bounded_json(r, 32768), r.headers
                            )
                        return catalog(await bounded_json(r, 1048576))
                # Per-call bearer avoids mutating a shared client during refresh. The HTTP pool belongs to Provider.
                sdk = DirectSDK(
                    api_key=token,
                    admin_api_key="",
                    organization="",
                    project="",
                    webhook_secret="",
                    base_url=RESOURCE,
                    max_retries=0,
                    http_client=self.http,
                    timeout=self.http.timeout,
                )
                async with sdk.responses.with_streaming_response.create(**body) as raw:
                    started = True
                    r = raw.http_response
                    if (
                        r.headers.get("content-type", "").split(";")[0].strip()
                        != "text/event-stream"
                    ):
                        raise Error("stream_failed")
                    return await consume(r, self.cfg.max_buffered_text_bytes)
        except APIStatusError as exc:
            error = classify(
                exc.status_code,
                await bounded_json(exc.response, 32768),
                exc.response.headers,
            )
        except (
            OpenAIError,
            httpx.HTTPError,
            ValueError,
            TypeError,
            RecursionError,
            UnicodeError,
        ):
            error = Error("stream_failed" if started else "transport")
        raise error

    async def _run(self, body):
        task = asyncio.current_task()
        cfg = self.cfg
        if self.closed:
            raise Error("temporarily_unavailable")
        if len(self.tasks) >= 2 * cfg.max_concurrent_requests:
            raise Error("rate_limited")
        self.tasks.add(task)
        deadline = time.monotonic() + cfg.total_timeout_seconds
        probe = False
        try:
            async with asyncio.timeout(cfg.total_timeout_seconds), self.slots:
                if self.cool_until:
                    if self.probing or self.cool_until > time.monotonic():
                        raise Error("temporarily_unavailable")
                    self.probing = probe = True
                    probe_until = self.cool_until
                for attempt in range(1 + cfg.pre_admission_retry_limit):
                    token, gen = await self.manager.take()
                    try:
                        result = await self._send(body, token)
                    except Error as e:
                        if e.category == "usage_paused":
                            await asyncio.to_thread(
                                self.manager.store.pause, True, gen, e.request_id
                            )
                        if e.category in (
                            "rate_limited",
                            "temporarily_unavailable",
                            "upstream",
                        ) and (
                            e.http_status in (429, 503, 502, 504)
                            or e.category == "temporarily_unavailable"
                        ):
                            delay = (
                                e.retry_after_seconds
                                if e.retry_after_seconds is not None
                                else cfg.temporary_cooldown_seconds
                            )
                            if (
                                e.http_status in (429, 503)
                                and attempt < cfg.pre_admission_retry_limit
                                and delay <= cfg.temporary_cooldown_seconds
                                and delay + 0.25 < deadline - time.monotonic()
                            ):
                                await asyncio.sleep(delay + random.uniform(0, 0.2))
                                continue
                            self.cool_until = max(
                                self.cool_until, time.monotonic() + max(0.1, delay)
                            )
                        raise
                    await asyncio.to_thread(self.manager.store.check, gen)
                    if probe and self.cool_until == probe_until:
                        self.cool_until = 0.0
                    return result
        except TimeoutError:
            pass
        finally:
            self.tasks.discard(task)
            if probe:
                self.probing = False
        raise Error("transport")

    async def close(self):
        self.closed = True
        jobs = list(self.tasks)
        for t in jobs:
            t.cancel()
        await asyncio.gather(*jobs, return_exceptions=True)
        try:
            await self.manager.close()
        finally:
            await self.http.aclose()
