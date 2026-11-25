"""Bound bytes *before* the SDK's SSE decoder accumulates an event."""

from openai._streaming import SSEDecoder

from .errors import Error, classify
from .oauth import text


def check(condition):
    if not condition:
        raise Error("stream_failed")


def completed(r):
    check(
        isinstance(r, dict)
        and r.get("status") == "completed"
        and not r.get("error")
        and not r.get("incomplete_details")
    )
    check(isinstance(r.get("output"), list))
    items = []
    for message in r["output"]:
        check(isinstance(message, dict))
        if message.get("type") == "reasoning":
            continue
        check(
            message.get("type") == "message"
            and message.get("role") == "assistant"
            and message.get("status", "completed") == "completed"
            and isinstance(message.get("content"), list)
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
        check(any(p[p["type"]].strip() for p in parts))
        item = dict(item_type="AssistantMessageItem", parts=parts)
        if message.get("phase") in ("commentary", "final_answer"):
            item["phase"] = message["phase"]
        items.append(item)
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
        check(size <= limit)
        yield chunk


async def consume(response, limit):
    decoder = SSEDecoder()
    async for frame in decoder.aiter_bytes(limited(response, limit)):
        if not frame.data:
            continue
        if frame.data == "[DONE]":
            break
        data = frame.json()
        check(isinstance(data, dict))
        typ = data.get("type")
        check(isinstance(typ, str) and (not frame.event or frame.event == typ))
        if typ == "response.completed":
            return completed(data.get("response"))
        if typ in ("response.failed", "error"):
            raise classify(
                200, data.get("response", data), response.headers, stream=True
            )
        if typ == "response.incomplete":
            break
        if typ in ("response.output_item.added", "response.output_item.done"):
            item = data.get("item")
            check(
                isinstance(item, dict) and item.get("type") in ("message", "reasoning")
            )
    raise Error("stream_failed")
