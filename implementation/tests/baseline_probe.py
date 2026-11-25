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
            usage=dict(input_tokens=3, output_tokens=8, total_tokens=11),
        )
    )
    restored = PluginLLMClient._build_api_response(
        result, "synthetic", "synthetic", require_output_items=True
    )
    assert restored.usage.total_tokens == 11
    request.context_items.append(restored.output_items[0])
    next_snap = serialize_response_request_snapshot(request)
    assert adapt("response", next_snap)["input"][1]["content"][0]["type"] == "refusal"
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
