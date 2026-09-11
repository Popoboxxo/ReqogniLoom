# Hermes IDE Plugin for ReqogniLoom — Design

**Status:** Approved for planning
**Date:** 2026-08-13

## Goal

Ship an official Hermes IDE plugin (target repo: `hermes-hq/plugins`, curated registry) that
lets a Hermes IDE user browse, search, create, and edit ReqogniLoom requirements from a
sidebar panel — the first of several ReqogniLoom-capability panels to follow the same
pattern (Architecture, Traceability, Test Runs, SE-Metrics are explicitly out of scope for
this round, planned as separate spec → plan → implementation cycles later).

## Why this scope, and what's out

"Support as many ReqogniLoom functions as possible" is several independent subsystems
crammed into one narrow (~300–400px) sidebar panel. Rather than one sprawling spec, this
round ships Requirements end-to-end (list, search, detail, create, edit) as the proven
vertical slice; later rounds add Traceability/Tests/Baselines/SE-Metrics panels reusing the
same manifest/auth/data-flow conventions established here.

Explicitly dropped for this round: a "create requirement from editor selection" command —
the Hermes Plugin API (`docs/PLUGIN-API.md` in `hermes-hq/plugins`, checked 2026-08-13) has
no editor/file/selection surface at all. Hermes IDE is terminal-centric: `api.sessions` and
`api.agents` expose terminal sessions and AI-agent transcripts, not a text buffer. A
clipboard-based substitute was considered and explicitly rejected by the user for this
round — MVP stays list/search/detail/create/edit only, no clipboard command.

## Repo location

`integrations/hermes-plugin/reqogniloom/` inside this repo (ReqogniLoom), **not** a fork of
`hermes-hq/plugins` — explicit user decision, overriding the otherwise-universal convention
(all 7 existing official plugins live in-tree in that monorepo under `plugins/<name>/`).
Publishing to `hermes-hq/plugins` (fork + PR per their `CONTRIBUTING.md`) is a later,
separate distribution step out of this round's scope — this round only produces the
plugin source, built and locally verified inside this repo.

Chosen over `dist/plugins/hermes/` (the existing `dist/plugins/claude-code|antigravity`
sibling path) because this is genuinely hand-written React/TS application code with its own
`package.json`/`node_modules`/Vite build, not generated config like the other two — a
different top-level integration point avoids confusing it with the generated-bundle
pattern.

## Reference implementation

`hermes-hq/plugins`' own `plugins/github/` plugin (`hermes-plugin.json` + `src/activate.ts`
+ `src/GitHubPanel.tsx`) is the closest analog — external service, token-based auth, single
panel with internal view states, status bar item — and is reused as the structural template
throughout this design rather than inventing new patterns.

## Manifest (`hermes-plugin.json`)

```json
{
  "id": "reqogniloom.reqogniloom",
  "name": "ReqogniLoom",
  "version": "<matches this repo's VERSION file at build time>",
  "description": "Browse, search, and manage ReqogniLoom requirements",
  "author": "ReqogniLoom",
  "main": "dist/index.js",
  "activationEvents": [{ "type": "onStartup" }],
  "contributes": {
    "commands": [
      { "command": "reqogniloom.open", "title": "Open ReqogniLoom", "category": "ReqogniLoom" }
    ],
    "panels": [
      { "id": "reqogniloom-panel", "name": "ReqogniLoom", "side": "left", "icon": "<svg .../>" }
    ],
    "statusBarItems": [
      { "id": "reqogniloom.status", "text": "ReqogniLoom", "alignment": "right", "priority": 20, "command": "reqogniloom.open" }
    ]
  },
  "permissions": ["network", "storage"]
}
```

No `contributes.settings` entries for the connection (workspace URL / API key) — see Auth
below. A `refreshInterval` setting (mirroring the github plugin's) is deferred; MVP refresh
is manual (a refresh button in the panel), avoiding auto-poll complexity for a first cut.

## Auth

Verified against `backend/auth_tenancy/rest.py::AuthTenancyAuthentication` (2026-08-13):
this authentication class is used across the **entire** REST API (`/api/v1/...`), not just
MCP, and accepts either an `X-API-Key` header or `Authorization: Bearer <api_key>` — the
same `reqlo_`-prefixed keys already issued via `ApiKeyViewSet` (`/api/v1/api-keys/`) and
already used by the MCP integration. No new backend auth path needed.

The plugin does **not** put the API key in `contributes.settings` (the schema/masking
behavior for secret-typed settings fields isn't documented, and `MANIFEST.md`'s
`contributes.settings` section wasn't found in the doc snapshot reviewed — an undocumented
gap, not confirmed absent). Instead, mirror the github plugin's own token pattern exactly:
an in-panel "Connect" screen with two plain-text inputs (Workspace URL, API Key), validated
with a lightweight `GET /api/v1/requirements/?page_size=1` call, then persisted via
`api.storage.set()` on success. `activate()` reads the stored connection on startup and
skips straight to the requirements list if present (same as github plugin's saved-token
check).

On a 401/403 from any call, clear the stored key and drop back to the Connect screen (same
as github plugin's `disconnect()`).

## Views (single panel, internal state machine)

`connect → list → detail → form (create | edit)`, all inside the one `reqogniloom-panel`
component — no multi-panel navigation for MVP, following the github plugin's single-panel
`View` union-type pattern (`"connect" | "authorizing" | "reviews" | "my-prs" |
"notifications"`).

- **list**: paginated (`GET /api/v1/requirements/`), search/filter by title/status/level,
  manual refresh button, status bar item shows an open-requirement count (exact "open"
  status set to be pulled from the OpenAPI schema at implementation time, not guessed here)
- **detail**: single requirement (`GET /api/v1/requirements/{id}/`) — title, REQ-ID, status,
  level, verification_method, acceptance_criteria, trace-link count
- **form**: create (`POST`) or edit (`PATCH`) — core SE fields; 400 validation errors
  surfaced per-field using this project's standard error-envelope shape, not a bare toast

## Data flow

- `reqloFetch(path, options?)` — a small wrapper around `api.network.fetch(url, {
  headers: { "X-API-Key": storedKey }, ...options })`, analogous to the reference plugin's
  `ghGet`/`ghPost` helpers, built on the documented (and reference-plugin-confirmed)
  `RequestInit`-accepting signature of `api.network.fetch`
- Module-level mutable state + `subscribe`/`notify()` pub-sub, exactly the github plugin's
  shape — deliberately not introducing Redux/Context/etc. for a panel this size
- Status bar item updates after every list load/refresh

## Error handling

| Case | Behavior |
|---|---|
| 401/403 | Clear stored key, return to Connect screen |
| Network unreachable | Inline error banner in panel + `api.ui.showToast(..., {type: "error"})` |
| 400 on create/edit | Per-field messages under the form, from the standard error envelope |
| Other 5xx | Inline error banner, retry via the existing manual refresh button (no auto-retry/backoff — this isn't a polling integration) |

## Testing

- Follow `hermes-hq/plugins`' own existing convention (`plugins/json-formatter/src/__tests__/`,
  Vitest) — mirror whatever config that reference actually uses at implementation time
  rather than assuming
- Unit tests for the state module: connect flow (success/401/network-error), list
  load/paginate/search, detail load, create/edit success and 400-validation paths — all
  against mocked `api.network.fetch`, no live backend required
- Before marking the round done: build the plugin, copy it into a local Hermes IDE plugins
  directory per `docs/DEVELOPMENT.md`'s manual dev-workflow, and verify live against a
  running ReqogniLoom dev stack (`docker compose up`) — same verification discipline as
  today's E2E work, not just unit-test-green

## CI

New `.github/workflows/hermes-plugin.yml`, path-filtered to `integrations/hermes-plugin/**`
so it doesn't run on unrelated backend/frontend changes and doesn't affect existing
workflow runtimes: `npm install`, lint, `npm test`, `npm run build`.

## Explicitly out of scope this round

- Architecture / Traceability / Test-Runs / Baselines / SE-Metrics panels (separate future
  rounds, same conventions)
- Publishing to `hermes-hq/plugins` (fork, PR, registry entry) — a later distribution step
- Auto-refresh interval setting
- Any editor-context command (clipboard-based or otherwise) — explicitly rejected by user
  for this round
