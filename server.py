"""
MCP JSON Explorer — a JSON toolkit for AI assistants.

Exposes tools for querying, searching, flattening, diffing, and validating
JSON documents without requiring jq-style filter syntax.
"""

import json
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("json-explorer")


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


class PathError(Exception):
    pass


def _parse_path(path: str) -> list[str | int]:
    path = path.strip()
    if path in ("", "$", "."):
        return []
    if path.startswith("$."):
        path = path[2:]
    elif path.startswith("$"):
        path = path[1:]

    tokens: list[str | int] = []
    for part in path.replace("[", ".[").split("."):
        if not part:
            continue
        if part.startswith("[") and part.endswith("]"):
            index_str = part[1:-1]
            if not index_str.lstrip("-").isdigit():
                raise PathError(f"Invalid list index '{part}' in path.")
            tokens.append(int(index_str))
        else:
            tokens.append(part)
    return tokens


def _format_path(tokens: list[str | int]) -> str:
    out = "$"
    for t in tokens:
        out += f"[{t}]" if isinstance(t, int) else f".{t}"
    return out


def _resolve_path(data: Any, tokens: list[str | int]) -> Any:
    current = data
    consumed: list[str | int] = []
    for token in tokens:
        location = _format_path(consumed)
        if isinstance(token, int):
            if not isinstance(current, list):
                raise PathError(
                    f"Expected a list at '{location}' but found "
                    f"{type(current).__name__}."
                )
            if token < 0 or token >= len(current):
                raise PathError(
                    f"Index {token} out of range at '{location}' "
                    f"(list has {len(current)} item(s))."
                )
            current = current[token]
        else:
            if not isinstance(current, dict):
                raise PathError(
                    f"Expected an object at '{location}' but found "
                    f"{type(current).__name__}."
                )
            if token not in current:
                available = ", ".join(map(str, current.keys())) or "(none)"
                raise PathError(
                    f"Key '{token}' not found at '{location}'. "
                    f"Available keys: {available}"
                )
            current = current[token]
        consumed.append(token)
    return current


def _flatten(data: Any, prefix: str = "$") -> dict[str, Any]:
    items: dict[str, Any] = {}
    if isinstance(data, dict):
        if not data:
            items[prefix] = {}
        for key, value in data.items():
            items.update(_flatten(value, f"{prefix}.{key}"))
    elif isinstance(data, list):
        if not data:
            items[prefix] = []
        for i, value in enumerate(data):
            items.update(_flatten(value, f"{prefix}[{i}]"))
    else:
        items[prefix] = data
    return items


def _depth(node: Any) -> int:
    if isinstance(node, dict):
        return 1 + max((_depth(v) for v in node.values()), default=0)
    if isinstance(node, list):
        return 1 + max((_depth(v) for v in node), default=0)
    return 0


def _load(json_data: str) -> Any:
    try:
        return json.loads(json_data)
    except json.JSONDecodeError as e:
        raise PathError(
            f"Invalid JSON: {e.msg} at line {e.lineno}, column {e.colno}."
        )


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def query(json_data: str, path: str) -> str:
    """
    Look up a value in a JSON document using a simple dot/bracket path,
    e.g. "data.items[0].name" or "$.users[2].email".

    Unlike jq, no filter syntax is required, and errors point out exactly
    where the path broke down and what keys/indices were actually available.
    """
    try:
        data = _load(json_data)
        tokens = _parse_path(path)
        result = _resolve_path(data, tokens)
    except PathError as e:
        return f"Error: {e}"

    if isinstance(result, (dict, list)):
        return json.dumps(result, indent=2)
    return json.dumps(result)


@mcp.tool()
def search(
    json_data: str,
    term: str,
    mode: Literal["key", "value", "both"] = "both",
) -> str:
    """
    Recursively search a JSON document for a term, matching against keys,
    values, or both (case-insensitive substring match). Returns every
    matching path found, without needing to know the structure in advance.
    """
    try:
        data = _load(json_data)
    except PathError as e:
        return f"Error: {e}"

    term_lower = term.lower()
    matches: list[dict[str, Any]] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                child_path = f"{path}.{key}"
                if mode in ("key", "both") and term_lower in str(key).lower():
                    matches.append(
                        {"path": child_path, "value": value, "matched": "key"}
                    )
                walk(value, child_path)
        elif isinstance(node, list):
            for i, value in enumerate(node):
                walk(value, f"{path}[{i}]")
        else:
            if mode in ("value", "both") and term_lower in str(node).lower():
                matches.append({"path": path, "value": node, "matched": "value"})

    walk(data, "$")

    if not matches:
        return f"No matches for '{term}' (mode={mode})."

    lines = [f"Found {len(matches)} match(es) for '{term}' (mode={mode}):\n"]
    for m in matches:
        value_repr = json.dumps(m["value"]) if not isinstance(m["value"], (dict, list)) else f"{type(m['value']).__name__}(...)"
        lines.append(f"  [{m['matched']}] {m['path']} = {value_repr}")
    return "\n".join(lines)


@mcp.tool()
def flatten(json_data: str) -> str:
    """
    Flatten a nested JSON document into flat "dot.path": value pairs,
    e.g. {"a": {"b": [1, 2]}} -> {"$.a.b[0]": 1, "$.a.b[1]": 2}.
    Useful for quickly skimming large or deeply nested payloads.
    """
    try:
        data = _load(json_data)
    except PathError as e:
        return f"Error: {e}"

    flat = _flatten(data)
    return json.dumps(flat, indent=2)


@mcp.tool()
def diff(json_a: str, json_b: str) -> str:
    """
    Compare two JSON documents and report added, removed, and changed
    paths in human-readable form (rather than a line-based text diff).
    """
    try:
        a = _load(json_a)
        b = _load(json_b)
    except PathError as e:
        return f"Error: {e}"

    flat_a = _flatten(a)
    flat_b = _flatten(b)

    keys_a, keys_b = set(flat_a), set(flat_b)
    added = sorted(keys_b - keys_a)
    removed = sorted(keys_a - keys_b)
    changed = sorted(
        k for k in (keys_a & keys_b) if flat_a[k] != flat_b[k]
    )

    if not (added or removed or changed):
        return "No differences found."

    lines = []
    if added:
        lines.append(f"Added ({len(added)}):")
        lines += [f"  + {k} = {json.dumps(flat_b[k])}" for k in added]
    if removed:
        lines.append(f"Removed ({len(removed)}):")
        lines += [f"  - {k} = {json.dumps(flat_a[k])}" for k in removed]
    if changed:
        lines.append(f"Changed ({len(changed)}):")
        lines += [
            f"  ~ {k}: {json.dumps(flat_a[k])} -> {json.dumps(flat_b[k])}"
            for k in changed
        ]
    return "\n".join(lines)


@mcp.tool()
def validate(json_data: str) -> str:
    """
    Validate a JSON string. On success, returns a pretty-printed version
    plus basic stats (type, depth, key/item count). On failure, reports
    the exact line and column of the syntax error.
    """
    try:
        data = json.loads(json_data)
    except json.JSONDecodeError as e:
        return f"Invalid JSON: {e.msg} at line {e.lineno}, column {e.colno}."

    stats = [f"Valid JSON.", f"Top-level type: {type(data).__name__}", f"Depth: {_depth(data)}"]
    if isinstance(data, dict):
        stats.append(f"Top-level keys: {len(data)}")
    elif isinstance(data, list):
        stats.append(f"Top-level items: {len(data)}")

    return "\n".join(stats) + "\n\n" + json.dumps(data, indent=2)


if __name__ == "__main__":
    mcp.run()
