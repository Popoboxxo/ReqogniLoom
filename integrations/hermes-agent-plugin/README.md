# reqogniloom (Hermes Agent plugin — POC)

Drives a ReqogniLoom requirements interview from inside Hermes via a
`/reqogniloom` slash command, plus a minimal read-only dashboard tab
showing a few stats.

**Status: proof of concept.** Built against the plugin contract observed
in [`NousResearch/hermes-agent`](https://github.com/NousResearch/hermes-agent)'s
[`plugins/disk-cleanup`](https://github.com/NousResearch/hermes-agent/tree/main/plugins/disk-cleanup)
(slash command + hooks) and
[`plugins/hermes-achievements`](https://github.com/NousResearch/hermes-agent/tree/main/plugins/hermes-achievements)
(dashboard tab: `manifest.json` + `plugin_api.py` FastAPI router + a
build-step-free `dist/index.js` that takes React/hooks/components from the
host's injected `window.__HERMES_PLUGIN_SDK__` but issues its own
`window.fetch` calls for data, because the host hands the plugin no credential
at all). Not yet verified against a live Hermes install (no local Hermes
instance was available while building this) —
same caveat the old `integrations/hermes-plugin/reqogniloom/` TS port
carried, which is why this POC exists: that earlier port was built against
a different, unverified `@hermes/plugin-sdk` contract (a desktop-IDE-style
`{id, name, register(ctx)}` with `ctx.register({area: "panes"|...})`) that
doesn't match either of the two real reference plugins above. That TS
project is left in place for now (`integrations/hermes-plugin/`) but is
very likely dead code — a follow-up should confirm and remove it once this
plugin is verified against a real Hermes install.

## Install (once verified against a real Hermes install)

```bash
ln -s /path/to/ReqogniLoom/integrations/hermes-agent-plugin ~/.hermes/plugins/reqogniloom
```

## Configuration

Environment variables, read at call time (no persisted config file):

- `REQOGNILOOM_BASE_URL` — default `http://localhost:8001`
- `REQOGNILOOM_API_KEY` — a ReqogniLoom API key (`reqlo_...`), sent as a Bearer token

### Dashboard inbound auth (see "Dashboard tab" below)

- `REQOGNILOOM_DASHBOARD_TOKEN` — **required** by the dashboard API. Expected
  value of the `X-ReqogniLoom-Dashboard-Token` request header. Unset or empty
  rejects *every* request: there is no default token and no dev-mode bypass.
  Must be exported into the environment of the process that runs the Hermes
  dashboard (not into the slash-command shell).
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

The client side of this is the tab itself, not the host SDK: `dist/index.js`
sends `X-ReqogniLoom-Dashboard-Token` on its own `window.fetch` calls, carrying
a token the operator types into the tab at runtime. `SDK.fetchJSON` is
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

All three routes are fail-closed behind the inbound credential described in
"Configuration": a missing, empty or wrong token, a disallowed `Origin`, or an
unconfigured token env var is refused with 401/403 and never reaches
ReqogniLoom. Only genuine `ReqogniLoomError` backend failures keep the older
`200 + {"error": …}` contract. This is an edge gate, not a second tenant-auth
layer: `REQOGNILOOM_API_KEY` remains the tenant credential.

### Using the dashboard tab

**Set up, on the server.** Export `REQOGNILOOM_DASHBOARD_TOKEN` into the
environment of the process that runs the Hermes dashboard, then restart that
process. Unset means *every* request is refused with 403 — there is no default
token and no dev-mode bypass — so a dashboard started without it answers 403 on
every call regardless of what the tab sends.

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
| 403 | `REQOGNILOOM_DASHBOARD_TOKEN is not set` | The server-side guard is unconfigured. | Export it into the dashboard process environment and restart the dashboard. |
| 403 | `origin is not in the dashboard allowlist` / `host is not in the dashboard allowlist` | The page's origin or host is outside the allowlist (default: loopback only). | Add that origin/host to `REQOGNILOOM_DASHBOARD_ALLOWED_ORIGINS` / `REQOGNILOOM_DASHBOARD_ALLOWED_HOSTS` and restart the dashboard. A `*` entry is discarded by the server on purpose, so widening to one is not the fix. |

A 401 also drops the stored token and returns the tab to the connect form; a
403 keeps it, because the value may well be right while the guard is not
configured. Each of these is rendered in the tab as a sentence built from the
status code and the server's own detail — never from the token.

### The host boundary (known limitation)

The credential travels in a custom request header on a same-origin request.
Whether the host forwards arbitrary request headers on
`/api/plugins/<name>/*` is undocumented host behaviour: the plugin cannot
control it and cannot detect it from its own side, and neither `plugin.yaml`
nor `dashboard/manifest.json` declares a `secrets`/`env` field the host could
fill for it. If the header is stripped in transit, the operator sees the 401
"missing … request header" row above, and the fix lies in the host or its
proxy, not in this plugin. (Why a header rather than a cookie: see the
preflight argument in "Configuration".)

## Files

```text
plugin.yaml              # plugin manifest (name/version/description/hooks)
__init__.py               # register(ctx) -> registers the /reqogniloom command
reqogniloom_client.py     # stdlib-only REST client shared by the command and the dashboard
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
└── test_plugin_api.py
```

## Development

```bash
cd tests
python3 -m unittest test_reqogniloom_client.py test_slash_command.py test_plugin_api.py -v
```

```bash
node --check dashboard/dist/index.js
python3 -m py_compile __init__.py reqogniloom_client.py dashboard/plugin_api.py
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
host: with `REQOGNILOOM_DASHBOARD_TOKEN` exported into the dashboard process,
open the tab, **Connect** with that value, see the three stat cards
(Requirements, Test Cases, Open Interviews) plus the ReqogniLoom version
footer, then **Disconnect** and confirm the connect form returns. A 401 on that
first load is the host-boundary case above, not a wrong token.

## Known gaps (POC scope)

- No hooks — purely command/dashboard-driven for now.
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
  gets the 401 "missing … request header" case; see "The host boundary".
- `stats()` and the dashboard tab always resolve to the *first* visible
  workspace unless one is passed explicitly; no workspace picker in the UI.
- `chat`'s reply-field name (`reply` vs `message`) is a best guess from
  `InterviewService.generate_chat_turn`'s response shape — not confirmed
  against a live call.
- Not verified against a real Hermes install (see Status above).
