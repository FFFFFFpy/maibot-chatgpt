"""Explicit source-baseline probe only. Never import Host from plugin runtime.
Usage: python tests/baseline_probe.py <pinned-MaiBot-source>
"""

import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from maibot_chatgpt_provider.adapter import adapt
from maibot_chatgpt_provider.responses import completed


def probe(host):
    sys.path.insert(0, str(host))
    os.environ["MAIBOT_INITIALIZE_ONLY"] = "1"
    os.environ["MAIBOT_INSTANCE_DIR"] = os.getcwd()
    from src.config.config import config_manager

    config_manager.model_config = SimpleNamespace(api_providers=[])
    from src.llm_models.model_client.plugin_client import PluginLLMClient
    from src.llm_models.request_snapshot import (
        serialize_response_request_snapshot,
        deserialize_model_info_snapshot,
    )
    from src.llm_models.model_client.base_client import ResponseRequest
    from src.llm_models.payload_content.context_snapshot import (
        deserialize_context_item_snapshot,
    )
    from src.llm_models.payload_content.resp_format import RespFormat
    from src.plugin_runtime.runner.manifest_validator import PluginManifest

    model = deserialize_model_info_snapshot(
        dict(
            model_identifier="synthetic-model",
            model_type="llm",
            api_provider="synthetic-provider",
            name="synthetic-name",
        )
    )
    user = deserialize_context_item_snapshot(
        dict(
            item_type="UserMessageItem",
            meta=dict(
                item_id="synthetic-user",
                logical_turn_id=None,
                timestamp="2026-01-01T00:00:00",
            ),
            parts=[dict(type="text", text="synthetic question")],
        )
    )
    request = ResponseRequest(
        model_info=model,
        context_items=[user],
        response_format=RespFormat(),
        logical_turn_id="synthetic-turn",
    )
    snap = serialize_response_request_snapshot(request)
    assert adapt("response", snap)["input"][0]["role"] == "user"
    result = completed(
        dict(
            status="completed",
            output=[
                dict(
                    type="message",
                    role="assistant",
                    content=[dict(type="refusal", refusal="synthetic refusal")],
                )
            ],
            usage=dict(
                input_tokens=3,
                output_tokens=8,
                total_tokens=11,
                input_tokens_details={"cached_tokens": 2},
            ),
        )
    )
    restored = PluginLLMClient._build_api_response(
        result, "synthetic", "synthetic", require_output_items=True
    )
    assert restored.usage.total_tokens == 11 and restored.usage.prompt_tokens == 3
    assert (
        restored.usage.prompt_cache_reported
        and restored.usage.prompt_cache_hit_tokens == 2
        and restored.usage.prompt_cache_miss_tokens == 1
    )
    request.context_items.append(restored.output_items[0])
    next_snap = serialize_response_request_snapshot(request)
    assert adapt("response", next_snap)["input"][1]["content"][0]["type"] == "refusal"
    # Execute the native row-test builders without starting its router/services.
    import ast, asyncio
    from typing import Any, Dict, List
    from src.llm_models.payload_content.context_item import ContextItemBuilder
    from src.llm_models.payload_content.tool_option import normalize_tool_options
    from tests.test_native_probe import function_item
    from tests.test_provider import sse, ev, response
    from tests.support import engine

    # Project two pure tool calls through the actual Host and reserialize them for
    # a second round in which the original tools no longer exist.
    from tests.test_planner import call

    raw = completed(
        response(output=[call("wait", "c1", {}), call("reply", "c2", {"a": 1})]),
        tool_names={"wait", "reply"},
    )
    native = PluginLLMClient._build_api_response(
        raw, "synthetic", "synthetic", require_output_items=True
    )
    assert [c.call_id for c in native.tool_calls] == ["c1", "c2"]
    history = [user, *native.output_items]
    for cid, name in [("c2", "reply"), ("c1", "wait")]:
        history.append(
            deserialize_context_item_snapshot(
                dict(
                    item_type="FunctionCallOutputItem",
                    meta=dict(
                        snap["context_items"][0]["meta"],
                        logical_turn_id="synthetic-turn",
                        item_id="result-" + cid,
                    ),
                    call_id=cid,
                    tool_name=name,
                    success=True,
                    output="synthetic result",
                )
            )
        )
    second = ResponseRequest(
        model_info=model,
        context_items=history,
        tool_options=normalize_tool_options(
            [
                {
                    "name": "web_fetch",
                    "description": "synthetic",
                    "parameters_schema": {"type": "object", "properties": {}},
                }
            ]
        ),
    )
    checked = adapt("response", serialize_response_request_snapshot(second))
    assert [t["name"] for t in checked["tools"]] == ["web_fetch"] and [
        i["call_id"] for i in checked["input"] if i["type"] == "function_call_output"
    ] == ["c2", "c1"]
    print(
        "native parallel tool-only response / changed definitions / reverse-order results roundtrip: PASS"
    )
    path = host / "src/webui/routers/model.py"
    root = ast.parse(path.read_text(encoding="utf-8"))
    keep = {
        "_build_model_test_prompt",
        "_build_model_test_tools",
        "_build_model_test_context_factory",
        "_serialize_model_test_tool_calls",
        "_build_model_test_response",
    }
    nodes = [
        n
        for n in root.body
        if (isinstance(n, ast.FunctionDef) and n.name in keep)
        or (
            isinstance(n, ast.Assign)
            and getattr(n.targets[0], "id", "")
            in {"MODEL_TEST_IMAGE_BASE64", "MODEL_TEST_TOOL_NAME"}
        )
    ]
    ns = dict(
        ContextItemBuilder=ContextItemBuilder,
        Any=Any,
        Dict=Dict,
        List=List,
        ModelTestToolCall=SimpleNamespace,
        ModelTestResponse=SimpleNamespace,
    )
    import __future__

    exec(
        compile(
            ast.Module(body=nodes, type_ignores=[]),
            str(path),
            "exec",
            flags=__future__.annotations.compiler_flag,
        ),
        ns,
    )
    for visual in (False, True):
        client = SimpleNamespace(
            get_support_image_formats=lambda: ["jpeg", "jpg", "png", "webp"]
        )
        req = ResponseRequest(
            model_info=model,
            context_items=ns["_build_model_test_context_factory"](visual)(client),
            tool_options=normalize_tool_options(ns["_build_model_test_tools"]()),
            max_tokens=512,
        )

        def upstream(r):
            body = json.loads(r.content)
            assert (
                body["model"] == model.model_identifier
                and body["tools"][0]["name"] == ns["MODEL_TEST_TOOL_NAME"]
            )
            assert (
                any(
                    p["type"] == "input_image"
                    for m in body["input"]
                    for p in m["content"]
                )
                == visual
            )
            return sse(
                ev(
                    "response.completed",
                    response=response(output=[function_item(visual)]),
                )
            )

        async def dispatch_probe():
            provider = engine(Path.cwd() / str(visual), upstream)
            try:
                return await provider.dispatch(
                    "response", serialize_response_request_snapshot(req)
                )
            finally:
                await provider.close()

        result = asyncio.run(dispatch_probe())
        native = PluginLLMClient._build_api_response(
            result, "synthetic", "synthetic", require_output_items=True
        )
        projected = SimpleNamespace(
            tool_calls=native.tool_calls,
            response=native.content or "",
            model_name="synthetic",
            reasoning=None,
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
        )
        assert ns["_build_model_test_response"](
            model_name="synthetic", visual_tested=visual, latency_ms=1, result=projected
        ).success
    print(
        "native row-test builders, plugin dispatch, synthetic upstream and Host success predicate: PASS (with/without image)"
    )
    manifest = json.loads((ROOT / "_manifest.json").read_bytes())
    PluginManifest.model_validate(manifest)
    print("synthetic source codec roundtrip and strict manifest schema: PASS")


if __name__ == "__main__":
    host = Path(sys.argv[1]).resolve()
    original = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        try:
            probe(host)
        finally:
            import logging

            logging.shutdown()
            os.chdir(original)
