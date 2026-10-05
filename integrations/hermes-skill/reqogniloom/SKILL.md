---
name: reqogniloom
description: REST and MCP client for ReqogniLoom from Hermes.
version: 0.1.0
author: ReqogniLoom
license: MIT
platforms:
  - tui
  - web
  - cli
  - desktop
metadata:
  hermes:
    tags:
      - requirements
      - traceability
      - mcp
      - rest
      - integration
---

# ReqogniLoom connector

Small stdlib-only connector that lets this skill talk to a ReqogniLoom instance
over its REST API and its native MCP server. It works on every Hermes surface —
TUI, web, CLI and desktop — because it depends on nothing beyond the Python
standard library.

## Setup

Export the server location and an API key (`reqlo_...`). Put these in
`~/.hermes/.env` so every surface inherits them:

```bash
export REQOGNILOOM_BASE_URL="http://localhost:8001"   # optional, this is the default
export REQOGNILOOM_API_KEY="reqlo_..."
export REQOGNILOOM_WORKSPACE_ID="00000000-0000-0000-0000-000000000000"  # optional
```

The key is sent as the `X-API-Key` header. If it is missing, the client fails
with a clear message instead of sending an anonymous request. Never put a key
in the skill itself.

## Usage

Run the client from this skill directory with `python`:

```bash
# List the workspaces the key can see (REST)
python scripts/reqogniloom_client.py list-workspaces

# Call any MCP tool with a JSON argument object
python scripts/reqogniloom_client.py mcp --tool requirement_query \
    --params '{"workspace_id": "00000000-0000-0000-0000-000000000000"}'
```

`--tool` is the MCP tool name; `--params` must be a JSON object (default `{}`).
Results are printed to stdout as readable JSON. Any failure — transport error,
REST error envelope, JSON-RPC protocol error (natural non-200 HTTP status), or
an MCP tool-execution error (`HTTP 200` with `result.isError`) — is printed as a
single normalised `code: message` line on stderr and the process exits with code
`1`, never with a traceback.

See [references/api.md](references/api.md) for the endpoints, the auth header,
both error shapes and the exact JSON-RPC frame.
