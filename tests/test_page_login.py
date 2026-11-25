"""Synthetic page transactions. Both paths share one PKCE attempt."""

import asyncio
from urllib.parse import parse_qs, urlsplit, urlencode
import httpx
import pytest
from maibot_chatgpt_provider.credentials import Store
from maibot_chatgpt_provider.oauth import OAuth, REVOKE
from maibot_chatgpt_provider.token_manager import TokenManager
from maibot_chatgpt_provider.page_login import PageLogin
from .support import CANARY, record
from .test_login import Site, key
from .test_cli_sdk import load_sdk_plugin

pytestmark = pytest.mark.offline


def create(path, key):
    site = Site(key, "success")

    def route(r):
        if str(r.url) == REVOKE:
            return httpx.Response(200)
        return site.endpoint(r)

    async def models():
        return [{"slug": "synthetic-test", "display_name": "Synthetic Test"}]

    return site, PageLogin(
        TokenManager(Store(path), OAuth(httpx.MockTransport(route))), models
    )


async def until(fn):
    async with asyncio.timeout(5):
        while not fn():
            await asyncio.sleep(0.01)


@pytest.mark.parametrize(
    "case",
    [
        "remote",
        "local",
        "race",
        "state",
        "origin",
        "path",
        "port",
        "duplicate",
        "fragment",
        "deny",
        "expire",
        "cancel",
        "stale",
    ],
)
def test_page_transaction(tmp_path, key, case):
    async def go():
        site, p = create(tmp_path, key)
        assert (await p.start())["ok"] and not (await p.start())["ok"]
        await until(lambda: p.phase == "waiting")
        s = await p.status()
        q = site.seen = parse_qs(urlsplit(s["authorize_url"]).query)
        redirect = q["redirect_uri"][0]
        args = dict(
            code="synthetic-code", state=q["state"][0], client_id="synthetic-issued"
        )
        raw = redirect + "?" + urlencode(args)
        assert not any(x in str(s) for x in ("code_verifier", CANARY, "synthetic-code"))
        if case == "state":
            raw = raw.replace(q["state"][0], "bad")
        if case == "origin":
            raw = raw.replace("127.0.0.1", "localhost")
        if case == "path":
            raw = raw.replace("/auth/callback", "/callback")
        if case == "port":
            raw = raw.replace(redirect, "http://127.0.0.1:1/auth/callback")
        if case == "duplicate":
            raw += "&code=other"
        if case == "fragment":
            raw += "#x"
        if case == "deny":
            raw += "&error=access_denied"
        if case == "expire":
            p.expire()
        if case == "cancel":
            assert (await p.cancel(p.attempt))["ok"]
        if case == "stale":
            p.manager.store.replace(record(), 0)
        if case == "local":
            async with httpx.AsyncClient(trust_env=False) as c:
                assert (await c.get(raw)).status_code == 200
        elif case == "race":
            results = await asyncio.gather(p.finish(raw), p.finish(raw))
            assert sum(r["ok"] for r in results) == 1
        else:
            assert (await p.finish(raw))["ok"] == (case in ["remote", "deny", "stale"])
        if case in ("local", "remote", "race", "deny", "stale"):
            await p.task
            assert not (await p.finish(raw))["ok"]
            assert site.exchanges == int(case != "deny")
            assert not (await p.status())["authorize_url"]
            if case in ("local", "remote", "race"):
                assert (await p.status())["session"] == "active"
                assert (await p.models())["ok"]
                await p.catalog_task
                assert (await p.status())["models"][0]["slug"] == "synthetic-test"
                assert (await p.logout())["ok"]
                await p.task
                s = await p.status()
                assert (
                    s["session"] == "logged_out"
                    and not s["account"]
                    and not s["models"]
                    and not p.manager.store.current()["tokens"]
                )
            else:
                assert p.phase == "failed"
        else:
            assert not site.exchanges and not p.manager.store.current()
        await p.close()

    asyncio.run(go())


def test_sdk_static_apis():
    defs = load_sdk_plugin().get_components()
    assert all(
        any(k in str(d) for d in defs)
        for k in (
            "connection_start",
            "connection_finish",
            "connection_status",
            "connection_cancel",
            "connection_models",
            "connection_logout",
        )
    )
