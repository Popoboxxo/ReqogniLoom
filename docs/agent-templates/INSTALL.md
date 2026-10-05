# Agent Template Installation

> **Per-client, one-command installs (DE/EN):** see
> [`docs/clients/`](../clients/README.md). That tree is generated from
> `clients/registry.yaml` and is the single source of truth for transport,
> auth, configuration, verification and pitfalls. This file covers the
> repackaging pipeline and the generated `dist/` artifacts.

## Claude Code

1. Add the local marketplace (once per machine, or point at the published
   Git repo once this package is pushed to one):
   ```bash
   claude plugin marketplace add dist/plugins/claude-code
   ```
2. Install the plugin:
   ```bash
   claude plugin install reqogniloom
   ```
3. Set the two required environment variables before starting Claude Code
   (never commit real values — use your shell profile or a secrets
   manager, matching this repo's own `templates/configs/mcp-secrets.local-template.yaml`
   convention):
   ```bash
   export REQOGNILOOM_MCP_URL="https://your-reqogniloom-instance"
   export REQOGNILOOM_API_KEY="reqlo_..."
   ```
4. Verify: `/plugin` inside Claude Code should list `reqogniloom` as
   installed with 5 agents and 1 MCP server (`reqogniloom`, SSE).
5. Invoke a role: `@requirements-architecture-manager` and ask it to call
   `workspace.get_context` — a successful response confirms the MCP
   connection, auth, and RBAC all resolved correctly end to end. Then try
   `@change-manager` and ask it to call `review.list_pending` — this
   confirms the Task 3 additions (CCB/review tools) actually reached the
   packaged agent.

## OpenCode

OpenCode has no plugin-marketplace install path — merge the generated MCP
block into your own project's config and drop the skill files where
OpenCode already looks for them:

1. Prefer the one command (canonical, `remote`/SSE):
   ```bash
   opencode mcp add reqogniloom --url "$REQOGNILOOM_MCP_URL/mcp/sse/"
   ```
   Or merge `dist/opencode/opencode.json.snippet`'s `mcp.reqogniloom` block
   into your project's `opencode.json` (or `~/.config/opencode/opencode.json`
   for a user-wide install). This is the **canonical** shape — earlier
   documentation showed a `type:"http"` + `options.headers` variant that never
   matched the shipped snippet and is now a CI failure to reintroduce:

   ```json
   {
     "mcp": {
       "reqogniloom": {
         "type": "remote",
         "url": "{env:REQOGNILOOM_MCP_URL}/mcp/sse/",
         "headers": {
           "X-API-Key": "{env:REQOGNILOOM_API_KEY}"
         }
       }
     }
   }
   ```

   **Important:** OpenCode only expands `{env:NAME}` and `{file:path}` — a bare `{...}` is sent literally and the server will reject it as an invalid key (401). Make sure to use the `env:` prefix for environment variable references.

2. Copy `dist/opencode/skills/*` into your project's `.opencode/skills/`.
   Each `SKILL.md` links to `../../DOMAIN_MODEL.md`, which this package does
   not ship (see the build script's reasoning) — also copy
   `docs/agent-templates/DOMAIN_MODEL.md` to `.opencode/DOMAIN_MODEL.md`
   (one level above `skills/`, i.e. two levels up from
   `.opencode/skills/<name>/SKILL.md`) so that link resolves.
3. Set the same two environment variables as the Claude Code install
   (`REQOGNILOOM_MCP_URL`, `REQOGNILOOM_API_KEY`) — OpenCode's `{env:...}`
   syntax resolves them at connection time, never store the literal key in
   `opencode.json`.
4. Verify: `opencode mcp list` should show `reqogniloom` as connected; ask
   any OpenCode agent to use the `traceability-audit` skill and call
   `traceability.query` to confirm read access end to end. OpenCode has no
   client-side tool-restriction concept for a skill (unlike Claude Code's
   `agents/`) — whatever the connected `REQOGNILOOM_API_KEY` is authorized
   for on the MCP server is what any skill can call; scope the key itself
   (not the skill choice) if you need to limit what an OpenCode session can
   write.

## Antigravity

1. Open Antigravity's MCP Store and import
   `dist/plugins/antigravity/reqogniloom/mcp_config.json`, **or** manually
   merge its `mcpServers.reqogniloom` block into
   `~/.gemini/config/mcp_config.json` (or your project's
   `.agents/mcp_config.json`).
2. Copy `dist/plugins/antigravity/reqogniloom/skills/*` into your project's
   Antigravity skills directory (or run
   `npx skills add dist/plugins/antigravity/reqogniloom -a antigravity`,
   the CLI Antigravity documents for third-party skill installs).
3. Set `REQOGNILOOM_MCP_URL` / `REQOGNILOOM_API_KEY` in the environment
   Antigravity's MCP client resolves `${...}` references from.
4. Verify: the Antigravity MCP panel shows `reqogniloom` connected; invoke
   the `vmodell-decomposition` skill and confirm a `workspace.get_context`
   call succeeds.

Antigravity is a free-quota preview product with documented security
findings around its browser subagent, and — like OpenCode — has no
client-side tool restriction per skill; the actual write-tool boundary is
whatever role the connected `REQOGNILOOM_API_KEY` has on the MCP server, not
which skill (`ccb-approval-and-baseline`, `vmodell-decomposition`, …) gets
invoked. Until the platform's own security posture matures, connect
Antigravity with a **read-only-role API key** (mirroring the
`quality-auditor` role's tool scope) against a production workspace, rather
than relying on skill choice to hold that boundary.

## Regenerating after a ReqogniLoom version upgrade

Every package in `dist/` is generated, not hand-maintained. After any
change to `backend/mcp_server/tool_registry.py`, a `VERSION` bump, a manual
edit to a `docs/agent-templates/<role>.md` role's `tools:` whitelist, or an
edit to a `docs/agent-templates/skills/<name>/SKILL.md` process skill, run
in order (each depends on the previous step's output):

```bash
docker-compose exec backend python manage.py export_tool_manifest
python -m pytest docs/agent-templates/test_role_tools_exist_in_manifest.py \
                  docs/agent-templates/test_process_skills_reference_real_tools.py -v
python docs/agent-templates/package_skills.py
python dist/plugins/claude-code/build_claude_plugin.py
python dist/plugins/antigravity/build_antigravity_plugin.py
python dist/opencode/build_opencode_package.py
```

The `test_tool_manifest_drift` test (`backend/mcp_server/tests/test_tool_manifest_drift.py`)
fails CI if step 1's output is committed stale relative to the registry —
treat a CI failure there as "you forgot to regenerate," not a code bug. The
`test_role_tools_exist_in_manifest.py` run in step 2 catches the same class
of drift one level up: a role file referencing a tool that got renamed or
removed since the role was last updated.

## One convention, and one place it disagrees

Every package above is generated with the same convention, and the backend is
what defines it:

| Fact | Value | Defined by |
|------|-------|------------|
| Env vars | `REQOGNILOOM_MCP_URL`, `REQOGNILOOM_API_KEY` | this document |
| Key prefix | `reqlo_` — MCP *requires* it, a JWT in `Authorization: Bearer` is rejected | `backend/auth_tenancy/rest.py` |
| Auth header | `X-API-Key`, or `Authorization: Bearer` — the backend accepts both | `backend/mcp_server/protocol_handler.py` |

Codex is the one package that uses the Bearer form: its Streamable-HTTP
transport has no custom-header mechanism, only `bearer_token_env_var`, which
the client expands into `Authorization: Bearer`. That is the *other* accepted
transport, not a workaround.

A second, divergent variant of this convention exists in the `.agent-meta`
submodule (`config/plugin-catalog.yaml`, regenerated by `sync.py` into
`.agent-meta/opencode.json`): `MCP_REQOGNILOOM_*` env vars, `Authorization:
Bearer` for all providers, and three extra headers — `X-Project-ID`,
`X-User-ID`, `X-Workspace-ID`. **It is upstream vendor content and is not
edited from this repo**; changing it needs an upstream change in
Popoboxxo/agent-meta followed by a `sync.py` re-run. The three extra headers
are dead weight either way: the backend has zero production reads of them
(`X-Workspace-ID` is measured in
`docs/se/reports/deep_audit/system-audit-2026-09/09-evidence-register.md`,
CR-22), so they read as configuration while affecting nothing. No active
provider config in this repo declares the ReqogniLoom MCP server, so the
divergence is currently inert at runtime.

`dist/test_mcp_convention_parity.py` fails if anything under `dist/` drifts
from the table above — a non-`REQOGNILOOM_` env prefix, an auth header the
backend does not read, or a literal key pasted into a shipped file. If it
fails, fix the builder and re-run the regeneration steps above; do not paper
over it by editing the generated artifact.

