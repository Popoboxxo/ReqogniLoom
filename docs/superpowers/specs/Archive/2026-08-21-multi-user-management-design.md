# Multi-User Management — Design Spec

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:writing-plans to
> turn this spec into an implementation plan, then execute via
> superpowers:subagent-driven-development or superpowers:executing-plans.

**Goal:** Complete multi-user functionality — creating, activating and
deactivating users — consistent with the roles already conceptualised in the
system, with the hard invariant that the system can never lose its last
active admin, at either the workspace or the tenant level.

**Architecture:** Extend the existing custom RBAC model (`UserRole`,
workspace-scoped) with a new, symmetric `TenantRole` model for a tenant-wide
admin concept. All mutating logic lives in the service layer
(`auth_tenancy/services/`); REST views and MCP tools are thin callers of the
same methods, so the two transports cannot drift apart. Django/DRF idioms
(`set_password()`, `ModelViewSet`+`Serializer`, `transaction.atomic()` +
`select_for_update()`) are used throughout, inside the project's existing
custom-RBAC architecture — not a switch to Django's built-in
Group/Permission system, which would introduce a second, parallel RBAC
model.

**Tech Stack:** Django 4.2+ / DRF (backend), React 18 + TypeScript (frontend
UI), the project's native MCP server (JSON-RPC 2.0 tool groups), PostgreSQL
(row-level locking for the last-admin race-condition guard).

**Spec:** this document. No separate spec exists for the prior
multi-palette-theming work; this is a new, independent design.

## Global Constraints

- Every mutation of admin-holding rows (`UserRole`, `TenantRole`,
  `User.is_active`) MUST pass through the service layer's last-admin guard —
  never write these fields directly from a view, serializer, or MCP tool
  handler.
- REST and MCP MUST enforce identical permission decisions for every
  user-management action, verified by a single shared test matrix consumed
  by both test suites (no per-surface permission logic, no per-surface
  matrix duplication).
- No new RBAC system (Django Group/Permission) is introduced; `TenantRole`
  mirrors the existing `UserRole` pattern exactly (same fields:
  `assigned_by`, `suspended_at`, `unique_together`).
- No email/invite infrastructure is introduced. User creation sets an
  initial password directly via `user.set_password()`, matching the
  project's current `user.create` MCP tool behaviour.
- Last-admin protection covers two independent, always-enforced invariants:
  (1) every workspace must retain ≥1 active admin (`UserRole`,
  `role=admin`, `suspended_at=None`, `user.is_active=True`), (2) every
  tenant must retain ≥1 active tenant-admin (`TenantRole`, same shape).
  `User.is_active=False` is checked against BOTH invariants across every
  workspace/tenant the user administers before it is allowed.
- All admin-count checks that gate a mutation MUST run inside
  `transaction.atomic()` with `select_for_update()` on the relevant role
  rows, to close the TOCTOU race between two concurrent last-admin removals.
- Every user-management action is written to the existing audit log via
  `AuditLogWriter`, matching the project's Audit-Compliance NFR.

## 1. Data Model

New model in `backend/auth_tenancy/models.py`, deliberately mirroring
`UserRole`:

```python
class TenantRole(AuditableModel):
    """Tenant-wide admin role — distinct from workspace-scoped UserRole.

    Only role="admin" exists today. Modelled as a role table (not a boolean
    flag on User) for symmetry with UserRole: same audit trail
    (assigned_by), same suspend/reactivate mechanism (suspended_at), same
    last-admin invariant enforcement code shape as the workspace level.
    """

    ROLE_ADMIN = "admin"
    ROLE_CHOICES = [(ROLE_ADMIN, "Admin")]

    tenant = models.ForeignKey(
        "persistence.Tenant", on_delete=models.CASCADE, related_name="tenant_roles"
    )
    user = models.ForeignKey(
        "persistence.User", on_delete=models.CASCADE, related_name="tenant_roles"
    )
    role = models.CharField(max_length=32, choices=ROLE_CHOICES, default=ROLE_ADMIN)
    assigned_by = models.ForeignKey(
        "persistence.User", null=True, on_delete=models.SET_NULL, related_name="+"
    )
    suspended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "at_tenant_role"
        unique_together = ("tenant", "user", "role")
```

**Migration + backfill:** the migration that creates `at_tenant_role` MUST
include a data migration that gives every existing tenant its first
tenant-admin, or the invariant is violated the moment this ships. Rule
(deterministic, no manual step): for each `Tenant`, take the `User` with the
earliest-created active `UserRole(role=admin, suspended_at=None)` across
that tenant's workspaces and create a `TenantRole(role=admin)` row for them,
`assigned_by=None` (system-assigned). A tenant with zero workspace admins
(should not exist given the pre-existing `0008_backfill_admin_roles...`
migration, but guard anyway) gets no row and is logged as a warning for
manual follow-up — do not silently invent a user.

## 2. Last-Admin Invariant Enforcement

Two independent, symmetrically-implemented checks, both living in the
service layer:

**Workspace level** — `AuthorizationService`
(`auth_tenancy/services/authorization.py`):
- `revoke_role(user, workspace, role)` and a new `suspend_role(user,
  workspace, role)` each, before mutating, run inside
  `transaction.atomic()` + `select_for_update()` on the workspace's
  `UserRole(role=admin, suspended_at=None)` rows, count remaining active
  admins EXCLUDING the target user, and raise `LastAdminError` (new
  exception, same shape as existing `WorkflowTransitionError`) if that
  count would reach 0.
- A new `reactivate_role(user, workspace, role)` clears `suspended_at`
  (no last-admin check needed — this only adds admins back).

**Tenant level** — same shape, new methods on `AuthorizationService` (or a
`TenantAuthorizationService` if the file would otherwise grow past a
reasonable size — decide at plan-writing time by reading the current file
length) operating on `TenantRole` instead of `UserRole`.

**Account deactivation is the connecting case:** the service method behind
`User.is_active=False` (currently a bare field write in the MCP
`user.deactivate` tool) MUST become a single service method,
`UserAccountService.deactivate(user, actor)`, that — inside one
`transaction.atomic()` — locks and checks EVERY workspace where this user
holds an active admin role AND their tenant-admin row (if any), refusing
the deactivation with a specific `LastAdminError` (naming the workspace or
"tenant") if any of them would drop to zero. `user.activate` /
`UserAccountService.activate` has no such check (activating never removes
an admin).

## 3. Permission Model & REST↔MCP Consistency

Single source of truth: a plain Python matrix constant in
`auth_tenancy/tests/user_management_matrix.py`, imported by both the REST
and MCP test suites — never hand-duplicated.

| Action | tenant-admin | workspace-admin (own WS) | editor | viewer | approver | no role |
|---|---|---|---|---|---|---|
| `user.create` | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `user.activate` / `user.deactivate` | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `workspace.assign_role` | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| `workspace.suspend_role` / `reactivate_role` | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| `tenant.assign_admin` / `revoke_admin` | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |

Second dimension, crossed with every removing action: `{is last workspace
admin: yes/no} × {is last tenant admin: yes/no} → ALLOW / BLOCKED
(LastAdminError)`.

Because REST views and MCP tools both call the exact same service methods
(`AuthorizationService.*`, `UserAccountService.*`), there is no code path
where the two surfaces could return different allow/deny decisions for the
same actor+action — the matrix test suite exists to prove this stays true,
not to be the only thing keeping it true.

## 4. API Surface

**REST** (`rest_api/`, `ModelViewSet` + `Serializer`, following existing
ViewSet conventions):

| Endpoint | Method | Auth |
|---|---|---|
| `/api/v1/users/` | GET (list), POST (create) | tenant-admin |
| `/api/v1/users/{id}/activate/` | POST | tenant-admin, last-admin n/a |
| `/api/v1/users/{id}/deactivate/` | POST | tenant-admin, last-admin gated |
| `/api/v1/users/{id}/tenant-admin/` | POST / DELETE | tenant-admin, last-admin gated |
| `/api/v1/workspaces/{id}/members/` | POST (assign role) — extends the existing GET-only `WorkspaceMembersView` | workspace-admin or tenant-admin |
| `/api/v1/workspaces/{id}/members/{user_id}/suspend/` \| `/reactivate/` | POST | workspace-admin or tenant-admin, last-admin gated |

**MCP** (`mcp_server/tools/users.py`, `UsersToolGroup`):

Unchanged contract, now routed through the same services:
`user.create`, `user.list`, `user.assign_role`, `user.deactivate`.

New tools (close today's gaps):
`user.activate`, `user.suspend_role`, `user.reactivate_role`,
`user.assign_tenant_admin`, `user.revoke_tenant_admin` — deliberately
separate tools rather than overloading `assign_role` with an optional/null
`workspace_id`, matching the project's existing one-tool-per-action
granularity.

## 5. Frontend UI

New `frontend/src/components/Settings/UserManagement/UserManagement.tsx`,
visible only to tenant-admins (role-gated like other Settings sections),
following the `WorkspaceSettings.tsx` form + `api`-wrapper + persistence
pattern:
- User list: username, email, active/inactive badge, tenant-admin badge,
  per-workspace role summary.
- "Create user" dialog: username, email, password.
- Row actions: activate/deactivate, grant/revoke tenant-admin — a
  `LastAdminError` from the API surfaces as an inline error naming the
  blocking workspace/tenant, not a generic failure toast.
- Existing workspace members view gains suspend/reactivate actions for
  workspace-admins.

New `frontend/src/api/users.ts` wrapper; new i18n keys under
`settings.userManagement.*` (DE/EN, `frontend/src/i18n/locales/`).

## 6. Edge Cases

- **Race condition:** two concurrent requests removing the last two admins
  could both pass a naive "≥1 will remain" check before either commits.
  Closed by `select_for_update()` inside `transaction.atomic()` around the
  count-and-mutate step (§2) — standard Django defense against this TOCTOU
  class.
- **Self-deactivation:** allowed as long as the actor is not the last
  admin — no extra restriction beyond the invariant itself (YAGNI; matches
  Django's own `is_superuser` self-deactivation behaviour).
- **Bootstrap:** `auth_tenancy/management/commands/bootstrap_admin.py` must
  additionally create the tenant's first `TenantRole(admin)` row, not just
  the workspace `UserRole(admin)` it creates today.
- **Audit:** every action in this spec (create, activate, deactivate,
  assign/suspend/reactivate role, assign/revoke tenant-admin) is written to
  the existing audit log via `AuditLogWriter`.

## 7. Test Plan

1. `TenantRole` model + migration/backfill tests (backend/auth_tenancy or
   backend/persistence migration test conventions).
2. Last-admin invariant unit tests — both levels, including a
   concurrency/race test exercising `select_for_update()` under two
   simultaneous removal attempts.
3. REST↔MCP consistency matrix tests, parametrized from the shared
   `user_management_matrix.py` constant (§3), one run against
   `ToolRegistry.dispatch_request` (mirroring
   `test_mcp_rbac_role_matrix.py`'s real-DB-role-resolution style) and one
   against DRF `APIClient`.
4. REST API tests: CRUD, validation, error codes (409/400 for
   `LastAdminError`, matching the project's existing error-envelope
   convention).
5. MCP tool tests for every new tool (`user.activate`, `suspend_role`,
   `reactivate_role`, `assign_tenant_admin`, `revoke_tenant_admin`).
6. Frontend component tests (Vitest) for `UserManagement.tsx` and the
   extended workspace-members UI, including last-admin error rendering.
7. At least one Playwright E2E test covering the full admin flow through
   the real UI: create user → assign workspace role → deactivate →
   reactivate.
8. `bootstrap_admin` command test updated to assert the first
   `TenantRole(admin)` row is created alongside the workspace admin role.
