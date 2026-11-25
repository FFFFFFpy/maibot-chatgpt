"""Synthetic cache-affinity tests; no real backend or account."""

import json
import logging
import httpx
import pytest
from maibot_chatgpt_provider.adapter import adapt, smoke_request
from maibot_chatgpt_provider.errors import Error
from maibot_chatgpt_provider.provider import catalog
from maibot_chatgpt_provider.responses import completed
from .test_provider import run, sse, final, response
from .support import engine, CANARY

pytestmark = pytest.mark.offline


def request(sid=None, anchor="anchor", turn="one", reminder="reminder"):
    q = smoke_request("model", CANARY)
    q["logical_turn_id"] = turn
    if sid:
        q["metadata"] = {"session_id": sid}
    if anchor:
        q["context_items"][0]["meta"] = {"item_id": anchor}
    q["context_items"].insert(
        0,
        dict(
            item_type="SystemMessageItem",
            parts=[dict(type="text", text=CANARY), dict(type="text", text=reminder)],
        ),
    )
    return q


def test_prefix_and_keys():
    q = request()
    history = {
        "item_type": "AssistantMessageItem",
        "parts": [dict(type="text", text="synthetic")],
    }
    q["context_items"].extend([history, {**history, "meta": {"item_id": CANARY}}])
    a = adapt("response", q)
    q["logical_turn_id"] = "new"
    q["context_items"] += smoke_request("model", "another")["context_items"]
    b = adapt("response", q)
    assert (
        a["input"] == b["input"][:-1]
        and a["input"][0]["role"] == "developer"
        and "instructions" not in b
        and a["input"][2]["id"] != a["input"][3]["id"]
        and CANARY not in a["input"][3]["id"]
    )
    assert (
        a["prompt_cache_key"]
        == b["prompt_cache_key"]
        == adapt("response", request(reminder="different"))["prompt_cache_key"]
    )
    q["session_id"] = CANARY * 9
    c = adapt("response", q)["prompt_cache_key"]
    assert (
        0 < len(c) <= 64
        and CANARY not in c
        and c != b["prompt_cache_key"]
        and c == adapt("response", request(sid=CANARY * 9))["prompt_cache_key"]
    )


@pytest.mark.parametrize("mode", ["sid", "fallback", "no-anchor"])
def test_replay_isolation(tmp_path, mode):
    state = "synthetic/opaque+=="

    def q(which, turn):
        return request(
            which if mode == "sid" else None,
            which if mode != "no-anchor" else None,
            turn,
        )

    seen = []

    def send(r):
        k = json.loads(r.content)["prompt_cache_key"]
        assert r.headers["session-id"] == r.headers["session_id"] == k
        seen.append((k, r.headers.get("x-codex-turn-state")))
        resp = sse(final())
        resp.headers["x-codex-turn-state"] = state if len(seen) == 1 else "other"
        return resp

    async def go(p):
        for which, t in [("A", "1"), ("B", "1"), ("A", "2")]:
            await p.dispatch("response", q(which, t))

    run(engine(tmp_path, send), go)
    assert (
        seen[0][0] == seen[2][0]
        and seen[1][1] is None
        and seen[2][1] == (None if mode == "no-anchor" else state)
    )


@pytest.mark.parametrize(
    "status,code,retry",
    [
        (400, "invalid_turn_state", True),
        (422, "expired_turn_state", True),
        (400, "invalid_schema", False),
        (401, "invalid_turn_state", False),
        (503, "invalid_turn_state", False),
    ],
)
def test_retry_only_explicit_preadmission(tmp_path, status, code, retry):
    seen = []

    def send(r):
        seen.append((r.headers.get("x-codex-turn-state"), r.content))
        res = sse(final())
        res.headers["x-codex-turn-state"] = CANARY
        if len(seen) == 2:
            return httpx.Response(status, json={"error": {"code": code}})
        if len(seen) == 3:
            return httpx.Response(400, json={"error": {"code": "invalid_turn_state"}})
        return res

    async def go(p):
        await p.dispatch("response", request("s"))
        with pytest.raises(Error):
            await p.dispatch("response", request("s"))
        if retry:
            await p.dispatch("response", request("s"))

    run(engine(tmp_path, send), go)
    assert [s for s, _ in seen] == (
        [None, CANARY, None, None] if retry else [None, CANARY]
    )
    assert all(b == seen[0][1] for _, b in seen)


def test_failed_stream_not_replayed(tmp_path):
    seen = []

    def send(r):
        seen.append(r.headers.get("x-codex-turn-state"))
        res = sse(final() if len(seen) == 1 else b"data: [DONE]\n\n")
        res.headers["x-codex-turn-state"] = CANARY
        return res

    async def go(p):
        await p.dispatch("response", request("s"))
        with pytest.raises(Error):
            await p.dispatch("response", request("s"))

    run(engine(tmp_path, send), go)
    assert seen == [None, CANARY]


@pytest.mark.parametrize("cached", [96, 0, None, True, -1, 101])
def test_cache_reporting(caplog, cached):
    caplog.set_level(logging.INFO)
    u = completed(
        response(
            usage=dict(
                input_tokens=100,
                output_tokens=3,
                total_tokens=103,
                input_tokens_details=dict(cached_tokens=cached),
            )
        )
    )["usage"]
    assert u["prompt_tokens"] == 100 and u["total_tokens"] == 103
    if type(cached) is int and 0 <= cached <= 100:
        assert (
            u["prompt_cache_hit_tokens"] == cached
            and u["prompt_cache_miss_tokens"] == 100 - cached
            and f"hit_rate={cached:.1f}%" in caplog.text
        )
    else:
        assert "prompt_cache_hit_tokens" not in u and not caplog.records


def test_catalog_levels():
    m = dict(
        slug="test",
        display_name="synthetic",
        visibility="list",
        supported_reasoning_levels=[
            {"effort": "ultra"},
            "max",
            {"effort": "xhigh"},
            "max",
            {},
        ],
    )
    assert catalog({"models": [m]})[0]["supported_reasoning_levels"] == [
        "ultra",
        "max",
        "xhigh",
    ]
