# ReqogniLoom for OpenCode

Registers a ReqogniLoom MCP server with OpenCode and ships the ReqogniLoom
process skills. OpenCode 1 and 2 both get a `remote` entry on `/mcp/`
(Streamable HTTP, `X-API-Key`); OpenCode 1 falls back to the SSE endpoint only
if the server does not answer the Streamable HTTP POST.

## Install

```bash
npm install -g @popoboxxo/reqogniloom-opencode
```

Add the plugin to your `opencode.json` (`plugin` is also accepted by OpenCode
2, which normalizes it to `plugins`):

```json
{
  "plugin": ["@popoboxxo/reqogniloom-opencode"]
}
```

Set the two environment variables OpenCode expands at connect time — never put
a key into the config file:

```bash
# Base URL, no path; do not end in /mcp (the plugin appends /mcp/ itself).
export REQOGNILOOM_MCP_URL="https://your-reqogniloom-host"
export REQOGNILOOM_API_KEY="<your API key>"
```

## Skills

The package bundles `skills/<name>/SKILL.md` and `DOMAIN_MODEL.md` at its root,
so the skills' `../../DOMAIN_MODEL.md` links resolve inside the installed
package. Copy `skills/*` into `~/.config/opencode/skills/` (and
`DOMAIN_MODEL.md` one level above) if you prefer a local, user-wide install.

## Listen mode (ambient capture)

The plugin also wires OpenCode's capture events: V1 `chat.message` and V2
`session.hook("prompt")` both hand the user message to `listen.mjs`, the same
relay core, copied into the package. It is **off by default**; the switch lives
in `~/.reqogniloom/listen/listen.json` and is shared with the Claude Code,
Hermes and Antigravity plugins.

```bash
node "$(npm root -g)/@popoboxxo/reqogniloom-opencode/listen.mjs" on <workspace_id>
node "$(npm root -g)/@popoboxxo/reqogniloom-opencode/listen.mjs" status
node "$(npm root -g)/@popoboxxo/reqogniloom-opencode/listen.mjs" off   # deletes unsent messages
```

Copy `command/reqogniloom-listen.md` into `.opencode/command/` to get
`/reqogniloom-listen`. Delivery uses `REQOGNILOOM_MCP_URL` (or
`REQOGNILOOM_BASE_URL`) and `REQOGNILOOM_API_KEY`. The hook never blocks the
turn: it writes a write-ahead queue and drains it without `await`. Contract:
`docs/clients/listen-mode-contract.md`.

## Verify

```bash
opencode mcp list   # -> reqogniloom connected
```
