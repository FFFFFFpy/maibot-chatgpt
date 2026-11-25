"""Local-only test: an ordinary CONNECT proxy denies tunnels before any bearer is sent."""

import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
import ssl
import threading

import certifi
import httpx
import pytest

from maibot_chatgpt_provider.errors import Error
from maibot_chatgpt_provider.oauth import OAuth
from maibot_chatgpt_provider.provider import Provider
from maibot_chatgpt_provider.token_manager import TokenManager
from maibot_chatgpt_provider.wire import network_client
from .support import setup

pytestmark = pytest.mark.offline


@pytest.fixture(autouse=True)
def clear_env(monkeypatch):
    for k in list(os.environ):
        if k.lower().endswith("_proxy") or k.upper() in (
            "SSL_CERT_FILE",
            "SSL_CERT_DIR",
            "REQUESTS_CA_BUNDLE",
        ):
            monkeypatch.delenv(k)


def test_both_clients_use_https_proxy(tmp_path, monkeypatch):
    seen = []

    class Deny(BaseHTTPRequestHandler):
        def do_CONNECT(self):
            seen.append((self.path, "Authorization" in self.headers))
            self.send_error(502)

        def log_message(self, *args):
            pass

    proxy = ThreadingHTTPServer(("127.0.0.1", 0), Deny)
    thread = threading.Thread(target=proxy.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("HTTPS_PROXY", f"http://127.0.0.1:{proxy.server_port}")
    monkeypatch.setenv("NO_PROXY", "localhost,[::1],127.0.0.1")
    try:
        with pytest.raises(Error):
            OAuth(timeout=3).discover()

        async def fetch():
            p = Provider(TokenManager(setup(tmp_path), OAuth()))
            try:
                with pytest.raises(Error):
                    await p.models()
            finally:
                await p.close()

        asyncio.run(fetch())
        assert seen == [("auth.openai.com:443", False), ("api.openai.com:443", False)]
    finally:
        proxy.shutdown()
        proxy.server_close()
        thread.join()


def test_proxy_bypass_per_official_origin(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1234")
    monkeypatch.setenv("NO_PROXY", "auth.openai.com,[::1]")
    assert network_client(lambda **kw: kw["proxy"], "auth.openai.com") is None
    assert (
        network_client(lambda **kw: kw["proxy"], "api.openai.com")
        == "http://127.0.0.1:1234"
    )


@pytest.mark.parametrize("variable", ["SSL_CERT_FILE", "REQUESTS_CA_BUNDLE"])
@pytest.mark.parametrize("factory", [httpx.Client, httpx.AsyncClient])
def test_invalid_ca_fails_closed(variable, factory, monkeypatch, tmp_path):
    monkeypatch.setenv(variable, str(tmp_path / "synthetic-private-path"))
    with pytest.raises(Error, match="invalid_config") as caught:
        network_client(factory, "api.openai.com")
    assert caught.value.__context__ is None and "synthetic-private-path" not in str(
        caught.value
    )


def test_ca_alias_and_precedence(monkeypatch):
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", certifi.where())
    ctx = network_client(lambda **opts: opts["verify"], "auth.openai.com")
    assert (
        ctx.verify_mode == ssl.CERT_REQUIRED
        and ctx.check_hostname
        and ctx.get_ca_certs()
    )
    monkeypatch.setenv("SSL_CERT_FILE", certifi.where())
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", "synthetic-unused")
    with network_client(httpx.Client, "auth.openai.com") as client:
        assert not client.follow_redirects
