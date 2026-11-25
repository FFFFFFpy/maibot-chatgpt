"""Only MaiBot's native model-row diagnostic; never execute a model tool."""

import base64
import hashlib
import json
from .errors import Error

NAME = "maibot_model_test_report"
TEST_PNG_SHA256 = "4499268b64fb570a60b35fc670e3debe2b6974f55607ed2ea2a8dc0dc00c263a"
FIELDS = {
    "status": "string",
    "echo": "string",
    "saw_image": "boolean",
    "image_summary": "string",
}


def diagnostic_definition(options):
    if options in (None, []):
        return None
    if (
        not isinstance(options, list)
        or len(options) != 1
        or not isinstance(options[0], dict)
    ):
        raise Error("unsupported_input")
    entry = options[0]
    fn = entry.get("function")
    if (
        entry.get("type") != "function"
        or not isinstance(fn, dict)
        or fn.get("name") != NAME
    ):
        raise Error("unsupported_input")
    schema = fn.get("parameters")
    if not isinstance(schema, dict) or schema.get("type") != "object":
        raise Error("unsupported_input")
    props = schema.get("properties")
    required = schema.get("required")
    if (
        not isinstance(props, dict)
        or set(props) != set(FIELDS)
        or not isinstance(required, list)
        or sorted(str(k) for k in required) != ["echo", "saw_image", "status"]
        or not all(
            isinstance(props[k], dict) and props[k].get("type") == t
            for k, t in FIELDS.items()
        )
        or props["status"].get("enum") != ["ok"]
    ):
        raise Error("unsupported_input")
    # Whitelist the contract, not arbitrary caller-provided tool/schema extensions.
    return dict(
        type="function",
        name=NAME,
        description="Report the result of the MaiBot model test.",
        strict=False,
        parameters=dict(
            type="object",
            properties={
                k: dict(type=t, **({"enum": ["ok"]} if k == "status" else {}))
                for k, t in FIELDS.items()
            },
            required=["status", "echo", "saw_image"],
            additionalProperties=False,
        ),
    )


def image_part(part):
    raw = part.get("image_base64")
    if (
        set(part) != {"type", "image_format", "image_base64"}
        or part.get("image_format") != "png"
        or not isinstance(raw, str)
        or len(raw) > 2048
    ):
        raise Error("unsupported_input")
    try:
        digest = hashlib.sha256(base64.b64decode(raw, validate=True)).hexdigest()
    except ValueError:
        digest = None
    if digest != TEST_PNG_SHA256:
        raise Error("unsupported_input")
    return dict(type="input_image", image_url="data:image/png;base64," + raw)


def report_item(item, expected_image):
    call_id = item.get("call_id")
    raw = item.get("arguments")
    if (
        item.get("name") != NAME
        or item.get("status", "completed") != "completed"
        or not isinstance(call_id, str)
        or not call_id.strip()
        or len(call_id) > 256
        or not isinstance(raw, str)
        or len(raw) > 8192
    ):
        raise Error("probe_failed")
    try:
        args = json.loads(raw)
    except (ValueError, RecursionError):
        args = None
    if (
        not isinstance(args, dict)
        or set(args) - set(FIELDS)
        or args.get("status") != "ok"
        or args.get("echo") != "maibot model test"
        or args.get("saw_image") is not expected_image
        or not isinstance(args.get("image_summary", ""), str)
    ):
        raise Error("probe_failed")
    return dict(
        item_type="FunctionCallItem",
        tool_call=dict(call_id=call_id, func_name=NAME, args=args),
    )
