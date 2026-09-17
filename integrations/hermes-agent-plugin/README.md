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
- `stats()` and the dashboard tab always resolve to the *first* visible
  workspace unless one is passed explicitly; no workspace picker in the UI.
- `chat`'s reply-field name (`reply` vs `message`) is a best guess from
  `InterviewService.generate_chat_turn`'s response shape — not confirmed
  against a live call.
- Not verified against a real Hermes install (see Status above).
