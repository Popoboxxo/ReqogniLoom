# reqogniloom (Hermes Agent plugin)

ReqogniLoom inside Hermes, on three surfaces over one client:

- **`/reqogniloom`** — drive one interview by hand, list workspaces, read stats,
  decide server-side suggestions, and manage several ReqogniLoom servers;
- a **dashboard tab** — artifacts and interviews per workspace, a **write** view
  for the artifact/flow operations, a **tool console** over the server's whole
  MCP surface, **server management** (multi-server switching, health, write gate)
  and an **admin** view for the destructive tools;
- an opt-in **listen mode** — while it is on, your messages are captured into a
  type-less multi-artifact interview and whatever ReqogniLoom proposes from them
  is parked as a *suggestion* for `/reqogniloom review`. Nothing is created
  without an explicit `/reqogniloom accept`.

Upstream tracking: [Popoboxxo/ReqogniLoom#1201](https://github.com/Popoboxxo/ReqogniLoom/issues/1201)
(agent-native integration + ambient capture) and
[Popoboxxo/ReqogniLoom#1202](https://github.com/Popoboxxo/ReqogniLoom/issues/1202)
(the live-QA findings this line of work answers — F1 token gate, F2 minimal tab,
F4 MCP surface unused, F5 base-URL default, F6 README drift, F7 host contract).

**Status: verified against one live install, thin by design.** The dashboard
routes were exercised against a running Hermes dashboard
(`/api/plugins/reqogniloom/`: `/version`, `/stats`, `/workspaces` answered 200
through the host dashboard's own auth, which is the only gate). The 1.0 rewrite
adds the tool catalogue, the write gate and multi-server management; the Python
half and the bundle are covered by the tests in `tests/` (see *Development*).

What is new in 1.0, and what is deliberately still a gap, is listed under
*Known gaps* — the short version: every tool the MCP server publishes is
reachable, every call that mutates state passes a confirmation gate, and nothing
is adopted without a human decision.

## Transport

The shared client (`reqogniloom_client.py`) speaks ReqogniLoom's **native MCP
server** for every operation: `POST {base_url}/mcp/` with a JSON-RPC 2.0 frame,
authenticated with the `X-API-Key` header. That is the same tool surface the
rest of the ecosystem uses, so the plugin cannot drift from a second, partial
API. The MCP transport rejects a `Bearer` JWT (`bearer_not_supported`), so the
key must travel as `X-API-Key`. Tool results arrive as MCP content blocks
(`result.content[0].text`, a JSON string) and are decoded by the client;
tool-execution errors arrive as HTTP 200 with `result.isError`.

Two things travel over MCP that are not `tools/call`:

- **`tools/list`** — the live catalogue (`ReqogniLoomClient.tools_list`). The
  dashboard reads it instead of vendoring a tool list, so a tool the server adds
  later is usable without a plugin release.
- **REST, only where no MCP tool exists.** Today that is exactly one call:
  `GET /api/v1/version/` is public, needs no key, and has no MCP counterpart —
  it is also how a server's *reachability* is probed independently of its key.
  Every further exception must be listed under *REST fallbacks (parity gaps)*
  below with its issue reference.

## Install

```bash
ln -s /path/to/ReqogniLoom/integrations/hermes-agent-plugin ~/.hermes/plugins/reqogniloom
```

## Configuration

### Servers (multi-server)

Servers live in `$HERMES_HOME/reqogniloom/servers.json`, mode **0600**, written
under a lock, managed from `/reqogniloom server …` or the tab's *Servers* view:

```json
{
  "registry_version": 1,
  "write_gate": true,
  "active": "qs",
  "servers": [
    {
      "id": "qs",
      "name": "QS 172.20.5.120",
      "base_url": "http://172.20.5.120:8001",
      "api_key": "reqlo_…",              "api_key_source": "file",
      "api_key_env": null,
      "user_api_key": null,              "user_api_key_source": "env",
      "user_api_key_env": "REQOGNILOOM_USER_API_KEY_QS",
      "default_workspace_id": null,
      "last_workspace_id": "b5a8ff85-…",
      "verify": { "reachable": true, "auth_ok": true, "app_version": "1.8.0-beta.21",
                  "tool_count": 248, "checked_at": "2026-10-18T18:00:00Z" }
    }
  ]
}
```

- **Why a file and not environment variables:** a server must be addable while
  the host process runs; the environment of a running process cannot be
  extended, so a var-only scheme would need a gateway restart per server.
- **Keys never leave the backend.** The dashboard API serialises entries with
  `public_server()`, which reports only *whether* a credential resolves and
  *where it comes from* (`file` or `env:NAME`) — never its value.
- **Two keys per server.** `api_key` (agent principal) carries every normal
  call; `user_api_key` (human principal) is used only for the approval-class
  tools, which the server refuses for an agent. Without it those buttons are
  disabled with an explanation instead of failing opaquely.
- **`write_gate`** is the global switch for mutating calls (default: open).
  Reads and computations run regardless.

### Migration from the environment (nothing to do)

An install that only ever set `REQOGNILOOM_BASE_URL` / `REQOGNILOOM_API_KEY`
migrates itself the first time a server is listed or the tab opens: it becomes
the entry `default`, referencing both variables — the key stays in the
environment, nothing is copied into the file. From then on the registry file is
authoritative; environment variables still win for an entry whose
`api_key_source` is `env` (which is what makes key rotation a `.env` edit).

Environment variables, read at call time:

- `REQOGNILOOM_BASE_URL` — default `http://localhost:8001`. An unset variable
  with a transport failure raises `could not reach … — REQOGNILOOM_BASE_URL is
  not set, so the request went to the default …`; an invalid value is rejected at
  construction. With a configured registry this variable is only a migration
  seed.
- `REQOGNILOOM_API_KEY` — the agent key (`reqlo_…`), sent as `X-API-Key`. Never
  sent on the public `GET /api/v1/version/`. A missing key fails fast.
- `REQOGNILOOM_API_KEY_<ID>` / `REQOGNILOOM_USER_API_KEY_<ID>` — per-server keys,
  referenced by `server add`. Keys are never typed on the command line, because
  that puts them into the shell history.

## Slash command

```
/reqogniloom start <artifact_type> [workspace_id]   Start a new interview (workspace_id optional)
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
/reqogniloom server list                             Servers, active marker, key sources, health
/reqogniloom server use <id>                         Switch the active server (the tab shares it)
/reqogniloom server add <id> <base_url>              Add a server (key via REQOGNILOOM_API_KEY_<ID>)
/reqogniloom server test [id]                        Probe reachability, version and key
/reqogniloom server rm <id>                          Remove a server
/reqogniloom help                                    Show this text
```

Every subcommand except `server` runs against the **active** server. The
"current interview" is remembered across command invocations in
`$HERMES_HOME/reqogniloom/state.json` (falls back to `~/.hermes` if
`HERMES_HOME` is unset).

## Dashboard tab

Five views over three backend capabilities:

| View | What it does |
|---|---|
| **Overview** | Counters (requirements, test cases, open interviews, tools on the server) and the open interviews as detail rows — a count answers "how many", never "which". |
| **Write** | Create any artifact type, link two artifacts, decide the review queue, stage a memory fact, drive an interview, snapshot a baseline. |
| **Tools** | The whole MCP catalogue of the active server: search, group filter, class and risk badges, one form per tool, result panel. |
| **Servers** | Registry CRUD, one-click health probe, active switch, write-gate toggle. |
| **Admin** | Every destructive tool of the server, each opening in the console. |

Forms are **rendered from the tool's JSON schema**. Nothing about a tool's fields
is hardcoded here, so a tool the server adds later is immediately usable. Only
*declared* parameters are offered: the backend accepts a few undeclared ones
(finding
[#1376](https://github.com/Popoboxxo/ReqogniLoom/issues/1376)) and this UI must
not be the place that starts sending them.

### The write gate

Every call from the tab goes through two backend steps:

1. `POST /write/preview` classifies the call and returns a `confirm_token` bound
   to `server|tool|arguments`, plus the risk class, the validation problems and a
   compact argument summary. **Nothing is executed.**
2. `POST /write` executes it — and refuses when the token no longer matches the
   arguments, when the write gate is closed for a mutating call, when a declared
   parameter is missing or unknown, or when an approval-class tool has no human
   key.

The UI wires this up as: reads and computations run straight through (still with
a token), **mutating** calls open a confirmation panel, and **destructive** calls
additionally require the tool name to be typed. The token is not a security
boundary — the plugin shares the host dashboard's session cookie, and the host's
auth is the only inbound gate — but it lives in the backend, so the confirmation
step cannot be skipped by a UI bug.

### What a write actually creates

Writes run under the plugin's **agent** key, so ReqogniLoom seeds the artifact
into the workflow state **`proposed`** (`workflow.services.initial_state_for`) —
it is never adopted as a final requirement by the plugin. The review queue in the
*Write* view (`review.list_pending`) plus the ADR-019 suggestion inbox
(`suggestion.list`) is where a human decides, and that decision needs the human
key. On a `minimal`-preset workspace there is no `proposed` state by design
(`SCHEMAS_WITHOUT_PROPOSED`), so an artifact starts in the preset's normal
initial state instead.

### Tool classification

MCP puts no `is_write` flag on the wire, so `reqogniloom_tools.py` derives one
from the tool name (`read` / `compute` / `mutate`), with explicit name maps for
the tools whose name lies (e.g. `requirement.acceptance_criteria.check` mutates,
`attribute_migration.plan` does not). The derivation is pinned against the repo's
generated `docs/agent-templates/tool-manifest.json` in **both** directions — no
server write may classify as `read`, no server read as `mutate` — so drift fails
in the test suite instead of silently dropping a confirmation dialog.
`compute` means "runs an LLM or a heavy analysis without changing state"
(`requirement.validate`, `traceability.coverage`, …): a spinner, not a
confirmation.

The `compute` class is the one place such a misclassification could hide — it
drops the confirmation dialog just as `read` does — so every member needs a line
in `COMPUTE_JUSTIFICATIONS` and the test asserts the map covers the set exactly.
Nine tools the manifest calls writes were sitting in `compute` (the
`ai_derivation.*` family, `requirement.decompose`, `requirement.suggest_level`,
`traceability.suggest_links`); they are `mutate` now.

If a server ever publishes the standard MCP `annotations`, those win over the
name heuristics — with one exception: an entry in `MUTATE_EXACT` stands, because a
`readOnlyHint` must not talk a persisting tool out of its dialog. Annotations may
add a mutation signal, never remove an explicit one.

### Destructive calls

`is_destructive()` matches name *segments* (`delete`, `purge`, `destroy`, `wipe`,
`reset`, `drop`), not a `.delete` suffix: `memory.delete_workspace` and
`attribute_definition.delete_workspace` are a GDPR wipe of every memory tier a
workspace owns, and the suffix test let them through with a plain yes/no. Verified
against all 248 manifest tools (12 matches, all hard deletes or resets).

### What a server URL may be

Every request sends the entry's key as `X-API-Key` to that entry's `base_url`, so
the URL is checked the way a credential destination has to be:

- a target in the link-local / cloud-metadata range, or an unspecified address, is
  refused when it is written **and** when it is used (the registry file is
  editable, and the environment can carry a URL too);
- private ranges are allowed on purpose — a ReqogniLoom install on a LAN is the
  normal case here;
- changing the `base_url` of an existing entry **clears its keys**, so a
  re-pointed entry cannot hand the previous host's key to a new one; the response
  says so.

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

Two deliberate limits: at most one capture every 45 s per install, and a hard cap
of 20 queued suggestions (oldest dropped first). Duplicates are dropped by
content hash. Diagnostics go to `$HERMES_HOME/reqogniloom/capture.log`; the
worker writes nothing to stdout and never fails the turn it was spawned from.

## Memory capabilities

ReqogniLoom exposes an AI long-term memory surface over its MCP server. The
plugin reaches it through the tool console (all 14 `memory.*` tools) and a
staged flow in the *Write* view:

| Tool | Direction | What it does |
| --- | --- | --- |
| `memory.query` | read | Semantic search over a `workspace`/`user`/`artifact` scope; returns `entries` plus `degraded`/`detail`. |
| `memory.digest` | read | Prompt-ready summary of a scope (`digest`, `derivation_status`, `derived_count`). |
| `memory.ask` | read | Natural-language answer (`answer`, `degraded`, `detail`). RBAC write-gated on the backend because it drives a generative LLM call, but it mutates nothing. |
| `memory.write` | **write** | Persists one fact (`content`, `scope` ∈ `workspace\|user\|artifact`). Staged in the UI, issued only on an explicit confirm. |

A read that legitimately returns no rows is reported **separately** from a
backend that could not answer: `degraded=true` together with a `detail` cause is
"backend unavailable/degraded", while an empty `entries` list with
`degraded=false` is a genuine "nothing remembered". Clients must not collapse
the two into one empty state.

## REST fallbacks (parity gaps)

The plugin is an MCP client. Every deviation from that is listed here, with its
tracking issue — a REST-only capability is a *backend* backlog item, not a
second client:

| Call | Why | Issue |
|---|---|---|
| `GET /api/v1/version/` | public, no key needed, no MCP counterpart; used both for the footer and as the key-independent reachability probe | [#1362](https://github.com/Popoboxxo/ReqogniLoom/issues/1362) (REST↔MCP coverage is asymmetric in both directions) |

When a write path exists on REST but not as an MCP tool, the tab reaches it
through the same write gate and it is added to this table — the plugin never
grows a parallel REST client.

## Files

```text
plugin.yaml                  # plugin manifest (name/version/description/hooks)
__init__.py                  # register(ctx) -> /reqogniloom (incl. `server` group) + pre_llm_call hook
reqogniloom_client.py        # MCP client (tools/call + tools/list), registry-aware target
                             #   resolution, principal routing; REST only for the version call
reqogniloom_registry.py      # servers.json: CRUD, migration, key resolution, health probes
reqogniloom_tools.py         # tool catalogue (tools/list, cached) + read/compute/mutate
                             #   classification + confirmation tokens + schema validation
reqogniloom_state.py         # state.json (interview, listen switch, suggestion queue) + lock
_capture.py                  # detached worker: one captured message -> one queued suggestion
dashboard/
├── manifest.json            # dashboard tab manifest (icon/position/entry/css/api)
├── plugin_api.py            # FastAPI router: reads, servers, catalogue, write gate
└── dist/
    ├── index.js             # the tab (no build step; five views, schema-driven forms)
    └── style.css
tests/
├── _loader.py                  # load __init__.py as a package (relative imports)
├── conftest.py                 # per-test HERMES_HOME (state + registry isolation)
├── test_reqogniloom_client.py  # MCP envelope, tool names, error shapes
├── test_registry.py            # registry CRUD, migration, credentials, probes
├── test_tools_catalog.py       # classification + the manifest guard
├── test_plugin_api.py          # every route, the write gate, HTTP level
├── test_slash_command.py       # command surface incl. the server group
├── test_listen_mode.py         # listen switch, review queue, capture worker
├── test_suggestion_surface.py  # ADR-019 client surface
└── plugin_ui_smoke.mjs         # renders the bundle against a stub host SDK
```

## Development

```bash
# from the repo root
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest integrations/hermes-agent-plugin/tests -q
python scripts/check_plugin_packages.py

# the bundle: syntax, then a real render against a stub host SDK
node --check integrations/hermes-agent-plugin/dashboard/dist/index.js
node integrations/hermes-agent-plugin/tests/plugin_ui_smoke.mjs
node integrations/hermes-agent-plugin/tests/plugin_ui_flow.mjs

python -m py_compile integrations/hermes-agent-plugin/__init__.py \
    integrations/hermes-agent-plugin/reqogniloom_client.py \
    integrations/hermes-agent-plugin/reqogniloom_registry.py \
    integrations/hermes-agent-plugin/reqogniloom_tools.py \
    integrations/hermes-agent-plugin/reqogniloom_state.py \
    integrations/hermes-agent-plugin/_capture.py \
    integrations/hermes-agent-plugin/dashboard/plugin_api.py
```

`tests/plugin_ui_smoke.mjs` renders the bundle with a stub
`window.__HERMES_PLUGIN_SDK__` and fails on an undefined component, a button
without `data-testid`, a `fetch` during render, or a tool name the server does
not publish. It needs node only; it is not wired into CI (the pipeline is
defined outside this directory) — run it before opening the tab by hand.

`tests/plugin_ui_flow.mjs` goes further: it *runs* the components (hook state,
dependency arrays, event handlers) and asserts the request bodies the tab
produces — that the create flow sends only what the operator stated, that an
untouched optional field is absent rather than empty, and that a tool which
declares no `workspace_id` never receives one. The static smoke test cannot see
inside a component, which is how a defect that made 11 of 12 create flows
unusable survived it.

### Verifying the dashboard tab

The browser half is a manual check and the only one that exercises the host:

1. `GET /api/dashboard/plugins` lists the plugin with `version: 1.0.0` and
   `has_api: true`.
2. Log in; the tab loads straight into the stat cards — no connect form, no
   prompt. If it asks for a token, a token-handling path has been reintroduced
   where it does not belong.
3. *Servers*: add/select a server, watch the health dot and version/tool count;
   toggle the write gate.
4. *Tools*: search, pick a read tool, run it (executes directly), then a mutating
   tool (confirmation panel) and a destructive one (typed confirmation).
5. *Write*: create an artifact and confirm it appears in the review queue.
6. Cross-check one value against an independent source — e.g. the tool count in
   the tab against `tools/list` on that server, or the version against
   `GET /api/v1/version/`. A tab that renders a cached constant is
   indistinguishable from a working one until you compare it.

## Known gaps

- **Per-tool UX is generic.** The curated flows pick *which* tool to open; the
  fields come from the schema. A hand-crafted form for the most-used artifact
  types would be nicer, and is a follow-up.
- **No artifact drill-in.** The *Overview* shows counters; there is no
  `/artifacts` route that lists and opens individual artifacts yet.
- **Ambient capture → `proposed` artifact (#1156) — wired, M1 path.** The
  capture → proposed → review-before-adoption loop is connected:
  `/reqogniloom accept` creates the captured artifacts via `interview.formalize`
  under the plugin's agent API-key context, so `workflow.services.initial_state_for`
  seeds them as **`proposed`**. Nothing is silently adopted.
- One hook, `pre_llm_call`, used only to capture the user's own messages while
  listen mode is on. It returns `None` and injects no context.
- The plugin cannot bind a socket or add middleware (it returns an `APIRouter`,
  not an app), so it cannot add its own inbound auth factor; the host dashboard's
  auth is the gate. `REQOGNILOOM_API_KEY` remains an outbound credential and is
  never a dashboard credential.
- `dist/index.js` issues its own `window.fetch` calls rather than the host's
  `SDK.fetchJSON` — that helper has no definition, shim or vendored copy in this
  repo, so its contract (headers, POST) is unverifiable.
- Listen mode depends on ReqogniLoom's multi-artifact chat turn, which drives an
  LLM server-side. On an instance whose chat provider is misconfigured the
  capture round fails and is only logged (`capture.log`).
- The proposal shape (`items`, `proposals`, or a bare list) is normalised
  defensively in `_capture.proposal_items` and in the review queue.
- `chat`'s reply field is `reply`, confirmed against the backend contract:
  `InterviewService.generate_chat_turn` returns `{"reply": <str>, "state": {...}}`
  (`backend/application/interview_service.py:1986`); `message` is only a
  defensive fallback.
- Background findings the plugin works around rather than fixes: a `workspace_id`
  the server accepts without declaring it
  ([#1376](https://github.com/Popoboxxo/ReqogniLoom/issues/1376)) — the UI offers
  declared parameters only; and `test.mark_reviewed`'s missing workspace fence
  ([#1373](https://github.com/Popoboxxo/ReqogniLoom/issues/1373)) — running it
  from the console on a foreign id can cross workspaces until that is fixed.
