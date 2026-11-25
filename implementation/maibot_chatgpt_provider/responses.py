"""Decode the official Responses event stream without importing a host OpenAI SDK."""

import json
import re

from .errors import Error, classify
from .oauth import text
from .model_probe import report_item


# Diagnostics are fixed vocabulary. Never copy arbitrary upstream text or SSE payloads.
class StreamError(Error):
    def __init__(self, reason, *, upstream_code=None):
        super().__init__("stream_failed")
        allowed = {
            "invalid_request_error",
            "server_error",
            "model_not_found",
            "unsupported_parameter",
            "rate_limit_exceeded",
            "content_filter",
            "max_output_tokens",
            "invalid_image",
            "invalid_image_format",
            "invalid_image_size",
            "image_too_small",
            "unsupported_value",
            "invalid_value",
            "insufficient_quota",
        }
        suffix = (
            "；官方分类：" + upstream_code
            if isinstance(upstream_code, str) and upstream_code in allowed
            else ""
        )
        self.args = (f"[chatgpt_subscription:stream_failed] {reason}{suffix}",)


def check(condition, reason="完成事件的输出结构不符合预期，未交付结果。"):
    if not condition:
        raise StreamError(reason)


def invalid_constant(_):
    raise ValueError


def completed(r, probe_image=None, tool_names=()):
    check(
        isinstance(r, dict)
        and r.get("status") == "completed"
        and not r.get("error")
        and not r.get("incomplete_details")
    )
    check(isinstance(r.get("output"), list), "完成事件未包含有效的 output 列表。")
    items = []
    reported = False
    call_ids = set()
    for message in r["output"]:
        check(isinstance(message, dict), "完成事件的输出项格式无效。")
        if probe_image is not None and message.get("type") == "function_call":
            check(not reported)
            items.append(report_item(message, probe_image))
            reported = True
            continue
        if tool_names and message.get("type") == "function_call":
            name = message.get("name")
            cid = message.get("call_id")
            raw = message.get("arguments")
            check(
                isinstance(name, str)
                and name in tool_names
                and isinstance(cid, str)
                and 0 < len(cid.strip())
                and len(cid) <= 256
                and cid not in call_ids
                and message.get("status", "completed") == "completed"
                and isinstance(raw, str),
                "完成事件的函数名、状态或 call_id 无效。",
            )
            try:
                args = json.loads(raw, parse_constant=invalid_constant)
            except (ValueError, RecursionError):
                args = None
            check(isinstance(args, dict), "工具调用参数不是合法 JSON 对象。")
            call_ids.add(cid)
            items.append(
                dict(
                    item_type="FunctionCallItem",
                    tool_call=dict(call_id=cid, func_name=name, args=args),
                )
            )
            continue
        if message.get("type") == "reasoning":
            continue
        check(
            message.get("type") == "message"
            and message.get("role") == "assistant"
            and message.get("status", "completed") == "completed"
            and isinstance(message.get("content"), list),
            "完成事件含不支持的输出项、角色或未完成消息。",
        )
        parts = []
        for p in message["content"]:
            check(isinstance(p, dict))
            typ = p.get("type")
            key = (
                "text"
                if typ == "output_text"
                else "refusal"
                if typ == "refusal"
                else None
            )
            check(key and isinstance(p.get(key), str))
            parts.append({"type": key, key: p[key]})
        if not any(p[p["type"]].strip() for p in parts):
            # A tool-only turn may have an empty assistant message alongside the real call.
            if probe_image is not None or tool_names:
                continue
            raise StreamError("完成事件里没有非空正文或拒答。")
        item = dict(item_type="AssistantMessageItem", parts=parts)
        if message.get("phase") in ("commentary", "final_answer"):
            item["phase"] = message["phase"]
        items.append(item)
    if probe_image is not None and not reported:
        raise Error("probe_failed")
    check(items)
    result = dict(item_schema_version=1, output_items=items, status="completed")
    if text(r.get("id")):
        result["response_id"] = r["id"]
    usage = r.get("usage")
    if usage is not None:
        check(isinstance(usage, dict))
        counts = {}
        for src, dst in [
            ("input_tokens", "prompt_tokens"),
            ("output_tokens", "completion_tokens"),
            ("total_tokens", "total_tokens"),
        ]:
            if src in usage:
                n = usage[src]
                check(type(n) is int and n >= 0)
                counts[dst] = n
        if counts:
            result["usage"] = counts
    return result


async def limited(response, limit):
    size = 0
    async for chunk in response.aiter_bytes():
        size += len(chunk)
        check(size <= limit, "事件流超出插件缓冲上限，已停止读取。")
        yield chunk


async def lines(response, limit):
    # Split only SSE's CR, LF and CRLF, never Unicode separators inside JSON.
    # Decode after a complete line so a split UTF-8 codepoint remains intact.
    pending = bytearray()
    after_cr = False
    first = True
    async for chunk in limited(response, limit):
        if not chunk:
            continue
        start = int(after_cr and chunk.startswith(b"\n"))
        after_cr = chunk.endswith(b"\r")
        for end in re.compile(rb"\r\n|[\r\n]").finditer(chunk, start):
            pending.extend(chunk[start : end.start()])
            yield pending.decode("utf-8-sig" if first else "utf-8")
            first = False
            pending.clear()
            start = end.end()
        pending.extend(chunk[start:])
    # EOF without the terminating blank line must not commit a partial event.


async def events(response, limit):
    data = []
    event = ""
    async for line in lines(response, limit):
        if not line:
            if data:
                yield event, "\n".join(data)
            event, data = "", []
            continue
        field, _, value = line.partition(":")
        value = value.removeprefix(" ")
        if field == "event":
            event = value
        elif field == "data":
            data.append(value)


async def consume(response, limit, probe_image=None, tool_names=()):
    saw_events = False
    async for event, payload in events(response, limit):
        if payload == "[DONE]":
            raise StreamError("收到 [DONE]，但没有官方完成事件。")
        saw_events = True
        data = json.loads(payload)
        check(isinstance(data, dict))
        typ = data.get("type")
        check(
            isinstance(typ, str) and (not event or event == typ),
            "事件类型缺失或与 SSE 标记不一致。",
        )
        if typ == "response.completed":
            return completed(data.get("response"), probe_image, tool_names)
        if typ in ("response.failed", "error"):
            body = data.get("response", data)
            failure = classify(200, body, response.headers, stream=True)
            if failure.category != "stream_failed":
                raise failure
            error = body.get("error", body) if isinstance(body, dict) else {}
            raise StreamError(
                "官方通过 SSE 返回失败事件，未收到成功结果。",
                upstream_code=error.get("code") if isinstance(error, dict) else None,
            )
        if typ == "response.incomplete":
            obj = data.get("response")
            detail = obj.get("incomplete_details") if isinstance(obj, dict) else None
            raise StreamError(
                "官方返回 response.incomplete，本次生成没有完成。",
                upstream_code=detail.get("reason")
                if isinstance(detail, dict)
                else None,
            )
        if typ in ("response.output_item.added", "response.output_item.done"):
            item = data.get("item")
            check(
                isinstance(item, dict)
                and (
                    item.get("type") in ("message", "reasoning")
                    or (
                        (probe_image is not None or tool_names)
                        and item.get("type") == "function_call"
                    )
                ),
                "事件流包含本次请求不支持的输出项类型。",
            )
    raise StreamError(
        "事件流提前结束：未收到 response.completed。"
        if saw_events
        else "响应结束但未收到完整 SSE 事件。"
    )
