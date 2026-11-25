import base64
import binascii
import json
import logging
from itertools import takewhile
import re
from hashlib import sha256
from .errors import Error
from .model_probe import NAME as PROBE_NAME, diagnostic_definition, image_part
from .oauth import RESOURCE, text

_ROLES = {
    "SystemMessageItem": "developer",
    "UserMessageItem": "user",
    "AssistantMessageItem": "assistant",
}
_warned = False
_NAME = re.compile(r"[A-Za-z0-9_-]{1,64}")


def require(test):
    if not test:
        raise Error("unsupported_input")


def definitions(raw):
    if raw in (None, []):
        return []
    require(isinstance(raw, list) and len(raw) <= 128)
    tools = []
    names = set()
    for t in raw:
        require(isinstance(t, dict) and t.get("type") == "function")
        f = t.get("function")
        require(isinstance(f, dict))
        name = f.get("name")
        params = f.get("parameters")
        desc = f.get("description", "")
        require(
            isinstance(name, str)
            and _NAME.fullmatch(name)
            and name not in names
            and isinstance(desc, str)
            and isinstance(params, dict)
            and params.get("type") == "object"
        )
        if name == PROBE_NAME:
            require(len(raw) == 1)
            return [diagnostic_definition(raw)]
        names.add(name)
        tools.append(
            dict(
                type="function",
                name=name,
                description=desc,
                parameters=params,
                strict=False,
            )
        )
    return tools


def valid_id(v):
    return isinstance(v, str) and bool(v.strip()) and len(v) <= 256


def content_parts(parts, role, visual, probe, budget):
    require(isinstance(parts, list) and parts)
    result = []
    for p in parts:
        require(isinstance(p, dict))
        typ = p.get("type")
        if typ == "text" and set(p) == {"type", "text"} and isinstance(p["text"], str):
            result.append(
                dict(type="output_text", text=p["text"], annotations=[])
                if role == "assistant"
                else dict(type="input_text", text=p["text"])
            )
        elif (
            typ == "refusal"
            and role == "assistant"
            and set(p) == {"type", "refusal"}
            and text(p["refusal"])
        ):
            result.append(p.copy())
        elif typ == "image" and role == "user":
            if probe:
                result.append(image_part(p))
                continue
            require(set(p) == {"type", "image_format", "image_base64"})
            fmt = p["image_format"]
            raw = p["image_base64"]
            require(isinstance(fmt, str) and isinstance(raw, str) and raw)
            if not visual:
                result.append(
                    dict(type="input_text", text="[图片未发送：该模型未启用视觉]")
                )
                continue
            mime = {
                "png": "png",
                "jpg": "jpeg",
                "jpeg": "jpeg",
                "webp": "webp",
                "gif": "gif",
            }.get(fmt.lower())
            require(mime and len(raw) <= 16 * 1024 * 1024)
            budget[0] += len(raw)
            require(budget[0] <= 32 * 1024 * 1024)
            try:
                base64.b64decode(raw, validate=True)
            except (ValueError, binascii.Error):
                raise Error("unsupported_input") from None
            result.append(
                dict(type="input_image", image_url=f"data:image/{mime};base64,{raw}")
            )
        else:
            raise Error("unsupported_input")
    return result


EFFORTS = ("none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra")


def digest(value):
    return sha256(
        json.dumps(
            value, ensure_ascii=True, separators=(",", ":"), sort_keys=True
        ).encode("ascii")
    ).hexdigest()[:40]


def session_id(request):
    meta = request.get("metadata")
    candidates = (
        request.get("session_id"),
        meta.get("session_id") if isinstance(meta, dict) else None,
    )
    return next(
        (s.strip() for s in candidates if isinstance(s, str) and s.strip()), None
    )


def cache_key(request, messages):
    sid = session_id(request)
    if sid:
        return "mb:s:" + digest(sid)
    # Only the first static text head, not later reminders, added turns or tool schemas.
    head = next(
        (
            p["text"][:1024]
            for m in takewhile(lambda x: x.get("role") == "developer", messages)
            for p in m["content"]
            if p.get("text")
        ),
        None,
    )
    if head is None:
        head = next(
            (
                p["text"][:1024]
                for m in messages
                if m.get("role") == "user"
                for p in m["content"]
                if p.get("text")
            ),
            "",
        )
    return "mb:p:" + digest(head)


def state_lane(request):
    # A prefix hash may be shared by unrelated chats. Never use it alone to replay opaque state.
    if session_id(request):
        return "session"
    for item in request["context_items"]:
        if item.get("item_type") == "UserMessageItem":
            meta = item.get("meta")
            anchor = meta.get("item_id") if isinstance(meta, dict) else None
            return (
                digest(anchor) if isinstance(anchor, str) and anchor.strip() else None
            )
    return None


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
        and r.get("tool_choice") in (None, "none")
        and not r.get("tools")
    )
    require(
        r.get("response_format")
        in (None, {}, {"format_type": "text"}, {"type": "text"})
    )
    tools = definitions(r.get("tool_options"))
    probe = bool(tools and tools[0]["name"] == PROBE_NAME)
    info = r.get("model_info")
    require(
        isinstance(info, dict)
        and text(info.get("model_identifier"))
        and info.get("model_type", "llm") == "llm"
    )
    provider = r.get("api_provider", {})
    require(isinstance(provider, dict))
    if provider.get("base_url", RESOURCE) != RESOURCE:
        raise Error("route_mismatch")
    body = dict(model=info["model_identifier"], input=[], stream=True, store=False)
    if tools:
        body["tools"] = tools
    if tools and r.get("tool_choice") == "none":
        body["tool_choice"] = "none"
    extra = {}
    for src in (info, r):
        opt = src.get("extra_params", {})
        require(isinstance(opt, dict))
        extra.update(opt)
    if "reasoning_effort" in extra:
        effort = extra.pop("reasoning_effort")
        require(effort in EFFORTS)
        body["reasoning"] = {"effort": effort}
    if extra:
        logging.getLogger(__name__).info(
            "已忽略未映射的 extra_params（%d 项）。", len(extra)
        )
    if not _warned and (
        r.get("temperature") is not None or r.get("max_tokens") is not None
    ):
        logging.getLogger(__name__).info("temperature/max_tokens 已忽略；不会发送。")
        _warned = True
    items = r.get("context_items")
    require(isinstance(items, list) and items)
    messages = body["input"]
    seen = set()
    pending = {}
    budget = [0]
    visual = info.get("visual") is True
    for item in items:
        require(isinstance(item, dict))
        kind = item.get("item_type")
        if kind == "ReasoningItem":
            # Private reasoning from a previous model is neither a message nor tool history.
            continue
        if kind == "FunctionCallItem":
            c = item.get("tool_call")
            require(isinstance(c, dict))
            cid = c.get("call_id")
            name = c.get("func_name")
            args = c.get("args")
            require(
                valid_id(cid)
                and cid not in seen
                and isinstance(name, str)
                and _NAME.fullmatch(name)
                and isinstance(args, dict)
            )
            seen.add(cid)
            pending[cid] = name
            messages.append(
                dict(
                    type="function_call",
                    call_id=cid,
                    name=name,
                    arguments=json.dumps(args, ensure_ascii=False, allow_nan=False),
                )
            )
            continue
        if kind == "FunctionCallOutputItem":
            cid = item.get("call_id")
            require(
                valid_id(cid)
                and cid in pending
                and item.get("tool_name") in (None, pending[cid])
            )
            del pending[cid]
            out = item.get("output")
            require(isinstance(out, (str, list)))
            if isinstance(out, list):
                out = content_parts(out, "user", visual, False, budget)
            messages.append(dict(type="function_call_output", call_id=cid, output=out))
            continue
        require(set(item) <= {"item_type", "meta", "parts", "phase"})
        role = _ROLES.get(kind)
        require(role)
        content = content_parts(item.get("parts"), role, visual, probe, budget)
        msg = dict(type="message", role=role, content=content)
        if role == "assistant":
            meta = item.get("meta")
            item_id = meta.get("item_id") if isinstance(meta, dict) else None
            seed = (
                ["host", item_id]
                if isinstance(item_id, str) and item_id.strip()
                else ["history", role, len(messages), content, item.get("phase")]
            )
            msg.update(id="msg_" + digest(seed), status="completed")
            phase = item.get("phase")
            if phase is not None:
                require(phase in ("commentary", "final_answer"))
                msg["phase"] = phase
        messages.append(msg)
    require(messages and not pending)
    body["prompt_cache_key"] = cache_key(r, messages)
    return body


def smoke_request(slug, prompt):
    return dict(
        item_schema_version=1,
        model_info=dict(model_identifier=slug),
        context_items=[
            dict(item_type="UserMessageItem", parts=[dict(type="text", text=prompt)])
        ],
    )
