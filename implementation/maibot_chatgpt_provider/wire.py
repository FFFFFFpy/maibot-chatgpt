"""Small adapter around the locked SDK. Keep limits on the raw SSE/error bytes."""

from contextlib import contextmanager
from contextvars import ContextVar
import logging
import threading

import httpx
from openai import AsyncOpenAI
from .oauth_constants import RESOURCE
from .errors import Error

_private = ContextVar("siwc_private_wire", default=False)


class _PrivateFilter(logging.Filter):
    def filter(self, record):
        return not _private.get()


_filter = _PrivateFilter()
_guard = threading.Lock()


@contextmanager
def private_wire():
    # Suppress library wire diagnostics only for this task/thread, never other providers.
    # httpcore creates these named loggers lazily (e.g. when TLS is negotiated).
    with _guard:
        for name in (
            "openai._base_client",
            "openai._client",
            "openai",
            "httpx",
            "httpcore.connection",
            "httpcore.http11",
            "httpcore.http2",
            "httpcore.proxy",
            "httpcore.socks",
            "httpcore.connection_pool",
        ):
            logging.getLogger(name).addFilter(_filter)
    mark = _private.set(True)
    try:
        yield
    finally:
        _private.reset(mark)


class DirectSDK(AsyncOpenAI):
    @property
    def default_headers(self):
        # Never merge OPENAI_CUSTOM_HEADERS, organization or project into requests.
        return {
            "Accept": "text/event-stream",
            "Accept-Encoding": "identity",
            "Content-Type": "application/json",
        }

    async def _send_request(self, request, *, stream, **kwargs):
        if str(request.url) != RESOURCE + "/responses" or request.method != "POST":
            raise Error("route_mismatch")
        r = await self._client.send(request, stream=True, follow_redirects=False)
        if r.status_code == 200:
            return r
        # SDK reads error responses before raising: cap the bytes BEFORE handing them back.
        buf = bytearray()
        try:
            async for chunk in r.aiter_bytes():
                if len(buf) + len(chunk) > 32768:
                    buf.clear()
                    break
                buf.extend(chunk)
        finally:
            await r.aclose()
        return httpx.Response(
            r.status_code,
            content=bytes(buf),
            headers={
                k: v
                for k, v in r.headers.items()
                if k in ("retry-after", "x-request-id", "content-type")
            },
            request=request,
        )
