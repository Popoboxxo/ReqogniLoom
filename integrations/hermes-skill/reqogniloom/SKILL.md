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
# List the workspaces the key can see (REST, all DRF pages are followed)
python scripts/reqogniloom_client.py list-workspaces

# Call any MCP tool with a JSON argument object
python scripts/reqogniloom_client.py mcp --tool requirement.query \
    --params '{"workspace_id": "00000000-0000-0000-0000-000000000000"}'
```

`--tool` is the MCP tool name; `--params` must be a JSON object (default `{}`).
Results are printed to stdout as readable JSON. Any failure — transport error,
REST error envelope, JSON-RPC protocol error (natural non-200 HTTP status), or
an MCP tool-execution error (`HTTP 200` with `result.isError`) — is printed as a
single normalised `code: message` line on stderr and the process exits with code
`1`, never with a traceback.

## Memory

Read the workspace's long-term memory:

```bash
# Semantic search (workspace scope; omit --workspace-id to use the env default)
python scripts/reqogniloom_client.py memory-query --query "reviewer" --top-k 5

# Search several scopes at once
python scripts/reqogniloom_client.py memory-query --query "reviewer" \
    --scopes workspace,user

# Prompt-ready digest of one scope
python scripts/reqogniloom_client.py memory-digest --workspace-id <uuid>

# Natural-language answer from one scope
python scripts/reqogniloom_client.py memory-ask --query "what changed?" \
    --workspace-id <uuid> --reasoning-level medium
```

Feed knowledge back in:

```bash
# Persist a fact for the calling user (no workspace/artifact id needed)
python scripts/reqogniloom_client.py memory-write --content "prefers tabs" --scope user

# Persist into a workspace or one artifact
python scripts/reqogniloom_client.py memory-write --content "..." \
    --scope workspace --workspace-id <uuid>
python scripts/reqogniloom_client.py memory-write --content "..." \
    --scope artifact --artifact-id <uuid>
```

`--workspace-id` is a global flag and defaults to `REQOGNILOOM_WORKSPACE_ID`;
`memory-digest`, `memory-ask`, `memory-query` with a workspace scope and
`memory-write --scope workspace` fail with a clear error when neither yields a
value. `--scopes` is comma-separated, repeatable and takes precedence over
`--scope`; `--artifact-id`, `--confidence` and `--change-reason` are optional.
Only the arguments you actually provide are sent (no `null` values), and an
incompatible `--scope`/`--artifact-id`/`--workspace-id` combination is
rejected with a clear error instead of being silently dropped.

Writing is a privileged action: the plugin gates `memory.write` behind an
explicit user confirmation before it issues the call. This skill itself only
frames the call — it never confirms on the user's behalf.

The "memory → proposed artifact" stage is **P4** (see the bugfix hub plan) and
is intentionally not implemented here.

See [references/api.md](references/api.md) for the endpoints, the auth header,
both error shapes, the exact JSON-RPC frame and every memory tool argument.
