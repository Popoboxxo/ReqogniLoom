# Memory Admin UI — Phase 4: User-Self-Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **This plan is self-contained** — grounded in a live read of `memory/memory_rest.py`, `memory/models.py`, `application/memory_admin_service.py`, `rest_api/api_key_views.py`, `frontend/src/components/UserProfileSettings/{UserProfileSettings,ApiKeysSection}.tsx` and `frontend/src/api/api-keys.ts`; no prior conversation context is required to implement it.

**Goal:** Let any authenticated user see how much of their own `UserTenantMemory` exists and delete it themselves — a GDPR-style self-service erasure control, independent of System-Admin (Phase 1) tooling. Never touches `WorkspaceMemory` (team-owned, not an individual's data).

**Architecture:** No new Django app, no new service class. A single thin `APIView` (`MemorySelfServiceView`) added to the existing `backend/memory/memory_rest.py`, filtering `UserTenantMemory` directly by the caller's own `ctx.user_id` — mirrors the "self-scoped, no admin gate" precedent of `rest_api/api_key_views.py::ApiKeyViewSet` (own-data CRUD, `HasOperationPermission` with no `required_operation` declared = authenticated access is sufficient, scoping happens via the `user_id` filter itself, not an RBAC role check). Frontend: new `MemorySection.tsx` in `frontend/src/components/UserProfileSettings/`, following `ApiKeysSection.tsx`'s structure verbatim (section card, load-on-mount, `window.confirm` before the destructive action), wired into `UserProfileSettings.tsx` next to `<ApiKeysSection />`.

**Tech Stack:** Django 4.2 (no migration — no new model/field), DRF `APIView`, React 18 + TS (existing `UserProfileSettings` page).

**Spec:** `docs/superpowers/specs/2026-08-26-memory-admin-ui-design.md`, "Phase 4 — User-Self-Service" section (lines 176-195).

## Rulings (plan-vs-spec conflicts resolved before execution — do not re-litigate; if new evidence contradicts one, ledger it and escalate, don't silently reverse it)

1. **Scope is `UserTenantMemory` ONLY.** `WorkspaceMemory` has no per-user attribution column (verified in `memory/models.py`) and is explicitly called out in the spec as team-owned, not an individual's data ("nie Workspace-Memory, das ist nicht Eigentum eines einzelnen Nutzers"). This endpoint must never read or delete `WorkspaceMemory` rows, even for workspaces the caller is a member/admin of — that remains exclusively `MemoryAdminService`'s (Phase 1) job.
2. **No new service class, no `ServiceBase`/`_audit()` call.** The spec says explicitly "Kein neuer Service nötig — dünner View". Precedent for NOT auditing self-service deletion of one's own data: `ApiKeyViewSet.destroy` (revokes the caller's own API key) has zero audit-log call anywhere in `AuthenticationService.revoke_api_key` — audit logging in this codebase is reserved for admin-acting-on-others'-data operations (e.g. `MemoryAdminService.delete_workspace_memory`'s `self._audit(...)`), not self-service actions on one's own rows. Do not add an audit call here; that would be a new, undiscussed pattern for this class of endpoint.
3. **Auth gate: authenticated-only, no RBAC role check.** `permission_classes = [HasOperationPermission]` with **no** `required_operation` class attribute declared (`HasOperationPermission.has_permission` returns `True` for any authenticated caller when `required_operation` is `None` — verified in `auth_tenancy/rest.py` lines 309-312). The endpoint carries no `workspace_id` and needs none: the `UserTenantMemory.objects.filter(user_id=ctx.user_id)` scoping IS the authorization boundary, exactly like every `ApiKeyViewSet` action. Do not add a `_is_system_admin`/`_is_superuser` check — this is deliberately available to every authenticated user, including one with no role anywhere (mirrors `ApiKeyViewSet`'s own "READ declared uniformly ... an authenticated user with NO role anywhere remains correctly denied" comment — but note `HasOperationPermission` with `required_operation=None` does NOT even do that check; it's authentication-only, one step more permissive than `ApiKeyViewSet`'s `Operation.READ`. This is intentional: managing your own memory should not require holding any workspace role, same as `SystemMemorySettingsView`'s admin-gated pattern being the odd one out, not the norm — `UserPreferenceView`/`MeView` are the closer precedent for "any authenticated user, no role needed").
4. **Response shape.** `GET` returns `{"entry_count": int, "last_updated_at": str | null}` (ISO-8601, `null` when the user has zero entries) — deliberately NOT the full per-entry content list (no pagination endpoint needed for an MVP delete-only self-service control; the spec's UI mock only shows a count + timestamp + delete button, no entry browser). `DELETE` returns `{"deleted": int}` (count of rows removed), `200 OK` even when `deleted == 0` (deleting nothing is not an error — mirrors `MemoryAdminService.delete_workspace_memory` returning counts rather than erroring on zero).
5. **i18n namespace:** new flat top-level `memorySelfService` key (mirrors `apiKeys`'s flat top-level style) in both `de.json`/`en.json`, NOT nested under the existing `memory.*` namespace (line ~713) — that namespace is already used by the System-Settings admin "Memory" tab (Phases 1-3) and mixing an end-user self-service string set into it risks confusing future maintainers about which strings gate on System-Admin vs. plain-auth.

## Global Constraints

- `UserTenantMemory.objects` is already a `TenantScopedModel` manager — reads inside a real request are automatically scoped to the active tenant (RLS + Django-level filter both armed by `AuthTenancyAuthentication`, same as every other view in `memory_rest.py`). No manual `tenant_id` filter needed for the `GET`; the `DELETE` doesn't need one either (same manager), but MUST still filter by `user_id=ctx.user_id` — never delete by `tenant_id` alone.
- Never touch `WorkspaceMemory` in this view (Ruling 1).
- Every new frontend-visible string needs a matching key in BOTH `frontend/src/i18n/locales/de.json` and `frontend/src/i18n/locales/en.json` (checked by `frontend/src/test/i18n-parity.test.ts`).
- `data-testid` on every interactive element (project convention, E2E-Pflicht) — reuse the naming scheme `memory-self-service-*` for consistency with `api-key-*`/`api-keys-*` siblings in the same file.
- Backend tests run via: `docker exec -e DB_USER=reqogniloom -e DB_PASSWORD=CHANGE-ME-strong-password reqogniloom-backend-1 bash -c "cd /app && python -m pytest <paths> -v"`. Frontend tests via: `docker exec reqogniloom-frontend-1 npx vitest run <path>`. Never run tests on the host.

---

### Task 1: Backend — `MemorySelfServiceView` (GET + DELETE `/api/v1/memory/me/`)

**Files:**
- Modify: `backend/memory/memory_rest.py` (add `MemorySelfServiceView`, add to `__all__`)
- Modify: `backend/rest_api/urls.py` (import + register route)
- Modify: `backend/memory/tests/test_memory_rest.py` (append tests — check the file's existing fixture/auth-context helper style first, e.g. `grep -n "def test_\|class Test" backend/memory/tests/test_memory_rest.py` before writing new tests, and reuse whatever request-building/auth-context helpers the existing `WorkspaceMemorySettingsView`/`SystemMemoryWorkspaceOverviewView` tests already use)

**Interfaces:**
- Consumes: `memory.models.UserTenantMemory`, `rest_api.auth_enforcer.get_auth_context`, `auth_tenancy.rest.HasOperationPermission`, `rest_api.serializers.build_error_response`/`detect_lang` (same imports the file already has).
- Produces: `memory.memory_rest.MemorySelfServiceView`, route `memory/me/` (name `memory-self-service`).

- [ ] **Step 1: Add `MemorySelfServiceView` to `backend/memory/memory_rest.py`**

  Add near the bottom, after `SystemMemoryWorkspaceDeleteView` and before `__all__`:

  ```python
  class MemorySelfServiceView(APIView):
      """``/api/v1/memory/me/`` — any authenticated user, no role required.

      Memory Admin UI Phase 4 (spec 2026-08-26). Self-service over the
      caller's OWN ``UserTenantMemory`` rows only — never ``WorkspaceMemory``,
      which is team-owned (see plan Ruling 1). No admin gate: the ``user_id``
      filter on every query IS the authorization boundary, mirroring
      ``ApiKeyViewSet``'s own-data-only self-service pattern.

      GET: ``{"entry_count": int, "last_updated_at": str | None}``.
      DELETE: deletes all of the caller's ``UserTenantMemory`` rows, returns
      ``{"deleted": int}`` — 200 even when nothing existed to delete.
      """

      permission_classes = [HasOperationPermission]

      def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
          lang = detect_lang(request)
          try:
              ctx = get_auth_context(request)
          except Exception:
              return Response(
                  build_error_response("AUTHENTICATION_REQUIRED", lang),
                  status=status.HTTP_401_UNAUTHORIZED,
              )
          agg = UserTenantMemory.objects.filter(user_id=ctx.user_id).aggregate(
              count=Count("id"), last=Max("created_at")
          )
          return Response(
              {
                  "entry_count": agg["count"] or 0,
                  "last_updated_at": agg["last"],
              }
          )

      def delete(self, request: Request, *args: Any, **kwargs: Any) -> Response:
          lang = detect_lang(request)
          try:
              ctx = get_auth_context(request)
          except Exception:
              return Response(
                  build_error_response("AUTHENTICATION_REQUIRED", lang),
                  status=status.HTTP_401_UNAUTHORIZED,
              )
          deleted, _ = UserTenantMemory.objects.filter(user_id=ctx.user_id).delete()
          return Response({"deleted": deleted})
  ```

  Add the needed imports at the top of the file:
  - `from django.db.models import Count, Max` (not yet imported in this file — check first, it currently has no `django.db.models` import).
  - Add `UserTenantMemory` to the existing `from memory.models import WorkspaceMemorySettings` line (`from memory.models import UserTenantMemory, WorkspaceMemorySettings`).

  Add `"MemorySelfServiceView"` to the `__all__` list at the bottom of the file.

- [ ] **Step 2: Register the route**

  In `backend/rest_api/urls.py`:
  - Add `MemorySelfServiceView` to the existing `from memory.memory_rest import (...)` block (alphabetical, matches the block's existing ordering).
  - Add a new `path(...)` entry directly after the `system-memory-workspace-delete` path (same block, keeps all memory routes contiguous):
    ```python
    # AI Long-Term Memory — user self-service (Memory Admin UI Phase 4,
    # spec 2026-08-26). Any authenticated user, own UserTenantMemory only.
    path(
        "memory/me/",
        MemorySelfServiceView.as_view(),
        name="memory-self-service",
    ),
    ```

- [ ] **Step 3: Tests in `backend/memory/tests/test_memory_rest.py`**

  Cover, following the file's existing fixture conventions exactly (read a couple of existing tests for `WorkspaceMemorySettingsView`/`SystemMemoryWorkspaceOverviewView` first):
  - GET with zero entries -> `entry_count: 0, last_updated_at: null`.
  - GET with N entries for the caller -> correct `entry_count`, `last_updated_at` matches the newest `created_at`.
  - GET/DELETE unauthenticated -> 401.
  - DELETE removes only the CALLER's own `UserTenantMemory` rows — seed a second user's `UserTenantMemory` row in the same tenant, assert it survives the caller's DELETE (`UserTenantMemory.objects.filter(user_id=other_user_id).count() == 1` after).
  - DELETE never touches `WorkspaceMemory` — seed a `WorkspaceMemory` row in a workspace the caller belongs to, assert it survives the DELETE.
  - DELETE with zero entries -> `200`, `{"deleted": 0}` (not an error).

---

### Task 2: Frontend — `MemorySection.tsx` in `UserProfileSettings`

**Files:**
- Create: `frontend/src/api/memory-self-service.ts`
- Create: `frontend/src/components/UserProfileSettings/MemorySection.tsx`
- Create: `frontend/src/components/UserProfileSettings/MemorySection.test.tsx`
- Modify: `frontend/src/components/UserProfileSettings/UserProfileSettings.tsx` (import + render `<MemorySection />` after `<ApiKeysSection />`)
- Modify: `frontend/src/i18n/locales/de.json`, `frontend/src/i18n/locales/en.json` (new top-level `memorySelfService` key, Ruling 5)

**Interfaces:**
- Consumes: `GET/DELETE /api/v1/memory/me/` (Task 1), `../../api/client`'s `apiClient` (same pattern as `api-keys.ts`).
- Produces: `frontend/src/api/memory-self-service.ts` exporting `memorySelfServiceApi.get()`/`.deleteAll()`, `MemorySection` component.

- [ ] **Step 1: `frontend/src/api/memory-self-service.ts`**

  Mirror `frontend/src/api/api-keys.ts`'s structure exactly:

  ```typescript
  import { apiClient } from "./client";

  export interface MemorySelfServiceOverview {
    entry_count: number;
    last_updated_at: string | null;
  }

  export interface MemorySelfServiceDeleteResult {
    deleted: number;
  }

  export const memorySelfServiceApi = {
    /** GET /api/v1/memory/me/ — the caller's own UserTenantMemory overview. */
    get(): Promise<MemorySelfServiceOverview> {
      return apiClient.get<MemorySelfServiceOverview>("/memory/me/");
    },

    /** DELETE /api/v1/memory/me/ — deletes all of the caller's own memory. */
    deleteAll(): Promise<MemorySelfServiceDeleteResult> {
      return apiClient.delete<MemorySelfServiceDeleteResult>("/memory/me/");
    },
  };
  ```

  Check `apiClient.delete`'s actual TS signature first (`frontend/src/api/client.ts`) — `ApiKeysSection`'s `apiKeysApi.revoke` calls `apiClient.delete` with no generic/return type, so confirm whether `delete<T>()` returning a typed body is actually supported before assuming the signature above compiles; adjust to match whatever `client.ts` actually exposes.

- [ ] **Step 2: `frontend/src/components/UserProfileSettings/MemorySection.tsx`**

  Follow `ApiKeysSection.tsx`'s structure: same style constants (`sectionStyle`, `headingStyle`, `cardStyle`, `dangerButtonStyle` — import/reuse if these get extracted to a shared module, otherwise duplicate the inline style objects exactly as `ApiKeysSection` does today, matching existing file-local duplication convention rather than introducing a new shared-styles module unprompted), same `extractErrorMessage`/`formatDate` local helpers.

  Behavior:
  - `data-testid="memory-self-service-section"` root `<section>`.
  - On mount, `GET` the overview; loading state `data-testid="memory-self-service-loading"`.
  - Show `entry_count` and formatted `last_updated_at` (or an em-dash / "no entries yet" state when `entry_count === 0`) — `data-testid="memory-self-service-count"` / `data-testid="memory-self-service-last-updated"`.
  - "Mein Memory löschen" button, `data-testid="memory-self-service-delete-btn"`, `disabled` when `entry_count === 0` or a delete is in flight.
  - `window.confirm(...)` before calling `deleteAll()` (mirrors `ApiKeysSection.handleRevoke`'s confirm pattern) — confirm text must make clear this deletes ALL of the user's own memory and is irreversible.
  - After a successful delete, re-fetch (or locally reset `entry_count` to `0`/`last_updated_at` to `null`) so the UI reflects the new empty state without a page reload.
  - Error state `data-testid="memory-self-service-error"`, same `role="alert"` pattern as `ApiKeysSection`'s `api-keys-error`.

- [ ] **Step 3: Wire into `UserProfileSettings.tsx`**

  Add `import { MemorySection } from "./MemorySection";` and render `<MemorySection />` immediately after `<ApiKeysSection />` (before the workspace-scoped `visibility-section` block, which stays last — it's the one section that's conditional on `activeWorkspace`).

- [ ] **Step 4: i18n keys**

  Add a new top-level `memorySelfService` object to BOTH `de.json` and `en.json` (Ruling 5), with (at minimum) keys for: title, hint/description, count label, last-updated label, empty state, delete button label, delete confirm dialog text, delete success feedback (if any), error fallback. Match `apiKeys`'s key-naming style (`title`, `hint`, ...) for consistency. Run `frontend/src/test/i18n-parity.test.ts` after to confirm both locale files stay in lockstep.

- [ ] **Step 5: `MemorySection.test.tsx`**

  Cover (mirror whatever mocking convention `MemorySettingsSection.test.tsx` or `MemoryManagementSection.test.tsx` already use for API mocking — check those first, don't invent a third pattern):
  - Loading state renders, then resolves to the overview.
  - Zero-entries state: delete button disabled, empty-state message shown.
  - Non-zero entries: count + last-updated rendered correctly.
  - Delete flow: click delete -> `window.confirm` mocked to return `true` -> `deleteAll()` called -> UI resets to empty state.
  - Delete flow: `window.confirm` mocked to return `false` -> `deleteAll()` NOT called.
  - API error on load or delete -> error message rendered.

---

### Task 3: Verification

- [ ] Run the new backend tests: `docker exec -e DB_USER=reqogniloom -e DB_PASSWORD=CHANGE-ME-strong-password reqogniloom-backend-1 bash -c "cd /app && python -m pytest memory/tests/test_memory_rest.py -v"`.
- [ ] Run the full `memory` app + `rest_api` test suites to catch any regression from the new import/route (`python -m pytest memory/ rest_api/ -v` in the same container invocation style).
- [ ] Run the new/changed frontend tests: `docker exec reqogniloom-frontend-1 npx vitest run src/components/UserProfileSettings src/api/memory-self-service`.
- [ ] Run `frontend/src/test/i18n-parity.test.ts` to confirm `de.json`/`en.json` stay in lockstep.
- [ ] Manual/browser check (or a short Playwright smoke test if the reviewer judges the existing E2E suite's coverage gap here to be worth closing): log in as a non-admin user with at least one `UserTenantMemory` row (e.g. via an existing memory-consolidation fixture/task), open the Profile page, confirm the count/timestamp render, delete, confirm the UI reflects the empty state and a second GET independently confirms `entry_count: 0`.
- [ ] Whole-diff review before PR: re-check Ruling 1 (no `WorkspaceMemory` code path anywhere in the new view) and Ruling 3 (no accidental RBAC/role check reintroduced) — these are the two ways this feature could silently become either too permissive (leaking another user's or a workspace's data) or too restrictive (locking out a role-less user from their own data).
