# MCP JSON Explorer

An [MCP](https://modelcontextprotocol.io) server that gives AI assistants like
Claude a practical toolkit for working with JSON — querying, searching,
flattening, diffing, and validating — without needing to learn `jq`-style
filter syntax.

## Why

`jq` is powerful but has a learning curve, and its error messages aren't
always AI-friendly. This server exposes the same kinds of operations as
plain function calls with forgiving, descriptive errors — e.g. instead of
a cryptic parse failure, `query` tells you exactly which key was missing
and what keys *were* available at that point in the document.

## Tools

| Tool | Description |
|---|---|
| `query(json_data, path)` | Look up a value with a simple dot/bracket path, e.g. `items[0].name`. Errors point out exactly where the path broke down. |
| `search(json_data, term, mode)` | Recursively search for a term in keys, values, or both — no need to know the structure up front. |
| `flatten(json_data)` | Flatten nested JSON into `"$.dot.path": value` pairs for quick skimming of large payloads. |
| `diff(json_a, json_b)` | Compare two JSON documents and report added / removed / changed paths in human-readable form. |
| `validate(json_data)` | Validate JSON syntax; on failure, reports the exact line and column of the error. |

## Setup

Requires Python 3.11+ and [`uv`](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/<your-username>/mcp-json-explorer.git
cd mcp-json-explorer
uv sync
```

## Running

Standalone (stdio transport):

```bash
uv run server.py
```

With the MCP inspector, for interactive debugging:

```bash
uv run mcp dev server.py
```

## Using it with Claude Desktop / Claude Code

Add this to your MCP client config (e.g. `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "json-explorer": {
      "command": "uv",
      "args": [
        "--directory",
        "/absolute/path/to/mcp-json-explorer",
        "run",
        "server.py"
      ]
    }
  }
}
```

Restart the client, and the five tools above will be available for Claude
to call whenever JSON is involved in the conversation.

## Example

```
> query({"items": [{"name": "Widget"}]}, "items[0].name")
"Widget"

> query({"user": {"name": "Ada"}}, "user.email")
Error: Key 'email' not found at '$.user'. Available keys: name

> search({"user": {"name": "Ada"}, "tags": ["name-check"]}, "name")
Found 2 match(es) for 'name' (mode=both):
  [key] $.user.name = "Ada"
  [value] $.tags[0] = "name-check"
```

## License

MIT
