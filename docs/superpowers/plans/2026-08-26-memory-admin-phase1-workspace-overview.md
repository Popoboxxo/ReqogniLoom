# Memory Admin UI — Phase 1: Workspace-Übersicht + Löschen — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give a System-Admin a table of all workspaces in their tenant showing memory activity (on/off, entry counts per tier, last consolidation), with a per-workspace delete action that removes both the workspace's `WorkspaceMemory` rows and its current members' `UserTenantMemory` rows.

**Architecture:** A new `MemoryAdminService` (Layer 2, `application/`) is the single entry point for the two new operations (list overview, delete). Two new `APIView`s in the existing `memory/memory_rest.py` module expose it as `GET`/`DELETE /api/v1/system/memory/workspaces/`, gated the same way as the existing `SystemMemorySettingsView` (`_is_system_admin`). The frontend adds a 4th "Memory" tab to `SystemSettings.tsx` with a new `MemoryManagementSection` component.

**Tech Stack:** Django 4.2 / DRF, React 18 + TypeScript, existing `WorkspaceMemory`/`UserTenantMemory`/`WorkspaceMemorySettings`/`UserRole` models (no new migration).

**Spec:** `docs/superpowers/specs/2026-08-26-memory-admin-ui-design.md` (Phase 1 section)

## Global Constraints

- No new Django migration — this plan only reads/writes existing tables (`WorkspaceMemory`, `UserTenantMemory`, `WorkspaceMemorySettings`, `UserRole`, `Workspace`).
- System-Admin gate: `ctx.has_role("admin") or AuthorizationService().is_tenant_admin(user_id=ctx.user_id, tenant_id=ctx.tenant_id)` — copied verbatim from `memory/memory_rest.py`'s existing `_is_system_admin()`. Do not invent a different check.
- Deleting a workspace's memory MUST remove both tiers: all `WorkspaceMemory` rows for that workspace, AND all `UserTenantMemory` rows belonging to users who are CURRENT (non-suspended) members of that workspace via `UserRole`. Never touch `UserTenantMemory` rows of users who are not members of the workspace being deleted.
- All new backend code lives inside an already-active request-scoped tenant context (this is only reachable via a real HTTP request through `AuthTenancyAuthentication`, never from Celery) — do NOT call `TenantContext.set_tenant(...)` or `memory.backends._tenant_context(...)` anywhere in this plan's code. Mirrors the explicit warning in `memory/memory_rest.py`'s module docstring.
- Every new frontend-visible string needs a matching key added to BOTH `frontend/src/i18n/locales/de.json` and `frontend/src/i18n/locales/en.json` (checked by `frontend/src/test/i18n-parity.test.ts`, which fails the whole suite if the two files' flattened key sets differ).
- Follow the existing `systemSettings.*` locale convention exactly: `tabs.*` is a real nested object; everything else under `systemSettings` (e.g. `themes.*`) uses flat keys containing a literal dot in the JSON property name (e.g. `"memory.heading": "..."`), NOT nested objects. Copy this convention — do not "fix" it into real nesting.

---

### Task 1: Backend — `MemoryAdminService`

**Files:**
- Create: `backend/application/memory_admin_service.py`
- Test: `backend/application/tests/test_memory_admin_service.py`

**Interfaces:**
- Consumes: `AuthContext` (`auth_tenancy.context.AuthContext`, has `.user_id: UUID`, `.tenant_id: UUID`, `.has_role(role: str) -> bool`), `ServiceBase`/`PermissionDeniedError`/`NotFoundError` from `application.base`, `AuthorizationService` from `auth_tenancy.services` (`.is_tenant_admin(user_id, tenant_id) -> bool`), `Workspace` from `persistence.models`, `UserRole` from `auth_tenancy.models`, `WorkspaceMemory`/`UserTenantMemory`/`WorkspaceMemorySettings` from `memory.models`.
- Produces: `MemoryAdminService().list_workspace_overview(ctx: AuthContext) -> list[dict]` — each dict has keys `workspace_id` (UUID), `workspace_name` (str), `enabled` (bool), `workspace_entry_count` (int), `user_entry_count` (int), `last_consolidated_at` (datetime | None). `MemoryAdminService().delete_workspace_memory(ctx: AuthContext, workspace_id: UUID) -> dict` — dict has keys `workspace_id` (UUID), `workspace_memory_deleted` (int), `user_memory_deleted` (int). Both raise `PermissionDeniedError` if `ctx` is not a System-Admin; `delete_workspace_memory` additionally raises `NotFoundError` if `workspace_id` does not resolve to a `Workspace` in the active tenant. Task 2 (REST views) calls these two methods directly.

- [ ] **Step 1: Write the failing tests**

Create `backend/application/tests/test_memory_admin_service.py`:

```python
"""Tests for MemoryAdminService (Memory Admin UI Phase 1)."""
import pytest

from application.base import NotFoundError, PermissionDeniedError
from application.memory_admin_service import MemoryAdminService
from memory.backends import get_memory_backend
from memory.models import UserTenantMemory, WorkspaceMemory, WorkspaceMemorySettings
from persistence.tests.factories import (
    active_tenant,
    assign_role,
    ctx_for_user,
    editor_ctx,
    make_user,
    make_workspace,
)


@pytest.mark.django_db
class TestMemoryAdminServiceListOverview:
    def test_lists_workspace_with_zero_entries(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant, name="Empty WS")
            admin_user = make_user(tenant)
            ctx = ctx_for_user(tenant, admin_user, roles=("admin",))

            overview = MemoryAdminService().list_workspace_overview(ctx)

            row = next(r for r in overview if r["workspace_id"] == ws.id)
            assert row["workspace_name"] == "Empty WS"
            assert row["enabled"] is True
            assert row["workspace_entry_count"] == 0
            assert row["user_entry_count"] == 0
            assert row["last_consolidated_at"] is None

    def test_counts_both_tiers_and_respects_disabled_flag(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant, name="Busy WS")
            member = make_user(tenant)
            assign_role(member, ws, "editor")
            WorkspaceMemorySettings.objects.create(tenant=tenant, workspace=ws, enabled=False)

            backend = get_memory_backend()
            backend.upsert(tenant.id, "workspace", ws.id, "workspace fact one")
            backend.upsert(tenant.id, "workspace", ws.id, "workspace fact two")
            backend.upsert(tenant.id, "user", member.id, "user fact one")

            admin_user = make_user(tenant)
            ctx = ctx_for_user(tenant, admin_user, roles=("admin",))

            overview = MemoryAdminService().list_workspace_overview(ctx)

            row = next(r for r in overview if r["workspace_id"] == ws.id)
            assert row["enabled"] is False
            assert row["workspace_entry_count"] == 2
            assert row["user_entry_count"] == 1
            assert row["last_consolidated_at"] is not None

    def test_excludes_non_member_user_memory(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant, name="Isolated WS")
            outsider = make_user(tenant)  # never assigned a role in ws

            backend = get_memory_backend()
            backend.upsert(tenant.id, "user", outsider.id, "outsider fact")

            admin_user = make_user(tenant)
            ctx = ctx_for_user(tenant, admin_user, roles=("admin",))

            overview = MemoryAdminService().list_workspace_overview(ctx)

            row = next(r for r in overview if r["workspace_id"] == ws.id)
            assert row["user_entry_count"] == 0

    def test_denies_non_admin(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)

            with pytest.raises(PermissionDeniedError):
                MemoryAdminService().list_workspace_overview(ctx)


@pytest.mark.django_db
class TestMemoryAdminServiceDelete:
    def test_deletes_both_tiers_for_current_members_only(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            member = make_user(tenant)
            assign_role(member, ws, "editor")
            outsider = make_user(tenant)  # not a member of ws

            backend = get_memory_backend()
            backend.upsert(tenant.id, "workspace", ws.id, "ws fact")
            backend.upsert(tenant.id, "user", member.id, "member fact")
            backend.upsert(tenant.id, "user", outsider.id, "outsider fact")

            admin_user = make_user(tenant)
            ctx = ctx_for_user(tenant, admin_user, roles=("admin",))

            result = MemoryAdminService().delete_workspace_memory(ctx, ws.id)

            assert result["workspace_memory_deleted"] == 1
            assert result["user_memory_deleted"] == 1
            assert WorkspaceMemory.objects.filter(workspace_id=ws.id).count() == 0
            assert UserTenantMemory.objects.filter(user_id=member.id).count() == 0
            # Outsider's memory is untouched.
            assert UserTenantMemory.objects.filter(user_id=outsider.id).count() == 1

    def test_raises_not_found_for_unknown_workspace(self):
        with active_tenant() as tenant:
            admin_user = make_user(tenant)
            ctx = ctx_for_user(tenant, admin_user, roles=("admin",))
            import uuid

            with pytest.raises(NotFoundError):
                MemoryAdminService().delete_workspace_memory(ctx, uuid.uuid4())

    def test_denies_non_admin(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)

            with pytest.raises(PermissionDeniedError):
                MemoryAdminService().delete_workspace_memory(ctx, ws.id)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && DB_USER=reqogniloom pytest application/tests/test_memory_admin_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'application.memory_admin_service'`

- [ ] **Step 3: Write the implementation**

Create `backend/application/memory_admin_service.py`:

```python
"""MemoryAdminService — System-Admin operations over consolidated memory
(Memory Admin UI Phase 1, spec 2026-08-26).

Both public methods run only inside an already-active request-scoped tenant
context (reached exclusively via a real HTTP request through
``AuthTenancyAuthentication``, never from Celery) — this mirrors
``memory/memory_rest.py``'s existing views and its module docstring's
explicit warning against a bare ``TenantContext.set_tenant(...)`` call:
that call only satisfies the Django-ORM side and never arms Postgres RLS.
Since this service is never invoked outside a request, no such call is
needed here at all.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from auth_tenancy.context import AuthContext
from auth_tenancy.models import UserRole
from auth_tenancy.services import AuthorizationService
from memory.models import UserTenantMemory, WorkspaceMemory, WorkspaceMemorySettings
from persistence.models import Workspace

from .base import NotFoundError, PermissionDeniedError, ServiceBase


class MemoryAdminService(ServiceBase):
    """System-Admin-only read/delete operations over workspace + user memory."""

    @staticmethod
    def _assert_system_admin(ctx: AuthContext) -> None:
        """Same System-Admin check as ``memory.memory_rest._is_system_admin``."""
        if ctx.has_role("admin") or AuthorizationService().is_tenant_admin(
            user_id=ctx.user_id, tenant_id=ctx.tenant_id
        ):
            return
        raise PermissionDeniedError("System-Admin role required")

    @staticmethod
    def _member_ids(workspace_id: UUID) -> list[UUID]:
        """Current (non-suspended) member user ids of *workspace_id*."""
        return list(
            UserRole.objects.filter(workspace_id=workspace_id, suspended_at__isnull=True)
            .values_list("user_id", flat=True)
            .distinct()
        )

    def list_workspace_overview(self, ctx: AuthContext) -> list[dict[str, Any]]:
        """Return one overview row per workspace in the active tenant.

        Relies on ``Workspace.objects``/``WorkspaceMemorySettings.objects``
        (both ``TenantScopedModel`` managers) already being scoped to the
        active tenant context — no manual ``tenant_id`` filter needed for
        reads (only writes need it explicitly, see
        ``WorkspaceMemorySettingsView.put``'s comment on ``update_or_create``).
        """
        self._assert_system_admin(ctx)

        settings_by_ws = {
            s.workspace_id: s.enabled for s in WorkspaceMemorySettings.objects.all()
        }

        overview: list[dict[str, Any]] = []
        for ws in Workspace.objects.all().order_by("name"):
            ws_qs = WorkspaceMemory.objects.filter(workspace_id=ws.id)
            ws_count = ws_qs.count()
            last_ws = ws_qs.order_by("-created_at").values_list("created_at", flat=True).first()

            member_ids = self._member_ids(ws.id)
            if member_ids:
                user_qs = UserTenantMemory.objects.filter(user_id__in=member_ids)
                user_count = user_qs.count()
                last_user = user_qs.order_by("-created_at").values_list("created_at", flat=True).first()
            else:
                user_count = 0
                last_user = None

            candidates = [d for d in (last_ws, last_user) if d is not None]
            last_consolidated = max(candidates) if candidates else None

            overview.append(
                {
                    "workspace_id": ws.id,
                    "workspace_name": ws.name,
                    "enabled": settings_by_ws.get(ws.id, True),
                    "workspace_entry_count": ws_count,
                    "user_entry_count": user_count,
                    "last_consolidated_at": last_consolidated,
                }
            )
        return overview

    def delete_workspace_memory(self, ctx: AuthContext, workspace_id: UUID) -> dict[str, Any]:
        """Delete BOTH tiers for *workspace_id*: its own ``WorkspaceMemory``
        rows, and the ``UserTenantMemory`` rows of its CURRENT members.

        Never deletes ``UserTenantMemory`` for a user who is not a current
        member of this workspace, even if that user has other memberships.
        """
        self._assert_system_admin(ctx)

        workspace = Workspace.objects.filter(id=workspace_id).first()
        if workspace is None:
            raise NotFoundError(f"Workspace {workspace_id} not found")

        member_ids = self._member_ids(workspace_id)

        ws_deleted, _ = WorkspaceMemory.objects.filter(workspace_id=workspace_id).delete()
        user_deleted = 0
        if member_ids:
            user_deleted, _ = UserTenantMemory.objects.filter(user_id__in=member_ids).delete()

        return {
            "workspace_id": workspace_id,
            "workspace_memory_deleted": ws_deleted,
            "user_memory_deleted": user_deleted,
        }


__all__ = ["MemoryAdminService"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && DB_USER=reqogniloom pytest application/tests/test_memory_admin_service.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/application/memory_admin_service.py backend/application/tests/test_memory_admin_service.py
git commit -m "feat: add MemoryAdminService for workspace memory overview/delete"
```

---

### Task 2: Backend — REST views + URL wiring

**Files:**
- Modify: `backend/memory/memory_rest.py` (append two new views, extend module docstring, extend `__all__`)
- Modify: `backend/rest_api/urls.py:56` (import) and around `backend/rest_api/urls.py:463-466` (add two `path()` entries after the existing `system/memory-settings/` entry)
- Test: `backend/memory/tests/test_memory_rest.py` (append a new test class)

**Interfaces:**
- Consumes: `MemoryAdminService` from Task 1 (`application.memory_admin_service.MemoryAdminService`, methods `list_workspace_overview(ctx) -> list[dict]` and `delete_workspace_memory(ctx, workspace_id) -> dict`), `PermissionDeniedError`/`NotFoundError` from `application.base`, existing `get_auth_context`, `build_error_response`, `detect_lang`, `HasOperationPermission` (all already imported at the top of `memory/memory_rest.py`).
- Produces: `GET /api/v1/system/memory/workspaces/` -> `{"results": [{...row...}]}` (200) or `403`. `DELETE /api/v1/system/memory/workspaces/<uuid:workspace_id>/` -> `{"workspace_id": ..., "workspace_memory_deleted": N, "user_memory_deleted": M}` (200), `403`, or `404`. URL names: `system-memory-workspace-overview`, `system-memory-workspace-delete`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/memory/tests/test_memory_rest.py` (add these imports to the existing `from persistence.tests.factories import (...)` block: `assign_role`, `make_user`; then add this class at the end of the file):

```python
@pytest.mark.django_db
class TestMemoryAdminWorkspaceOverviewRest:
    def test_lists_workspace_overview(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant, name="Overview WS")
            admin_user, token = admin_user_and_token(tenant)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

            response = client.get("/api/v1/system/memory/workspaces/")

            assert response.status_code == 200
            row = next(r for r in response.data["results"] if r["workspace_id"] == str(ws.id))
            assert row["workspace_name"] == "Overview WS"
            assert row["enabled"] is True
            assert row["workspace_entry_count"] == 0
            assert row["user_entry_count"] == 0

    def test_overview_denies_non_admin(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user, token = editor_user_and_token(tenant, ws)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

            response = client.get("/api/v1/system/memory/workspaces/")

            assert response.status_code == 403


@pytest.mark.django_db
class TestMemoryAdminWorkspaceDeleteRest:
    def test_deletes_both_tiers(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            member = make_user(tenant)
            assign_role(member, ws, "editor")

            from memory.backends import get_memory_backend

            backend = get_memory_backend()
            backend.upsert(tenant.id, "workspace", ws.id, "ws fact")
            backend.upsert(tenant.id, "user", member.id, "member fact")

            admin_user, token = admin_user_and_token(tenant)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

            response = client.delete(f"/api/v1/system/memory/workspaces/{ws.id}/")

            assert response.status_code == 200
            assert response.data["workspace_memory_deleted"] == 1
            assert response.data["user_memory_deleted"] == 1

    def test_delete_denies_non_admin(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user, token = editor_user_and_token(tenant, ws)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

            response = client.delete(f"/api/v1/system/memory/workspaces/{ws.id}/")

            assert response.status_code == 403

    def test_delete_unknown_workspace_returns_404(self):
        import uuid

        with active_tenant() as tenant:
            admin_user, token = admin_user_and_token(tenant)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

            response = client.delete(f"/api/v1/system/memory/workspaces/{uuid.uuid4()}/")

            assert response.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && DB_USER=reqogniloom pytest memory/tests/test_memory_rest.py -v -k "Overview or Delete"`
Expected: FAIL with 404 (URL not found, `Resolver404`) for all new tests — the URLs don't exist yet.

- [ ] **Step 3: Write the implementation**

Append to `backend/memory/memory_rest.py`, replacing the final `__all__` line:

```python
from application.base import NotFoundError, PermissionDeniedError
from application.memory_admin_service import MemoryAdminService


class SystemMemoryWorkspaceOverviewView(APIView):
    """``GET /api/v1/system/memory/workspaces/`` — System-Admin only.

    Memory Admin UI Phase 1 (spec 2026-08-26). Lists one row per workspace
    in the active tenant: memory enabled/disabled, entry counts per tier,
    last consolidation timestamp. Delegates to :class:`MemoryAdminService`.
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
        try:
            overview = MemoryAdminService().list_workspace_overview(ctx)
        except PermissionDeniedError:
            return Response(
                build_error_response("PERMISSION_DENIED", lang),
                status=status.HTTP_403_FORBIDDEN,
            )
        return Response({"results": overview})


class SystemMemoryWorkspaceDeleteView(APIView):
    """``DELETE /api/v1/system/memory/workspaces/<uuid:workspace_id>/``.

    System-Admin only. Deletes BOTH tiers: the workspace's own
    ``WorkspaceMemory`` rows and its current members' ``UserTenantMemory``
    rows. See :meth:`MemoryAdminService.delete_workspace_memory`.
    """

    permission_classes = [HasOperationPermission]

    def delete(self, request: Request, workspace_id: str, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
        except Exception:
            return Response(
                build_error_response("AUTHENTICATION_REQUIRED", lang),
                status=status.HTTP_401_UNAUTHORIZED,
            )
        try:
            result = MemoryAdminService().delete_workspace_memory(ctx, workspace_id)
        except PermissionDeniedError:
            return Response(
                build_error_response("PERMISSION_DENIED", lang),
                status=status.HTTP_403_FORBIDDEN,
            )
        except NotFoundError as exc:
            return Response(
                build_error_response("NOT_FOUND", lang, message=str(exc)),
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(result)


__all__ = [
    "SystemMemorySettingsView",
    "WorkspaceMemorySettingsView",
    "SystemMemoryWorkspaceOverviewView",
    "SystemMemoryWorkspaceDeleteView",
]
```

Move the two new imports (`from application.base import ...` and `from application.memory_admin_service import MemoryAdminService`) up to the top of the file, next to the existing imports (after `from memory.models import WorkspaceMemorySettings`), so all imports stay grouped at the top per PEP 8 — do not leave them inline before the class as shown above; that placement above is only to show which lines are new.

Modify `backend/rest_api/urls.py:56`, replacing the existing import line:

```python
from memory.memory_rest import (
    SystemMemorySettingsView,
    SystemMemoryWorkspaceDeleteView,
    SystemMemoryWorkspaceOverviewView,
    WorkspaceMemorySettingsView,
)
```

Modify `backend/rest_api/urls.py`, inserting these two `path()` entries immediately after the existing `system/memory-settings/` entry (after line 466's closing `),`):

```python
    # AI Long-Term Memory — System-Admin workspace overview + delete
    # (Memory Admin UI Phase 1, spec 2026-08-26).
    path(
        "system/memory/workspaces/",
        SystemMemoryWorkspaceOverviewView.as_view(),
        name="system-memory-workspace-overview",
    ),
    path(
        "system/memory/workspaces/<uuid:workspace_id>/",
        SystemMemoryWorkspaceDeleteView.as_view(),
        name="system-memory-workspace-delete",
    ),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && DB_USER=reqogniloom pytest memory/tests/test_memory_rest.py -v`
Expected: PASS (all tests in the file, old and new)

- [ ] **Step 5: Commit**

```bash
git add backend/memory/memory_rest.py backend/rest_api/urls.py backend/memory/tests/test_memory_rest.py
git commit -m "feat: add system memory workspace overview/delete REST endpoints"
```

---

### Task 3: Frontend — Memory tab in System Settings

**Files:**
- Create: `frontend/src/api/memoryAdmin.ts`
- Create: `frontend/src/components/SystemSettings/MemoryManagementSection.tsx`
- Create: `frontend/src/components/SystemSettings/MemoryManagementSection.module.css`
- Create: `frontend/src/components/SystemSettings/MemoryManagementSection.test.tsx`
- Modify: `frontend/src/components/SystemSettings/SystemSettings.tsx`
- Modify: `frontend/src/i18n/locales/de.json` (add `systemSettings.tabs.memory` + `systemSettings."memory.*"` keys)
- Modify: `frontend/src/i18n/locales/en.json` (same keys, English text)

**Interfaces:**
- Consumes: `apiClient` from `./client` (`.get<T>(path)`, `.delete<T>(path)`), backend contract from Task 2 (`GET /system/memory/workspaces/` -> `{results: [...]}`, `DELETE /system/memory/workspaces/{id}/` -> `{workspace_id, workspace_memory_deleted, user_memory_deleted}`), `Dialog` from `../shared/Dialog` (props: `title`, `onClose`, `size`, `testId`, `footer`, children — see `WorkspaceAdminSection.tsx`'s delete modal for exact usage).
- Produces: `memoryAdminApi.listWorkspaceOverview()`, `memoryAdminApi.deleteWorkspaceMemory(workspaceId)`, exported `WorkspaceMemoryOverviewRow`/`WorkspaceMemoryDeleteResult` types, and `<MemoryManagementSection />` component mounted as the 4th `SystemSettings` tab (`activeTab === "memory"`).

- [ ] **Step 1: Write the API client**

Create `frontend/src/api/memoryAdmin.ts`:

```ts
/**
 * ARCH-L1-001 ReactFrontend — Memory Admin API (Memory Admin UI Phase 1).
 *
 * Wraps the System-Admin-only endpoints:
 *   GET    /api/v1/system/memory/workspaces/           — per-workspace overview
 *   DELETE /api/v1/system/memory/workspaces/<uuid>/     — delete both memory tiers
 */

import { apiClient } from "./client";
import type { UUID } from "../types";

export interface WorkspaceMemoryOverviewRow {
  workspace_id: UUID;
  workspace_name: string;
  enabled: boolean;
  workspace_entry_count: number;
  user_entry_count: number;
  last_consolidated_at: string | null;
}

export interface WorkspaceMemoryDeleteResult {
  workspace_id: UUID;
  workspace_memory_deleted: number;
  user_memory_deleted: number;
}

export const memoryAdminApi = {
  listWorkspaceOverview(): Promise<{ results: WorkspaceMemoryOverviewRow[] }> {
    return apiClient.get<{ results: WorkspaceMemoryOverviewRow[] }>(
      "/system/memory/workspaces/"
    );
  },

  deleteWorkspaceMemory(workspaceId: UUID): Promise<WorkspaceMemoryDeleteResult> {
    return apiClient.delete<WorkspaceMemoryDeleteResult>(
      `/system/memory/workspaces/${workspaceId}/`
    );
  },
};
```

- [ ] **Step 2: Add locale keys**

In `frontend/src/i18n/locales/de.json`, inside the existing `"systemSettings": { ... }` object: add `"memory": "Memory"` inside the existing `"tabs": { ... }` sub-object (alongside `administration`/`workflowDefaults`/`permissionDefaults`), and add these flat-dotted keys as siblings of the existing `"themes.*"` keys (same object, same convention):

```json
    "memory.heading": "Memory-Übersicht",
    "memory.hint": "Pro Workspace: Memory-Status, Anzahl Einträge je Ebene, letzte Konsolidierung. Löschen entfernt Workspace-Memory und das Tenant-Memory der aktuellen Workspace-Mitglieder unwiderruflich.",
    "memory.colWorkspace": "Workspace",
    "memory.colEnabled": "Aktiv",
    "memory.colWorkspaceEntries": "Workspace-Einträge",
    "memory.colUserEntries": "User-Einträge",
    "memory.colLastConsolidated": "Letzte Konsolidierung",
    "memory.deleteButton": "Löschen",
    "memory.deleteConfirmTitle": "Memory löschen",
    "memory.deleteConfirmBody": "{{wsCount}} Workspace-Einträge und {{userCount}} User-Einträge für \"{{workspace}}\" werden unwiderruflich gelöscht.",
    "memory.deleteConfirmButton": "Endgültig löschen",
    "memory.noWorkspaces": "Keine Workspaces gefunden.",
    "memory.loadError": "Memory-Übersicht konnte nicht geladen werden."
```

In `frontend/src/i18n/locales/en.json`, the same keys in the same two places with English text:

```json
    "memory.heading": "Memory Overview",
    "memory.hint": "Per workspace: memory status, entry counts per tier, last consolidation. Deleting permanently removes workspace memory and the tenant memory of the workspace's current members.",
    "memory.colWorkspace": "Workspace",
    "memory.colEnabled": "Enabled",
    "memory.colWorkspaceEntries": "Workspace Entries",
    "memory.colUserEntries": "User Entries",
    "memory.colLastConsolidated": "Last Consolidated",
    "memory.deleteButton": "Delete",
    "memory.deleteConfirmTitle": "Delete Memory",
    "memory.deleteConfirmBody": "{{wsCount}} workspace entries and {{userCount}} user entries for \"{{workspace}}\" will be permanently deleted.",
    "memory.deleteConfirmButton": "Permanently Delete",
    "memory.noWorkspaces": "No workspaces found.",
    "memory.loadError": "Failed to load memory overview."
```

And `"memory": "Memory"` inside `en.json`'s `systemSettings.tabs` object.

- [ ] **Step 3: Write the failing component test**

Create `frontend/src/components/SystemSettings/MemoryManagementSection.test.tsx`:

```tsx
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { MemoryManagementSection } from "./MemoryManagementSection";
import { memoryAdminApi } from "../../api/memoryAdmin";

vi.mock("../../api/memoryAdmin", () => ({
  memoryAdminApi: {
    listWorkspaceOverview: vi.fn(),
    deleteWorkspaceMemory: vi.fn(),
  },
}));

const ROW = {
  workspace_id: "11111111-1111-1111-1111-111111111111",
  workspace_name: "Acme Project",
  enabled: true,
  workspace_entry_count: 5,
  user_entry_count: 2,
  last_consolidated_at: "2026-08-20T10:00:00Z",
};

describe("MemoryManagementSection", () => {
  beforeEach(() => {
    vi.mocked(memoryAdminApi.listWorkspaceOverview).mockResolvedValue({ results: [ROW] });
    vi.mocked(memoryAdminApi.deleteWorkspaceMemory).mockResolvedValue({
      workspace_id: ROW.workspace_id,
      workspace_memory_deleted: 5,
      user_memory_deleted: 2,
    });
  });

  it("renders a row per workspace with counts", async () => {
    render(<MemoryManagementSection />);

    const row = await screen.findByTestId(`memory-row-${ROW.workspace_id}`);
    expect(within(row).getByText("Acme Project")).toBeInTheDocument();
    expect(within(row).getByText("5")).toBeInTheDocument();
    expect(within(row).getByText("2")).toBeInTheDocument();
  });

  it("shows an empty state when there are no workspaces", async () => {
    vi.mocked(memoryAdminApi.listWorkspaceOverview).mockResolvedValue({ results: [] });

    render(<MemoryManagementSection />);

    expect(await screen.findByTestId("memory-management-empty")).toBeInTheDocument();
  });

  it("delete flow: opens confirm dialog, confirms, calls API, reloads", async () => {
    const user = userEvent.setup();
    render(<MemoryManagementSection />);

    const row = await screen.findByTestId(`memory-row-${ROW.workspace_id}`);
    await user.click(within(row).getByTestId(`memory-delete-btn-${ROW.workspace_id}`));

    const dialog = await screen.findByTestId("memory-delete-confirm-dialog");
    expect(within(dialog).getByText(/5/)).toBeInTheDocument();
    expect(within(dialog).getByText(/2/)).toBeInTheDocument();

    vi.mocked(memoryAdminApi.listWorkspaceOverview).mockResolvedValue({ results: [] });
    await user.click(within(dialog).getByTestId("memory-delete-confirm-btn"));

    await waitFor(() => {
      expect(memoryAdminApi.deleteWorkspaceMemory).toHaveBeenCalledWith(ROW.workspace_id);
    });
    await waitFor(() => {
      expect(screen.queryByTestId("memory-delete-confirm-dialog")).not.toBeInTheDocument();
    });
    expect(await screen.findByTestId("memory-management-empty")).toBeInTheDocument();
  });
});
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/components/SystemSettings/MemoryManagementSection.test.tsx`
Expected: FAIL — `Cannot find module './MemoryManagementSection'`

- [ ] **Step 5: Write the component**

Create `frontend/src/components/SystemSettings/MemoryManagementSection.module.css`:

```css
.section {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-5);
  margin-bottom: var(--space-5);
  box-shadow: var(--shadow-card);
}

.hint {
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
  margin-top: 0;
  margin-bottom: var(--space-4);
}

.table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--font-size-sm);
}

.table th {
  text-align: left;
  color: var(--color-text-muted);
  font-weight: 600;
  padding: var(--space-2) var(--space-3);
  border-bottom: 1px solid var(--color-border);
}

.table td {
  padding: var(--space-2) var(--space-3);
  border-bottom: 1px solid var(--color-border);
}

.deleteBtn {
  background: var(--color-danger);
  color: white;
  border: none;
  border-radius: var(--radius-md);
  padding: var(--space-2) var(--space-3);
  font-size: var(--font-size-sm);
  font-weight: 600;
  cursor: pointer;
}

.empty {
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
  padding: var(--space-4) 0;
}

.error {
  color: var(--color-danger);
  font-size: var(--font-size-sm);
  padding: var(--space-3) 0;
}
```

Create `frontend/src/components/SystemSettings/MemoryManagementSection.tsx`:

```tsx
/**
 * Memory Admin UI Phase 1 (spec 2026-08-26) — System-Admin workspace
 * memory overview + delete, mounted as the "memory" tab in SystemSettings.
 */

import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  memoryAdminApi,
  type WorkspaceMemoryOverviewRow,
} from "../../api/memoryAdmin";
import { Dialog } from "../shared/Dialog";
import styles from "./MemoryManagementSection.module.css";

function extractErrorMessage(err: unknown): string {
  const e = err as { error?: { message?: string }; message?: string };
  return e?.error?.message ?? e?.message ?? String(err);
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export function MemoryManagementSection(): JSX.Element {
  const { t } = useTranslation();
  const [rows, setRows] = useState<WorkspaceMemoryOverviewRow[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<WorkspaceMemoryOverviewRow | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const reload = useCallback((): void => {
    memoryAdminApi
      .listWorkspaceOverview()
      .then((r) => {
        setRows(r.results);
        setLoadError(null);
      })
      .catch((err: unknown) => {
        setLoadError(extractErrorMessage(err) || t("systemSettings.memory.loadError"));
      });
  }, [t]);

  useEffect(() => {
    reload();
  }, [reload]);

  const handleDelete = useCallback(async (): Promise<void> => {
    if (!pendingDelete) return;
    setIsDeleting(true);
    setDeleteError(null);
    try {
      await memoryAdminApi.deleteWorkspaceMemory(pendingDelete.workspace_id);
      setPendingDelete(null);
      reload();
    } catch (err: unknown) {
      setDeleteError(extractErrorMessage(err));
    } finally {
      setIsDeleting(false);
    }
  }, [pendingDelete, reload]);

  return (
    <section className={styles.section} data-testid="memory-management-section">
      <h3>{t("systemSettings.memory.heading")}</h3>
      <p className={styles.hint}>{t("systemSettings.memory.hint")}</p>

      {loadError && (
        <p role="alert" data-testid="memory-management-error" className={styles.error}>
          {loadError}
        </p>
      )}

      {!loadError && rows.length === 0 && (
        <p data-testid="memory-management-empty" className={styles.empty}>
          {t("systemSettings.memory.noWorkspaces")}
        </p>
      )}

      {rows.length > 0 && (
        <table className={styles.table} data-testid="memory-management-table">
          <thead>
            <tr>
              <th>{t("systemSettings.memory.colWorkspace")}</th>
              <th>{t("systemSettings.memory.colEnabled")}</th>
              <th>{t("systemSettings.memory.colWorkspaceEntries")}</th>
              <th>{t("systemSettings.memory.colUserEntries")}</th>
              <th>{t("systemSettings.memory.colLastConsolidated")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.workspace_id} data-testid={`memory-row-${row.workspace_id}`}>
                <td>{row.workspace_name}</td>
                <td>{row.enabled ? "✓" : "—"}</td>
                <td>{row.workspace_entry_count}</td>
                <td>{row.user_entry_count}</td>
                <td>{formatDate(row.last_consolidated_at)}</td>
                <td>
                  <button
                    type="button"
                    className={styles.deleteBtn}
                    data-testid={`memory-delete-btn-${row.workspace_id}`}
                    onClick={() => {
                      setDeleteError(null);
                      setPendingDelete(row);
                    }}
                  >
                    {t("systemSettings.memory.deleteButton")}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {pendingDelete && (
        <Dialog
          title={t("systemSettings.memory.deleteConfirmTitle")}
          onClose={() => setPendingDelete(null)}
          size="sm"
          testId="memory-delete-confirm-dialog"
          footer={
            <div style={{ display: "flex", gap: "var(--space-2)" }}>
              <button type="button" onClick={() => setPendingDelete(null)}>
                {t("actions.cancel", "Cancel")}
              </button>
              <button
                type="button"
                data-testid="memory-delete-confirm-btn"
                disabled={isDeleting}
                onClick={() => void handleDelete()}
                className={styles.deleteBtn}
              >
                {isDeleting ? "…" : t("systemSettings.memory.deleteConfirmButton")}
              </button>
            </div>
          }
        >
          <p>
            {t("systemSettings.memory.deleteConfirmBody", {
              wsCount: pendingDelete.workspace_entry_count,
              userCount: pendingDelete.user_entry_count,
              workspace: pendingDelete.workspace_name,
            })}
          </p>
          {deleteError && (
            <p role="alert" className={styles.error}>
              {deleteError}
            </p>
          )}
        </Dialog>
      )}
    </section>
  );
}
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `cd frontend && npx vitest run src/components/SystemSettings/MemoryManagementSection.test.tsx`
Expected: PASS (3 tests)

- [ ] **Step 7: Wire the new tab into `SystemSettings.tsx`**

In `frontend/src/components/SystemSettings/SystemSettings.tsx`, make these four edits:

1. Add the import (next to the other section imports):

```tsx
import { MemoryManagementSection } from "./MemoryManagementSection";
```

2. Extend the tab type and list (`SystemTabId` union and `TAB_IDS` array):

```tsx
type SystemTabId = "administration" | "workflow-defaults" | "permission-defaults" | "memory";

const TAB_IDS: SystemTabId[] = [
  "administration",
  "workflow-defaults",
  "permission-defaults",
  "memory",
];
```

3. Add the tab button entry to the `TABS` array (after `permission-defaults`):

```tsx
    { id: "memory", label: t("systemSettings.tabs.memory", "Memory") },
```

4. Add the tab panel content (after the `permission-defaults` panel):

```tsx
        {activeTab === "memory" && <MemoryManagementSection />}
```

- [ ] **Step 8: Run the full frontend test suite for this directory**

Run: `cd frontend && npx vitest run src/components/SystemSettings/`
Expected: PASS (all tests in `SystemSettings/`, old and new)

- [ ] **Step 9: Run the i18n parity test**

Run: `cd frontend && npx vitest run src/test/i18n-parity.test.ts`
Expected: PASS (de.json and en.json still have identical flattened key sets)

- [ ] **Step 10: Commit**

```bash
git add frontend/src/api/memoryAdmin.ts \
        frontend/src/components/SystemSettings/MemoryManagementSection.tsx \
        frontend/src/components/SystemSettings/MemoryManagementSection.module.css \
        frontend/src/components/SystemSettings/MemoryManagementSection.test.tsx \
        frontend/src/components/SystemSettings/SystemSettings.tsx \
        frontend/src/i18n/locales/de.json \
        frontend/src/i18n/locales/en.json
git commit -m "feat: add Memory tab with workspace overview and delete to System Settings"
```

---

## Post-Plan Note

This plan implements Phase 1 only. Phases 2-5 (health-check rows, settings override, user self-service, visualization) are separate future plans against the same spec (`docs/superpowers/specs/2026-08-26-memory-admin-ui-design.md`) and are NOT part of this plan's scope.

**Deviation from the spec, discovered while writing this plan:** the spec's Phase 1 table included an "Embedding-Provider/Dimension" column sourced from a per-entry "EmbeddingProvider metadata field." No such field exists — `WorkspaceMemory`/`UserTenantMemory` hardcode `VectorField(dimensions=384)` at the schema level with no per-row provider/dimension metadata anywhere. This plan's overview table omits that column; the currently active embedding provider is a tenant-wide fact already exposed by the existing `GET /api/v1/system/memory-settings/` endpoint (Phase 3's concern), not a per-workspace one.
