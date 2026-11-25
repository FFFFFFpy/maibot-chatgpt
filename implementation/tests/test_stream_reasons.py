"""Distinguish failures without ever echoing upstream messages or raw SSE."""

import httpx
import pytest
from maibot_chatgpt_provider.errors import Error
from .support import engine, CANARY
from .test_provider import run, ev, response, sse
from .test_native_probe import request, function_item

pytestmark = pytest.mark.offline


def dispatch(tmp_path, res):
    p = engine(tmp_path, lambda _: res)
    return run(p, lambda p: p.dispatch("response", request()))


@pytest.mark.parametrize("order", ["before", "after"])
def test_valid_report_with_empty_message(tmp_path, order):
    items = [
        {"type": "message", "role": "assistant", "status": "completed", "content": []},
        function_item(False),
    ]
    if order == "after":
        items.reverse()
    result = dispatch(
        tmp_path, sse(ev("response.completed", response=response(output=items)))
    )
    assert [x["item_type"] for x in result["output_items"]] == ["FunctionCallItem"]


@pytest.mark.parametrize(
    "case,reason",
    [
        ("done", "[DONE]"),
        ("eof", "提前结束"),
        ("failed", "官方通过 SSE"),
        ("incomplete", "max_output_tokens"),
        ("invalid", "JSON"),
        ("wrongmime", "text/event-stream"),
        ("empty", "probe_failed"),
        ("bad-item", "不支持的输出项"),
    ],
)
def test_failure_reason(tmp_path, case, reason):
    res = {
        "done": sse(b"data: [DONE]" + bytes([10, 10])),
        "eof": sse(ev("response.created")),
        "failed": sse(ev("error", code=CANARY, message=CANARY)),
        "incomplete": sse(
            ev(
                "response.incomplete",
                response=dict(incomplete_details=dict(reason="max_output_tokens")),
            )
        ),
        "invalid": sse(b"data: " + CANARY.encode() + bytes([10, 10])),
        "wrongmime": httpx.Response(200, text=CANARY),
        "empty": sse(
            ev(
                "response.completed",
                response=response(
                    output=[dict(type="message", role="assistant", content=[])]
                ),
            )
        ),
        "bad-item": sse(ev("response.output_item.added", item=dict(type=CANARY))),
    }[case]
    with pytest.raises(Error) as caught:
        dispatch(tmp_path, res)
    assert reason in str(caught.value) and CANARY not in str(caught.value)
