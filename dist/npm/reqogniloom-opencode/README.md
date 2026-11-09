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
export REQOGNILOOM_MCP_URL="https://your-reqogniloom-host"
export REQOGNILOOM_API_KEY="<your API key>"
```

## Skills

The package bundles `skills/<name>/SKILL.md` and `DOMAIN_MODEL.md` at its root,
so the skills' `../../DOMAIN_MODEL.md` links resolve inside the installed
package. Copy `skills/*` into `~/.config/opencode/skills/` (and
`DOMAIN_MODEL.md` one level above) if you prefer a local, user-wide install.

## Verify

```bash
opencode mcp list   # -> reqogniloom connected
```
