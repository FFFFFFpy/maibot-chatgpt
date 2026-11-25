"""Synthetic sessions, real files and spawn workers on both OS families."""

import asyncio
import multiprocessing as mp
import os
from pathlib import Path
import stat
import threading
import time
from urllib.parse import parse_qs
import httpx
import pytest
from maibot_chatgpt_provider import credentials as cred
from maibot_chatgpt_provider.credentials import Store, stamp, atomic
from maibot_chatgpt_provider.errors import Error
from maibot_chatgpt_provider.oauth import (
    OAuth,
    TOKEN,
    RESOURCE,
    DISCOVERY,
    REVOKE,
    AUTHORIZE,
    JWKS,
    ISSUER,
    TERMINAL,
)
from maibot_chatgpt_provider.token_manager import TokenManager
from .support import setup, record, CANARY

pytestmark = pytest.mark.offline


class Rotator:
    timeout = 5

    def __init__(self):
        self.calls = 0

    def refresh(self, d):
        self.calls += 1
        d["expires_at"] = stamp(time.time() + 3600)
        d["tokens"].update(
            refresh_token="synthetic-rotated", access_token="synthetic-fresh"
        )
        return d


def test_QA010(tmp_path, monkeypatch):
    source = setup(tmp_path / "source")
    target = Store(tmp_path / "target")
    host = target.begin()[0]
    assert source.begin()[0] != host
    target.transfer(source.path)
    assert (
        target.begin()[0] == host
        and target.current()["tokens"] == source.current()["tokens"]
    )
    other = record()
    other["registration"]["subject"] = "another"
    atomic(source.path, other)
    before = target.path.read_bytes()
    with pytest.raises(Error, match="registration_mismatch"):
        target.transfer(source.path)
    assert before == target.path.read_bytes()
    if os.name != "nt":
        source.path.chmod(0o644)
        with pytest.raises(Error, match="storage_failed"):
            target.transfer(source.path)
    else:
        # Exercise the Unix policy predicate, not an actual Windows DACL measurement.
        class PosixView:
            name = "posix"

        monkeypatch.setattr(cred, "os", PosixView)
        with pytest.raises(Error, match="storage_failed"):
            target.transfer(source.path)


@pytest.mark.parametrize(
    "exp,earliest,want",
    [
        (600, None, False),
        (10, None, True),
        (10, "future", False),
        (10, "numeric", False),
        (10, "invalid", False),
        (-1, "invalid", "deny"),
        (-1, 0, True),
    ],
)
def test_QA012(tmp_path, exp, earliest, want):
    s = Store(tmp_path)
    d = record(exp)
    d["earliest_refresh_at"] = {
        "future": stamp(time.time() + 200),
        "numeric": int(time.time() + 200),
    }.get(earliest, earliest)
    s.replace(d)
    rot = Rotator()
    m = TokenManager(s, rot)
    if want == "deny":
        with pytest.raises(Error, match="temporarily_unavailable"):
            m._take()
    else:
        m._take()
    assert rot.calls == int(want is True)


def twin(path, barrier, count, results):
    def refresh(r):
        assert str(r.url) == TOKEN
        form = parse_qs(r.content.decode())
        assert form == dict(
            grant_type=["refresh_token"],
            refresh_token=["synthetic-refresh"],
            resource=[RESOURCE],
            client_id=["synthetic-client"],
        )
        with count.get_lock():
            count.value += 1
        time.sleep(0.15)
        return httpx.Response(
            200,
            json=dict(
                access_token="synthetic-fresh",
                refresh_token="synthetic-rotated",
                expires_in=3600,
                token_type="Bearer",
            ),
        )

    barrier.wait(10)
    results.put(
        asyncio.run(
            TokenManager(Store(path), OAuth(httpx.MockTransport(refresh))).take()
        )
    )


def test_QA013(tmp_path):
    s = setup(tmp_path, 0)
    ctx = mp.get_context("spawn")
    barrier = ctx.Barrier(2)
    count = ctx.Value("i", 0)
    results = ctx.Queue()
    workers = [
        ctx.Process(target=twin, args=(tmp_path, barrier, count, results))
        for _ in range(2)
    ]
    for p in workers:
        p.start()
    try:
        for p in workers:
            p.join(15)
            assert p.exitcode == 0
        assert [results.get(timeout=1) for _ in workers] == [("synthetic-fresh", 1)] * 2
        assert (
            count.value == 1
            and s.current()["revision"] == 2
            and s.current()["session_generation"] == 1
        )
    finally:
        for p in workers:
            if p.is_alive():
                p.kill()
                p.join()


def test_QA014(tmp_path):
    s = setup(tmp_path, 0)
    _, gen = TokenManager(s, Rotator())._take()
    s.check(gen)
    s.replace(record())
    with pytest.raises(Error, match="stale_attempt"):
        s.check(gen)
    gen = s.current()["session_generation"]
    TokenManager(s, OAuth(httpx.MockTransport(lambda _: httpx.Response(500)))).logout()
    with pytest.raises(Error, match="stale_attempt"):
        s.check(gen)


@pytest.mark.parametrize("phase", ["before_lock", "in_http", "after_write"])
def test_QA015(tmp_path, phase):
    s = setup(tmp_path, 0)
    started = threading.Event()
    release = threading.Event()
    rot = Rotator()
    m = TokenManager(s, rot)

    def hold():
        started.set()
        assert release.wait(5)

    if phase == "before_lock":
        original = m._take

        def wait():
            hold()
            return original()

        m._take = wait
    elif phase == "in_http":

        def endpoint(_):
            hold()
            return httpx.Response(
                200,
                json=dict(
                    access_token="synthetic-fresh",
                    refresh_token="synthetic-rotated",
                    expires_in=3600,
                    token_type="Bearer",
                ),
            )

        m.oauth = OAuth(httpx.MockTransport(endpoint))
    else:
        original = s.save

        def save(d):
            original(d)
            hold()

        s.save = save

    async def exercise():
        t = asyncio.create_task(m.take())
        assert await asyncio.to_thread(started.wait, 4)
        t.cancel()
        with pytest.raises(asyncio.CancelledError):
            await t
        waiter = asyncio.create_task(m.take())
        release.set()
        assert (await waiter)[0] == "synthetic-fresh"
        await m.close()

    asyncio.run(exercise())
    assert (
        s.current()["revision"] == 2
        and s.current()["tokens"]["refresh_token"] == "synthetic-rotated"
    )


def occupy(path, ready):
    with Store(path).lock():
        ready.set()
        time.sleep(30)


def test_QA016(tmp_path):
    ctx = mp.get_context("spawn")
    ready = ctx.Event()
    p = ctx.Process(target=occupy, args=(tmp_path, ready))
    p.start()
    s = Store(tmp_path, 0.1)
    try:
        assert ready.wait(6)
        with pytest.raises(Error, match="storage_busy"):
            s.begin()
    finally:
        p.terminate()
        p.join(4)
    assert (tmp_path / "credentials.lock").exists()
    assert s.begin()[0].startswith("urn:uuid:")


@pytest.mark.parametrize(
    "scenario",
    [
        "read-error",
        "invalid_grant",
        "invalid_client",
        "connect",
        "bad-id",
        "bad-schema",
        "broken",
        "null",
        "replace-fail",
    ],
)
def test_QA017(tmp_path, scenario, monkeypatch):
    s = setup(tmp_path, 0)
    calls = []

    def upstream(r):
        calls.append(1)
        if scenario == "read-error":
            raise httpx.ReadTimeout(CANARY)
        if scenario == "connect":
            raise httpx.ConnectError(CANARY)
        if scenario == "bad-id":
            return httpx.Response(
                200,
                json=dict(
                    access_token=CANARY,
                    token_type="Bearer",
                    expires_in=60,
                    id_token=CANARY,
                ),
            )
        return httpx.Response(400, json={"error": scenario})

    m = TokenManager(s, OAuth(httpx.MockTransport(upstream)))
    if scenario in ("broken", "bad-schema", "null", "replace-fail"):
        if scenario != "replace-fail":
            s.path.write_text(
                {"broken": "{", "bad-schema": '{"schema_version":2}', "null": "null"}[
                    scenario
                ]
            )
        else:

            def fail(*_):
                raise OSError(CANARY)

            monkeypatch.setattr(os, "replace", fail)
            m.oauth = Rotator()
        before = s.path.read_bytes()
        with pytest.raises(Error, match="storage_failed"):
            m._take()
        assert s.path.read_bytes() == before and not list(tmp_path.glob(".siwc-*"))
    else:
        with pytest.raises(Error):
            m._take()
        d = s.current()
        if scenario in ("read-error", "invalid_grant", "bad-id"):
            assert d["tokens"] == {} and d["state"] == (
                "auth_required" if scenario == "invalid_grant" else "refresh_uncertain"
            )
            with pytest.raises(Error):
                m._take()
            assert len(calls) == 1
        else:
            assert d["state"] == "active"


@pytest.mark.parametrize("scenario", ["ok", "5xx", "network"])
def test_QA018(tmp_path, scenario):
    s = setup(tmp_path)
    h = s.begin()[0]
    calls = []

    def endpoint(r):
        if str(r.url) == DISCOVERY:
            return httpx.Response(
                200,
                json=dict(
                    issuer=ISSUER,
                    authorization_endpoint=AUTHORIZE,
                    token_endpoint=TOKEN,
                    jwks_uri=JWKS,
                    revocation_endpoint=REVOKE,
                ),
            )
        assert str(r.url) == REVOKE and parse_qs(r.content.decode()) == dict(
            token=["synthetic-refresh"],
            token_type_hint=["refresh_token"],
            client_id=["synthetic-client"],
        )
        calls.append(1)
        if scenario == "network":
            raise httpx.ConnectError(CANARY)
        return httpx.Response(200 if scenario == "ok" else 500, json={})

    m = TokenManager(s, OAuth(httpx.MockTransport(endpoint)))
    assert m.logout() == (scenario == "ok")
    host, d = s.begin()
    assert (
        h == host
        and d["state"] == "logged_out"
        and d["tokens"] == {}
        and d["session_generation"] == 2
    )
    assert len(calls) == (1 if scenario == "ok" else 2)
