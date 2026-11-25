"""WebUI transaction tests: no real account or external connection."""

import asyncio
import json
import os
from urllib.parse import parse_qs, urlsplit, urlencode
import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from maibot_chatgpt_provider.credentials import Store
from maibot_chatgpt_provider.oauth import OAuth
from maibot_chatgpt_provider.token_manager import TokenManager
from maibot_chatgpt_provider.page_login import PageLogin, REDIRECT, b64, oaep, unb64
from scripts.desktop_callback import decode_pair
from .support import CANARY, record
from .test_login import Site, key
from .test_cli_sdk import load_sdk_plugin

pytestmark = pytest.mark.offline


def create(path, key):
    site = Site(key, "success")
    manager = TokenManager(Store(path), OAuth(httpx.MockTransport(site.endpoint)))
    return site, PageLogin(manager)


def receipt(pair, raw):
    pub = serialization.load_der_public_key(unb64(pair["pub"]))
    aes = AESGCM.generate_key(256)
    iv = os.urandom(12)
    return json.dumps(
        dict(
            id=pair["id"],
            iv=b64(iv),
            key=b64(pub.encrypt(aes, oaep())),
            box=b64(AESGCM(aes).encrypt(iv, raw.encode(), pair["id"].encode())),
        )
    )


@pytest.mark.parametrize(
    "case",
    [
        "ok",
        "invalid-state",
        "corrupt",
        "deny",
        "cancel",
        "expire",
        "stale",
        "foreign-receipt",
    ],
)
def test_page_remote(tmp_path, key, case):
    async def go():
        site, p = create(tmp_path, key)
        assert (await p.start("desktop"))["ok"]
        assert not (await p.start("desktop"))["ok"]
        await p.task
        status = await p.status()
        assert status["phase"] == "waiting" and CANARY not in str(status)
        pair, state = decode_pair(status["material"])
        site.seen = parse_qs(urlsplit(pair["url"]).query)
        assert site.seen["redirect_uri"] == [REDIRECT]
        args = dict(code="synthetic-code", state=state, client_id="synthetic-issued")
        if case == "invalid-state":
            args["state"] = "unrelated"
        if case == "deny":
            args["error"] = "access_denied"
        env = receipt(pair, REDIRECT + "?" + urlencode(args))
        assert "synthetic-code" not in env
        if case == "foreign-receipt":
            env = env.replace(pair["id"], "another-attempt")
        if case == "corrupt":
            env = "broken"
        if case == "expire":
            p.expire()
        if case == "cancel":
            assert (await p.cancel(pair["id"]))["ok"]
        if case == "stale":
            p.manager.store.replace(record(), 0)
        result = await p.finish(env)
        if case in ("ok", "stale"):
            assert result["ok"] and not (await p.finish(env))["ok"]
            await p.task
            s = await p.status()
            assert not s["material"] and CANARY not in str(s)
            assert (
                s["phase"] == ("complete" if case == "ok" else "failed")
                and site.exchanges == 1
            )
            assert p.manager.store.current()["session_generation"] == 1
        else:
            assert (
                not result["ok"]
                and site.exchanges == 0
                and not p.manager.store.current()
            )
        await p.close()

    asyncio.run(go())


def test_sdk_static_apis():
    definitions = load_sdk_plugin().get_components()
    assert all(
        any(name in str(d) for d in definitions)
        for name in (
            "connection_start",
            "connection_finish",
            "connection_cancel",
            "connection_status",
        )
    )
