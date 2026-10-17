# E2E Testing Notes

Setup, commands, and prerequisites are documented in the main
[README.md](../README.md#end-to-end-tests-playwright). This file covers
things the Playwright suite structurally cannot catch.

## Known Gap: Stale Host / Session Drift

Playwright's `baseURL` (`e2e/playwright.config.ts`) is pinned to
`http://localhost:5173` (or `$FRONTEND_URL`), and every test logs in fresh
at the start of its own run. That setup can never reproduce bugs caused by:

- **Accessing the frontend via a LAN IP instead of `localhost`.** If the dev
  machine's IP is DHCP-assigned, it can change between sessions (e.g. after
  a reconnect or a router lease renewal). A browser tab left open at the old
  IP keeps trying to reach a host that's no longer answering.
- **A tab that predates a backend restart or `docker compose` recreate.**
  Cookies/JWTs issued by a previous backend instance may still look valid to
  the browser tab but no longer match what the current stack expects, or the
  tab may simply be talking to a container that no longer exists.
- **Long-idle sessions.** Playwright runs are short and always start with a
  fresh login; they don't exercise "left the tab open for hours" behavior.

### Symptom

`GET /api/v1/auth/me/` returns `401` in the browser console, but the
request **never shows up in the backend's access log at all**
(`docker compose logs backend | grep auth/me`). That combination — a 401
the frontend clearly received, but the backend never logged — is the
signature of hitting a stale/wrong host rather than an actual auth bug in
the running stack.

### How to check

```bash
# 1. Confirm you're pointed at a host that's actually reachable right now
hostname -I            # or: ip -4 addr show
# Compare against the URL in the browser's address bar.

# 2. Confirm the backend you're hitting is the one you think it is
curl http://<host>:8000/api/v1/version/

# 3. Confirm the request is even reaching the backend
docker compose logs backend --since 30m | grep -E '"(GET|POST) /api/v1/auth'

# 4. Rule out cached/service-worker responses
# DevTools → Application → Service Workers → Unregister, then hard-reload
# (Ctrl+Shift+R / Cmd+Shift+R).
```

If step 3 shows nothing for a request the browser clearly made, the browser
is not talking to this stack — reopen the app at the current, confirmed
address rather than debugging the backend.

## LLM-backed specs (derive-requirements)

Some API-level specs assert on `POST /api/v1/needs/{id}/derive-requirements/`
(`hermes-bugfix-campaign.spec.ts`, `ui-test-campaign.spec.ts`), which calls the
configured LLM provider synchronously.

- **CI** runs the stack with `LLM_PROVIDER=mock`
  (`.github/workflows/playwright.yml`): the call answers in ~0.1 s and the
  specs run with the normal 15 s request budget (`use.actionTimeout`).
- **A local dev stack may use a real provider.** Measured on 2026-10-17 with
  `LLM_PROVIDER=opencode_go` / `mimo-v2.5`: one derive call takes 46-74 s and
  returns real drafts. Playwright's `request` fixture inherits the 15 s
  `actionTimeout`, which surfaced as
  `TimeoutError: apiRequestContext.post: Timeout 15000ms exceeded`
  (issues #1343/#1344/#1345).

The specs therefore probe `GET /api/v1/llm-settings/` first
(`e2e/helpers/llm.ts`): with a non-mock provider they **skip** with an
actionable message instead of failing. To actually exercise the real-provider
path (slower, ~1-2 min per call):

```bash
E2E_REAL_LLM=1 npx playwright test tests/hermes-bugfix-campaign.spec.ts --grep "REQ-128"
```

That grants the request a 180 s budget (aligned with the backend's
`LLM_LONG_RUNNING_TIMEOUT`) and marks the test `slow` (180 s test timeout).
Do not raise the global `actionTimeout` for this: it would hide real hangs in
every other spec.
