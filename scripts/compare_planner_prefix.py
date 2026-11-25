"""Offline structural comparison of two MaiBot request snapshots. Standard library only."""

import argparse
import json
from pathlib import Path


def load(path):
    with path.open("rb") as stream:
        doc = json.load(stream)
    items = doc["request_items"]
    tools = doc["tool_definitions"]
    if not isinstance(items, list) or not isinstance(tools, list):
        raise ValueError
    return doc, items, tools


def compare(first, second):
    a, x, ta = first
    b, y, tb = second
    # No text, paths, identifiers, raw tool names or fingerprints in output.
    for idx, items in enumerate((x, y), 1):
        positions = [
            str(i)
            for i, m in enumerate(items, 1)
            if m.get("item_type") == "SystemMessageItem"
        ]
        print(
            f"{idx}: items={len(items)} system_positions="
            + (",".join(positions) or "none")
        )
    print("tools_equal=" + str(ta == tb))
    print(
        "model_equal="
        + str(
            a["model_info"].get("model_identifier")
            == b["model_info"].get("model_identifier")
        )
    )
    print("reasoning_effort_equal=" + str(effort(a) == effort(b)))
    for i, (m, n) in enumerate(zip(x, y), 1):
        k = m["item_type"]
        role = {
            "UserMessageItem": "user",
            "AssistantMessageItem": "assistant",
            "SystemMessageItem": "developer",
            "FunctionCallItem": "call",
            "FunctionCallOutputItem": "result",
        }.get(k, "other")
        if k != n["item_type"]:
            print(f"first_change=item:{i} kind")
            return
        if role == "assistant" and (m.get("meta") or {}).get("item_id") != (
            n.get("meta") or {}
        ).get("item_id"):
            print(f"first_change=item:{i} assistant-id")
            return
        p = m.get("parts", [])
        q = n.get("parts", [])
        for j, (v, w) in enumerate(zip(p, q), 1):
            if v != w:
                print(f"first_change=item:{i} role:{role} part:{j}")
                if v.get("type") == w.get("type") == "text":
                    s = v["text"]
                    t = w["text"]
                    common = next(
                        (k for k, (c, d) in enumerate(zip(s, t)) if c != d),
                        min(len(s), len(t)),
                    )
                    print("common_chars_in_part=" + str(common))
                return
        if len(p) != len(q):
            print(
                f"first_change=item:{i} role:{role} part:{1 + min(len(p), len(q))} (length)"
            )
            return
        if {k: v for k, v in m.items() if k not in ("parts", "meta")} != {
            k: v for k, v in n.items() if k not in ("parts", "meta")
        }:
            print(f"first_change=item:{i} role:{role} fields")
            return
    print("shared_items_equal=" + str(min(len(x), len(y))))


def effort(doc):
    params = {
        **(doc["model_info"].get("extra_params") or {}),
        **(doc["request_parameters"].get("extra_params") or {}),
    }
    return params.get("reasoning_effort")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("first", type=Path)
    parser.add_argument("second", type=Path)
    args = parser.parse_args()
    try:
        compare(load(args.first), load(args.second))
    except (ValueError, OSError, KeyError, TypeError, AttributeError):
        parser.exit(
            2, "Cannot compare: expected two readable MaiBot request snapshots.\n"
        )
