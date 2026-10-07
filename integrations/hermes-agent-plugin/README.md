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
`/version`, `/stats`, `/workspaces` answered 200; the same routes answer 401
without a credential when the gate is configured). The listen mode and the
opt-in gate in this revision are unit-tested, not yet re-verified live. Built
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
`integrations/hermes-plugin/reqogniloom/` TS port was built against a
different, unverified `@hermes/plugin-sdk` contract (a desktop-IDE-style
`{id, name, register(ctx)}` with `ctx.register({area: "panes"|...})`) that
doesn't match either of the two real reference plugins above — which is why
this POC exists. That TS project is left in place for now
(`integrations/hermes-plugin/`) but is very likely dead code — a follow-up
should confirm and remove it.

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
- `REQOGNILOOM_API_KEY` — a ReqogniLoom API key (`reqlo_...`), sent as a Bearer token

### Dashboard inbound auth (see "Dashboard tab" below)

- `REQOGNILOOM_DASHBOARD_TOKEN` — **optional, opt-in** second factor. When set,
  it is the expected value of the `X-ReqogniLoom-Dashboard-Token` request
  header, and the origin/host allowlists below are enforced alongside it. When
  unset or blank, the gate is inactive and the host dashboard's own auth is the
  only gate: the tab loads without any token. Must be exported into the
  environment of the process that runs the Hermes dashboard (not into the
  slash-command shell).
- `REQOGNILOOM_DASHBOARD_ALLOWED_ORIGINS` — optional comma-separated
  `Origin` allowlist, e.g. `https://dashboard.example,http://localhost:*`.
  Unset means loopback only (`http://localhost:*`, `http://127.0.0.1:*`,
  `http://[::1]:*`); it never widens to `*`, and a `*` entry is discarded
  rather than honoured. An entry naming a port matches that port only — use
  `host:*` for any port.
- `REQOGNILOOM_DASHBOARD_ALLOWED_HOSTS` — optional comma-separated `Host`
  allowlist, same loopback default. Blunts DNS-rebinding, where a rebound name
  reaches `127.0.0.1` while sending an attacker-chosen `Host`.

A custom request header is used instead of a cookie because it forces a CORS
preflight for every cross-origin browser request, so a foreign-origin page can
neither attach the credential silently nor read the response. Cookies are
attached automatically by the browser and are CSRF-able; query parameters leak
into access logs and browser history. The comparison is constant-time
(`secrets.compare_digest`) and the token is never logged or echoed back.

Failing **closed** on an unset token — the previous behaviour — is deliberately
gone: it answered 403 to every request the read-only tab made on any install
that had not exported a secret the host never handed the plugin, and the
operator could not fix that from the browser. The endpoints are unchanged
otherwise: same-origin only, read-only, and fully checked whenever a token *is*
configured.

The client side of this is the tab itself, not the host SDK: `dist/index.js`
sends `X-ReqogniLoom-Dashboard-Token` on its own `window.fetch` calls **once a
token is stored** — it probes `/version` first and only shows the connect form
after a 401, so a workspace with the gate switched off needs no token at all.
`SDK.fetchJSON` is
deliberately unused — it has no definition, shim or vendored copy anywhere in
this repo, so whether it even accepts a `headers` option is unverifiable, and
an option it silently ignored would reproduce exactly the missing-header 401
below. See "Using the dashboard tab".

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
/reqogniloom help                                    Show this text
```

The "current interview" is remembered across command invocations in
`$HERMES_HOME/reqogniloom/state.json` (falls back to `~/.hermes` if
`HERMES_HOME` is unset) — same pattern `disk-cleanup` uses for its own
state file.

## Dashboard tab

Read-only POC: three numbers (requirements, test cases, open interviews)
for the resolved workspace, plus the ReqogniLoom build version. Backend
routes are mounted at `/api/plugins/reqogniloom/` by the Hermes dashboard
(`GET /stats`, `GET /workspaces`, `GET /version`) — see `dashboard/plugin_api.py`.

All three routes sit behind the opt-in inbound credential described in
"Configuration": when `REQOGNILOOM_DASHBOARD_TOKEN` is set, a missing, empty
or wrong token, a disallowed `Origin`, or a disallowed `Host` is refused with
401/403 and never reaches ReqogniLoom; when it is unset the gate is inert and
the host dashboard's own auth is the only gate. Only genuine `ReqogniLoomError`
backend failures keep the older `200 + {"error": …}` contract. This is an edge
gate, not a second tenant-auth layer: `REQOGNILOOM_API_KEY` remains the tenant
credential.

### Using the dashboard tab

**Set up, on the server.** Export `REQOGNILOOM_DASHBOARD_TOKEN` into the
environment of the process that runs the Hermes dashboard, then restart that
process. The gate is opt-in: with the variable unset there is no second factor,
the tab loads without a token, and the host dashboard's own auth is the only
gate. With it set, the value is required and must be typed into the tab exactly
(see "Host contract"). There is no default token and no dev-mode bypass.

**Connect, in the tab.** Open the ReqogniLoom tab, paste that same value into
the token field and press **Connect**. The value must equal the env var value
exactly: surrounding whitespace is trimmed on both sides, everything else is
compared byte for byte and is case-sensitive. The tab holds it in
`sessionStorage` under the key `reqogniloom.dashboard.token` — deliberately not
`localStorage` — so it disappears when the browser session ends and is gone
after a restart, and the operator re-enters it. **Disconnect** clears it
immediately. The value is read at call time and leaves the tab only as the
`X-ReqogniLoom-Dashboard-Token` request header on same-origin
`/api/plugins/reqogniloom/…` requests: never in a URL, never in a log, never
echoed back.

### Reading the failure modes

| Status | Server detail | What it means | What to do |
| --- | --- | --- | --- |
| 401 | `missing X-ReqogniLoom-Dashboard-Token request header` | The request carried no token, so nothing was ever compared — this is *not* a wrong token. | With the tab connected, the host or an intermediate proxy is dropping the custom request header. This is the one case the plugin cannot fix from its own side. |
| 401 | `invalid dashboard credential` | The header arrived, the value did not match. | **Disconnect** and re-enter the env var value. |
| 403 | `REQOGNILOOM_DASHBOARD_TOKEN is not set` | Only an **older** build: the gate is opt-in now, so an unset token means "no second factor", not "reject everything". | Upgrade the plugin; or, if you want the second factor, export the variable into the dashboard process and restart it. |
| 403 | `origin is not in the dashboard allowlist` / `host is not in the dashboard allowlist` | The page's origin or host is outside the allowlist (default: loopback only). | Add that origin/host to `REQOGNILOOM_DASHBOARD_ALLOWED_ORIGINS` / `REQOGNILOOM_DASHBOARD_ALLOWED_HOSTS` and restart the dashboard. A `*` entry is discarded by the server on purpose, so widening to one is not the fix. |

A 401 also drops the stored token and returns the tab to the connect form; a
403 keeps it, because the value may well be right while the guard is not
configured. Each of these is rendered in the tab as a sentence built from the
status code and the server's own detail — never from the token.

### Host contract

For the opt-in second factor to work, the operator and the host each own one
half. Nothing in this plugin can supply either half on its own:

- **The operator sets** `REQOGNILOOM_DASHBOARD_TOKEN` in the environment of the
  process that runs the **Hermes dashboard** — *not* the slash-command shell.
  The plugin is mounted into that process, so that is the only environment it
  can read.
- **The browser tab sends** `X-ReqogniLoom-Dashboard-Token` on its own
  `window.fetch` calls. The server checks the same constant,
  `CREDENTIAL_HEADER` in `dashboard/plugin_api.py`.
- **The host (or any proxy in front of it) must forward** that custom request
  header on same-origin **`/api/plugins/reqogniloom/*`** requests. This is
  documented-host behaviour: the plugin neither controls it nor can detect it
  from its own side, and neither `plugin.yaml` nor `dashboard/manifest.json`
  declares a `secrets`/`env` field the host could fill for it. If the header is
  stripped in transit, the operator sees the 401
  "missing `X-ReqogniLoom-Dashboard-Token` request header" row above, and the
  fix lies in the host or its proxy, not in this plugin.

**Default behaviour.** With `REQOGNILOOM_DASHBOARD_TOKEN` unset the gate is
inert: the tab loads, no token is needed, and the host dashboard's own auth is
the only gate. With it set, the loopback-only `Origin`/`Host` allowlists apply
alongside the exact-value comparison (`secrets.compare_digest`). Either
allowlist can be widened via `REQOGNILOOM_DASHBOARD_ALLOWED_ORIGINS` /
`REQOGNILOOM_DASHBOARD_ALLOWED_HOSTS`, and a `*` entry is discarded rather than
honoured.

(Why a header rather than a cookie: see the preflight argument in
"Configuration".)

## Listen mode ("hear along")

Opt-in, off by default, and it never creates anything by itself:

```text
/reqogniloom listen on [workspace_id]   # capture from now on
/reqogniloom listen status              # on/off, where, when the last capture was
/reqogniloom listen off                 # stay quiet again
/reqogniloom review                     # what ReqogniLoom proposed from your words
/reqogniloom accept <index|all>         # create the artifacts you approve
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

Two deliberate limits: at most one capture every 45 s per install (a chatty
session must not queue an LLM turn per message), and a hard cap of 20 queued
suggestions (oldest dropped first) so the queue cannot grow without bound.
Duplicates are dropped by content hash. Diagnostics go to
`$HERMES_HOME/reqogniloom/capture.log`; the worker writes nothing to stdout and
never fails the turn it was spawned from.

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
Hermes desktop plugin (`integrations/hermes-plugin/reqogniloom/` — the read
panel with its degraded/empty split and the toggle + Review capture gate) plus
the importable skill (`integrations/hermes-skill/reqogniloom/` — the
`memory-query` / `memory-digest` / `memory-ask` / `memory-write` CLI
subcommands). This agent-plugin POC (`integrations/hermes-agent-plugin/`) is
slash-command/dashboard-only and does **not** call the memory surface yet.

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
reqogniloom_client.py     # stdlib-only REST client shared by the command and the dashboard
reqogniloom_state.py      # state.json (interview, listen switch, suggestion queue) + lock
_capture.py               # detached worker: one captured message -> one queued suggestion
dashboard/
├── manifest.json          # dashboard tab manifest (icon/position/entry/css/api)
├── plugin_api.py          # FastAPI router, mounted under /api/plugins/reqogniloom/
└── dist/
    ├── index.js            # dashboard tab UI (no build step — plain JS, host-injected React,
    │                         # runtime token form + stats, all via window.fetch)
    └── style.css
tests/
├── _loader.py               # shared helper to load __init__.py as a package (relative-import support)
├── test_reqogniloom_client.py
├── test_slash_command.py
├── test_listen_mode.py     # listen switch, review queue, hook, capture worker
└── test_plugin_api.py
```

## Development

```bash
cd tests
python3 -m unittest test_reqogniloom_client.py test_slash_command.py test_plugin_api.py test_listen_mode.py -v
```

```bash
node --check dashboard/dist/index.js
python3 -m py_compile __init__.py reqogniloom_client.py reqogniloom_state.py _capture.py dashboard/plugin_api.py
```

### Verifying the dashboard tab

`dist/index.js` is an unbuilt IIFE and this repo has no JS test harness for it,
so the tab has no automated coverage of its own. The two checks that do exist,
run from the repo root:

```bash
# syntax of the bundle — nothing more than that
node --check integrations/hermes-agent-plugin/dashboard/dist/index.js

# the server-side half of the auth contract: header name and exact-value
# comparison, origin/host allowlists, and the 401/403 status/detail pairs
# dist/index.js branches on
pytest integrations/hermes-agent-plugin/tests -q
```

The browser half is a manual check, and it is the only one that exercises the
host. With the gate switched **off** (no `REQOGNILOOM_DASHBOARD_TOKEN` in the
dashboard process) the tab must load straight into the stat cards — no connect
form, no prompt; if it asks for a token instead, the probe-first path or the
server's opt-in gate is broken. With the gate **on**, export the variable into
the dashboard process, open the tab, **Connect** with that value, see the three
stat cards (Requirements, Test Cases, Open Interviews), the workspace picker and
the open-interview table, then **Disconnect** and confirm the connect form
returns. A 401 on that first load is the host-contract case above, not a wrong
token.

## Known gaps (POC scope)

- One hook, `pre_llm_call`, used only to capture the user's own messages while
  listen mode is on. It returns `None` and injects no context; the interview flow
  itself is still command/dashboard-driven.
- The plugin cannot bind a socket or add middleware (it returns an
  `APIRouter`, not an app), so "default-bind to loopback" is **not**
  implementable from here, and the host contract (`plugin.yaml`,
  `dashboard/manifest.json`) declares no `secrets`/`env`/port field. The
  inbound token must be injected by the operator into the dashboard process
  environment, and whether the host preserves it is unverified.
- `dist/index.js` does send `X-ReqogniLoom-Dashboard-Token` itself, from a
  token the operator types into the tab at runtime. The earlier assumption that
  the host's `SDK.fetchJSON` "handles host auth" was wrong: the host injects no
  credential, and `fetchJSON` has no definition, shim or vendored copy in this
  repo. What stays unverifiable is the host side — whether it forwards
  arbitrary request headers on `/api/plugins/<name>/*`. If it does not, the tab
  gets the 401 "missing … request header" case; see "Host contract".
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
- `interview.chat` exists on the REST surface but not among the MCP tools, so the
  ambient path cannot be driven through MCP. The artifact surface stays with MCP
  (220 tools); this plugin owns the interview flow. Upstream:
  [#1201](https://github.com/Popoboxxo/ReqogniLoom/issues/1201).
- `chat`'s reply field is `reply`, confirmed against the backend contract:
  `InterviewService.generate_chat_turn` returns `{"reply": <str>,
  "state": {...}}` (`backend/application/interview_service.py:1986`) and
  `POST /api/v1/interviews/{id}/chat/` returns that body unchanged
  (`backend/rest_api/interview_views.py:382-400`). The plugin reads
  `result.get("reply") or result.get("message")` (`__init__.py:329`); `reply`
  is the real field, `message` is only a defensive fallback.
