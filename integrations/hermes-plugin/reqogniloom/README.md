# ReqogniLoom — Hermes desktop plugin

Desktop panel + status-bar entry for the Hermes desktop app. The generated
client guide (`docs/clients/hermes.md` / `.de.md`, section "Desktop plugin")
is the user-facing entry point; this file documents the source tree itself.

## Features

- Connect to a ReqogniLoom server with an API key; the workspace is resolved once.
- Interviews via the MCP server (existing views).
- Requirements: filterable, paginated list; read-only detail; create/edit form.
  `level`, `tier_name`, `level_source` and `suspect` are derived server-side and
  are shown, never edited. A read-only key can browse; saving answers 403 and is
  surfaced as an error banner.
- Known limits: no delete, no allocation editing, no level override in the form.

## Build and load

```bash
cd integrations/hermes-plugin/reqogniloom
npm ci
npm run build          # -> dist/plugin.js; postbuild runs scripts/verify-build.mjs
# load this folder as a desktop plugin in Hermes
```

## Manifest (`hermes-plugin.json`)

- Panel `reqogniloom-panel` (`area: panes`, left).
- Status-bar item `reqogniloom.status` (`area: statusBar.right`, priority 20).
- Command `reqogniloom.open` — opens the panel.

## Version rule

The plugin follows the repository `VERSION` (ADR-017 Option A). Drift between
the installed and shipped plugin is caught by
`scripts/check_plugin_packages.py` at release time.

## Tests

```bash
npm test               # vitest
```
