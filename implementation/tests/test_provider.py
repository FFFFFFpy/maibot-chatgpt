"""All traffic and content are synthetic; exercise HTTPX and bounded Responses SSE decoding."""

import asyncio
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
import json
import logging
import ssl
import time
import traceback
import httpx
import pytest
from maibot_chatgpt_provider import adapter
from maibot_chatgpt_provider.adapter import adapt, smoke_request
from maibot_chatgpt_provider.credentials import atomic
from maibot_chatgpt_provider.errors import Error, retry_after, CODES
from maibot_chatgpt_provider.oauth import OAuth, RESOURCE, DISCOVERY
from .support import engine, record, CANARY

pytestmark = pytest.mark.offline
REQ = smoke_request("synthetic-model", "合成问题")
QUOTA = "subscription_sharing_usage_limit_exceeded"


def ev(kind, **fields):
    return (
        "event: "
        + kind
        + "\ndata: "
        + json.dumps(dict(type=kind, **fields), ensure_ascii=False)
        + "\n\n"
    ).encode()


def response(parts=None, **kwargs):
    return dict(
        dict(
            id="resp_synthetic",
            status="completed",
            output=[
                dict(
                    type="message",
                    role="assistant",
                    status="completed",
                    content=parts
                    if parts is not None
                    else [dict(type="output_text", text="合成回复")],
                )
            ],
        ),
        **kwargs,
    )


def final(**kw):
    return ev("response.completed", response=response(**kw))


@pytest.mark.parametrize("ending", [b"\r", b"\n", b"\r\n"])
def test_raw_sse_without_sdk(tmp_path, ending):
    # Start with a split BOM and partition even multibyte characters/CRLF.
    wire = b"\xef\xbb\xbf" + final().replace(b"\n", ending)

    class Bytes(httpx.AsyncByteStream):
        async def __aiter__(self):
            for byte in wire:
                yield bytes([byte])

    def reply(_):
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, stream=Bytes()
        )

    assert run(engine(tmp_path, reply))["status"] == "completed"


def test_no_blank_line_no_completed_event(tmp_path):
    with pytest.raises(Error, match="stream_failed"):
        run(engine(tmp_path, lambda _: sse(final().rstrip(b"\n") + b"\n")))


def sse(raw):
    return httpx.Response(
        200, content=raw, headers={"Content-Type": "text/event-stream"}
    )


async def call(p):
    return await p.dispatch("response", REQ)


def run(p, fn=call):
    async def go():
        try:
            return await fn(p)
        finally:
            await p.close()

    return asyncio.run(go())


@pytest.mark.parametrize("scenario", ["base", "redirect", "tls", "discovery"])
def test_QA011(tmp_path, scenario):
    seen = []

    def handle(r):
        seen.append(str(r.url))
        if scenario == "tls":
            raise httpx.ConnectError(
                "synthetic TLS verify failed"
            ) from ssl.SSLCertVerificationError(CANARY)
        return httpx.Response(
            302, headers={"location": "https://synthetic.invalid/collect"}
        )

    if scenario == "discovery":
        with pytest.raises(Error, match="route_mismatch"):
            OAuth(
                httpx.MockTransport(
                    lambda _: httpx.Response(
                        200, json={"issuer": "https://synthetic.invalid"}
                    )
                )
            ).discover()
    else:
        p = engine(tmp_path, handle)
        req = (
            REQ
            if scenario != "base"
            else dict(REQ, api_provider={"base_url": RESOURCE + "@synthetic.invalid"})
        )
        with pytest.raises(Error):
            run(p, lambda p: p.dispatch("response", req))
        assert seen == ([] if scenario == "base" else [RESOURCE + "/responses"])


@pytest.mark.parametrize("bad", [False, True, "empty", "hidden", "legacy"])
def test_QA019(tmp_path, bad):
    rows = [
        dict(slug="synthetic-z", display_name="Z", visibility="list"),
        dict(visibility="hide"),
        dict(slug="synthetic-a", display_name="A", visibility="list"),
    ]
    obj = (
        {"models": rows}
        if bad is False
        else {"models": {"bad": 1}}
        if bad is True
        else {"models": []}
        if bad == "empty"
        else {"models": rows[1:2]}
        if bad == "hidden"
        else {"data": [{"id": "x"}]}
    )

    def handle(r):
        assert (
            r.method == "GET"
            and str(r.url) == RESOURCE + "/models"
            and r.headers["authorization"] == "Bearer " + CANARY
        )
        return httpx.Response(200, json=obj)

    p = engine(tmp_path, handle)
    if bad is False:
        assert [m["slug"] for m in run(p, lambda p: p.models())] == [
            "synthetic-z",
            "synthetic-a",
        ]
    else:
        with pytest.raises(Error):
            run(p, lambda p: p.models())


def test_QA021():
    sys = {
        "item_type": "SystemMessageItem",
        "parts": [{"type": "text", "text": "synthetic system"}],
    }
    user = REQ["context_items"][0]
    assistant = {
        "item_type": "AssistantMessageItem",
        "parts": [
            {"type": "text", "text": "prior"},
            {"type": "refusal", "refusal": "synthetic refusal"},
        ],
    }
    body = adapt("response", dict(REQ, context_items=[sys, user, assistant, user]))
    assert (
        set(body) == {"model", "input", "store", "stream", "instructions"}
        and body["stream"]
        and not body["store"]
    )
    msgs = body["input"]
    assert body["instructions"] == "synthetic system"
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert [p["type"] for m in msgs for p in m["content"]] == [
        "input_text",
        "output_text",
        "refusal",
        "input_text",
    ] and msgs[1]["status"] == "completed"


@pytest.mark.parametrize(
    "change",
    [
        {"tool_options": [{}]},
        {"tool_choice": "required"},
        {"response_format": {"format_type": "json_schema"}},
        {"item_schema_version": 2},
        {"item_schema_version": True},
        {"model_info": {}},
        {"message_list": []},
        *(
            {
                "context_items": [
                    {"item_type": k, "parts": [{"type": "text", "text": "synthetic"}]}
                ]
            }
            for k in (
                "Unknown",
                "ReasoningItem",
                "FunctionCallItem",
                "FunctionCallOutputItem",
            )
        ),
        *(
            {
                "context_items": [
                    {"item_type": "UserMessageItem", "parts": [{"type": k}]}
                ]
            }
            for k in ("image", "audio", "refusal", "unknown")
        ),
    ],
)
def test_QA022(tmp_path, change):
    p = engine(tmp_path, lambda _: pytest.fail("network before validation"))
    with pytest.raises(Error, match="unsupported_input"):
        run(p, lambda p: p.dispatch("response", dict(REQ, **change)))


def test_QA023(caplog, monkeypatch):
    monkeypatch.setattr(adapter, "_warned", False)
    caplog.set_level(logging.INFO)
    for _ in range(2):
        assert set(adapt("response", dict(REQ, max_tokens=12, temperature=0.7))) == {
            "model",
            "input",
            "stream",
            "store",
        }
    assert caplog.text.count("temperature/max_tokens") == 1
    for change in [
        dict(extra_params={"metadata": 1}),
        dict(model_info=dict(REQ["model_info"], extra_params={"bad": 1})),
    ]:
        assert adapt("response", dict(REQ, **change)) == adapt("response", REQ)
    assert "已忽略未映射" in caplog.text


@pytest.mark.parametrize(
    "usage",
    [
        None,
        dict(input_tokens=8, output_tokens=3, total_tokens=11),
        dict(output_tokens=1),
        dict(input_tokens=True),
        "bad",
    ],
)
def test_QA024(tmp_path, usage, monkeypatch):
    for var in [
        "OPENAI_API_KEY",
        "OPENAI_ORG_ID",
        "OPENAI_PROJECT_ID",
        "OPENAI_CUSTOM_HEADERS",
        "OPENAI_BASE_URL",
    ]:
        monkeypatch.setenv(var, "synthetic-env-secret")

    def handle(r):
        assert (
            r.headers["Authorization"] == "Bearer " + CANARY
            and "openai-organization" not in r.headers
            and "openai-project" not in r.headers
        )
        assert (
            r.method == "POST"
            and str(r.url) == RESOURCE + "/responses"
            and json.loads(r.content) == adapt("response", REQ)
            and "synthetic-env-secret" not in str(r.headers.raw)
        )
        return sse(
            ev("response.output_text.delta", delta="合成")
            + ev("response.output_text.delta", delta="回复")
            + final(usage=usage)
        )

    p = engine(tmp_path, handle)
    if usage == "bad" or isinstance(usage, dict) and usage.get("input_tokens") is True:
        with pytest.raises(Error):
            run(p)
    else:
        out = run(p)
        assert out["output_items"][0]["parts"] == [{"type": "text", "text": "合成回复"}]
        if usage is None:
            assert "usage" not in out
        elif "total_tokens" in usage:
            assert out["usage"] == dict(
                prompt_tokens=8, completion_tokens=3, total_tokens=11
            )
        else:
            assert out["usage"] == dict(completion_tokens=1)


@pytest.mark.parametrize(
    "ending",
    [
        b"",
        b"data: [DONE]\n\n",
        b"data: {oops\n\n",
        ev("response.incomplete"),
        ev("response.failed", response={"error": {"code": "unknown"}}),
        ev("error", code=QUOTA),
        ev("response.failed", response={"error": {"code": QUOTA}}),
        final(status="incomplete"),
        final(output=[]),
        final(parts=[]),
        final(output=[{"type": "function_call"}]),
    ],
)
def test_QA025(tmp_path, ending):
    n = []

    def handle(_):
        n.append(1)
        return sse(ev("response.output_text.delta", delta=CANARY) + ending)

    p = engine(tmp_path, handle, pre_admission_retry_limit=1)
    with pytest.raises(Error) as info:
        run(p)
    assert (
        str(info.value).find(CANARY) < 0
        and len(n) == 1
        and p.manager.store.current()["pause"]["usage_paused"]
        == (QUOTA.encode() in ending)
    )


def test_QA026(tmp_path):
    output = [
        {"type": "reasoning", "summary": [CANARY]},
        response(parts=[dict(type="refusal", refusal="合成拒答")])["output"][0],
    ]
    p = engine(
        tmp_path,
        lambda _: sse(
            ev("response.reasoning_text.delta", delta=CANARY) + final(output=output)
        ),
    )
    out = run(p)
    assert CANARY not in str(out) and out["output_items"][0]["parts"] == [
        {"type": "refusal", "refusal": "合成拒答"}
    ]
    assert (
        adapt("response", dict(REQ, context_items=out["output_items"]))["input"][0][
            "content"
        ]
        == out["output_items"][0]["parts"]
    )


class Chunks(httpx.AsyncByteStream):
    def __init__(self, mode):
        self.mode = mode
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.closed = False

    async def __aiter__(self):
        self.started.set()
        if self.mode == "cancel":
            await self.release.wait()
        if self.mode == "timeout":
            raise httpx.ReadTimeout(CANARY)
        if self.mode == "cap":
            yield b"x" * 2048
            return
        raw = b": keepalive\r\n\r\n" + final().replace(
            b', "response"', b',\ndata: "response"'
        )
        for b in raw:
            yield bytes([b])

    async def aclose(self):
        self.closed = True


@pytest.mark.parametrize("mode", ["split", "cancel", "timeout", "cap"])
def test_QA027(tmp_path, mode):
    async def exercise():
        chunks = Chunks(mode)
        replies = [
            httpx.Response(
                200, stream=chunks, headers={"content-type": "text/event-stream"}
            ),
            sse(final()),
        ]
        p = engine(tmp_path, lambda _: replies.pop(0), max_buffered_text_bytes=1024)
        t = asyncio.create_task(call(p))
        await asyncio.wait_for(chunks.started.wait(), 2)
        if mode == "cancel":
            t.cancel()
            with pytest.raises(asyncio.CancelledError):
                await t
        elif mode in ("timeout", "cap"):
            with pytest.raises(Error):
                await t
        else:
            assert (await t)["status"] == "completed"
        assert chunks.closed and (await call(p))["status"] == "completed"
        await p.close()

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "status,body,category",
    [
        (401, {"detail": CANARY}, "admission_denied"),
        (403, {"detail": CANARY}, "admission_denied"),
        (429, {}, "rate_limited"),
        (503, {}, "upstream"),
        *(
            (403, {"error": {"code": k, "message": CANARY}}, v)
            for k, v in CODES.items()
        ),
    ],
)
def test_QA028(tmp_path, status, body, category):
    calls = []

    def h(_):
        calls.append(1)
        return httpx.Response(status, json=body)

    p = engine(tmp_path, h)
    with pytest.raises(Error, match=category) as caught:
        run(p)
    assert (
        caught.value.http_status == status
        and len(calls) == 1
        and CANARY not in str(caught.value)
    )


@pytest.mark.parametrize(
    "retry,expected",
    [
        ("0", 2),
        ("300", 1),
        (format_datetime(datetime.now(timezone.utc) + timedelta(hours=1)), 1),
        ("bad", 1),
    ],
)
def test_QA028_budget(tmp_path, retry, expected):
    calls = []

    def h(_):
        calls.append(1)
        return (
            httpx.Response(429, json={}, headers={"retry-after": retry})
            if len(calls) == 1
            else sse(final())
        )

    async def exercise():
        p = engine(tmp_path, h, total_timeout_seconds=1, pre_admission_retry_limit=1)
        if expected == 1:
            with pytest.raises(Error, match="rate_limited"):
                await call(p)
            with pytest.raises(Error, match="temporarily_unavailable"):
                await call(p)
            assert p.cool_until - time.monotonic() > 1
        else:
            assert (await call(p))["status"] == "completed"
        await p.close()

    asyncio.run(exercise())
    assert len(calls) == expected


def test_QA029(tmp_path):
    async def exercise():
        n = []

        def h(_):
            n.append(1)
            return (
                httpx.Response(429, json={"error": {"code": QUOTA}})
                if len(n) == 1
                else sse(final())
            )

        p = engine(tmp_path, h)
        failures = await asyncio.gather(call(p), call(p), return_exceptions=True)
        assert all(e.category == "usage_paused" for e in failures) and len(n) == 1
        m = p.manager
        store = m.store
        await p.close()
        store.replace(record(), 1)
        source = tmp_path / "synthetic-transfer"
        atomic(source, record())
        store.transfer(source)
        from maibot_chatgpt_provider.token_manager import TokenManager
        from maibot_chatgpt_provider.provider import Provider

        p = Provider(TokenManager(store, OAuth()), transport=httpx.MockTransport(h))
        with pytest.raises(Error, match="usage_paused"):
            await call(p)
        store.pause(False)
        assert (await call(p))["status"] == "completed" and len(n) == 2
        await p.close()

    asyncio.run(exercise())


@pytest.mark.parametrize("action", ["import", "logout", "refresh"])
def test_QA014_inflight(tmp_path, action):
    async def check():
        stream = Chunks("cancel")
        p = engine(
            tmp_path,
            lambda _: httpx.Response(
                200, stream=stream, headers={"Content-Type": "text/event-stream"}
            ),
        )
        s = p.manager.store
        t = asyncio.create_task(call(p))
        await stream.started.wait()
        if action == "import":
            s.replace(record())
        elif action == "logout":
            p.manager.oauth = OAuth(httpx.MockTransport(lambda _: httpx.Response(500)))
            p.manager.logout()
        else:
            from .test_store import Rotator

            with s.lock():
                d = s.current()
                d["expires_at"] = 0
                s.save(d)
            p.manager.oauth = Rotator()
            await p.manager.take()
        stream.release.set()
        if action == "refresh":
            assert (await t)["status"] == "completed"
        else:
            with pytest.raises(Error, match="stale_attempt"):
                await t
        await p.close()

    asyncio.run(check())
