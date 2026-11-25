import socket
import ssl
import traceback

import httpx
import pytest

from maibot_chatgpt_provider.errors import Error
from maibot_chatgpt_provider.oauth import OAuth

pytestmark = pytest.mark.offline


@pytest.mark.parametrize(
    "scenario,word",
    [
        ("dns", "DNS"),
        ("cert", "证书校验"),
        ("proxy", "代理连接"),
        ("timeout", "超时"),
        ("403", "HTTP 403"),
        ("302", "HTTP 302"),
        ("html", "有效的登录配置"),
    ],
)
def test_discovery_safe_diagnostics(scenario, word):
    secret = "synthetic-private-detail"
    calls = []

    def handle(req):
        calls.append(str(req.url))
        assert "Authorization" not in req.headers
        if scenario in ("dns", "cert"):
            cause = (
                socket.gaierror(secret)
                if scenario == "dns"
                else ssl.SSLCertVerificationError(secret)
            )
            raise httpx.ConnectError(secret) from cause
        if scenario == "proxy":
            raise httpx.ProxyError(secret)
        if scenario == "timeout":
            raise httpx.ReadTimeout(secret)
        return httpx.Response(
            200 if scenario == "html" else int(scenario),
            text=secret,
            headers={"location": "https://example.invalid/"},
        )

    with pytest.raises(Error) as error:
        OAuth(httpx.MockTransport(handle)).discover()
    assert word in error.value.hint and secret not in "".join(
        traceback.format_exception(error.value)
    )
    assert calls == ["https://auth.openai.com/.well-known/openid-configuration"]
