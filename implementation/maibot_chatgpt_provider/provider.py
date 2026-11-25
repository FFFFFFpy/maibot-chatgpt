import asyncio
import json
import random
import re
import time
from dataclasses import dataclass
from collections import OrderedDict
import httpx
from .wire import private_wire, network_client

from .adapter import adapt, state_lane, EFFORTS
from .errors import Error, classify
from .oauth import RESOURCE, text
from .responses import StreamError, consume
from .model_probe import NAME as PROBE_NAME


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
            entry = {k: m[k] for k in ("slug", "display_name")}
            raw = m.get("supported_reasoning_levels")
            levels = []
            if isinstance(raw, list):
                for value in raw:
                    level = value.get("effort") if isinstance(value, dict) else value
                    if (
                        isinstance(level, str)
                        and level.strip() in EFFORTS
                        and level.strip() not in levels
                    ):
                        levels.append(level.strip())
            if levels:
                entry["supported_reasoning_levels"] = levels
            out.append(entry)
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


class _StateRejected(Exception):
    pass


def rejected_state(status, problem):
    if status not in (400, 409, 422) or not isinstance(problem, dict):
        return False
    err = problem.get("error", problem)
    if not isinstance(err, dict):
        return False
    return any(
        isinstance(err.get(k), str)
        and re.search(
            r"(?i)\b(?:x-codex-turn-state|(?:invalid[_ -]|expired[_ -]|unknown[_ -]|stale[_ -])turn[_ -]state)\b",
            err[k],
        )
        for k in ("code", "param", "message")
    )


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
        self.turn_states = OrderedDict()
        self.closed = False
        self.cool_until = 0.0
        self.probing = False

    async def dispatch(self, operation, request):
        body = adapt(operation, request)
        return await self._run(body, state_lane(request))

    async def models(self):
        return await self._run(None)

    async def _send(self, body, token, state=None):
        method, path = ("GET", "/models") if body is None else ("POST", "/responses")
        headers = {
            "Authorization": "Bearer " + token,
            "Accept": "application/json" if body is None else "text/event-stream",
            "Accept-Encoding": "identity",
        }
        if body is not None:
            headers["session_id"] = headers["session-id"] = body["prompt_cache_key"]
            if state is not None:
                headers["x-codex-turn-state"] = state
        started = False
        try:
            with private_wire():
                async with self.http.stream(
                    method,
                    RESOURCE + path,
                    headers=headers,
                    **({"json": body} if body is not None else {}),
                ) as r:
                    if r.status_code != 200:
                        problem = await bounded_json(r, 32768)
                        if state is not None and rejected_state(r.status_code, problem):
                            raise _StateRejected()
                        # Use only a whitelisted param path, never echo raw upstream messages.
                        err = (
                            problem.get("error") if isinstance(problem, dict) else None
                        )
                        param = err.get("param") if isinstance(err, dict) else None
                        match = (
                            re.fullmatch(
                                r"tools(?:\[(\d{1,3})\]|\.(\d{1,3}))\.parameters(?:\.(not))?",
                                param,
                            )
                            if isinstance(param, str)
                            else None
                        )
                        if r.status_code == 400 and body and match:
                            idx = int(match[1] or match[2])
                            tools = body.get("tools", [])
                            if idx < len(tools) and tools[idx]["name"] == "schedule":
                                raise Error(
                                    "schedule_not_rejected"
                                    if match[3]
                                    else "schedule_schema_rejected",
                                    status=400,
                                    request_id=r.headers.get("x-request-id"),
                                )
                        raise classify(r.status_code, problem, r.headers)
                    if body is None:
                        return catalog(await bounded_json(r, 1048576)), None
                    started = True
                    content_type = r.headers.get("content-type", "").strip()
                    if (
                        content_type
                        and content_type.partition(";")[0].strip().lower()
                        != "text/event-stream"
                    ):
                        raise StreamError(
                            "HTTP 200，但返回内容不是 text/event-stream。请检查出口代理是否改写响应。"
                        )
                    names = (
                        {t["name"] for t in body.get("tools", [])}
                        if body.get("tool_choice") != "none"
                        else set()
                    )
                    probe_image = (
                        any(
                            part["type"] == "input_image"
                            for msg in body["input"]
                            for part in msg.get("content", [])
                        )
                        if names == {PROBE_NAME}
                        else None
                    )
                    result = await consume(
                        r,
                        self.cfg.max_buffered_text_bytes,
                        probe_image,
                        names if probe_image is None else (),
                    )
                    # Preserve the header bytes; never log, persist or forward them elsewhere.
                    raw = r.headers.get_list("x-codex-turn-state")
                    new = (
                        raw[0]
                        if len(raw) == 1 and re.fullmatch(r"[!-~][ -~]{0,4095}", raw[0])
                        else None
                    )
                    return result, new
        except httpx.TimeoutException:
            error = (
                StreamError("接收官方事件流时超时，未交付部分结果。")
                if started
                else Error("transport")
            )
        except (
            httpx.HTTPError,
            ValueError,
            TypeError,
            RecursionError,
            UnicodeError,
        ) as exc:
            error = (
                StreamError(
                    "读取事件流时连接中断。"
                    if isinstance(exc, httpx.HTTPError)
                    else "事件流编码或 JSON 格式无效，未交付结果。"
                )
                if started
                else Error("transport")
            )
        raise error

    async def _run(self, body, lane=None):
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
                recovered = False
                for attempt in range(1 + cfg.pre_admission_retry_limit):
                    token, gen = await self.manager.take()
                    try:
                        key = (
                            (gen, body["model"], body["prompt_cache_key"], lane)
                            if body and lane
                            else None
                        )
                        state = self.turn_states.get(key)
                        if state is not None:
                            self.turn_states.move_to_end(key)
                        try:
                            result, new = await self._send(body, token, state)
                        except _StateRejected:
                            recovered = True
                            if self.turn_states.get(key) == state:
                                self.turn_states.pop(key, None)
                            await asyncio.to_thread(self.manager.store.check, gen)
                            result, new = await self._send(body, token)
                            state = None
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
                                not recovered
                                and e.http_status in (429, 503)
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
                    if key and new and self.turn_states.get(key) == state:
                        self.turn_states[key] = new
                        self.turn_states.move_to_end(key)
                        if len(self.turn_states) > 256:
                            self.turn_states.popitem(last=False)
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
            self.turn_states.clear()
            await self.http.aclose()
