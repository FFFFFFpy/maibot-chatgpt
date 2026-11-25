import asyncio
import json
from pathlib import Path
import threading
import httpx
import pytest
from .support import CANARY, engine, setup
from .test_login import Site, key
from .test_provider import sse, final, call, run
from maibot_chatgpt_provider.errors import Error
from maibot_chatgpt_provider.oauth import OAuth, login, DIRECT
from maibot_chatgpt_provider.credentials import Store

pytestmark = pytest.mark.offline


def test_QA009_two_browsers(tmp_path, key):
    async def go():
        s = Store(tmp_path)
        older = Site(key, "success")
        later = Site(key, "success")
        ready = threading.Event()
        commit = threading.Event()

        def delayed(url):
            ready.set()
            assert commit.wait(10)
            older.open(url)

        t = asyncio.create_task(
            login(s, OAuth(httpx.MockTransport(older.endpoint)), delayed)
        )
        assert await asyncio.to_thread(ready.wait, 5)
        try:
            await login(s, OAuth(httpx.MockTransport(later.endpoint)), later.open)
            before = s.path.read_bytes()
        finally:
            commit.set()
        with pytest.raises(Error, match="stale_attempt"):
            await t
        assert before == s.path.read_bytes() and s.current()["session_generation"] == 1

    asyncio.run(go())


def test_QA007_missing_issued(tmp_path, key):
    site = Site(key, "no-issued")
    s = Store(tmp_path)
    with pytest.raises(Error, match="invalid_login"):
        asyncio.run(login(s, OAuth(httpx.MockTransport(site.endpoint)), site.open))
    assert s.current() is None and site.exchanges == 0


def test_QA011_oauth_redirect(tmp_path):
    seen = []

    def redirect(r):
        seen.append(str(r.url))
        return httpx.Response(302, headers={"Location": "https://synthetic.invalid"})

    o = OAuth(httpx.MockTransport(redirect))
    with pytest.raises(Error):
        o.refresh(setup(tmp_path).current())
    assert len(seen) == 1


def test_QA028_concurrent_cooldown(tmp_path):
    async def go():
        gate = asyncio.Event()
        ready = asyncio.Event()
        calls = []

        async def upstream(r):
            calls.append(1)
            if len(calls) == 1:
                ready.set()
                await gate.wait()
                return sse(final())
            return httpx.Response(429, json={}, headers={"Retry-After": "3"})

        p = engine(tmp_path, upstream, max_concurrent_requests=2)
        earlier = asyncio.create_task(call(p))
        await ready.wait()
        try:
            with pytest.raises(Error, match="rate_limited"):
                await call(p)
            gate.set()
            assert (await earlier)["status"] == "completed"
            with pytest.raises(Error, match="temporarily_unavailable"):
                await call(p)
            assert len(calls) == 2
        finally:
            gate.set()
            await p.close()

    asyncio.run(go())


@pytest.mark.parametrize(
    "name",
    [
        "text_completed",
        "refusal_completed",
        "interrupted",
        "partial_failed",
        "incomplete",
    ],
)
def test_pack_sse(tmp_path, name):
    fixtures = Path(__file__).resolve().parents[2] / "fixtures"
    raw = (fixtures / "responses" / (name + ".sse")).read_bytes()
    req = json.loads((fixtures / "maibot/context-items-v1.request.json").read_bytes())
    p = engine(tmp_path, lambda _: sse(raw))
    if name.endswith("_completed"):
        assert run(p, lambda p: p.dispatch("response", req))["status"] == "completed"
    else:
        with pytest.raises(Error):
            run(p, lambda p: p.dispatch("response", req))
