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
build-step-free `dist/index.js` using the host's injected
`window.__HERMES_PLUGIN_SDK__`). Not yet verified against a live Hermes
install (no local Hermes instance was available while building this) —
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

The client side of this is **not** wired up yet: `dist/index.js` still calls
`SDK.fetchJSON` without the header, so the dashboard tab will only work once
the tab sends `X-ReqogniLoom-Dashboard-Token` and the host is configured to
forward it — see "Known gaps".

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

## Files

```text
plugin.yaml              # plugin manifest (name/version/description/hooks)
__init__.py               # register(ctx) -> registers the /reqogniloom command
reqogniloom_client.py     # stdlib-only REST client shared by the command and the dashboard
dashboard/
├── manifest.json          # dashboard tab manifest (icon/position/entry/css/api)
├── plugin_api.py          # FastAPI router, mounted under /api/plugins/reqogniloom/
└── dist/
    ├── index.js            # dashboard tab UI (no build step — plain JS, host-injected React)
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

## Known gaps (POC scope)

- No hooks — purely command/dashboard-driven for now.
- The plugin cannot bind a socket or add middleware (it returns an
  `APIRouter`, not an app), so "default-bind to loopback" is **not**
  implementable from here, and the host contract (`plugin.yaml`,
  `dashboard/manifest.json`) declares no `secrets`/`env`/port field. The
  inbound token must be injected by the operator into the dashboard process
  environment, and whether the host preserves it is unverified.
- `dist/index.js` does not yet send `X-ReqogniLoom-Dashboard-Token`; it still
  relies on the unverified assumption that the host's `SDK.fetchJSON` "handles
  host auth". Until the tab sends the header (and the host forwards it), the
  dashboard tab gets 401/403 by design.
- `stats()` and the dashboard tab always resolve to the *first* visible
  workspace unless one is passed explicitly; no workspace picker in the UI.
- `chat`'s reply-field name (`reply` vs `message`) is a best guess from
  `InterviewService.generate_chat_turn`'s response shape — not confirmed
  against a live call.
- Not verified against a real Hermes install (see Status above).
