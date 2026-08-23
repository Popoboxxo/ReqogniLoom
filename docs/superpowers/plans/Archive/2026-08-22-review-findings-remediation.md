# Review Findings Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close every still-open finding from `docs/reviews/DEEP_DIVE_REVIEW_2026-08-22.md` and `docs/reviews/GESAMTTEST_BERICHT_2026-08-21.md` — security/code-hygiene issues, one critical data-reachability bug, WCAG 2.1 AA accessibility violations, and app-wide design-consistency defects.

**Architecture:** No new subsystems. This plan is a remediation sweep across four independent clusters (critical product bug, accessibility, backend/security hygiene, design consistency) that mostly touch disjoint files, sequenced by severity. Each task fixes exactly what its cited finding describes — no incidental refactoring beyond what's needed to close the finding.

**Tech Stack:** Django 4.2+ / DRF (backend), React 18 + TypeScript 5.5+ (frontend), the project's native MCP server, existing CSS token system (`frontend/src/styles/tokens.css`), existing `Dialog` shared primitive.

**Spec:** `docs/reviews/DEEP_DIVE_REVIEW_2026-08-22.md` (backend/security/MCP findings, IDs B/C/D/E-\*) and `docs/reviews/GESAMTTEST_BERICHT_2026-08-21.md` (E2E, accessibility, design findings — consolidated table in §7, plus the §10 follow-up audit). Both are read-only inputs; this plan does not modify them until the final task.

## Global Constraints

- **Already resolved, do not re-plan:** every E2E test-infrastructure finding in `GESAMTTEST_BERICHT_2026-08-21.md` §4.2–4.4 (Gruppen 2–4: title-fill helper, DE/EN locale assertions, `needs-cross-boundary.spec.ts` selector) and the waterkettle fixture staleness in §4.5 were fixed and merged in PR #694 (2026-08-22, issues #687–693). Task 16 of this plan re-verifies §4.1's "Traceability hängt im Ladezustand" finding specifically because its symptom (page stuck loading past a timeout under suite load) matches the root cause PR #694 already fixed for a *different* test (issue #692) — confirm rather than re-investigate from scratch.
- Every finding cited below carries its own file:line evidence from the source review; re-verify the exact line number against current `main` before editing (both reviews are current as of 2026-08-21/22, but lines may have drifted).
- No new dependencies. No new shared primitives unless a task explicitly says to reuse an existing one (`Dialog`, `getAllPages`).
- CSS changes use `frontend/src/styles/tokens.css` custom properties — no hardcoded hex/rgba colors introduced (project convention, CLAUDE.md).
- `data-testid` on every interactive element touched or added (project convention).
- Follow this project's existing REST error-envelope shape (`error_envelope.py`) and MCP `ToolResult` error shape when normalizing error messages — do not invent a new error format.
- Backend test runs: SOLO only, docker one-shot pattern with `DB_APP_PASSWORD=CHANGE-ME-strong-app-password` (not `CHANGE-ME-app-password` — the wrong value corrupts the shared dev Postgres app-role password and breaks the running dev stack; see `.claude` session history 2026-08-22). Check `free -h` before any docker-based test run; this host has a history of severe memory-pressure incidents. Prefer narrow/targeted test runs over full-suite runs.
- Git mutations only via the `git` subagent — never direct commits from an implementer or the main chat.

---

## Phase 1 — Critical Product Bug

### Task 1: Workspace-switcher pagination (data-reachability bug)

**Files:**
- Modify: `frontend/src/context/WorkspaceContext.tsx:225-260` (`reloadWorkspaces`)
- Modify: `frontend/src/api/client.ts` (only if `getAllPages`'s silent 100-page cap needs a visible warning — see step 3)
- Test: `frontend/src/context/WorkspaceContext.test.tsx` (or wherever this context's existing tests live — check first)

**Finding:** `GESAMTTEST_BERICHT_2026-08-21.md` §10.2 (Critical): `WorkspaceContext.tsx:229-230` calls `workspacesApi.list()`, which fetches only page 1 of the paginated `/api/v1/workspaces/` response (`resp.results`, `resp.next` discarded). A tenant with more than one page of workspaces (confirmed reproduction: 28 workspaces, page size 25) can never reach workspace #26+ through the UI — no pagination, no search in the switcher. Deep-Dive companion finding E-1 (`client.ts:514`): the existing `getAllPages` utility this fix should reuse has its own silent truncation at 100 pages with no warning.

- [ ] **Step 1: Confirm current behavior**

Read `frontend/src/context/WorkspaceContext.tsx`'s `reloadWorkspaces` (currently ~line 225-260) in full, and `frontend/src/api/client.ts`'s `getAllPages` (currently ~line 490-520) and `getList` (currently ~line 473-489). Confirm `getAllPages<T extends {id: string}>(path, params?)` already does exactly what's needed: follows `resp.next` across pages, returns the concatenated array. Confirm `workspacesApi.list()` (`frontend/src/api/workspaces.ts:29-31`) currently wraps `getList`, not `getAllPages`.

- [ ] **Step 2: Add a `listAll` method to `workspacesApi`**

```typescript
// frontend/src/api/workspaces.ts — add alongside the existing `list()`
listAll(): Promise<Workspace[]> {
  return getAllPages<Workspace>("/workspaces/");
},
```

- [ ] **Step 3: Fix `getAllPages`'s silent truncation (Deep-Dive E-1)**

In `frontend/src/api/client.ts`, inside `getAllPages`'s `while (nextUrl && pageCount < 100)` loop: when the loop exits because `pageCount` hit 100 while `nextUrl` is still non-null (i.e., more pages exist), `console.warn` with the path and page count, so a truncation is at least visible in the browser console instead of silently returning an incomplete list. Do not change the 100-page cap itself (out of scope — no reported case in this codebase has more than 100 pages of anything).

- [ ] **Step 4: Wire `reloadWorkspaces` to the new method**

In `WorkspaceContext.tsx`, replace `const resp = await workspacesApi.list();` / `const list = (resp.results ?? []).map(normalizePreset);` with a call to `workspacesApi.listAll()` mapped through `normalizePreset`, preserving every other line of `reloadWorkspaces`'s existing logic (stored-ID restoration, selection fallback) untouched.

- [ ] **Step 5: Add a regression test**

Add a test to this context's test file asserting that when the mocked `workspacesApi` (or underlying `apiClient.get`) returns a 2-page paginated response (e.g. page 1 with `next` set, page 2 with `next: null`), `reloadWorkspaces` results in `workspaces` containing entries from *both* pages — the exact regression this bug describes. Match the existing test file's mock style.

- [ ] **Step 6: Run the test, verify it passes**

Run the specific test file only (`npx vitest run <path>`), not the full suite.

- [ ] **Step 7: Commit** (via git subagent)

```
fix: fetch all pages of the workspace list, not just page 1

Workspaces beyond the first page (25 entries) were unreachable via the
UI switcher — no pagination, no search. Reuses the existing getAllPages
helper, which now also warns on its own silent 100-page truncation cap.
```

---

## Phase 2 — Accessibility: Blocker + Critical (WCAG A)

### Task 2: WorkflowEditor canvas is fully keyboard-unreachable

**Files:**
- Modify: `frontend/src/components/WorkflowEditor/StateNode.tsx` (~line 59-90, the outer `role="button"` div)
- Modify: `frontend/src/components/WorkflowEditor/TransitionEdge.tsx` (~line 86-90, the `role="button"` element)
- Test: whichever existing test file covers these components (check `frontend/src/test/` and `frontend/src/components/WorkflowEditor/` for `*.test.tsx`)

**Finding:** `GESAMTTEST_BERICHT_2026-08-21.md` §10.1 (Blocker, WCAG 2.1.1, "der schwerste Einzelfund des gesamten Gesamttests"): both `StateNode.tsx` and `TransitionEdge.tsx` mark their root element `role="button" tabIndex={0}`/`{-1}` but attach only `onDoubleClick` (StateNode) or a click handler (TransitionEdge) — no `onKeyDown`. A keyboard-only user can tab to a state node or transition edge but has no way to activate it. Live-verified via focus + Enter/Space by the audit agent.

- [ ] **Step 1: Read both components' current click/interaction logic in full**

`StateNode.tsx`'s outer div currently (confirmed 2026-08-22): `role="button" tabIndex={0}` at lines 63-64, `onDoubleClick` only, no `onClick`, no `onKeyDown` (the `onKeyDown` at ~line 127 belongs to a *different*, nested inline-edit input — leave that one alone). `TransitionEdge.tsx`'s `role="button" tabIndex={-1}` element at ~lines 86-87 — read its surrounding JSX to find what click handler (if any) it currently has.

- [ ] **Step 2: Add keyboard activation to `StateNode.tsx`**

Add an `onKeyDown` handler on the same div that has `role="button"`, that triggers the same action as `onDoubleClick` when `e.key === "Enter" || e.key === " "` (call `e.preventDefault()` for the space key to stop page scroll, matching the pattern already used in `WorkspaceCard.tsx:67`: `onKeyDown={(e) => e.key === "Enter" && onSelect(workspace)}` — extend that pattern to also handle space, since this node's primary action is edit-open which conventionally responds to both keys):

```typescript
onKeyDown={
  editMode
    ? (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          e.stopPropagation();
          setDraft(state.name);
          // ...whatever setEditing(true)-equivalent the existing
          // onDoubleClick handler does — mirror it exactly, don't
          // duplicate divergent logic.
        }
      }
    : undefined
}
```
Mirror whatever the real `onDoubleClick` body does exactly (read it first — the snippet above assumes it opens the rename-editing state; adjust to match reality, do not guess).

- [ ] **Step 3: Add keyboard activation to `TransitionEdge.tsx`**

Same pattern: read the element's real click handler, add an equivalent `onKeyDown` for Enter/Space with `preventDefault()`.

- [ ] **Step 4: Add/extend a11y regression test**

Add a test (RTL `fireEvent.keyDown` or `userEvent.keyboard`) asserting that focusing the state-node/transition-edge element and pressing Enter (and Space) triggers the same state change as the existing double-click/click test already asserts. If an existing test already covers the click path, add the keyboard-equivalent case right next to it in the same `describe` block.

- [ ] **Step 5: Run the test file, verify it passes**

- [ ] **Step 6: Commit**

```
fix: make WorkflowEditor canvas keyboard-accessible

StateNode and TransitionEdge declared role="button" but had no
onKeyDown handler, making the entire workflow editor canvas
unreachable for keyboard-only users (WCAG 2.1.1 A).
```

### Task 3: Missing form labels (5 fields, WCAG A)

**Files:**
- Modify: `frontend/src/components/GlossaryView/GlossaryView.tsx` (the `create-link` dialog, 4 fields)
- Modify: `frontend/src/components/.../CreateWorkspaceModal.tsx` (`workspace-name-input` — find via `grep -rln "CreateWorkspaceModal"`)
- Modify: whichever component renders `custom-field-type-select` (Settings) and `backup-type-select` (System Settings) — find via `grep -rn "custom-field-type-select\|backup-type-select" frontend/src`
- Modify: `frontend/src/components/WorkflowEditor/TransitionDialog.tsx` ("Von" field)
- Test: existing test files for each touched component, or new tests if none cover label presence

**Finding:** `GESAMTTEST_BERICHT_2026-08-21.md` §5 Critical findings 1-3, and §10.1's TransitionDialog addition: 3 form fields in the Glossary link-create dialog, the workspace-create name input, 2 `<select>` elements (custom-field-type, backup-type), and the WorkflowEditor `TransitionDialog`'s "Von" field all lack an accessible name (WCAG 4.1.2 / 3.3.2).

- [ ] **Step 1: Locate every field and its current markup**

For each of the 6 fields (4 in Glossary + workspace-name + custom-field-type-select + backup-type-select + TransitionDialog "Von"), grep for its `data-testid` to find the exact JSX. Confirm none currently has a `<label htmlFor>`, `aria-label`, or `aria-labelledby`.

- [ ] **Step 2: Add a native `<label htmlFor="...">` per field**

For each field, add (or wrap in) a `<label htmlFor={<the input's id>}>` with the field's existing visible text (placeholder text or a nearby heading) as the label content — reuse copy that's already in the DOM where possible rather than inventing new i18n strings; only add a new i18n key (DE/EN) if no suitable existing text exists nearby. Ensure the input actually has a matching `id` attribute (add one if missing, scoped uniquely — check it doesn't collide if the dialog can render multiple instances).

- [ ] **Step 3: Add tests**

For each touched component's existing test file, add an assertion that the field is queryable via its accessible name (`screen.getByLabelText(...)`) — this is the correct regression test for "First Rule of ARIA" fixes, since a passing `getByLabelText` query is direct proof the label association works.

- [ ] **Step 4: Run the touched test files, verify they pass**

- [ ] **Step 5: Commit**

```
fix: add missing form labels across 6 fields (WCAG 4.1.2)

Glossary link-create dialog (4 fields), workspace-create name input,
custom-field-type-select, backup-type-select, and WorkflowEditor
TransitionDialog's "Von" field had no accessible name.
```

---

## Phase 3 — Backend / Security Hygiene

### Task 4: Remove dead, broken `persistence/managers.py`

**Files:**
- Delete: `backend/persistence/managers.py`
- Modify: `backend/persistence/models.py` (docstring at ~line 980 claiming `get_with_level()` exists)
- Modify: `backend/rest_api/serializers.py` (docstring at ~line 681, same claim)
- Modify: `backend/rest_api/views.py` (docstring at ~line 3753, same claim)
- Test: none needed (removing genuinely-unreachable dead code); add a short regression grep-test only if this codebase already has a "no dead-import modules" convention test (check `rest_api/tests/test_architecture.py` for anything resembling this pattern first)

**Finding:** `DEEP_DIVE_REVIEW_2026-08-22.md` B-1 (🔴): `managers.py:18` imports `from persistence.base import TenantManager` — `persistence/base.py` does not exist (`TenantManager` actually lives in `persistence/tenancy.py:117`), so the module cannot be imported at all. It also has a second, independent bug (`get_with_level()`'s `OuterRef` passed as a raw SQL param, which would fail at execution time even if the import worked). `ArchitectureElement` never uses this manager (`models.py` uses the plain `TenantManager`); `ArchitectureElementManager` has zero import sites repo-wide. Four other files' docstrings claim this manager is wired up and usable.

- [ ] **Step 1: Confirm dead-ness**

`grep -rn "ArchitectureElementManager\|from persistence.managers\|persistence\.managers" backend/ --include=*.py` — confirm the only hit is the file's own definition (i.e., genuinely zero external references). `grep -rn "get_with_level" backend/` — read every hit; the plan's assumption (per the Deep-Dive review) is that all of them are either the dead module itself or documentation claiming it exists, never a real call site. Verify this before deleting — if a real call site exists, STOP and report back to the plan owner (a ruling is needed, not a delete).

- [ ] **Step 2: Delete the module**

`rm backend/persistence/managers.py` (or the plan-writer's alternative, "repair" — the Deep-Dive review offers both options; deletion is the lower-risk choice since step 1 confirms zero real callers, and repairing a manager nobody uses just to keep dead code alive has no benefit).

- [ ] **Step 3: Fix the 3 misleading docstrings**

In `models.py` (~line 980), `serializers.py` (~line 681), `views.py` (~line 3753): remove or correct the specific sentence(s) claiming `get_with_level()`/`ArchitectureElementManager` is available — read each docstring's full surrounding paragraph first so the fix reads coherently, not just a deleted clause leaving a dangling sentence.

- [ ] **Step 4: Run a narrow backend check**

Confirm the app still imports cleanly: `python -c "import django; django.setup(); import persistence.models, rest_api.serializers, rest_api.views"` inside the docker one-shot pattern (SOLO, correct `DB_APP_PASSWORD`), or a narrower `pytest --collect-only` on `rest_api/tests/` if that's cheaper. Do not run the full backend suite for this change alone.

- [ ] **Step 5: Commit**

```
fix: remove dead, unimportable persistence/managers.py

The module's only import target (persistence.base.TenantManager)
doesn't exist, and its CTE query had a second, independent bug
(OuterRef passed as a raw SQL param). Never wired to any model;
zero external references. Also corrects 3 docstrings elsewhere
that claimed this manager was available.
```

### Task 5: Stop leaking raw exception text to clients (REST + MCP)

**Files:**
- Modify: `backend/rest_api/diagram_canvas_views.py` (lines ~188, 267, 345, 406, 484, 545)
- Modify: `backend/rest_api/audit_views.py` (line ~241)
- Modify: `backend/rest_api/diagram_views.py` (lines ~148, 221, 251)
- Modify: `backend/mcp_server/tool_registry.py` (lines ~748-750, `_validate_api_key`'s `except Exception` branch)
- Test: extend or add tests asserting the client-facing message is generic while the log still captures the real exception

**Finding:** `DEEP_DIVE_REVIEW_2026-08-22.md` C-1 (🟠) and D-3 (🟡): multiple REST views build their 500-response body with `str(exc)` (raw exception text — CWE-209, can leak DB error details, file paths, library internals), while the MCP layer already deliberately masks this (`tool_registry.py:706`, "An internal error occurred."). D-3 is the same class of leak, specifically in the auth-failure path where it's worse (leaks under `AUTH_FAILED`, exposing infra details to an unauthenticated-or-wrongly-authenticated caller).

- [ ] **Step 1: Confirm every cited call site**

Read each file:line from the finding. For each, confirm the pattern is `build_error_response("INTERNAL_SERVER_ERROR", lang, message=str(exc))` (REST) or `str(exc)` interpolated into an MCP `AUTH_FAILED` error (`tool_registry.py`). Note whether `logger.exception(...)` (or equivalent) already runs before the client response is built — the finding says it does everywhere; confirm rather than assume, since the fix must preserve that logging.

- [ ] **Step 2: Replace client-facing message with a generic one, REST**

For every REST call site: keep the existing `logger.exception(...)` call (or add one if genuinely missing at a specific site — flag this as a deviation if found, since the review states logging is already present everywhere it audited). Change `message=str(exc)` to a generic, already-localized string matching this codebase's existing i18n pattern for error messages (check `error_envelope.py` / `build_error_response`'s other call sites for the exact convention — e.g. a `common.internalError` key or similar) — do not hardcode English.

- [ ] **Step 3: Replace client-facing message with a generic one, MCP**

In `tool_registry.py`'s `_validate_api_key` except-Exception branch (~line 748-750): mirror the exact masking pattern already used at `tool_registry.py:706` ("An internal error occurred.") — reuse the same string/constant if one exists rather than introducing a second, slightly-different generic message.

- [ ] **Step 4: Add regression tests**

For at least 2-3 of the REST call sites and the MCP one: a test that forces the exception path (mock/monkeypatch the underlying call to raise) and asserts the response body does NOT contain the raw exception's `str()` representation, while a separate assertion (via `caplog`/log capture) confirms the real exception text WAS logged. This is the correct regression shape — proving both halves (safe to client, visible to operators) rather than just one.

- [ ] **Step 5: Run the touched test files only**

- [ ] **Step 6: Commit**

```
fix: stop leaking raw exception text to REST/MCP clients

9 REST call sites and 1 MCP auth-failure path returned str(exc)
directly in the response body (CWE-209) — internal DB/library error
details, paths, or stack fragments could reach the client. All now
return a generic message; the real exception is still logged.
```

### Task 6: Restrict MCP `params.api_key` to stdio transport only

**Files:**
- Modify: `backend/mcp_server/protocol_handler.py` (key-extraction priority list, ~line 250-267)
- Test: `backend/mcp_server/tests/` — extend whichever test covers key-extraction precedence

**Finding:** `DEEP_DIVE_REVIEW_2026-08-22.md` D-1 (🟠): the JSON-RPC `params.api_key` field is accepted as a valid key source for *all* transports, while the query-parameter fallback is explicitly rejected for the same reason (keys land in logs/proxies/tracing — REQ-018 / SYSTEM_AUDIT P-05). `clean_params` strips the key before dispatch but doesn't stop it from being logged on the way in. The policy is applied inconsistently.

- [ ] **Step 1: Read the current key-extraction logic in full**

`protocol_handler.py`'s key-extraction function (~line 250-267): identify how it currently knows which transport a request arrived on (stdio vs HTTP vs SSE) — this information must already be threaded through somewhere for the fix to distinguish transports; find that signal before writing the conditional.

- [ ] **Step 2: Gate `params.api_key` on stdio only**

Change the priority-3 branch so `params.api_key` is only consulted when the request's transport is stdio; for HTTP/SSE, skip straight to whatever the next-lower-priority (header-only) source is, and if none is present, fail the same way a genuinely-missing key already fails (do not invent a new error code).

- [ ] **Step 3: Add a regression test**

A test asserting: (a) stdio transport + `params.api_key` present + no header → key IS extracted (existing behavior preserved for the one transport that legitimately needs it); (b) HTTP/SSE transport + `params.api_key` present + no header → key extraction FAILS the same way a missing key does (new, correct behavior).

- [ ] **Step 4: Run the touched test file**

- [ ] **Step 5: Commit**

```
fix: restrict MCP params.api_key acceptance to stdio transport

HTTP/SSE clients could pass the API key in the JSON-RPC body, which
the project's own audit policy already treats as a logging-exposure
risk equivalent to query-string keys (REQ-018) — but only rejected
the query-string form. stdio has no header mechanism, so it keeps
this path; HTTP/SSE now require the Authorization header.
```

### Task 7: Preset-gate fail-open logging + CORS fallback fix

**Files:**
- Modify: `backend/mcp_server/tool_registry.py` (~line 910-913, preset-gate fail-open branch)
- Modify: `backend/mcp_server/views.py` (~line 116-119, CORS origin-mirroring fallback)
- Test: extend existing tests covering these two code paths

**Finding A (D-2, 🟡):** preset-lookup failures fail-open (the call is allowed) with only a `logger.debug` — silent, and a DB hiccup could silently re-enable gated features (cost implication for LLM-gated tools). **Finding B (D-4, 🟡):** when the request's Origin isn't on the CORS allowlist, the code still sets `Access-Control-Allow-Origin` to the *first* configured allowlist origin instead of omitting the header — semantically wrong (not directly exploitable, since credentialed reads are still blocked by the origin mismatch, but misleading metadata).

- [ ] **Step 1: Preset-gate — raise the log level, don't change the fail-open decision**

Read `tool_registry.py:910-913`. The review's recommendation is logging visibility, not necessarily flipping to fail-closed (that's a judgment call the review itself leaves open — "mindestens sollte der Fail-open geloggt werden"). Change `logger.debug` to `logger.warning` (or this codebase's equivalent "this needs operator attention" level — check what level nearby fail-open/fail-closed decisions elsewhere in this file use for consistency) so a preset-lookup failure is visible in normal log-monitoring, not just debug-mode. Do not change the fail-open behavior itself in this task — that would be a policy change beyond what this finding asks for.

- [ ] **Step 2: CORS fallback — omit the header instead of mirroring the wrong origin**

Read `views.py:116-119`. When the request Origin is not in the allowlist, remove the branch that sets `Access-Control-Allow-Origin` to the first allowlist entry; simply don't set the header at all for that response (matching standard CORS-allowlist-miss behavior).

- [ ] **Step 3: Add regression tests**

For the preset-gate: a test asserting a forced preset-lookup failure results in the call being allowed (existing behavior — do not break this) AND a warning-level log line being emitted (new assertion, via `caplog`). For CORS: a test asserting a non-allowlisted Origin produces a response with no `Access-Control-Allow-Origin` header at all (currently it would contain the first allowlist entry — assert its *absence* now).

- [ ] **Step 4: Run the touched test files**

- [ ] **Step 5: Commit**

```
fix: log preset-gate fail-open at warning level; stop CORS origin-mirroring

A preset-lookup failure silently allowed the call through at debug
log level only — raised to warning so it's operator-visible. CORS
now omits Access-Control-Allow-Origin entirely for non-allowlisted
origins instead of echoing the first configured allowlist entry.
```

### Task 8: Minor backend/frontend hygiene batch

**Files:**
- Modify: `backend/rest_api/diagram_canvas_views.py:43`, `backend/rest_api/diagram_views.py:49`, `backend/rest_api/icd_views.py:51` (C-2: direct `persistence.models` imports)
- Modify: `backend/auth_tenancy/services/authentication.py:245` (B-2: clarify the no-op self-compare)
- Modify: `backend/mcp_server/views.py:487` (D-5a: non-constant-time compare)
- Modify: `backend/mcp_server/sse_pubsub.py:94-95` (D-5b: silent Redis failure on session-key store)
- Modify: `backend/mcp_server/views.py:59-62, 403-420` (D-6: executor threads, no `close_old_connections`)
- Modify: `backend/mcp_server/views.py:260` (D-7a: stdio label on HTTP transport advertisement)
- Modify: `backend/mcp_server/protocol_handler.py:512` (D-7b: redundant `import json`)
- Modify: `frontend/src/api/client.ts:43-55, 225-227` (E-2: dead legacy in-memory bearer path)
- Test: only where an existing test would need updating because of a behavior change (D-5a, D-5b, D-6) — C-2, B-2, D-7, E-2 are pure cleanup, no new test required.

This task batches several small, independent, low-risk fixes explicitly called out as low-severity (🟡/⚪) in the Deep-Dive review, since none individually warrants its own review cycle.

- [ ] **Step 1 (C-2, convention only, no security impact):** In the 3 REST view files, replace the direct `persistence.models.Tenant`/`User` query with a call through the appropriate existing application-layer service (check `application/` for an existing `get_tenant`/`get_user`-shaped method first; only add a new thin service method if genuinely none exists — do not invent new service classes for this).

- [ ] **Step 2 (B-2, clarity only):** In `authentication.py:245`, either remove the no-op `hmac.compare_digest(computed_hash, computed_hash)` self-compare entirely (the review confirms the real lookup happens via the hash index and the real compare at line 249 already exists — this line does nothing but is misleadingly commented as if it were a timing-safety measure) or correct its comment to state plainly it's intentionally a padding no-op. Prefer removal — dead code that reads as a security control is worse than no code.

- [ ] **Step 3 (D-5a):** In `views.py:487`, change `bound_key == api_key` to `hmac.compare_digest(bound_key, api_key)`, matching this codebase's constant-time-compare convention used elsewhere for key comparisons.

- [ ] **Step 4 (D-5b):** In `sse_pubsub.py:94-95`, `store_session_api_key`'s Redis-failure path currently swallows the error (with a warn log) and returns a session ID that will inevitably hit `SESSION_EXPIRED`. Change it to raise/fail session creation instead, so the caller gets an immediate, honest error rather than a session ID that's already dead.

- [ ] **Step 5 (D-6):** In `views.py`'s bound `ThreadPoolExecutor` request-processing path (~403-420), call `django.db.close_old_connections()` at the start (and/or end) of the per-request work function, matching Django's per-request connection-hygiene convention that the framework normally applies via request signals — these pool threads bypass that.

- [ ] **Step 6 (D-7a/b, trivial):** `views.py:260` — don't advertise `"stdio"` as a transport on the HTTP `GET /mcp/` discovery response. `protocol_handler.py:512` — remove the redundant inner `import json` (already imported at module scope).

- [ ] **Step 7 (E-2):** In `frontend/src/api/client.ts:43-55, 225-227`, confirm (grep) the in-memory `_token` bearer path genuinely has zero callers in the SPA flow (the review states this), then delete it — dead code that implies two parallel auth mechanisms is a real confusion risk for the next reader, per the review's own reasoning.

- [ ] **Step 8:** Add/update tests only for steps 3-5 (behavior changes); run the touched files.

- [ ] **Step 9: Commit**

```
chore: backend/frontend hygiene batch (ORM imports, dead code, timing-safe compares)

Bundles several small, independently low-risk fixes from the deep-dive
review: route 3 REST views through the application-service layer
instead of direct model queries, remove a no-op timing-padding compare,
switch an SSE session-key compare to constant-time, fail session
creation instead of silently returning a doomed session ID on a Redis
write failure, add connection hygiene to the bound executor's request
path, drop a stray stdio-transport label and a redundant import, and
delete a dead legacy in-memory bearer-token path in the frontend client.
```

### Task 9: Login response body token removal (deferred flag, not a fix)

**Files:** none modified in this task — this is a documentation/tracking step only.

**Finding:** `DEEP_DIVE_REVIEW_2026-08-22.md` C-3 (🟡): `auth_views.py:188-201` still returns the bearer token in the login response body, documented as intentional backward-compat for E2E/tooling; the SPA itself ignores it (uses the httpOnly cookie). The review's own recommendation is "langfristig entfernen oder per Flag deaktivierbar machen" — a longer-term, higher-blast-radius change (breaks any external tool/script currently relying on the body token) that needs its own decision, not a drive-by fix bundled into this remediation sweep.

- [ ] **Step 1:** File a GitHub issue (via the `feedback` agent or `gh issue create` through the `git` subagent) titled something like "Deprecate bearer-token-in-login-response-body (XSS re-exposure risk if ever consumed by JS)", body citing `DEEP_DIVE_REVIEW_2026-08-22.md` C-3 verbatim, labeled for future triage — not closed by this plan. Reference the issue number in this plan's ledger when done.

---

## Phase 4 — Accessibility (Serious) + Design Consistency

### Task 10: Sitewide contrast fixes (build version, preset badge, text-muted)

**Files:**
- Modify: `frontend/src/components/NavigationShell/SidebarNavigation.module.css` (`.buildVersion` ~line 567-570, `.presetBadge` ~line 411-419)
- Modify: `frontend/src/styles/tokens.css` (if `--color-text-muted` itself needs adjustment for Bauhaus/Sepia — check first, see step 3)
- Test: this project's existing a11y/contrast test tooling if one exists (check `frontend/src/test/` for a contrast-ratio test pattern before writing a new one from scratch)

**Finding:** `GESAMTTEST_BERICHT_2026-08-21.md` §5 findings 4-5 and §10.1's confirmation: `.buildVersion` fails contrast in **all 5 themes** (1.69:1–3.80:1, needs 4.5:1) — root cause is `color: var(--color-text-muted); opacity: 0.7;` compounding an already-muted color with reduced opacity. `.presetBadge` fails at 2.06:1 (`color: var(--color-primary)` on a semi-transparent `rgba(79, 110, 247, 0.2)` background — actual contrast depends on the composited background per theme). Bauhaus/Sepia additionally fail on `--color-text-muted`-on-surface generally (4.21:1, 3.80:1), not just in this one component — a token-level issue for those two themes specifically.

- [ ] **Step 1: Measure current computed contrast per theme**

For `.buildVersion` and `.presetBadge`, and for `--color-text-muted` against `--color-surface` in the Bauhaus and Sepia theme definitions specifically (check `frontend/src/styles/tokens.css` or wherever per-theme token overrides live — likely a `[data-theme="bauhaus"]`/`[data-theme="sepia"]` block), compute the actual composited colors (accounting for `rgba` backgrounds and `opacity`) and their WCAG contrast ratios against `--color-text-muted`'s reference background in each of the 5 themes. Use the same methodology the audit used (axe-core / a manual contrast calculator) — the review's numbers are the ground truth to match against, not to re-derive from scratch, but confirm current values haven't drifted since 2026-08-21.

- [ ] **Step 2: Fix `.buildVersion`**

Remove the `opacity: 0.7` (the primary contributor — an already-muted-toned color losing another 30% opacity is the direct cause of the 1.69:1 floor) OR, if the opacity is load-bearing for a visual "de-emphasized" effect the design wants to keep, swap to a token whose contrast ratio against the actual background already clears 4.5:1 at full opacity, then reintroduce a smaller opacity reduction if needed and re-measure. Prefer the simplest fix (drop the opacity) unless it visibly breaks the intended de-emphasis, in which case document the tradeoff in a code comment.

- [ ] **Step 3: Fix `.presetBadge`**

Increase the background `rgba` alpha and/or adjust `--color-primary`'s badge-specific rendering so the composited badge background against `--color-primary` text clears 4.5:1 in every theme — this likely needs a per-theme check since `--color-primary` itself varies by theme. If a single alpha value can't satisfy all 5 themes simultaneously, consider a dedicated `--color-badge-bg`/`--color-badge-text` token pair (defined per-theme in `tokens.css`) instead of deriving the badge's colors ad hoc from `--color-primary` — but only introduce a new token pair if the single-alpha approach genuinely can't work; check first.

- [ ] **Step 4: Fix Bauhaus/Sepia `--color-text-muted`**

For these two themes specifically, adjust the theme's `--color-text-muted` value (in its `tokens.css` override block) until it clears 4.5:1 against `--color-surface` in that theme — verify this doesn't regress the other 3 themes (Light/Dark/Nordic aren't reported as failing, so their token values should stay untouched; confirm the fix is scoped to the 2 failing theme blocks only).

- [ ] **Step 5: Re-measure all 5 themes**

Recompute contrast for all 3 fixed items (`.buildVersion`, `.presetBadge`, `--color-text-muted`-on-surface) across all 5 themes, confirm every one now clears 4.5:1.

- [ ] **Step 6: Add a regression test if this codebase has contrast-testing infrastructure**

Check `e2e/a11y-followup.js` (referenced as uncommitted in the review — confirm whether it or a committed equivalent exists now) or any `frontend/src/test/*contrast*` file. If real automated contrast testing exists anywhere in this repo, extend it to cover these 2 components across all 5 themes so this can't silently regress per-theme again. If no such infrastructure exists, note this as a gap in the commit message rather than inventing a new test harness from scratch (out of scope for this task).

- [ ] **Step 7: Commit**

```
fix: sitewide contrast failures in .buildVersion, .presetBadge, and Bauhaus/Sepia text-muted

.buildVersion failed WCAG AA contrast (1.69-3.80:1 vs required 4.5:1)
in all 5 themes, mainly from a redundant opacity reduction on an
already-muted color token. .presetBadge failed at 2.06:1. Bauhaus and
Sepia additionally had a theme-level --color-text-muted contrast gap
against --color-surface, independent of these two components.
```

### Task 11: Nested interactive elements + roleless aria-label spans

**Files:**
- Modify: `frontend/src/components/DashboardViews/WorkspaceCard.tsx` (~line 60-135, nested `<button>` inside `role="button"` div)
- Modify: whichever component renders `/metrics`' `metric-status-*` spans (find via `grep -rn "metric-status-" frontend/src`)
- Test: existing tests for both components

**Finding:** `GESAMTTEST_BERICHT_2026-08-21.md` §5 findings 6-7: `WorkspaceCard.tsx` wraps a real `<button>` (confirmed at ~line 131) inside an outer `role="button"` div (~line 61-67) — nested interactive elements are an accessibility-tree violation (a screen reader announces "button" then, inside it, another "button", which is semantically invalid and behaviorally confusing for activation). Separately, `/metrics` has 5 `metric-status-*` `<span>` elements carrying `aria-label` with no `role` — `aria-label` on a roleless element is not reliably exposed by all screen readers.

- [ ] **Step 1: Read `WorkspaceCard.tsx`'s outer div and the nested button in full**

Confirm what the inner `<button>` (~line 131) does — likely a secondary action (e.g. a per-card menu/delete/settings trigger) distinct from the card's primary `onClick={() => onSelect(workspace)}`.

- [ ] **Step 2: Restructure to avoid nesting**

The standard fix for "primary card click + secondary inline action" is: make the outer container a plain `<div>` (drop `role="button"`/`tabIndex`/the card-level `onClick`/`onKeyDown`), and instead make the *specific clickable region* (e.g. the card's title/main content area, not the whole card) the real interactive element — OR keep the card-level click but move the inner action button to render as a sibling (not a descendant) of the `role="button"` region, using CSS positioning to keep the same visual layout. Read the inner button's actual purpose first to pick the right restructuring — don't guess; if the inner button's action is destructive/distinct enough that click-through-to-parent would be a real bug (e.g. clicking "delete" also triggering "select"), confirm the current code's `stopPropagation()` (or lack of it) on the inner button's click handler before restructuring, and preserve that behavior.

- [ ] **Step 3: Fix the roleless `aria-label` spans**

For each of the 5 `metric-status-*` spans, either add an explicit `role="img"` (if the span is purely a visual status indicator, matching the common pattern for icon-like status dots) or `role="status"` (if it's meant to be announced as a live status), whichever matches its actual semantic purpose — read the surrounding component to determine which, don't default to one without checking.

- [ ] **Step 4: Add/update tests**

For `WorkspaceCard`: a test confirming the accessibility tree no longer nests an interactive descendant inside the primary interactive region (e.g. via `@testing-library`'s query behavior — a `getByRole("button")` query should not find 2 nested matches in the same card). For the metrics spans: a test confirming each now has both a role and an accessible name.

- [ ] **Step 5: Run the touched test files**

- [ ] **Step 6: Commit**

```
fix: remove nested interactive elements and add roles to labeled status spans

WorkspaceCard nested a real <button> inside a role="button" div —
invalid in the accessibility tree. 5 metric-status-* spans on
/metrics had aria-label with no role, which some screen readers
won't reliably announce.
```

### Task 12: Migrate 6 create-forms to the existing `Dialog` primitive

**Files:**
- Modify: the 6 create-form call sites for Requirements, Architecture, ICD, Diagram, TestRuns, TraceLinks (find each via `grep -rln "create-req-btn\|create-arch-btn\|create-icd-btn\|create-diagram-btn\|create-testrun-btn\|create-trace-link"` and locate the surrounding inline-toggle form in each)
- Reference (do not modify): `frontend/src/components/shared/Dialog/Dialog.tsx` (the primitive being adopted)
- Test: existing tests for each of the 6 forms

**Finding:** `GESAMTTEST_BERICHT_2026-08-21.md` §5 finding 8 (Major): these 6 "Neu anlegen" forms use plain inline toggles instead of the project's own existing `Dialog` primitive (which already has `role="dialog"`, a focus trap, and Escape-to-close). Inline toggles have none of that — no focus management when opened, no keyboard-Escape dismissal.

- [ ] **Step 1: Read `Dialog.tsx`'s public interface**

Understand its props (open/onClose/children, or similar), and how an existing consumer already uses it (find at least one real call site elsewhere in the codebase that already uses `Dialog` correctly, to copy the integration pattern from).

- [ ] **Step 2: Read each of the 6 current inline-toggle implementations**

For each (Requirements, Architecture, ICD, Diagram, TestRuns, TraceLinks quick-create forms), note: what state currently controls "form is open" (likely a local `useState<boolean>`), what fields it renders, what the save/cancel handlers do. This session's earlier work today already touched `requirement-editor.spec.ts`/`se-workflow.spec.ts`/etc.'s E2E expectations for the Requirements quick-create form (`req-new-title-input`, `req-new-save-btn` testids, PR #694) — do NOT change those testids or the quick-create's fill-then-save flow; only wrap the existing form markup in `Dialog` instead of its current inline-conditional-render, so the already-fixed E2E tests keep passing unmodified.

- [ ] **Step 3: Migrate each of the 6, one at a time**

For each: replace the inline `{isOpen && <div className="...quickCreateForm...">...}` -style conditional render with `<Dialog open={isOpen} onClose={handleClose}>...(the same form contents, unchanged)...</Dialog>`. Preserve every existing `data-testid` exactly (E2E and existing unit tests depend on them). Do not change field order, labels, or button text — only the wrapping container/mechanism.

- [ ] **Step 4: Verify focus-trap and Escape behavior per form**

For each migrated form: confirm (by reading `Dialog.tsx`'s implementation, and/or a quick manual/test check) that opening it moves focus into the dialog and Escape closes it — this should come for free from `Dialog`, but verify per-instance since some of these forms may have quirks (e.g. an autofocus on a specific field that could conflict with `Dialog`'s own focus-trap initial-focus behavior).

- [ ] **Step 5: Run each of the 6 touched components' existing tests**

Since testids are unchanged, existing tests should pass without modification — if any fail, that's a signal the migration changed behavior it shouldn't have; investigate rather than adjusting the test to match.

- [ ] **Step 6: Commit** (one commit is fine, or one per form if the diffs are large enough to review independently — controller's judgment at execution time)

```
fix: migrate 6 create-forms to the existing Dialog primitive

Requirements, Architecture, ICD, Diagram, TestRuns, and TraceLinks
quick-create forms used a plain inline toggle instead of the shared
Dialog component, so none of them had focus-trap or Escape-to-close
behavior. All data-testids and form contents are unchanged.
```

### Task 13: EnforcementFlipDialog i18n + `lang` attribute

**Files:**
- Modify: `frontend/src/components/WorkflowEditor/EnforcementFlipDialog.tsx`
- Modify: `frontend/src/i18n/locales/de.json`, `frontend/src/i18n/locales/en.json` (new keys)
- Test: this component's existing test file (the review notes it was only jsdom-tested, not live-verified — the review's own concern about a real live-DOM verification still applies; this task's implementer should attempt one if the app can be reached, but a jsdom test asserting the new i18n keys resolve is the minimum bar)

**Finding:** `GESAMTTEST_BERICHT_2026-08-21.md` §10.1: `EnforcementFlipDialog` hardcodes English text with no `lang` attribute, inside an otherwise fully German document — both an i18n gap and a WCAG 3.1.2 (Language of Parts) violation since a screen reader would read the English text with German pronunciation rules unless `lang="en"` is present.

- [ ] **Step 1: Read the component's current hardcoded strings**

Identify every hardcoded English string in `EnforcementFlipDialog.tsx`.

- [ ] **Step 2: Add DE/EN i18n keys and replace hardcoded strings**

Add real translations (not placeholder English-only defaults) under a sensible new namespace (e.g. `workflow.enforcementFlip.*`) in both locale files, and replace every hardcoded string with `t("workflow.enforcementFlip....")` calls.

- [ ] **Step 3: Confirm no `lang="en"` workaround is needed after the i18n fix**

Once the text is properly translated per the active locale, there's no more English-in-German-document mismatch to fix with a `lang` attribute — this finding is fully closed by the i18n fix itself, not by adding `lang="en"` (which would be the wrong fix, since the goal is a German dialog for German users, not an English dialog correctly marked as English).

- [ ] **Step 4: Add/update the test**

Extend the existing jsdom test (or add one) asserting the dialog renders the correct locale-specific string per the active i18n language, and that `frontend/src/test/i18n-parity.test.ts`'s ratchet (if it exists — check) doesn't flag the new keys as missing.

- [ ] **Step 5: Run the touched test file(s)**

- [ ] **Step 6: Commit**

```
fix: translate EnforcementFlipDialog instead of hardcoding English

The dialog rendered English text unconditionally in an otherwise
fully German UI. Added real DE/EN i18n keys.
```

### Task 14: Unify primary-button styling across 6 list pages

**Files:**
- Modify: whichever shared button component(s) back the header "Neue X"-button and the empty-state CTA button (find via `grep -rln "radius-md\|radius-sm"` cross-referenced with the 6 pages: Requirements, Needs, ADRs, Risks, Testcases, Goals — likely 2 distinct component implementations to reconcile, per the finding)
- Test: visual-regression baseline if it covers these pages (check `e2e/tests/visual-regression.spec.ts`, committed per §10.3 of the Gesamttest-Bericht on a separate, not-yet-merged branch `feat/e2e-visual-regression-baseline` — confirm whether that branch has since merged; if so, this task's changes will need new baseline screenshots for the affected pages, not a code-only fix)

**Finding:** `GESAMTTEST_BERICHT_2026-08-21.md` §6 Top-1 (Major, highest design-finding reach): on Requirements/Needs/ADRs/Risks/Testcases/Goals, the header "Neue X" button (radius 12px, no hover-darken) and the empty-state CTA button (radius 6px, correct hover) are visually two different button implementations despite sharing a base color — different `--radius-md`/`--radius-sm` tokens, inconsistent hover feedback.

- [ ] **Step 1: Identify the 2 divergent implementations**

Find the actual component/style source for both the header button and the empty-state CTA button on at least 2 of the 6 affected pages (to confirm the pattern is really the same divergent pair repeated, not 6 independently different bugs) — read their JSX/CSS to see if they're two different shared components, or one shared component used inconsistently with different prop overrides.

- [ ] **Step 2: Decide the canonical style**

Per the finding, the empty-state CTA's behavior (radius 6px = `--radius-sm`, correct hover-darken) is described as the "correct" one implicitly (the header button is the one missing hover feedback, a real UX defect, not just a style inconsistency). Standardize both on `--radius-sm` + working hover-darken, unless reading the actual design-token intent (`tokens.css`'s own comments, if any, about which radius is meant for primary CTAs) suggests otherwise — check before assuming.

- [ ] **Step 3: Apply the fix**

If both call sites already go through one shared button component with divergent props, fix the props at each of the header-button call sites (6 pages) to match the empty-state CTA's configuration. If they're genuinely two different components, either consolidate to one (preferred, closes the root cause) or, if consolidation is too large for this task's scope, apply matching style overrides to both so they render identically — note in the commit message which approach was taken and why.

- [ ] **Step 4: Verify all 6 pages**

Visually confirm (screenshot or the visual-regression suite, if merged and available) that both buttons now match on all 6 affected pages.

- [ ] **Step 5: Update visual-regression baselines if that suite is merged and covers these pages**

If `feat/e2e-visual-regression-baseline` has merged by execution time, regenerate the specific snapshots for the 6 affected pages (`npx playwright test visual-regression.spec.ts --update-snapshots -- <affected page tests>`) rather than the whole baseline, and review the diffs manually before committing the updated PNGs.

- [ ] **Step 6: Commit**

```
fix: unify primary-button styling across 6 list pages

Header "Neue X" buttons and empty-state CTA buttons used different
border-radius tokens and the header variant was missing hover-darken
feedback, despite sharing a base color — two unreconciled button
implementations on Requirements/Needs/ADRs/Risks/Testcases/Goals.
```

### Task 15: i18n gap — 6 hardcoded English text blocks

**Files:**
- Modify: Traceability dialog ("Derivation"), ICD dialog ("One per line"), TestCase dialog (placeholder "e.g. Test case title..."), Baselines "Compare" button, the ReqIF Import panel, the Backup & Restore card texts — find each via grep for its literal English string
- Modify: `frontend/src/i18n/locales/de.json`, `frontend/src/i18n/locales/en.json`

**Finding:** `GESAMTTEST_BERICHT_2026-08-21.md` §6 Top-3: 6 independent spots of hardcoded English in an otherwise fully German UI — described as a systemic i18n gap, not isolated typos.

- [ ] **Step 1: Locate each of the 6 strings**

Grep for the literal text ("Derivation", "One per line", "e.g. Test case title", "Compare" in the Baselines context specifically — "Compare" may appear elsewhere legitimately, scope the grep to the Baselines component, the ReqIF Import panel's full text block, the Backup & Restore card's full text block).

- [ ] **Step 2: Add real DE translations and wire them up**

For each, add a properly-named i18n key under the relevant existing namespace (match this file's existing key-naming convention per area — e.g. `traceability.*`, `icd.*`, `testcase.*`, `baselines.*`, `import.reqif.*`, `admin.backup.*`) with a real German translation, and replace the hardcoded string with a `t(...)` call. The ReqIF Import panel and Backup & Restore card are described as "komplett" untranslated — expect multiple strings per area, not just one each; translate the whole panel/card's text content, not just the one representative phrase named in the finding.

- [ ] **Step 3: Verify against the i18n-parity ratchet**

If `frontend/src/test/i18n-parity.test.ts` (or equivalent) exists, confirm the new keys don't regress its baseline (they should improve it, since these were previously-undefined-in-locale gaps if the ratchet catches missing-key-usage; if it catches something else, read its actual mechanism before assuming).

- [ ] **Step 4: Run the i18n-parity test and any component tests touched**

- [ ] **Step 5: Commit**

```
fix: translate 6 remaining hardcoded English UI text blocks

Traceability dialog, ICD dialog, TestCase dialog placeholder,
Baselines compare button, the ReqIF Import panel, and the Backup &
Restore card were still English-only in an otherwise fully German UI.
```

### Task 16: Layout/consistency batch + traceability loading-state verification

**Files:** many small, independent — see each sub-item
- Sort-dropdown clipping (6+ pages: Needs, ADRs, Risks, Issues, Testcases, Goals, Requirements, Diagrams, ICDs) — the dropdown's caret icon overlaps its own text
- Dashboard workspace card: preset-badge/active-pill overlap
- Workflow-editor: "deprecated" transition-edge label overlapping the "APPROVED" state node, text truncated
- Architecture page: empty-state missing the headline+CTA pattern every sibling list page has
- Glossary toolbar: missing status filter, sort dropdown, "create in dialog" toggle that every sibling artifact list has
- Sidebar navigation: no scroll indicator when items overflow below the viewport (cut off after "Architektur" at 1366×900)
- Admin System-Settings: "+ Create Backup" collapses to bare "…" with no minimum width during its loading state, instead of an in-place spinner
- SE-Metrics grid: 5th metric card orphaned alone in row 2 of a 4-column grid
- Traceability list: target-requirement-id hard-truncated with no ellipsis, ~1100px of unused horizontal space alongside it
- Requirements category filter: offers a dead "stakeholder" option with 0 real matches (792 total requirements)

**Finding:** `GESAMTTEST_BERICHT_2026-08-21.md` §6 items 2, 4-10, 21, 23 and §10.2. Each is independent, scoped to 1-2 files, low individual risk. Batched into one task since none needs its own review cycle, but each gets its own commit (or a tightly-grouped set) so a bisect can isolate any regression.

- [ ] **Step 1: Sort-dropdown clipping** — find the shared sort-dropdown component (likely one shared component given it repeats identically across 8+ pages), fix the caret icon's positioning (padding-right on the text, or repositioning the icon) so it no longer overlaps the label text. Fixing the ONE shared component should resolve all affected pages at once — confirm it really is one shared component before treating this as "1 fix propagates everywhere" (if it's copy-pasted per page, this becomes 8+ separate small fixes instead).

- [ ] **Step 2: Dashboard badge/pill overlap** — read `WorkspaceCard.tsx`'s preset-badge and active-pill positioning (likely both absolutely positioned or flex-adjacent without enough gap); adjust spacing/positioning so they don't overlap at 1366px and 1920px.

- [ ] **Step 3: Workflow-editor edge-label collision** — in `TransitionEdge.tsx` (already touched in Task 2 for keyboard access — coordinate to avoid two agents editing the same file simultaneously if this plan is executed with parallel dispatch), adjust the edge-label's positioning/max-width or add text-overflow ellipsis so "deprecated" no longer visually collides with/gets truncated against the "APPROVED" state node.

- [ ] **Step 4: Architecture empty-state** — find Architecture's empty-state render path, compare against a sibling page's empty state (e.g. Requirements) that has the correct headline+explanatory-text+CTA pattern, and bring Architecture's in line with that existing pattern (reuse the sibling's shared empty-state component if one exists, rather than hand-copying markup).

- [ ] **Step 5: Glossary toolbar gaps** — compare Glossary's toolbar against a sibling artifact list's toolbar (e.g. Needs or ADRs) that has the status filter + sort dropdown + "create in dialog" toggle; add the missing controls to Glossary's toolbar using the same shared components the sibling pages use (not new one-off implementations).

- [ ] **Step 6: Sidebar scroll indicator** — add a visible scroll affordance (fade gradient, chevron, or a native scrollbar that isn't suppressed by whatever current CSS hides it) to the sidebar nav container when its content overflows the viewport height.

- [ ] **Step 7: Admin backup-button loading state** — give the "+ Create Backup" button a fixed/minimum width so it doesn't collapse when its label switches to a loading indicator; use an in-place spinner (check if this codebase has an existing spinner/loading-button pattern to reuse) instead of collapsing to "…".

- [ ] **Step 8: SE-Metrics orphaned grid row** — adjust the metrics grid's CSS (e.g. via `grid-template-columns` with a different column count, or `justify-content`/`place-items` on the last row) so a 5th card in a 4-column grid doesn't leave a large empty gap — the simplest fix is usually letting the last item span or center itself rather than forcing a 5-column-capable layout.

- [ ] **Step 9: Traceability truncation** — find the target-requirement-id cell's CSS in the traceability list; add `text-overflow: ellipsis` (with the accompanying `overflow: hidden; white-space: nowrap;` it requires) matching how every other list in this app already truncates long IDs, and free up the ~1100px of unused space by widening that column (check the table's `grid-template-columns`/flex-basis for that column and increase it).

- [ ] **Step 10: Dead "stakeholder" category filter** — find where the Requirements category-filter options are sourced (likely a hardcoded list or an enum that includes "stakeholder" alongside real categories); since the review confirms 0 of 792 requirements use it, either remove the option (if "stakeholder" is genuinely not a valid requirement category in this domain model) or investigate why it's offered with zero matches (if it's a legitimate category that simply has no current data, this may not be a bug at all — read the category enum/model definition first to determine which case this is before deleting anything).

- [ ] **Step 11: Verify the traceability loading-state finding (§4.1) against PR #694's fix**

This is verification, not necessarily a new fix. `GESAMTTEST_BERICHT_2026-08-21.md` §4.1 reported `/traceability` hanging past a 10s timeout under a freshly-reseeded ~880-requirement dataset, unconfirmed as a real product bug vs. a too-short test timeout. Issue #692 (fixed in PR #694, merged 2026-08-22) raised a *test's* timeout for the exact same symptom (`/traceability` stuck loading under full-suite load) from 10s to 30s, reasoning it was suite-load-induced backend slowness, not a functional bug. Read `e2e/tests/tracelink-creation.spec.ts`'s current state (post-#694) and confirm whether the specific test §4.1 refers to (`[REQ-L2-RF-006] traceability page shows list or empty state`, `tracelink-creation.spec.ts:150` per the original report) is the SAME test #692 already fixed, or a different one. If the same test: this finding is already resolved, mark it as such in this task's report, no further action. If different: this needs its own manual repro (open DevTools against `/traceability` with a large dataset) before deciding whether it's a real backend performance issue — do not silently apply the same timeout-increase fix without confirming it's the same root cause, since the original review explicitly flagged this finding as "unklar, nicht bestätigt."

- [ ] **Step 12: Commit** (group related sub-items into a few commits rather than 10 separate ones — controller's judgment; e.g. one commit for pure-CSS layout fixes, one for the toolbar/empty-state consistency fixes, one for the traceability truncation+verification)

---

## Phase 5 — Close-Out

### Task 17: Mark both review documents as processed

**Files:**
- Rename: `docs/reviews/DEEP_DIVE_REVIEW_2026-08-22.md` → `docs/reviews/DEEP_DIVE_REVIEW_2026-08-22_RESOLVED.md`
- Rename: `docs/reviews/GESAMTTEST_BERICHT_2026-08-21.md` → `docs/reviews/GESAMTTEST_BERICHT_2026-08-21_RESOLVED.md`
- Modify: both renamed files — add a short header note

**User's explicit instruction (this plan's origin conversation, 2026-08-22):** after implementation, rename the review files and mark them as processed/resolved.

- [ ] **Step 1: Confirm every finding from both reports has a corresponding completed task above**

Cross-check this plan's Tasks 1-16 (plus the already-resolved E2E items from PR #694, per this plan's Global Constraints) against every single finding ID in both source documents (Deep-Dive's A-1..E-3, Gesamttest's consolidated table items 1-23 plus §10's follow-up findings). Any finding that ended up deliberately deferred rather than fixed (e.g. Task 9's C-3, filed as a separate issue instead of fixed inline) must be named explicitly in the header note added in Step 2 — this close-out step is not allowed to silently drop a finding that was never actually addressed.

- [ ] **Step 2: Add a resolution header to each renamed file**

At the top of each renamed file (above its existing `# ` title), add:

```markdown
> **STATUS: RESOLVED** — findings addressed via `docs/superpowers/plans/2026-08-22-review-findings-remediation.md`
> (Tasks 1-16), merged in PR(s) #<fill in after merge>. Deferred (not fixed, tracked separately):
> <list any deliberately-deferred findings by ID and the issue number tracking them, e.g. "C-3 (bearer-token-in-login-body) — see issue #<N>">.
> Resolved on <date>.

---

```

- [ ] **Step 3: Commit** (via git subagent, likely bundled with whichever PR closes out the final remaining task rather than its own standalone PR)

```
chore: mark review docs as resolved

docs/reviews/DEEP_DIVE_REVIEW_2026-08-22.md and
GESAMTTEST_BERICHT_2026-08-21.md findings addressed via the
2026-08-22-review-findings-remediation plan.
```

---

## Self-Review Notes (for the plan author, already applied above)

- **Spec coverage:** every 🔴/🟠/🟡 finding in the Deep-Dive review maps to Tasks 4-9 (B-1→T4, C-1/D-3→T5, D-1→T6, D-2/D-4→T7, B-2/C-2/D-5/D-6/D-7/E-2→T8, C-3→T9 deferred-with-issue). Every non-already-fixed item in the Gesamttest-Bericht's consolidated table (§7) and §10 follow-up maps to Tasks 1-3, 10-16. ⚪-severity/positive-only findings (A-1..A-9, C-4, D-7's batch-frame note, E-3) are informational, not remediation targets — correctly excluded from task list.
- **Placeholder scan:** every task names its exact files (with line numbers from the source review, flagged for re-verification against current `main`) and either shows real code or gives an unambiguous, checkable target state ("clears 4.5:1 contrast," "matches the sibling page's existing empty-state component") rather than "add appropriate styling"-style vagueness. Task 16 batches many small layout fixes without full code for each — acceptable per this skill's own guidance on investigation-step tasks, since the plan-writing pass didn't have budget to hand-derive exact CSS for 10 independent, low-risk visual tweaks; each sub-step names the exact problem, the exact file/component to find, and the exact target behavior.
- **Type consistency:** Task 1's `workspacesApi.listAll()` matches `getAllPages`'s real existing signature (verified against current `client.ts` source, not guessed). Task 12 explicitly protects Task 1/2's untouched testids and today's already-merged PR #694 E2E fixes from being broken by the Dialog migration.
