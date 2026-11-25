"""Small adapter around the locked SDK. Keep limits on the raw SSE/error bytes."""

from contextlib import contextmanager
from contextvars import ContextVar
import logging
import os
import ssl
from urllib.request import getproxies_environment, proxy_bypass_environment
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


def network_client(factory, host, **options):
    """Resolve transport settings only for the single official HTTPS origin."""
    try:
        # HTTPX 0.28 parses every NO_PROXY entry as a mount. Some common IPv6
        # loopback entries break unrelated HTTPS calls. Evaluate just our origin.
        proxies = getproxies_environment()
        proxy = None
        if options.get("transport") is None and not proxy_bypass_environment(
            host + ":443", proxies
        ):
            proxy = proxies.get("https") or proxies.get("all")
        cafile = os.getenv("SSL_CERT_FILE")
        capath = os.getenv("SSL_CERT_DIR")
        if not (cafile or capath):
            cafile = os.getenv("REQUESTS_CA_BUNDLE")
        verify = (
            ssl.create_default_context(cafile=cafile, capath=capath)
            if cafile or capath
            else True
        )
        # Do not let HTTPX resolve the same environment again, or the SDK
        # inherit API credentials. TLS verification and hostname checks stay on.
        return factory(
            trust_env=False,
            proxy=proxy,
            verify=verify,
            follow_redirects=False,
            **options,
        )
    except (OSError, ValueError, ImportError, httpx.InvalidURL):
        # A proxy URL may contain a password. Do not propagate the original exception.
        pass
    raise Error("invalid_config")


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
