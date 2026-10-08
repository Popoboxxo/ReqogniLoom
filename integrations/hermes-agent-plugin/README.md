# reqogniloom (Hermes Agent plugin)

Drives ReqogniLoom requirements work from inside Hermes, and can listen along
while you talk:

- `/reqogniloom` — start, answer and formalize one interview by hand;
- a read-only dashboard tab — per-workspace counts and the interviews still open;
- an opt-in **listen mode** — while it is on, your messages are captured into a
  type-less multi-artifact interview and whatever ReqogniLoom proposes from them
  is parked as a *suggestion* for `/reqogniloom review`. Nothing is created
  without an explicit `/reqogniloom accept`.

Upstream tracking: [Popoboxxo/ReqogniLoom#1201](https://github.com/Popoboxxo/ReqogniLoom/issues/1201)
(agent-native integration + ambient capture) and
[Popoboxxo/ReqogniLoom#1202](https://github.com/Popoboxxo/ReqogniLoom/issues/1202)
(the live-QA findings this rewrite addresses — F1 token gate, F2 minimal tab,
F4 MCP surface unused, F5 base-URL default, F6 README drift, F7 host
contract).

**Status: verified against one live install, thin by design.** The mounted router
was exercised against a running Hermes dashboard (`/api/plugins/reqogniloom/`:
`/version`, `/stats`, `/workspaces` answered 200 through the host dashboard's own
auth, which is the only gate). The listen mode in this revision is unit-tested,
not yet re-verified live. Built
against the plugin contract observed
in [`NousResearch/hermes-agent`](https://github.com/NousResearch/hermes-agent)'s
[`plugins/disk-cleanup`](https://github.com/NousResearch/hermes-agent/tree/main/plugins/disk-cleanup)
(slash command + hooks) and
[`plugins/hermes-achievements`](https://github.com/NousResearch/hermes-agent/tree/main/plugins/hermes-achievements)
(dashboard tab: `manifest.json` + `plugin_api.py` FastAPI router + a
build-step-free `dist/index.js` that takes React/hooks/components from the
host's injected `window.__HERMES_PLUGIN_SDK__` but issues its own
`window.fetch` calls for data, because the host hands the plugin no credential
at all). Since then the plugin has been exercised against a live Hermes
install ([#1202](https://github.com/Popoboxxo/ReqogniLoom/issues/1202),
[#1203](https://github.com/Popoboxxo/ReqogniLoom/issues/1203)). The old
`integrations/hermes-plugin/reqogniloom/` TS port targeted a different,
unverified `@hermes/plugin-sdk` contract (a desktop-IDE-style
`{id, name, register(ctx)}` with `ctx.register({area: "panes"|...})`) that
doesn't match either of the two real reference plugins above, and has been
removed; this plugin and the skill are the shipped Hermes integrations.

## Transport

The shared client (`reqogniloom_client.py`) speaks ReqogniLoom's **native MCP
server** for every operation: `POST {base_url}/mcp/` with a JSON-RPC 2.0
`tools/call` frame, authenticated with the `X-API-Key` header. That is the same
tool surface the rest of the ecosystem uses, so the plugin cannot drift from a
second, partial API. The MCP transport rejects a `Bearer` JWT
(`bearer_not_supported`), so the key must travel as `X-API-Key`. Tool results
arrive as MCP content blocks (`result.content[0].text`, a JSON string) and are
decoded by the client; tool-execution errors arrive as HTTP 200 with
`result.isError`.

Only `GET /api/v1/version/` stays on REST: it is public and has no MCP tool. It
never sends the API key.


## Install

```bash
ln -s /path/to/ReqogniLoom/integrations/hermes-agent-plugin ~/.hermes/plugins/reqogniloom
```

## Configuration

Environment variables, read at call time (no persisted config file):

- `REQOGNILOOM_BASE_URL` — default `http://localhost:8001`. The default is
  intentional, but when the variable is **unset** and a transport failure
  occurs the client raises a `ReqogniLoomError` naming the variable, e.g.
  `could not reach http://localhost:8001/… — REQOGNILOOM_BASE_URL is not set,
  so the request went to the default http://localhost:8001; set
  REQOGNILOOM_BASE_URL to your ReqogniLoom instance (e.g.
  https://reqogniloom.example.com)`. An invalid (non-`http(s)` or empty) value
  is rejected at construction, e.g. `invalid REQOGNILOOM_BASE_URL
  'ftp://nope': expected an http:// or https:// URL, e.g.
  REQOGNILOOM_BASE_URL=http://localhost:8001`.
- `REQOGNILOOM_API_KEY` — a ReqogniLoom API key (`reqlo_...`), sent as the
  `X-API-Key` header on every MCP call. It is **never** sent on the public
  `GET /api/v1/version/` call. A missing key fails fast, before any request.

## Slash command

```
/reqogniloom start <artifact_type> [workspace_id]   Start a new interview (workspace_id optional — defaults to your first visible workspace)
/reqogniloom status                                 Show the current interview's phase and missing fields
/reqogniloom answer <field> <value...>               Answer one field of the current interview
/reqogniloom chat <message...>                       Send a free-form chat turn
/reqogniloom formalize                               Turn the interview into a real artifact
/reqogniloom abandon                                 Cancel the current interview
/reqogniloom workspaces                              List workspaces visible to this API key
/reqogniloom stats [workspace_id]                    Quick counts (requirements, testcases, open interviews)
/reqogniloom suggestion list [workspace_id]          List server-side ADR-019 suggestions (read-only)
/reqogniloom suggestion accept <id>                  Accept one server-side suggestion by id
/reqogniloom suggestion reject <id> [reason...]      Reject one server-side suggestion by id
/reqogniloom help                                    Show this text
```

The "current interview" is remembered across command invocations in
`$HERMES_HOME/reqogniloom/state.json` (falls back to `~/.hermes` if
`HERMES_HOME` is unset) — same pattern `disk-cleanup` uses for its own
state file.

## Dashboard tab

Read-only: per-workspace artifact counters (requirements, test cases, open
interviews) for the picked workspace, the open interviews as detail rows
(session id, type, phase, status, updated), and the ReqogniLoom build version.
Backend routes are mounted at `/api/plugins/reqogniloom/` by the Hermes
dashboard (`GET /stats`, `GET /workspaces`, `GET /version`, `GET /interviews`)
— see `dashboard/plugin_api.py`. The workspace picker defaults to the first
visible workspace and re-loads the counters and interview rows on change.

The tab relies on the **host dashboard's own auth**: there is no plugin-level
token, header or credential, and the tab loads straight into the data. The four
routes are read-only and same-origin; a genuine `ReqogniLoomError` backend
failure keeps the `200 + {"error": …}` contract so the tab can render it instead
of a 500. `REQOGNILOOM_API_KEY` remains the outbound tenant credential and is
never a dashboard credential.

## Listen mode ("hear along")

Opt-in, off by default, and it never creates anything by itself:

```text
/reqogniloom listen on [workspace_id]   # capture from now on
/reqogniloom listen status              # on/off, where, when the last capture was
/reqogniloom listen off                 # stay quiet again
/reqogniloom review                     # what ReqogniLoom proposed from your words
/reqogniloom review pending [ws]        # server-side queue: proposals awaiting a human
/reqogniloom accept <index|all>         # create the captured artifacts as proposals
/reqogniloom dismiss <index|all>        # drop them without creating anything
```

**How it works.** The plugin registers one `pre_llm_call` hook, which the host
calls with the user's message on every turn. While listen mode is on and the
message looks substantial (≥40 characters, not a command), the message is handed
to a **detached** worker process (`_capture.py`) — detached because the hook sits
on the turn's critical path while a capture round is two or three network calls
plus a server-side LLM turn:

1. it opens (once) a type-less, multi-artifact interview in the chosen workspace;
2. sends the message as a chat turn;
3. reads back the proposal ReqogniLoom built from it;
4. queues that proposal in `state.json` as a suggestion.

`/reqogniloom accept` then formalizes exactly the queued items — one artifact per
item, with the confirmed proposal passed back to the API — and removes them from
the queue. Nothing else creates artifacts, and a failed capture leaves the queue
untouched.

**What `accept` actually creates: proposals, not final requirements.** The
accept path is `interview.formalize` under the plugin's API-key context, which
is an *agent* principal. ReqogniLoom seeds an agent-created artifact into the
workflow state **`proposed`** (`workflow.services.initial_state_for`), so the
artifact is born as a proposal and waits for a human confirm — it is never
adopted as a final requirement by the plugin. Use `/reqogniloom review pending`
to list that server-side queue (`review.list_pending`) together with the ADR-019
suggestion inbox (`suggestion.list`); nothing is auto-confirmed.

This is the M1 proposal semantics (the workflow `proposed` state), reused rather
than re-implemented (ADR-01 thin client). The plugin does **not** route artifact
creation through the ADR-019 `suggestion.accept` adapter: in the ADR-019 MVP the
`artifact_create` kind is registered but dormant, so no generic accept path for
new artifacts exists server-side. `suggestion.list`/`suggestion.accept`/
`suggestion.reject` are available in the client and surfaced by `review pending`
for the kinds that *are* live (e.g. `trace_link`).

One honest boundary: the `minimal` rigor preset deliberately has no `proposed`
state (`workflow/definition_store.py`, `SCHEMAS_WITHOUT_PROPOSED`), so on a
`minimal`-preset workspace `formalize` lands the artifact in the preset's normal
initial state (`draft`) instead — still not a final/adopted requirement, but also
not parked in the review queue. The proposal loop is only meaningful for the
`standard`/`extended` presets. Forcing `proposed` into `minimal` is explicitly
out of scope (ADR-019 O3).

Two deliberate limits: at most one capture every 45 s per install (a chatty
session must not queue an LLM turn per message), and a hard cap of 20 queued
suggestions (oldest dropped first) so the queue cannot grow without bound.
Duplicates are dropped by content hash. Diagnostics go to
`$HERMES_HOME/reqogniloom/capture.log`; the worker writes nothing to stdout and
never fails the turn it was spawned from.

## Server-side suggestions (ADR-019)

The ADR-019 suggestion inbox can also be decided straight from the command line,
by **explicit id** — the listing itself stays read-only:

```text
/reqogniloom suggestion list [ws]                 # read-only: server-side suggestions of a workspace
/reqogniloom suggestion accept <id>               # accept ONE server-side suggestion by id
/reqogniloom suggestion reject <id> [reason...]   # reject ONE, with an optional reason
```

`accept` and `reject` always name exactly one suggestion id: there is no default
and no `all`, so **nothing is ever accepted automatically**. An incomplete
command (no id) prints the usage line and calls no tool. This is deliberately
distinct from the listen-mode pair above: `accept <index|all>` formalizes the
*local* suggestions that listen mode captured into `state.json`, whereas
`suggestion accept|reject <id>` decide a *server-side* ADR-019 suggestion by its
server id. An agent may not accept its own proposal — the server answers
`PERMISSION_DENIED`, which the command renders as a readable
`ReqogniLoom error: …` instead of raising.

## Memory capabilities

ReqogniLoom exposes an AI long-term memory surface over its MCP server. The
Hermes integration reaches it through four dotted tool names:

| Tool | Direction | What it does |
| --- | --- | --- |
| `memory.query` | read | Semantic search over a `workspace`/`user`/`artifact` scope; returns `entries` plus `degraded`/`detail`. |
| `memory.digest` | read | Prompt-ready summary of a scope (`digest`, `derivation_status`, `derived_count`). |
| `memory.ask` | read | Natural-language answer (`answer`, `degraded`, `detail`). RBAC write-gated on the backend because it drives a generative LLM call, but it mutates nothing. |
| `memory.write` | **write** | Persists one fact (`content`, `scope` ∈ `workspace\|user\|artifact`). The only memory tool that mutates state, and the only one gated behind an explicit user confirmation. |

A read that legitimately returns no rows is reported **separately** from a
backend that could not answer: `degraded=true` together with a `detail` cause is
"backend unavailable/degraded", while an empty `entries` list with
`degraded=false` is a genuine "nothing remembered". Clients must not collapse
the two into one empty state.

Writing is never automatic. Capture is a two-step, user-driven flow — an on/off
**toggle** that enables the surface, then a **Review** step that stages the
draft locally, and only an explicit **Confirm** issues `memory.write`; Cancel
(or turning the toggle off) discards the draft. Nothing typed or toggled reaches
the backend on its own, and no auto-submit path exists.

**Where this lives.** The shipped implementation of the surface above is the
importable Hermes skill
(`integrations/hermes-skill/reqogniloom/` — the `memory-query` /
`memory-digest` / `memory-ask` / `memory-write` CLI subcommands, all backed by
the `memory.*` MCP tools). This agent-plugin POC
(`integrations/hermes-agent-plugin/`) is slash-command/dashboard-only and does
**not** call the memory surface yet.

**P4 boundary.** The follow-on stage "capture → `proposed` artifact → human
accept" is deliberately **not** implemented. It is the proposal loop deferred to
P4 of the bugfix-hub work plan
(`docs/plans/2026-10-05-bugfix-hub-integrationen.md`, AP-B5.4). The capture gate
described here only persists a memory fact via `memory.write`; it never proposes
an artifact.

## Files

```text
plugin.yaml              # plugin manifest (name/version/description/hooks)
__init__.py               # register(ctx) -> /reqogniloom command + pre_llm_call listen hook
reqogniloom_client.py     # stdlib-only MCP client (REST only for GET /api/v1/version/),
                          #   shared by the command and the dashboard
reqogniloom_state.py      # state.json (interview, listen switch, suggestion queue) + lock
_capture.py               # detached worker: one captured message -> one queued suggestion
dashboard/
├── manifest.json          # dashboard tab manifest (icon/position/entry/css/api)
├── plugin_api.py          # FastAPI router, mounted under /api/plugins/reqogniloom/
└── dist/
    ├── index.js            # dashboard tab UI (no build step — plain JS, host-injected React,
    │                         # workspace picker + counters + open-interview rows, all via window.fetch)
    └── style.css
tests/
├── _loader.py               # shared helper to load __init__.py as a package (relative-import support)
├── test_reqogniloom_client.py
├── test_slash_command.py
├── test_listen_mode.py     # listen switch, review queue, hook, capture worker
├── test_suggestion_surface.py  # ADR-019 client surface, review pending, suggestion slash group
└── test_plugin_api.py
```

## Development

```bash
# from the repo root — the plugin tests pin the MCP envelope, tool names and
# both error shapes, plus a guard that every tool name exists in
# docs/agent-templates/tool-manifest.json
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest integrations/hermes-agent-plugin/tests -q
```

```bash
node --check integrations/hermes-agent-plugin/dashboard/dist/index.js
python -m py_compile integrations/hermes-agent-plugin/__init__.py \
    integrations/hermes-agent-plugin/reqogniloom_client.py \
    integrations/hermes-agent-plugin/reqogniloom_state.py \
    integrations/hermes-agent-plugin/_capture.py \
    integrations/hermes-agent-plugin/dashboard/plugin_api.py
```

### Verifying the dashboard tab

`dist/index.js` is an unbuilt IIFE and this repo has no JS test harness for it,
so the tab has no automated coverage of its own. The two checks that do exist,
run from the repo root:

```bash
# syntax of the bundle — nothing more than that
node --check integrations/hermes-agent-plugin/dashboard/dist/index.js

# the server side: every route serves without any credential, and the
# 200 + {"error": …} contract survives a backend failure
pytest integrations/hermes-agent-plugin/tests -q
```

The browser half is a manual check, and it is the only one that exercises the
host. The tab must load straight into the stat cards — no connect form, no
prompt. Then verify the workspace picker, the three counters (Requirements,
Test Cases, Open Interviews) and the open-interview detail rows. If it asks for
a token, a token-handling path has been reintroduced where it does not belong.

## Known gaps (POC scope)

- **Ambient capture → `proposed` artifact (#1156) — wired, M1 path.** The
  capture → proposed → review-before-adoption loop is connected: `/reqogniloom
  accept` creates the captured artifacts via `interview.formalize` under the
  plugin's agent API-key context, so `workflow.services.initial_state_for` seeds
  them as **`proposed`** and they appear in the server-side review queue
  (`review.list_pending`, `ReviewQueueService`), which `/reqogniloom review
  pending` surfaces. Nothing is silently adopted. The `minimal` preset has no
  `proposed` state by design (ADR-019 O3), so there the artifact starts in the
  preset's normal initial state instead; the ADR-019 `artifact_create` adapter
  that would give `minimal` a proposal loop is dormant in the MVP. The existing
  listen mode (`_capture.py`, `tests/test_listen_mode.py`) is left unchanged and
  still only queues suggestions for `/reqogniloom review`.
- One hook, `pre_llm_call`, used only to capture the user's own messages while
  listen mode is on. It returns `None` and injects no context; the interview flow
  itself is still command/dashboard-driven.
- The plugin cannot bind a socket or add middleware (it returns an
  `APIRouter`, not an app), so "default-bind to loopback" is **not**
  implementable from here, and the host contract (`plugin.yaml`,
  `dashboard/manifest.json`) declares no `secrets`/`env`/port field. The
  dashboard tab therefore has no plugin-level credential: it relies on the host
  dashboard's own auth, which is unverifiable from inside the plugin.
- `dist/index.js` issues its own `window.fetch` calls with no credential, rather
  than the host's `SDK.fetchJSON` — that helper has no definition, shim or
  vendored copy in this repo, so its contract is unverifiable.
- Follow-up: a per-workspace artifact drill-in is not built. The tab shows the
  counters and the open-interview detail rows only; there is no `/artifacts`
  endpoint to drill into yet.
- The dashboard tab has a workspace picker and `/reqogniloom stats [workspace_id]`
  takes one, but the hand interview and listen mode still fall back to the first
  visible workspace when none is given.
- Listen mode depends on ReqogniLoom's multi-artifact chat turn, which drives an
  LLM server-side. On an instance whose chat provider is misconfigured the
  capture round fails and is only logged (`capture.log`); the suggestion then
  simply never appears — deliberately not surfaced as a broken turn.
- The proposal shape (`items`, `proposals`, or a bare list) is normalised
  defensively in `_capture.proposal_items` and has not been observed against a
  live *successful* multi-artifact chat turn.
- The whole interview flow — including `interview.chat` (issue #1164) and the
  `interview.propose` readout the ambient path depends on — is driven through
  the MCP server, so there is no separate REST path to keep in sync. Upstream:
  [#1201](https://github.com/Popoboxxo/ReqogniLoom/issues/1201).
- `chat`'s reply field is `reply`, confirmed against the backend contract:
  `InterviewService.generate_chat_turn` returns `{"reply": <str>,
  "state": {...}}` (`backend/application/interview_service.py:1986`) and the
  MCP `interview.chat` tool returns that body unchanged
  (`backend/mcp_server/tools/interview.py:_handle_chat`). The plugin reads
  `result.get("reply") or result.get("message")` (`__init__.py:352`); `reply`
  is the real field, `message` is only a defensive fallback.
