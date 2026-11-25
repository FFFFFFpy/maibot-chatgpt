"""Synthetic upstream; no real token, paid inference or tool execution."""

import asyncio
import json
import pytest
from maibot_chatgpt_provider.adapter import adapt, smoke_request
from maibot_chatgpt_provider.errors import Error
from maibot_chatgpt_provider.model_probe import NAME, FIELDS
from .support import engine
from .test_provider import ev, sse, response

pytestmark = pytest.mark.offline
TEST_PNG = "iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAYAAABzenr0AAAAAXNSR0IArs4c6QAAAARnQU1BAACxjwv8YQUAAAAJcEhZcwAADsMAAA7DAcdvqGQAAABBSURBVFhH7c6hDQAgDEXBDstKjMkM4GsQBIq4Js9U/Fy0PmZlkR+vAwAA2AJOL+/lAAAAAAAAAP4H3A4AAKAcsAB+y6u1cyDAxAAAAABJRU5ErkJggg=="


def request(visual=False):
    q = smoke_request("synthetic-row", "synthetic test prompt")
    props = {k: {"type": v} for k, v in FIELDS.items()}
    props["status"]["enum"] = ["ok"]
    schema = {
        "type": "object",
        "properties": props,
        "required": ["status", "echo", "saw_image"],
    }
    q["tool_options"] = [
        {"type": "function", "function": {"name": NAME, "parameters": schema}}
    ]
    if visual:
        q["context_items"][0]["parts"].append(
            dict(type="image", image_format="png", image_base64=TEST_PNG)
        )
    return q


def function_item(visual):
    return dict(
        type="function_call",
        status="completed",
        name=NAME,
        call_id="synthetic-call",
        arguments=json.dumps(
            dict(status="ok", echo="maibot model test", saw_image=visual)
        ),
    )


@pytest.mark.parametrize("visual", [True, False])
@pytest.mark.parametrize(
    "case",
    [
        "valid",
        "no-call",
        "wrong-call",
        "wrong-args",
        "partial",
        "unsolicited",
        "wrong-image",
    ],
)
def test_native_lightning(tmp_path, visual, case):
    q = request(visual)
    item = function_item(visual)
    seen = []
    if case == "unsolicited":
        q = smoke_request("synthetic-row", "synthetic")

    def upstream(r):
        body = json.loads(r.content)
        seen.append(body)
        assert body["model"] == "synthetic-row" and str(r.url).endswith("/responses")
        if case != "unsolicited":
            assert (
                body["tools"][0]["name"] == NAME
                and any(p["type"] == "input_image" for p in body["input"][0]["content"])
                == visual
            )
        if case == "wrong-call":
            item["name"] = "other"
        if case == "wrong-args":
            item["arguments"] = "{invalid"
        if case == "wrong-image":
            item["arguments"] = function_item(not visual)["arguments"]
        final = response() if case == "no-call" else response(output=[item])
        wire = (
            b""
            if case == "no-call"
            else ev(
                "response.output_item.added",
                item={**item, "arguments": "", "status": "in_progress"},
            )
        )
        return sse(
            wire
            + (
                ev("response.incomplete", response=final)
                if case == "partial"
                else ev("response.completed", response=final)
            )
        )

    async def go():
        p = engine(tmp_path, upstream)
        try:
            return await p.dispatch("response", q)
        finally:
            await p.close()

    if case == "valid":
        out = asyncio.run(go())["output_items"][0]
        assert (
            out["item_type"] == "FunctionCallItem"
            and out["tool_call"]["call_id"] == "synthetic-call"
            and out["tool_call"]["args"] == json.loads(item["arguments"])
        )
    else:
        with pytest.raises(Error):
            asyncio.run(go())
    assert len(seen) == 1


@pytest.mark.parametrize("case", ["two", "changed-schema", "unknown-image"])
def test_native_tool_contract_stays_strict(case):
    q = request(True)
    if case == "two":
        q["tool_options"] *= 2
    if case == "changed-schema":
        del q["tool_options"][0]["function"]["parameters"]["properties"]["echo"]
    if case == "unknown-image":
        q["context_items"][0]["parts"][-1]["image_base64"] = "AAAA"
    with pytest.raises(Error, match="unsupported_input"):
        adapt("response", q)
