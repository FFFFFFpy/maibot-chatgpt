import logging
from uuid import uuid4
from .errors import Error
from .oauth import RESOURCE, text

_ROLES = {
    "SystemMessageItem": "developer",
    "UserMessageItem": "user",
    "AssistantMessageItem": "assistant",
}
_warned = False


def require(test):
    if not test:
        raise Error("unsupported_input")


def adapt(operation, r):
    global _warned
    require(
        operation == "response"
        and isinstance(r, dict)
        and r.get("request_kind", "response") == "response"
    )
    require(type(r.get("item_schema_version")) is int and r["item_schema_version"] == 1)
    require(
        "message_list" not in r
        and r.get("tool_options") in (None, [])
        and r.get("tool_choice") is None
        and not r.get("tools")
    )
    require(
        r.get("response_format")
        in (None, {}, {"format_type": "text"}, {"type": "text"})
    )
    info = r.get("model_info")
    require(
        isinstance(info, dict)
        and text(info.get("model_identifier"))
        and info.get("model_type", "llm") == "llm"
    )
    require(r.get("extra_params", {}) == {} and info.get("extra_params", {}) == {})
    provider = r.get("api_provider", {})
    require(isinstance(provider, dict))
    if provider.get("base_url", RESOURCE) != RESOURCE:
        raise Error("route_mismatch")
    if not _warned and (
        r.get("temperature") is not None or r.get("max_tokens") is not None
    ):
        logging.getLogger(__name__).info("temperature/max_tokens 已忽略；不会发送。")
        _warned = True
    items = r.get("context_items")
    require(isinstance(items, list) and items)
    messages = []
    for item in items:
        require(
            isinstance(item, dict)
            and set(item) <= {"item_type", "meta", "parts", "phase"}
        )
        role = next((v for k, v in _ROLES.items() if k == item.get("item_type")), None)
        require(role is not None)
        parts = item.get("parts")
        require(isinstance(parts, list) and parts)
        msg = dict(type="message", role=role, content=[])
        if role == "assistant":
            msg.update(id="msg_" + uuid4().hex, status="completed")
            if item.get("phase") is not None:
                require(item["phase"] in ("commentary", "final_answer"))
                msg["phase"] = item["phase"]
        for p in parts:
            require(isinstance(p, dict))
            if (
                set(p) == {"type", "text"}
                and p["type"] == "text"
                and isinstance(p["text"], str)
            ):
                part = (
                    dict(type="input_text", text=p["text"])
                    if role != "assistant"
                    else dict(type="output_text", text=p["text"], annotations=[])
                )
            elif (
                role == "assistant"
                and set(p) == {"type", "refusal"}
                and p["type"] == "refusal"
                and text(p["refusal"])
            ):
                part = p.copy()
            else:
                raise Error("unsupported_input")
            msg["content"].append(part)
        messages.append(msg)
    return dict(
        model=info["model_identifier"], input=messages, stream=True, store=False
    )


def smoke_request(slug, prompt):
    return dict(
        item_schema_version=1,
        model_info=dict(model_identifier=slug),
        context_items=[
            dict(item_type="UserMessageItem", parts=[dict(type="text", text=prompt)])
        ],
    )
