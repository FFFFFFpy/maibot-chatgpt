"""Synthetic multi-round planner snapshots. No Host tools are ever executed."""

import json
import httpx
import pytest
from maibot_chatgpt_provider.adapter import adapt, smoke_request
from maibot_chatgpt_provider.errors import Error
from .support import engine, CANARY
from .test_native_probe import TEST_PNG
from .test_provider import ev, response, run, sse

pytestmark = pytest.mark.offline


def tool(name):
    return dict(
        type="function",
        function=dict(
            name=name,
            description="synthetic",
            parameters={
                "type": "object",
                "properties": {
                    "a": {
                        "anyOf": [
                            {"type": ["string", "null"], "minLength": 1},
                            {"type": "number", "exclusiveMinimum": 0},
                        ],
                        "default": None,
                    }
                },
                "not": {"required": ["a", "b"]},
                "minProperties": 1,
            },
        ),
    )


def q(names):
    r = smoke_request("synthetic", "hello")
    r["tool_options"] = [tool(n) for n in names]
    r["model_info"].update(visual=True, extra_params={"reasoning_effort": "high"})
    r["extra_params"] = {"reasoning_effort": "low", CANARY: CANARY}
    r["context_items"].insert(
        0,
        {
            "item_type": "SystemMessageItem",
            "parts": [{"type": "text", "text": "one"}, {"type": "text", "text": "two"}],
        },
    )
    return r


def call(name, cid, args):
    return dict(
        type="function_call",
        status="completed",
        name=name,
        call_id=cid,
        arguments=json.dumps(args),
    )


def test_parallel_roundtrip(tmp_path, caplog):
    first = q(
        [
            "wait",
            "reply",
            "schedule",
            "query_memory",
            "query_image_memory",
            "query_person_profile",
            "tool_search",
            "read_tool_result",
        ]
    )
    second = {
        **first,
        "tool_options": [
            tool("view_forward_message"),
            tool("web_search"),
            tool("web_fetch"),
        ],
    }
    seen = []

    def handler(req):
        b = json.loads(req.content)
        seen.append(b)
        assert (
            "instructions" not in b
            and [p["text"] for p in b["input"][0]["content"]] == ["one", "two"]
            and b["reasoning"] == {"effort": "low"}
            and CANARY not in str(b)
        )
        if len(seen) == 1:
            assert (
                len(b["tools"]) == 8
                and b["tools"][2]["parameters"]
                == first["tool_options"][2]["function"]["parameters"]
                and all(t["strict"] is False for t in b["tools"])
            )
            items = [
                call("tool_search", "c1", {"q": "x"}),
                call("query_memory", "c2", {}),
            ]
        else:
            assert [t["name"] for t in b["tools"]] == [
                "view_forward_message",
                "web_search",
                "web_fetch",
            ]
            x = b["input"]
            assert [(i["type"], i["call_id"]) for i in x if "call_id" in i] == [
                ("function_call", "c1"),
                ("function_call", "c2"),
                ("function_call_output", "c2"),
                ("function_call_output", "c1"),
            ]
            assert (
                x[-1]["content"][0]["text"] == "media_index=tool_result:c1:1"
                and x[-1]["content"][1]["type"] == "input_image"
            )
            items = [call("web_fetch", "c3", {})]
        return sse(
            ev("response.output_item.added", item=items[0])
            + ev("response.completed", response=response(output=items))
        )

    p = engine(tmp_path, handler)

    async def rounds(p):
        a = await p.dispatch("response", first)
        h = a["output_items"]
        assert [i["tool_call"]["call_id"] for i in h] == ["c1", "c2"]
        results = [
            dict(
                item_type="FunctionCallOutputItem",
                call_id=c,
                tool_name=n,
                output="synthetic result",
            )
            for c, n in [("c2", "query_memory"), ("c1", "tool_search")]
        ]
        media = dict(
            item_type="UserMessageItem",
            parts=[
                dict(type="text", text="media_index=tool_result:c1:1"),
                dict(type="image", image_format="png", image_base64=TEST_PNG),
            ],
        )
        second["context_items"] = first["context_items"] + h + results + [media]
        return await p.dispatch("response", second)

    out = run(p, rounds)
    assert (
        out["output_items"][0]["tool_call"]["func_name"] == "web_fetch"
        and CANARY not in caplog.text
    )


@pytest.mark.parametrize("case", ["unknown", "duplicate", "broken-json", "partial"])
def test_bad_calls_not_committed(tmp_path, case):
    item = call("other" if case == "unknown" else "reply", "cid", {})
    items = [item, item] if case == "duplicate" else [item]
    if case == "broken-json":
        item["arguments"] = "NaN"
    if case == "partial":
        item["status"] = "in_progress"
    with pytest.raises(Error):
        run(
            engine(
                tmp_path,
                lambda _: sse(
                    ev("response.completed", response=response(output=items))
                ),
            ),
            lambda p: p.dispatch("response", q(["reply"])),
        )


@pytest.mark.parametrize("case", ["paired", "mismatch", "orphan", "unanswered"])
def test_tool_result_media(case):
    r = q(["wait"])
    r["model_info"]["visual"] = False
    if case != "orphan":
        r["context_items"].append(
            dict(
                item_type="FunctionCallItem",
                tool_call=dict(call_id="cid", func_name="old_tool", args={}),
            )
        )
    if case != "unanswered":
        r["context_items"].append(
            dict(
                item_type="FunctionCallOutputItem",
                call_id="cid",
                tool_name="wrong" if case == "mismatch" else "old_tool",
                output=[
                    dict(type="text", text="ref"),
                    dict(type="image", image_format="png", image_base64=TEST_PNG),
                ],
            )
        )
    if case == "paired":
        out = adapt("response", r)["input"][-1]["output"]
        assert out[0]["text"] == "ref" and "未发送" in out[1]["text"]
    else:
        with pytest.raises(Error):
            adapt("response", r)


def test_not_attribution(tmp_path):
    def reject(_):
        return httpx.Response(
            400, json={"error": {"param": "tools[1].parameters.not", "message": CANARY}}
        )

    with pytest.raises(Error, match="schedule.parameters.not") as exc:
        run(
            engine(tmp_path, reject),
            lambda p: p.dispatch("response", q(["wait", "schedule"])),
        )
    assert CANARY not in str(exc.value)
