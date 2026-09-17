# Multi-User Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete multi-user functionality — create/activate/deactivate users, workspace-role and new tenant-admin management — with an always-enforced invariant that no workspace or tenant can ever drop to zero active admins, surfaced identically through REST and MCP.

**Architecture:** A new `TenantRole` model mirrors the existing workspace-scoped `UserRole` model exactly (same fields, same `TenantScopedModel` base, same suspend/reactivate mechanism). All mutating logic — role assignment, suspension, revocation, account activation/deactivation, and every last-admin check — lives in `auth_tenancy/services/`. REST views (`rest_api/`, `auth_tenancy/`) and MCP tools (`mcp_server/tools/users.py`) are thin callers of those same service methods, so the two transports cannot diverge. Race-condition protection uses `transaction.atomic()` + `select_for_update()`, standard Django practice for count-then-mutate invariants.

**Tech Stack:** Django 4.2+, DRF (plain `ViewSet` classes per this codebase's convention — not `ModelViewSet`, since ADR-01 forbids direct model access from views), the project's native MCP tool-group pattern, React 18 + TypeScript, PostgreSQL row locking.

**Spec:** `docs/superpowers/specs/2026-08-21-multi-user-management-design.md`

## Global Constraints

- Every mutation of `UserRole`, `TenantRole`, or `User.is_active` for a user who holds an admin role anywhere MUST go through a service-layer method that runs the last-admin check — never write these fields directly from a view, serializer, or MCP tool handler (mirrors the existing rule violated only by today's `user.deactivate`, which this plan fixes).
- Every last-admin count-then-mutate check runs inside `transaction.atomic()` with `select_for_update()` on the relevant role rows.
- `TenantRole` inherits `persistence.TenantScopedModel` (NOT a manually-declared `tenant` FK — `TenantScopedModel` already provides `tenant`, the tenant-scoped `objects` manager, and the `unscoped` escape hatch), exactly like `UserRole` does.
- No Django Group/Permission system is introduced. `TenantRole` follows the exact shape of `UserRole` (`role`, `assigned_by`, `suspended_at`, `unique_together`).
- No email/invite infrastructure. `user.create` (existing MCP tool, unchanged contract) and the new REST create endpoint both use `user.set_password()` directly.
- REST and MCP permission decisions for every user-management action are verified identical via one shared Python matrix constant (`auth_tenancy/tests/user_management_matrix.py`), imported by both test suites — never hand-duplicated.
- Every action in this plan is written to the audit log: REST via the existing `audit.services.log_write` (same call `write_mcp_audit` wraps for MCP), MCP via `write_mcp_audit` (`mcp_server/tools/base.py`).
- Follow existing file conventions exactly: services in `auth_tenancy/services/authorization.py` (or a new sibling file only if that file would otherwise exceed ~700 lines after this plan's additions — check line count at Task 2 time and decide then, not preemptively), REST views as plain `rest_framework.viewsets.ViewSet` subclasses (see `rest_api/api_key_views.py`, `auth_tenancy/rest_workspace_members.py`), MCP tools inside the existing `UsersToolGroup` (`mcp_server/tools/users.py`).

---

### Task 1: `TenantRole` model + migration + backfill

**Files:**
- Modify: `backend/auth_tenancy/models.py` (add `TenantRole` after `UserRole`, ~line 155)
- Create: `backend/auth_tenancy/migrations/0009_add_tenant_role.py`
- Create: `backend/auth_tenancy/migrations/0010_backfill_tenant_admins.py`
- Test: `backend/auth_tenancy/tests/test_tenant_role_model.py`
- Test: `backend/auth_tenancy/tests/test_backfill_tenant_admins.py`

**Interfaces:**
- Produces: `TenantRole` model — `tenant` (from `TenantScopedModel`), `user` (FK to `persistence.User`), `role` (`"admin"` only today), `assigned_by` (nullable FK), `suspended_at` (nullable), `db_table="at_tenant_role"`, `unique_together=("tenant", "user", "role")`. Later tasks query it as `TenantRole.objects.filter(tenant_id=..., role=TenantRole.ROLE_ADMIN, suspended_at__isnull=True)`.

- [ ] **Step 1: Write the failing model test**

```python
# backend/auth_tenancy/tests/test_tenant_role_model.py
from __future__ import annotations

import pytest
from django.db import IntegrityError

from auth_tenancy.models import TenantRole
from persistence.models import Tenant, User
from persistence.tenancy import TenantContext


@pytest.fixture(autouse=True)
def _clear_tenant_context():
    TenantContext.clear_tenant()
    yield
    TenantContext.clear_tenant()


@pytest.mark.django_db
def test_tenant_role_admin_can_be_created():
    tenant = Tenant.objects.create(name="T", slug="tr-model-t")
    user = User.objects.create(username="tr-user", email="tr@t.test", tenant=tenant)
    TenantContext.set_tenant(tenant.id)
    role = TenantRole.objects.create(
        tenant=tenant, user=user, role=TenantRole.ROLE_ADMIN
    )
    assert role.role == "admin"
    assert role.suspended_at is None
    assert role.is_active is True


@pytest.mark.django_db
def test_tenant_role_unique_together_blocks_duplicate():
    tenant = Tenant.objects.create(name="T2", slug="tr-model-t2")
    user = User.objects.create(username="tr-user2", email="tr2@t.test", tenant=tenant)
    TenantContext.set_tenant(tenant.id)
    TenantRole.objects.create(tenant=tenant, user=user, role=TenantRole.ROLE_ADMIN)
    with pytest.raises(IntegrityError):
        TenantRole.objects.create(tenant=tenant, user=user, role=TenantRole.ROLE_ADMIN)


@pytest.mark.django_db
def test_tenant_role_is_active_reflects_suspension():
    from datetime import datetime, timezone

    tenant = Tenant.objects.create(name="T3", slug="tr-model-t3")
    user = User.objects.create(username="tr-user3", email="tr3@t.test", tenant=tenant)
    TenantContext.set_tenant(tenant.id)
    role = TenantRole.objects.create(tenant=tenant, user=user, role=TenantRole.ROLE_ADMIN)
    role.suspended_at = datetime.now(timezone.utc)
    role.save(update_fields=["suspended_at"])
    assert role.is_active is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker run --rm --network reqogniloom_default -v "$(pwd)/backend:/app" -w /app -e DB_HOST=postgres -e DB_USER=reqogniloom -e DB_PASSWORD=CHANGE-ME-strong-password -e DB_APP_PASSWORD=CHANGE-ME-strong-app-password -e SECRET_KEY=x -e AUTH_JWT_SECRET=x -e FIELD_ENCRYPTION_KEY="$(python3 -c 'import secrets,base64;print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())')" python:3.12-slim bash -c "pip install -q -r requirements.txt && pytest auth_tenancy/tests/test_tenant_role_model.py -v"` (or use the project's own `run-backend-pytest.sh` helper if one exists in the active worktree)
Expected: FAIL with `ImportError: cannot import name 'TenantRole'`

- [ ] **Step 3: Add the `TenantRole` model**

In `backend/auth_tenancy/models.py`, immediately after the `UserRole` class (after its `is_active` property, before `ItemPermission`):

```python
class TenantRole(TenantScopedModel):
    """Tenant-wide admin role assignment (issue: multi-user management).

    Distinct from the workspace-scoped ``UserRole``: this grants
    administrative authority over the whole tenant (creating users,
    assigning workspace roles across any workspace in the tenant),
    not just one workspace. Only ``role="admin"`` exists today; modelled
    as a role table (not a boolean flag on ``User``) for symmetry with
    ``UserRole`` — same audit trail (``assigned_by``), same
    suspend/reactivate mechanism (``suspended_at``), same last-admin
    invariant enforcement code shape as the workspace level.

    Inherits ``TenantScopedModel``: UUID PK, audit fields, the ``tenant``
    FK and the tenant-isolating default manager.
    """

    ROLE_ADMIN = "admin"
    ROLE_CHOICES = ((ROLE_ADMIN, "Admin"),)

    user = models.ForeignKey(
        "persistence.User",
        on_delete=models.CASCADE,
        related_name="tenant_role_assignments",
    )
    role = models.CharField(max_length=32, choices=ROLE_CHOICES, default=ROLE_ADMIN)
    suspended_at = models.DateTimeField(null=True, blank=True)
    assigned_by = models.ForeignKey(
        "persistence.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        db_table = "at_tenant_role"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "user", "role"],
                name="uq_tenantrole_tenant_user_role",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "user"], name="idx_tenantrole_tenant_user"),
        ]

    def __str__(self) -> str:
        return f"TenantRole({self.user_id}, {self.role}@{self.tenant_id})"

    @property
    def is_active(self) -> bool:
        """Return whether the assignment is effective (not suspended)."""
        return self.suspended_at is None
```

Also add `TenantRole` to the module's `__all__` / import surface wherever `UserRole` is exported (check the top of `auth_tenancy/models.py` for an `__all__` list; if none exists, no change needed — Python has no implicit export list here).

- [ ] **Step 4: Run test to verify the model test passes**

Run the same pytest command as Step 2, targeting `test_tenant_role_model.py`.
Expected: 3 passed (the model doesn't exist as a migration yet — this will actually fail with "relation at_tenant_role does not exist" until Step 5's migration is generated; if so, proceed to Step 5 first, this is expected).

- [ ] **Step 5: Generate the migration**

Run (inside the same docker container as Step 2, with `manage.py` reachable):
`python manage.py makemigrations auth_tenancy --name add_tenant_role`

Verify the generated file is named `0009_add_tenant_role.py` and depends on `("auth_tenancy", "0008_backfill_admin_roles_for_roleless_workspaces")`. Django's autogenerated `CreateModel` operation is sufficient — no hand-editing needed for this migration.

- [ ] **Step 6: Run model + migration tests to verify they pass**

Run: `pytest auth_tenancy/tests/test_tenant_role_model.py -v`
Expected: 3 passed

- [ ] **Step 7: Write the failing backfill migration test**

```python
# backend/auth_tenancy/tests/test_backfill_tenant_admins.py
"""Tests the data migration that gives every existing tenant its first
TenantRole(admin), driven directly (not via migrator harness, matching
this codebase's convention for testing migration RunPython functions —
see test_prompt_template_migration.py for the MigrationExecutor pattern
used elsewhere, though this one is simpler: no schema rollback needed,
just the RunPython function itself, importable directly since it has a
normal module name)."""
from __future__ import annotations

import pytest

from auth_tenancy.migrations.0010_backfill_tenant_admins import (
    backfill_tenant_admins,
)
```

Note for the implementer: a module name starting with a digit cannot be
imported with a dotted `import` statement (`0010_backfill_tenant_admins`
is not a valid Python identifier). Use `importlib.util.spec_from_file_location`
exactly like `backend/persistence/tests/test_prompt_template_migration.py`
does for `_load_split_singleton_rows` — mirror that helper here instead of
the (invalid) import shown above. Full corrected test:

```python
# backend/auth_tenancy/tests/test_backfill_tenant_admins.py
from __future__ import annotations

import importlib.util
import pathlib

import pytest

from auth_tenancy.models import ROLE_ADMIN, TenantRole, UserRole
from persistence.models import Tenant, User, Workspace
from persistence.tenancy import TenantContext

_MIGRATION_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "migrations"
    / "0010_backfill_tenant_admins.py"
)


def _load_backfill_tenant_admins():
    spec = importlib.util.spec_from_file_location(
        "_backfill_tenant_admins_under_test", _MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.backfill_tenant_admins


@pytest.fixture(autouse=True)
def _clear_tenant_context():
    TenantContext.clear_tenant()
    yield
    TenantContext.clear_tenant()


@pytest.mark.django_db
def test_earliest_workspace_admin_becomes_tenant_admin():
    backfill_tenant_admins = _load_backfill_tenant_admins()

    tenant = Tenant.objects.create(name="Backfill T", slug="backfill-t1")
    TenantContext.set_tenant(tenant.id)
    ws = Workspace.objects.create(tenant=tenant, name="WS")
    early_admin = User.objects.create(
        username="early-admin", email="early@t.test", tenant=tenant
    )
    later_admin = User.objects.create(
        username="later-admin", email="later@t.test", tenant=tenant
    )
    UserRole.objects.create(
        tenant=tenant, user=later_admin, workspace=ws, role=ROLE_ADMIN
    )
    early_role = UserRole.objects.create(
        tenant=tenant, user=early_admin, workspace=ws, role=ROLE_ADMIN
    )
    # Force early_role's created_at earlier than later_admin's role, since
    # both were just created in the same test with near-identical timestamps.
    from datetime import timedelta

    UserRole.objects.filter(pk=early_role.pk).update(
        created_at=early_role.created_at - timedelta(days=1)
    )

    backfill_tenant_admins(apps=None, schema_editor=None)

    tenant_admins = TenantRole.unscoped.filter(tenant=tenant, role=ROLE_ADMIN)
    assert tenant_admins.count() == 1
    assert tenant_admins.first().user_id == early_admin.id


@pytest.mark.django_db
def test_tenant_with_no_workspace_admin_gets_no_row():
    backfill_tenant_admins = _load_backfill_tenant_admins()

    tenant = Tenant.objects.create(name="No Admin T", slug="backfill-t2")

    backfill_tenant_admins(apps=None, schema_editor=None)

    assert TenantRole.unscoped.filter(tenant=tenant).count() == 0
```

Note for the implementer: the real migration's `backfill_tenant_admins(apps,
schema_editor)` signature must accept historical models via `apps.get_model(...)`
when run for real by Django's migration executor (see `0008_backfill_admin_roles_for_roleless_workspaces.py`
for the pattern), but this direct-import test calls it with
`apps=None, schema_editor=None` and the function's body must therefore use
`apps.get_model(...)` conditionally OR (simpler, matching this codebase's
existing test convention for `0008`'s style) just use the historical-model
pattern unconditionally — `apps.get_model("auth_tenancy", "TenantRole")`
requires a real `apps` registry. Since this test passes `apps=None`, the
migration function as written for Step 8 below imports the CURRENT
(non-historical) models directly instead of via `apps.get_model`, which is
safe here because the migration runs immediately after `0009_add_tenant_role`
adds the exact same schema the current model reflects (no intervening
schema drift risk within this one two-migration pair). Import
`auth_tenancy.models.TenantRole` and `auth_tenancy.models.UserRole` directly.

- [ ] **Step 8: Run backfill test to verify it fails**

Run: `pytest auth_tenancy/tests/test_backfill_tenant_admins.py -v`
Expected: FAIL — `0010_backfill_tenant_admins.py` does not exist yet.

- [ ] **Step 9: Write the backfill migration**

```python
# backend/auth_tenancy/migrations/0010_backfill_tenant_admins.py
"""Backfill the first TenantRole(admin) for every existing tenant.

Companion migration to 0009_add_tenant_role: without this, every tenant
that existed before this deploy would have zero tenant-admins the moment
the last-admin invariant starts being enforced, permanently locking out
tenant-admin-only actions (user.create, tenant-admin assign/revoke) for
every pre-existing tenant.

Rule (deterministic, no manual step): for each Tenant, promote the User
holding the earliest-created active UserRole(role=admin, suspended_at=None)
across that tenant's workspaces. A tenant with zero workspace admins
(should not exist given 0008's own backfill, but guarded anyway) is left
without a row and must be handled manually — inventing an admin identity
would be worse than leaving a gap visible.

Reverse is a no-op, matching 0008's own reasoning: the created rows are
indistinguishable from legitimate manual assignments once applied.
"""
from __future__ import annotations

from django.db import migrations

ROLE_ADMIN = "admin"


def backfill_tenant_admins(apps, schema_editor):
    """Promote each tenant's earliest workspace admin to tenant-admin."""
    from auth_tenancy.models import TenantRole, UserRole
    from persistence.models import Tenant

    for tenant_id in Tenant.objects.values_list("id", flat=True):
        if TenantRole.unscoped.filter(tenant_id=tenant_id, role=ROLE_ADMIN).exists():
            continue
        earliest_admin_role = (
            UserRole.unscoped.filter(
                tenant_id=tenant_id, role=ROLE_ADMIN, suspended_at__isnull=True
            )
            .order_by("created_at")
            .first()
        )
        if earliest_admin_role is None:
            continue
        TenantRole.unscoped.create(
            tenant_id=tenant_id,
            user_id=earliest_admin_role.user_id,
            role=ROLE_ADMIN,
            assigned_by=None,
        )


def noop_reverse(apps, schema_editor):
    """Intentionally does not revert the grants (see module docstring)."""


class Migration(migrations.Migration):

    dependencies = [
        ("auth_tenancy", "0009_add_tenant_role"),
    ]

    operations = [
        migrations.RunPython(backfill_tenant_admins, noop_reverse),
    ]
```

- [ ] **Step 10: Run backfill test to verify it passes**

Run: `pytest auth_tenancy/tests/test_backfill_tenant_admins.py -v`
Expected: 2 passed

- [ ] **Step 11: Commit**

```bash
git add backend/auth_tenancy/models.py \
        backend/auth_tenancy/migrations/0009_add_tenant_role.py \
        backend/auth_tenancy/migrations/0010_backfill_tenant_admins.py \
        backend/auth_tenancy/tests/test_tenant_role_model.py \
        backend/auth_tenancy/tests/test_backfill_tenant_admins.py
git commit -m "feat: add TenantRole model with backfill for existing tenants"
```

---

### Task 2: Workspace-level last-admin guard

**Files:**
- Modify: `backend/auth_tenancy/services/authorization.py` (add `LastAdminError`, `suspend_role`, `reactivate_role`; modify `revoke_role`)
- Test: `backend/auth_tenancy/tests/test_last_admin_invariant.py` (create — workspace-level cases; Task 3 adds tenant-level cases to this same file)

**Interfaces:**
- Consumes: `UserRole` (Task 1's sibling model, already exists), `AuthorizationService` (existing class in the same file).
- Produces: `LastAdminError(Exception)` — new exception, raised with a message naming the workspace. `AuthorizationService.suspend_role(*, actor_roles, target_user_id, workspace_id, role) -> None`. `AuthorizationService.reactivate_role(*, actor_roles, target_user_id, workspace_id, role) -> None`. `AuthorizationService.revoke_role(...)` — same signature as today, now raises `LastAdminError` instead of silently dropping to zero admins.

- [ ] **Step 1: Write the failing tests**

```python
# backend/auth_tenancy/tests/test_last_admin_invariant.py
from __future__ import annotations

import threading

import pytest
from django.db import connection, transaction

from auth_tenancy.models import ROLE_ADMIN, ROLE_EDITOR, UserRole
from auth_tenancy.services.authorization import (
    AuthorizationService,
    LastAdminError,
)
from persistence.models import Tenant, User, Workspace
from persistence.tenancy import TenantContext


@pytest.fixture(autouse=True)
def _clear_tenant_context():
    TenantContext.clear_tenant()
    yield
    TenantContext.clear_tenant()


def _make_workspace_with_admin(username_suffix: str):
    tenant = Tenant.objects.create(name="LA-T", slug=f"la-t-{username_suffix}")
    TenantContext.set_tenant(tenant.id)
    ws = Workspace.objects.create(tenant=tenant, name="WS")
    admin = User.objects.create(
        username=f"admin-{username_suffix}", email=f"a-{username_suffix}@t.test", tenant=tenant
    )
    role = UserRole.objects.create(tenant=tenant, user=admin, workspace=ws, role=ROLE_ADMIN)
    return tenant, ws, admin, role


@pytest.mark.django_db
def test_revoke_role_blocks_removing_the_last_workspace_admin():
    tenant, ws, admin, _role = _make_workspace_with_admin("solo")
    service = AuthorizationService()

    with pytest.raises(LastAdminError):
        service.revoke_role(
            actor_roles=(ROLE_ADMIN,),
            target_user_id=admin.id,
            workspace_id=ws.id,
            role=ROLE_ADMIN,
        )
    assert UserRole.objects.filter(
        user=admin, workspace=ws, role=ROLE_ADMIN, suspended_at__isnull=True
    ).exists()


@pytest.mark.django_db
def test_revoke_role_allowed_when_another_admin_remains():
    tenant, ws, admin, _role = _make_workspace_with_admin("two-a")
    second_admin = User.objects.create(
        username="admin-two-b", email="two-b@t.test", tenant=tenant
    )
    UserRole.objects.create(tenant=tenant, user=second_admin, workspace=ws, role=ROLE_ADMIN)
    service = AuthorizationService()

    service.revoke_role(
        actor_roles=(ROLE_ADMIN,), target_user_id=admin.id, workspace_id=ws.id, role=ROLE_ADMIN
    )
    assert not UserRole.objects.filter(user=admin, workspace=ws, role=ROLE_ADMIN).exists()


@pytest.mark.django_db
def test_revoke_role_non_admin_role_never_blocked():
    tenant, ws, admin, _role = _make_workspace_with_admin("editor-ok")
    editor = User.objects.create(username="editor-x", email="editor-x@t.test", tenant=tenant)
    UserRole.objects.create(tenant=tenant, user=editor, workspace=ws, role=ROLE_EDITOR)
    service = AuthorizationService()

    service.revoke_role(
        actor_roles=(ROLE_ADMIN,), target_user_id=editor.id, workspace_id=ws.id, role=ROLE_EDITOR
    )
    assert not UserRole.objects.filter(user=editor, workspace=ws, role=ROLE_EDITOR).exists()


@pytest.mark.django_db
def test_suspend_role_blocks_suspending_the_last_workspace_admin():
    tenant, ws, admin, _role = _make_workspace_with_admin("suspend-solo")
    service = AuthorizationService()

    with pytest.raises(LastAdminError):
        service.suspend_role(
            actor_roles=(ROLE_ADMIN,), target_user_id=admin.id, workspace_id=ws.id, role=ROLE_ADMIN
        )
    role = UserRole.objects.get(user=admin, workspace=ws, role=ROLE_ADMIN)
    assert role.suspended_at is None


@pytest.mark.django_db
def test_reactivate_role_has_no_last_admin_check():
    tenant, ws, admin, role = _make_workspace_with_admin("reactivate")
    role.suspended_at = role.created_at
    role.save(update_fields=["suspended_at"])
    service = AuthorizationService()

    service.reactivate_role(
        actor_roles=(ROLE_ADMIN,), target_user_id=admin.id, workspace_id=ws.id, role=ROLE_ADMIN
    )
    role.refresh_from_db()
    assert role.suspended_at is None


@pytest.mark.django_db(transaction=True)
def test_concurrent_revoke_of_last_two_admins_only_one_succeeds():
    """Race-condition guard: two threads try to revoke the last two admins
    of the same workspace simultaneously. select_for_update() must ensure
    only one succeeds and the workspace never drops to zero admins."""
    tenant = Tenant.objects.create(name="Race-T", slug="race-t")
    TenantContext.set_tenant(tenant.id)
    ws = Workspace.objects.create(tenant=tenant, name="Race-WS")
    admin_a = User.objects.create(username="race-a", email="race-a@t.test", tenant=tenant)
    admin_b = User.objects.create(username="race-b", email="race-b@t.test", tenant=tenant)
    UserRole.objects.create(tenant=tenant, user=admin_a, workspace=ws, role=ROLE_ADMIN)
    UserRole.objects.create(tenant=tenant, user=admin_b, workspace=ws, role=ROLE_ADMIN)
    tenant_id, ws_id, a_id, b_id = tenant.id, ws.id, admin_a.id, admin_b.id
    TenantContext.clear_tenant()

    results = {}

    def _revoke(target_user_id, key):
        connection.close()  # force a fresh connection per thread
        TenantContext.set_tenant(tenant_id)
        service = AuthorizationService()
        try:
            service.revoke_role(
                actor_roles=(ROLE_ADMIN,),
                target_user_id=target_user_id,
                workspace_id=ws_id,
                role=ROLE_ADMIN,
            )
            results[key] = "ok"
        except LastAdminError:
            results[key] = "blocked"
        finally:
            TenantContext.clear_tenant()
            connection.close()

    t1 = threading.Thread(target=_revoke, args=(a_id, "a"))
    t2 = threading.Thread(target=_revoke, args=(b_id, "b"))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    TenantContext.set_tenant(tenant_id)
    remaining = UserRole.objects.filter(
        workspace_id=ws_id, role=ROLE_ADMIN, suspended_at__isnull=True
    ).count()
    assert remaining == 1, "workspace must retain exactly one admin, not zero"
    assert sorted(results.values()) == ["blocked", "ok"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest auth_tenancy/tests/test_last_admin_invariant.py -v`
Expected: FAIL — `ImportError: cannot import name 'LastAdminError'`

- [ ] **Step 3: Implement the guard**

In `backend/auth_tenancy/services/authorization.py`, add near the top (after the `Operation` enum, before `_RBAC_MATRIX`):

```python
class LastAdminError(Exception):
    """Raised when a mutation would leave a workspace or tenant with zero
    active admins (multi-user management invariant)."""

    def __init__(self, scope: str, identifier: str) -> None:
        self.scope = scope  # "workspace" or "tenant"
        self.identifier = identifier
        super().__init__(
            f"Cannot complete this action: it would leave {scope} "
            f"{identifier} with no active admin."
        )
```

Add the import `from django.db import transaction` near the top of the file
alongside the existing `from datetime import datetime, timezone` import.

Replace the existing `revoke_role` method body, and add `suspend_role` /
`reactivate_role` immediately after it:

```python
    def revoke_role(
        self,
        *,
        actor_roles: tuple[str, ...],
        target_user_id: UUID,
        workspace_id: UUID,
        role: str,
    ) -> None:
        """Remove a role assignment (admin-guarded, last-admin protected)."""
        if ROLE_ADMIN not in {r.lower() for r in actor_roles}:
            raise PermissionDenied(required_role=ROLE_ADMIN)
        normalized = role.lower()
        with transaction.atomic():
            if normalized == ROLE_ADMIN:
                self._assert_not_last_workspace_admin(
                    workspace_id=workspace_id, excluding_user_id=target_user_id
                )
            UserRole.objects.filter(
                user_id=target_user_id, workspace_id=workspace_id, role=normalized
            ).delete()

    def suspend_role(
        self,
        *,
        actor_roles: tuple[str, ...],
        target_user_id: UUID,
        workspace_id: UUID,
        role: str,
    ) -> None:
        """Soft-suspend a role assignment (admin-guarded, last-admin protected).

        Reversible via :meth:`reactivate_role`, unlike :meth:`revoke_role`
        which deletes the row.
        """
        if ROLE_ADMIN not in {r.lower() for r in actor_roles}:
            raise PermissionDenied(required_role=ROLE_ADMIN)
        normalized = role.lower()
        with transaction.atomic():
            if normalized == ROLE_ADMIN:
                self._assert_not_last_workspace_admin(
                    workspace_id=workspace_id, excluding_user_id=target_user_id
                )
            UserRole.objects.filter(
                user_id=target_user_id,
                workspace_id=workspace_id,
                role=normalized,
                suspended_at__isnull=True,
            ).update(suspended_at=datetime.now(timezone.utc))

    def reactivate_role(
        self,
        *,
        actor_roles: tuple[str, ...],
        target_user_id: UUID,
        workspace_id: UUID,
        role: str,
    ) -> None:
        """Clear ``suspended_at`` on a role assignment (admin-guarded).

        No last-admin check: reactivating only ever adds an admin back.
        """
        if ROLE_ADMIN not in {r.lower() for r in actor_roles}:
            raise PermissionDenied(required_role=ROLE_ADMIN)
        UserRole.objects.filter(
            user_id=target_user_id, workspace_id=workspace_id, role=role.lower()
        ).update(suspended_at=None)

    @staticmethod
    def _assert_not_last_workspace_admin(
        *, workspace_id: UUID, excluding_user_id: UUID
    ) -> None:
        """Raise LastAdminError if removing ``excluding_user_id`` would leave
        ``workspace_id`` with zero active admins.

        MUST be called inside an already-open ``transaction.atomic()`` block
        (see callers above) — ``select_for_update()`` only takes effect
        inside a transaction, and the caller's atomic block is what makes
        the count-then-mutate sequence race-safe.
        """
        remaining = (
            UserRole.objects.select_for_update()
            .filter(workspace_id=workspace_id, role=ROLE_ADMIN, suspended_at__isnull=True)
            .exclude(user_id=excluding_user_id)
            .count()
        )
        if remaining == 0:
            raise LastAdminError(scope="workspace", identifier=str(workspace_id))
```

Update the module's `__all__` list at the bottom of the file to include
`"LastAdminError"`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest auth_tenancy/tests/test_last_admin_invariant.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add backend/auth_tenancy/services/authorization.py \
        backend/auth_tenancy/tests/test_last_admin_invariant.py
git commit -m "feat: enforce last-admin invariant at workspace level"
```

---

### Task 3: Tenant-level last-admin guard + tenant-admin assignment

**Files:**
- Modify: `backend/auth_tenancy/services/authorization.py` (add `assign_tenant_admin`, `revoke_tenant_admin`)
- Modify: `backend/auth_tenancy/tests/test_last_admin_invariant.py` (append tenant-level cases)

**Interfaces:**
- Consumes: `TenantRole` (Task 1), `LastAdminError` (Task 2).
- Produces: `AuthorizationService.assign_tenant_admin(*, actor_is_tenant_admin, target_user_id, tenant_id, assigned_by_user_id) -> TenantRole`. `AuthorizationService.revoke_tenant_admin(*, actor_is_tenant_admin, target_user_id, tenant_id) -> None` (raises `LastAdminError` if `target_user_id` is the last active tenant-admin). `AuthorizationService.is_tenant_admin(user_id, tenant_id) -> bool` (helper, used by Task 4 and REST/MCP callers to resolve `actor_is_tenant_admin`).

- [ ] **Step 1: Write the failing tests (append to the same file from Task 2)**

Append to `backend/auth_tenancy/tests/test_last_admin_invariant.py`:

```python
from auth_tenancy.models import TenantRole


def _make_tenant_with_admin(slug_suffix: str):
    tenant = Tenant.objects.create(name="TA-T", slug=f"ta-t-{slug_suffix}")
    TenantContext.set_tenant(tenant.id)
    admin = User.objects.create(
        username=f"ta-{slug_suffix}", email=f"ta-{slug_suffix}@t.test", tenant=tenant
    )
    role = TenantRole.objects.create(tenant=tenant, user=admin, role=TenantRole.ROLE_ADMIN)
    return tenant, admin, role


@pytest.mark.django_db
def test_is_tenant_admin_true_for_active_row():
    tenant, admin, _role = _make_tenant_with_admin("is-admin")
    service = AuthorizationService()
    assert service.is_tenant_admin(user_id=admin.id, tenant_id=tenant.id) is True


@pytest.mark.django_db
def test_is_tenant_admin_false_for_no_row():
    tenant = Tenant.objects.create(name="TA-none", slug="ta-none")
    non_admin = User.objects.create(username="ta-none-u", email="ta-none@t.test", tenant=tenant)
    service = AuthorizationService()
    assert service.is_tenant_admin(user_id=non_admin.id, tenant_id=tenant.id) is False


@pytest.mark.django_db
def test_assign_tenant_admin_requires_tenant_admin_actor():
    tenant, admin, _role = _make_tenant_with_admin("assign-guard")
    target = User.objects.create(username="ta-target", email="ta-target@t.test", tenant=tenant)
    service = AuthorizationService()

    from auth_tenancy.errors import PermissionDenied

    with pytest.raises(PermissionDenied):
        service.assign_tenant_admin(
            actor_is_tenant_admin=False,
            target_user_id=target.id,
            tenant_id=tenant.id,
            assigned_by_user_id=admin.id,
        )


@pytest.mark.django_db
def test_assign_tenant_admin_succeeds_for_tenant_admin_actor():
    tenant, admin, _role = _make_tenant_with_admin("assign-ok")
    target = User.objects.create(username="ta-target2", email="ta-target2@t.test", tenant=tenant)
    service = AuthorizationService()

    result = service.assign_tenant_admin(
        actor_is_tenant_admin=True,
        target_user_id=target.id,
        tenant_id=tenant.id,
        assigned_by_user_id=admin.id,
    )
    assert result.user_id == target.id
    assert service.is_tenant_admin(user_id=target.id, tenant_id=tenant.id) is True


@pytest.mark.django_db
def test_revoke_tenant_admin_blocks_removing_the_last_one():
    tenant, admin, _role = _make_tenant_with_admin("revoke-solo")
    service = AuthorizationService()

    with pytest.raises(LastAdminError):
        service.revoke_tenant_admin(
            actor_is_tenant_admin=True, target_user_id=admin.id, tenant_id=tenant.id
        )
    assert service.is_tenant_admin(user_id=admin.id, tenant_id=tenant.id) is True


@pytest.mark.django_db
def test_revoke_tenant_admin_allowed_when_another_remains():
    tenant, admin, _role = _make_tenant_with_admin("revoke-two")
    second = User.objects.create(username="ta-second", email="ta-second@t.test", tenant=tenant)
    TenantRole.objects.create(tenant=tenant, user=second, role=TenantRole.ROLE_ADMIN)
    service = AuthorizationService()

    service.revoke_tenant_admin(
        actor_is_tenant_admin=True, target_user_id=admin.id, tenant_id=tenant.id
    )
    assert service.is_tenant_admin(user_id=admin.id, tenant_id=tenant.id) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest auth_tenancy/tests/test_last_admin_invariant.py -v -k tenant_admin`
Expected: FAIL — `AttributeError: 'AuthorizationService' object has no attribute 'is_tenant_admin'`

- [ ] **Step 3: Implement the tenant-level methods**

In `backend/auth_tenancy/services/authorization.py`, add the `TenantRole`
import to the existing `from ..models import (...)` block:

```python
from ..models import (
    ROLE_ADMIN,
    ROLE_APPROVER,
    ROLE_EDITOR,
    ROLE_VIEWER,
    TenantRole,
    UserRole,
)
```

Add these methods to `AuthorizationService`, after `reactivate_role` (from Task 2):

```python
    def is_tenant_admin(self, *, user_id: UUID, tenant_id: UUID) -> bool:
        """Return whether ``user_id`` holds an active tenant-admin role."""
        return TenantRole.objects.filter(
            user_id=user_id,
            tenant_id=tenant_id,
            role=TenantRole.ROLE_ADMIN,
            suspended_at__isnull=True,
        ).exists()

    def assign_tenant_admin(
        self,
        *,
        actor_is_tenant_admin: bool,
        target_user_id: UUID,
        tenant_id: UUID,
        assigned_by_user_id: UUID,
    ) -> TenantRole:
        """Grant tenant-admin to a user (tenant-admin-guarded)."""
        if not actor_is_tenant_admin:
            raise PermissionDenied(required_role="tenant-admin")
        role, _created = TenantRole.objects.update_or_create(
            user_id=target_user_id,
            tenant_id=tenant_id,
            role=TenantRole.ROLE_ADMIN,
            defaults={"assigned_by_id": assigned_by_user_id, "suspended_at": None},
        )
        return role

    def revoke_tenant_admin(
        self, *, actor_is_tenant_admin: bool, target_user_id: UUID, tenant_id: UUID
    ) -> None:
        """Revoke tenant-admin from a user (tenant-admin-guarded, last-admin
        protected)."""
        if not actor_is_tenant_admin:
            raise PermissionDenied(required_role="tenant-admin")
        with transaction.atomic():
            remaining = (
                TenantRole.objects.select_for_update()
                .filter(tenant_id=tenant_id, role=TenantRole.ROLE_ADMIN, suspended_at__isnull=True)
                .exclude(user_id=target_user_id)
                .count()
            )
            if remaining == 0:
                raise LastAdminError(scope="tenant", identifier=str(tenant_id))
            TenantRole.objects.filter(
                user_id=target_user_id, tenant_id=tenant_id, role=TenantRole.ROLE_ADMIN
            ).delete()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest auth_tenancy/tests/test_last_admin_invariant.py -v`
Expected: 12 passed (6 from Task 2 + 6 new)

- [ ] **Step 5: Commit**

```bash
git add backend/auth_tenancy/services/authorization.py \
        backend/auth_tenancy/tests/test_last_admin_invariant.py
git commit -m "feat: enforce last-admin invariant at tenant level"
```

---

### Task 4: `UserAccountService` — activate/deactivate, the connecting case

**Files:**
- Create: `backend/auth_tenancy/services/user_account.py`
- Test: `backend/auth_tenancy/tests/test_user_account_service.py`

**Interfaces:**
- Consumes: `AuthorizationService.is_tenant_admin` (Task 3), `LastAdminError` (Task 2), `UserRole`, `TenantRole`.
- Produces: `UserAccountService.deactivate(*, actor_is_tenant_admin, target_user_id) -> None` (raises `LastAdminError` naming the FIRST blocking workspace or tenant found; raises `PermissionDenied` if actor is not a tenant-admin). `UserAccountService.activate(*, actor_is_tenant_admin, target_user_id) -> None` (no last-admin check). `UserAccountService.create(*, actor_is_tenant_admin, tenant_id, username, email, password) -> User` (tenant-admin-guarded; consolidates the logic `mcp_server/tools/users.py::_handle_user_create` currently duplicates inline — Task 6 rewires the MCP tool to call this instead of writing `User.objects.create` directly).

- [ ] **Step 1: Write the failing tests**

```python
# backend/auth_tenancy/tests/test_user_account_service.py
from __future__ import annotations

import pytest

from auth_tenancy.errors import PermissionDenied
from auth_tenancy.models import ROLE_ADMIN, TenantRole, UserRole
from auth_tenancy.services.authorization import LastAdminError
from auth_tenancy.services.user_account import UserAccountService
from persistence.models import Tenant, User, Workspace
from persistence.tenancy import TenantContext


@pytest.fixture(autouse=True)
def _clear_tenant_context():
    TenantContext.clear_tenant()
    yield
    TenantContext.clear_tenant()


@pytest.mark.django_db
def test_create_requires_tenant_admin_actor():
    tenant = Tenant.objects.create(name="UA-T", slug="ua-t1")
    service = UserAccountService()
    with pytest.raises(PermissionDenied):
        service.create(
            actor_is_tenant_admin=False,
            tenant_id=tenant.id,
            username="new-user",
            email="new@t.test",
            password="a-real-password-123",
        )


@pytest.mark.django_db
def test_create_succeeds_and_sets_a_usable_password():
    tenant = Tenant.objects.create(name="UA-T2", slug="ua-t2")
    service = UserAccountService()
    user = service.create(
        actor_is_tenant_admin=True,
        tenant_id=tenant.id,
        username="new-user2",
        email="new2@t.test",
        password="a-real-password-123",
    )
    assert user.is_active is True
    assert user.check_password("a-real-password-123") is True


@pytest.mark.django_db
def test_deactivate_blocked_when_target_is_last_workspace_admin():
    tenant = Tenant.objects.create(name="UA-T3", slug="ua-t3")
    TenantContext.set_tenant(tenant.id)
    ws = Workspace.objects.create(tenant=tenant, name="WS")
    target = User.objects.create(username="ua-target", email="ua-target@t.test", tenant=tenant)
    UserRole.objects.create(tenant=tenant, user=target, workspace=ws, role=ROLE_ADMIN)
    service = UserAccountService()

    with pytest.raises(LastAdminError):
        service.deactivate(actor_is_tenant_admin=True, target_user_id=target.id)
    target.refresh_from_db()
    assert target.is_active is True


@pytest.mark.django_db
def test_deactivate_blocked_when_target_is_last_tenant_admin():
    tenant = Tenant.objects.create(name="UA-T4", slug="ua-t4")
    TenantContext.set_tenant(tenant.id)
    target = User.objects.create(username="ua-target2", email="ua-target2@t.test", tenant=tenant)
    TenantRole.objects.create(tenant=tenant, user=target, role=TenantRole.ROLE_ADMIN)
    service = UserAccountService()

    with pytest.raises(LastAdminError):
        service.deactivate(actor_is_tenant_admin=True, target_user_id=target.id)
    target.refresh_from_db()
    assert target.is_active is True


@pytest.mark.django_db
def test_deactivate_succeeds_for_a_non_admin_user():
    tenant = Tenant.objects.create(name="UA-T5", slug="ua-t5")
    TenantContext.set_tenant(tenant.id)
    target = User.objects.create(username="ua-target3", email="ua-target3@t.test", tenant=tenant)
    service = UserAccountService()

    service.deactivate(actor_is_tenant_admin=True, target_user_id=target.id)
    target.refresh_from_db()
    assert target.is_active is False


@pytest.mark.django_db
def test_activate_has_no_last_admin_check_and_requires_tenant_admin():
    tenant = Tenant.objects.create(name="UA-T6", slug="ua-t6")
    TenantContext.set_tenant(tenant.id)
    target = User.objects.create(
        username="ua-target4", email="ua-target4@t.test", tenant=tenant, is_active=False
    )
    service = UserAccountService()

    with pytest.raises(PermissionDenied):
        service.activate(actor_is_tenant_admin=False, target_user_id=target.id)

    service.activate(actor_is_tenant_admin=True, target_user_id=target.id)
    target.refresh_from_db()
    assert target.is_active is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest auth_tenancy/tests/test_user_account_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'auth_tenancy.services.user_account'`

- [ ] **Step 3: Implement `UserAccountService`**

```python
# backend/auth_tenancy/services/user_account.py
"""Account-level user lifecycle: create, activate, deactivate.

The last-admin invariant's connecting case: deactivating a User's account
(``is_active=False``) implicitly removes every admin role that user holds
— at both workspace and tenant scope — in one action. This service is the
ONLY place that flips ``User.is_active``; REST and MCP both call it, so
no code path can bypass the check (multi-user management design spec).
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from django.db import transaction

from .authorization import LastAdminError
from ..errors import PermissionDenied
from ..models import ROLE_ADMIN, UserRole
from persistence.models import Tenant, User


class UserAccountService:
    """Tenant-admin-guarded account lifecycle: create / activate / deactivate."""

    def create(
        self,
        *,
        actor_is_tenant_admin: bool,
        tenant_id: UUID,
        username: str,
        email: str,
        password: str,
    ) -> User:
        """Create a new user with an initial password (tenant-admin-guarded).

        Mirrors the pattern ``mcp_server/tools/users.py::_handle_user_create``
        used inline before this service existed: ``User.objects.create`` +
        ``set_password`` + ``save``, the only user-creation path in the
        codebase (confirmed at the time that handler was written).
        """
        if not actor_is_tenant_admin:
            raise PermissionDenied(required_role="tenant-admin")
        tenant = Tenant.objects.get(id=tenant_id)
        user = User.objects.create(
            username=username, email=email, tenant=tenant, is_active=True
        )
        user.set_password(password)
        user.save(update_fields=["password", "modified_at", "version"])
        return user

    def activate(self, *, actor_is_tenant_admin: bool, target_user_id: UUID) -> None:
        """Set ``is_active=True`` (tenant-admin-guarded, no last-admin check —
        activating never removes an admin)."""
        if not actor_is_tenant_admin:
            raise PermissionDenied(required_role="tenant-admin")
        User.objects.filter(id=target_user_id).update(is_active=True)

    def deactivate(
        self, *, actor_is_tenant_admin: bool, target_user_id: UUID
    ) -> None:
        """Set ``is_active=False`` (tenant-admin-guarded, last-admin protected
        at BOTH workspace and tenant scope).

        Raises :class:`LastAdminError` naming the first blocking workspace or
        tenant found if deactivating this user would drop any of them to
        zero active admins. Locks the same row sets
        :meth:`AuthorizationService._assert_not_last_workspace_admin` and
        :meth:`AuthorizationService.revoke_tenant_admin` lock, so a
        concurrent per-role revoke and a full-account deactivate cannot race
        each other into a zero-admin state either.
        """
        if not actor_is_tenant_admin:
            raise PermissionDenied(required_role="tenant-admin")

        with transaction.atomic():
            admin_workspace_ids = list(
                UserRole.objects.select_for_update()
                .filter(user_id=target_user_id, role=ROLE_ADMIN, suspended_at__isnull=True)
                .values_list("workspace_id", flat=True)
            )
            for workspace_id in admin_workspace_ids:
                remaining = (
                    UserRole.objects.select_for_update()
                    .filter(workspace_id=workspace_id, role=ROLE_ADMIN, suspended_at__isnull=True)
                    .exclude(user_id=target_user_id)
                    .count()
                )
                if remaining == 0:
                    raise LastAdminError(scope="workspace", identifier=str(workspace_id))

            from ..models import TenantRole

            tenant_admin_tenant_ids = list(
                TenantRole.objects.select_for_update()
                .filter(user_id=target_user_id, role=TenantRole.ROLE_ADMIN, suspended_at__isnull=True)
                .values_list("tenant_id", flat=True)
            )
            for tenant_id in tenant_admin_tenant_ids:
                remaining = (
                    TenantRole.objects.select_for_update()
                    .filter(tenant_id=tenant_id, role=TenantRole.ROLE_ADMIN, suspended_at__isnull=True)
                    .exclude(user_id=target_user_id)
                    .count()
                )
                if remaining == 0:
                    raise LastAdminError(scope="tenant", identifier=str(tenant_id))

            User.objects.filter(id=target_user_id).update(is_active=False)


__all__ = ["UserAccountService"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest auth_tenancy/tests/test_user_account_service.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add backend/auth_tenancy/services/user_account.py \
        backend/auth_tenancy/tests/test_user_account_service.py
git commit -m "feat: add UserAccountService with last-admin-protected deactivate"
```

---

### Task 5: `bootstrap_admin` creates the first tenant-admin

**Files:**
- Modify: `backend/auth_tenancy/provisioning.py` (`provision_admin`, `_ensure_admin_role` area)
- Test: `backend/auth_tenancy/tests/test_provisioning.py` (create, or extend if a file with this name already exists — check first with `find backend/auth_tenancy/tests -iname "*provision*"`)

**Interfaces:**
- Consumes: `TenantRole` (Task 1).
- Produces: `provision_admin(...)` now also returns a `ProvisionResult.tenant_role: TenantRole` field (in addition to the existing `role: UserRole` workspace-role field), and the function itself creates it idempotently.

- [ ] **Step 1: Write the failing test**

```python
# backend/auth_tenancy/tests/test_provisioning.py
"""If backend/auth_tenancy/tests/test_provisioning.py already exists,
add these test functions to it instead of creating a new file — check
first."""
from __future__ import annotations

import pytest

from auth_tenancy.models import TenantRole
from auth_tenancy.provisioning import provision_admin


@pytest.mark.django_db
def test_provision_admin_creates_first_tenant_admin_role():
    result = provision_admin(
        username="bootstrap-test-admin",
        email="bootstrap-test@demo.local",
        password="a-real-password-123",
    )
    assert result.tenant_role.user_id == result.user.id
    assert result.tenant_role.tenant_id == result.tenant.id
    assert result.tenant_role.role == TenantRole.ROLE_ADMIN
    assert TenantRole.unscoped.filter(
        tenant_id=result.tenant.id, user_id=result.user.id, role=TenantRole.ROLE_ADMIN
    ).exists()


@pytest.mark.django_db
def test_provision_admin_is_idempotent_for_tenant_role_too():
    first = provision_admin(
        username="bootstrap-test-admin2",
        email="bootstrap-test2@demo.local",
        password="a-real-password-123",
    )
    second = provision_admin(
        username="bootstrap-test-admin2",
        email="bootstrap-test2@demo.local",
        password="unused-on-second-call",
    )
    assert TenantRole.unscoped.filter(
        tenant_id=first.tenant.id, user_id=first.user.id, role=TenantRole.ROLE_ADMIN
    ).count() == 1
    assert second.tenant_role.id == first.tenant_role.id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest auth_tenancy/tests/test_provisioning.py -v`
Expected: FAIL — `AttributeError: 'ProvisionResult' object has no attribute 'tenant_role'`

- [ ] **Step 3: Wire in the tenant-admin creation**

In `backend/auth_tenancy/provisioning.py`:

Add `TenantRole` to the existing `from auth_tenancy.models import ROLE_ADMIN, UserRole` line (becomes `from auth_tenancy.models import ROLE_ADMIN, TenantRole, UserRole`).

Add a `tenant_role: TenantRole` field to the `ProvisionResult` dataclass, right after the existing `role: UserRole` field.

In `provision_admin`, right after `role = _ensure_admin_role(tenant, user, workspace)` (still inside the `try`/`finally` block, before `finally: clear_request_tenant()`), add:

```python
        tenant_role = _ensure_tenant_admin_role(tenant, user)
```

Update the `return ProvisionResult(...)` call to include `tenant_role=tenant_role,` alongside the existing `role=role,`.

Add this new helper function after `_ensure_admin_role`:

```python
def _ensure_tenant_admin_role(tenant: Tenant, user: User) -> TenantRole:
    """Get-or-create the tenant-admin TenantRole for the user."""
    tenant_role, _created = TenantRole.objects.get_or_create(
        tenant=tenant,
        user=user,
        role=TenantRole.ROLE_ADMIN,
        defaults={"suspended_at": None},
    )
    if tenant_role.suspended_at is not None:
        tenant_role.suspended_at = None
        tenant_role.save(update_fields=["suspended_at", "modified_at"])
    return tenant_role
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest auth_tenancy/tests/test_provisioning.py -v`
Expected: 2 passed

- [ ] **Step 5: Update the `bootstrap_admin` command's own test if one exists**

Run: `find backend/auth_tenancy/tests -iname "*bootstrap*"` — if a test file
covering `bootstrap_admin.py` exists, add an assertion there too that
`TenantRole.unscoped.filter(...).exists()` after running the command, using
the same pattern as Step 1's tests. If no such test file exists, skip this
step (the command is a thin wrapper over `provision_admin`, already covered).

- [ ] **Step 6: Commit**

```bash
git add backend/auth_tenancy/provisioning.py \
        backend/auth_tenancy/tests/test_provisioning.py
git commit -m "feat: bootstrap_admin creates the first tenant-admin role"
```

---

### Task 6: Shared permission matrix constant

**Files:**
- Create: `backend/auth_tenancy/tests/user_management_matrix.py`

**Interfaces:**
- Produces: `USER_MANAGEMENT_MATRIX: dict[str, dict[str, bool]]` — `{action_name: {role_name: expected_allowed}}`, where `role_name` is one of `"tenant-admin"`, `"workspace-admin"`, `"editor"`, `"viewer"`, `"approver"`, `"no-role"`. Consumed by Task 9 (MCP tests) and Task 10 (consistency tests) via `from auth_tenancy.tests.user_management_matrix import USER_MANAGEMENT_MATRIX, ACTIONS`.

- [ ] **Step 1: Write the matrix module (no test — this is a pure data constant; its correctness is proven by the tests in Tasks 9-10 that consume it)**

```python
# backend/auth_tenancy/tests/user_management_matrix.py
"""Single source of truth for user-management permission decisions.

Imported by BOTH the MCP test suite (mcp_server/tests/
test_user_management_rbac_matrix.py) and the REST test suite
(rest_api/tests/test_user_management_rbac_matrix.py) so the two
transports are proven to enforce identical decisions from one shared
definition — never hand-duplicated (multi-user management design spec,
section 3).

Roles here are the CALLER's roles, not a target's roles:
  "tenant-admin"    — caller holds TenantRole(admin) in the tenant
  "workspace-admin" — caller holds UserRole(admin) in the target workspace
  "editor"          — caller holds UserRole(editor) in the target workspace
  "viewer"          — caller holds UserRole(viewer) in the target workspace
  "approver"        — caller holds UserRole(approver) in the target workspace
  "no-role"         — caller has no role at all in the tenant/workspace
"""
from __future__ import annotations

ROLES = ("tenant-admin", "workspace-admin", "editor", "viewer", "approver", "no-role")

# action -> {role -> expected allowed}
USER_MANAGEMENT_MATRIX: dict[str, dict[str, bool]] = {
    "user.create": {
        "tenant-admin": True,
        "workspace-admin": False,
        "editor": False,
        "viewer": False,
        "approver": False,
        "no-role": False,
    },
    "user.activate": {
        "tenant-admin": True,
        "workspace-admin": False,
        "editor": False,
        "viewer": False,
        "approver": False,
        "no-role": False,
    },
    "user.deactivate": {
        "tenant-admin": True,
        "workspace-admin": False,
        "editor": False,
        "viewer": False,
        "approver": False,
        "no-role": False,
    },
    "workspace.assign_role": {
        "tenant-admin": True,
        "workspace-admin": True,
        "editor": False,
        "viewer": False,
        "approver": False,
        "no-role": False,
    },
    "workspace.suspend_role": {
        "tenant-admin": True,
        "workspace-admin": True,
        "editor": False,
        "viewer": False,
        "approver": False,
        "no-role": False,
    },
    "workspace.reactivate_role": {
        "tenant-admin": True,
        "workspace-admin": True,
        "editor": False,
        "viewer": False,
        "approver": False,
        "no-role": False,
    },
    "tenant.assign_admin": {
        "tenant-admin": True,
        "workspace-admin": False,
        "editor": False,
        "viewer": False,
        "approver": False,
        "no-role": False,
    },
    "tenant.revoke_admin": {
        "tenant-admin": True,
        "workspace-admin": False,
        "editor": False,
        "viewer": False,
        "approver": False,
        "no-role": False,
    },
}

ACTIONS = tuple(USER_MANAGEMENT_MATRIX.keys())
```

- [ ] **Step 2: Commit**

```bash
git add backend/auth_tenancy/tests/user_management_matrix.py
git commit -m "test: add shared REST/MCP user-management permission matrix"
```

---

### Task 7: REST — `UserViewSet`

**Files:**
- Create: `backend/rest_api/user_management_views.py`
- Modify: `backend/rest_api/urls.py` (register the new routes)
- Test: `backend/rest_api/tests/test_user_management_views.py`

**Interfaces:**
- Consumes: `UserAccountService` (Task 4), `AuthorizationService.assign_tenant_admin` / `revoke_tenant_admin` / `is_tenant_admin` (Task 3).
- Produces: URLs `GET/POST /api/v1/users/`, `POST /api/v1/users/<uuid:pk>/activate/`, `POST /api/v1/users/<uuid:pk>/deactivate/`, `POST/DELETE /api/v1/users/<uuid:pk>/tenant-admin/`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/rest_api/tests/test_user_management_views.py
from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, TenantRole, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace


@pytest.fixture
def tenant(db) -> Tenant:
    return Tenant.objects.create(name="UMV-T", slug="umv-t", is_active=True)


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    set_request_tenant(tenant.id)
    try:
        return Workspace.objects.create(tenant=tenant, name="UMV-WS", preset={"name": "extended"})
    finally:
        clear_request_tenant()


def _make_authed_client(tenant: Tenant, workspace: Workspace, *, is_tenant_admin: bool, is_workspace_admin: bool = False) -> APIClient:
    set_request_tenant(tenant.id)
    try:
        user = User.objects.create(username=f"umv-{is_tenant_admin}-{is_workspace_admin}", email=f"umv-{is_tenant_admin}-{is_workspace_admin}@t.test", tenant=tenant)
        user.set_password("hunter2pass")
        user.save(update_fields=["password"])
        if is_tenant_admin:
            TenantRole.objects.create(tenant=tenant, user=user, role=TenantRole.ROLE_ADMIN)
        if is_workspace_admin:
            UserRole.objects.create(tenant=tenant, user=user, workspace=workspace, role=ROLE_ADMIN)
    finally:
        clear_request_tenant()

    client = APIClient()
    login = client.post("/api/v1/auth/login/", {"username": user.username, "password": "hunter2pass"}, format="json")
    assert login.status_code == 200, login.content
    token = login.json()["token"]
    authed = APIClient()
    authed.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return authed


@pytest.mark.django_db
def test_create_user_requires_tenant_admin(tenant, workspace):
    client = _make_authed_client(tenant, workspace, is_tenant_admin=False, is_workspace_admin=True)
    resp = client.post("/api/v1/users/", {"username": "newbie", "email": "newbie@t.test", "password": "a-real-password-123"}, format="json")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_create_user_succeeds_for_tenant_admin(tenant, workspace):
    client = _make_authed_client(tenant, workspace, is_tenant_admin=True)
    resp = client.post("/api/v1/users/", {"username": "newbie2", "email": "newbie2@t.test", "password": "a-real-password-123"}, format="json")
    assert resp.status_code == 201, resp.content
    assert resp.json()["username"] == "newbie2"


@pytest.mark.django_db
def test_deactivate_blocks_last_tenant_admin(tenant, workspace):
    client = _make_authed_client(tenant, workspace, is_tenant_admin=True)
    set_request_tenant(tenant.id)
    try:
        target = User.objects.get(username__startswith="umv-True")
    finally:
        clear_request_tenant()
    resp = client.post(f"/api/v1/users/{target.id}/deactivate/")
    assert resp.status_code == 409, resp.content
    assert resp.json()["error"] == "LAST_ADMIN"


@pytest.mark.django_db
def test_activate_succeeds_for_tenant_admin(tenant, workspace):
    client = _make_authed_client(tenant, workspace, is_tenant_admin=True)
    set_request_tenant(tenant.id)
    try:
        other = User.objects.create(username="umv-inactive", email="umv-inactive@t.test", tenant=tenant, is_active=False)
    finally:
        clear_request_tenant()
    resp = client.post(f"/api/v1/users/{other.id}/activate/")
    assert resp.status_code == 200, resp.content
    other.refresh_from_db()
    assert other.is_active is True


@pytest.mark.django_db
def test_grant_and_revoke_tenant_admin(tenant, workspace):
    client = _make_authed_client(tenant, workspace, is_tenant_admin=True)
    set_request_tenant(tenant.id)
    try:
        target = User.objects.create(username="umv-future-admin", email="umv-future@t.test", tenant=tenant)
    finally:
        clear_request_tenant()

    grant = client.post(f"/api/v1/users/{target.id}/tenant-admin/")
    assert grant.status_code == 200, grant.content

    revoke = client.delete(f"/api/v1/users/{target.id}/tenant-admin/")
    assert revoke.status_code == 200, revoke.content
    assert AuthorizationService().is_tenant_admin(user_id=target.id, tenant_id=tenant.id) is False


from auth_tenancy.services import AuthorizationService  # noqa: E402 (used above)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest rest_api/tests/test_user_management_views.py -v`
Expected: FAIL — 404 on `/api/v1/users/` (not yet routed)

- [ ] **Step 3: Implement the view**

```python
# backend/rest_api/user_management_views.py
"""
Multi-user management — REST adapter (multi-user management design spec).

Endpoints:
    GET  /api/v1/users/                       — list users (tenant-scoped, tenant-admin)
    POST /api/v1/users/                       — create user (tenant-admin)
    POST /api/v1/users/<uuid:pk>/activate/    — activate (tenant-admin)
    POST /api/v1/users/<uuid:pk>/deactivate/  — deactivate (tenant-admin, last-admin protected)
    POST   /api/v1/users/<uuid:pk>/tenant-admin/ — grant tenant-admin (tenant-admin)
    DELETE /api/v1/users/<uuid:pk>/tenant-admin/ — revoke tenant-admin (tenant-admin, last-admin protected)

Thin HTTP-translation layer: delegates all logic to
:class:`UserAccountService` / :class:`AuthorizationService` (ADR-01, no
model access from views).
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from auth_tenancy.context import AuthContext
from auth_tenancy.errors import PermissionDenied
from auth_tenancy.services import AuthorizationService
from auth_tenancy.services.authorization import LastAdminError
from auth_tenancy.services.user_account import UserAccountService
from persistence.models import User


def _user_to_dict(user: User) -> dict[str, Any]:
    return {
        "id": str(user.id),
        "username": user.username,
        "email": user.email,
        "is_active": user.is_active,
    }


def _err(code: str, message: str, http_status: int) -> Response:
    return Response({"error": code, "message": message}, status=http_status)


class UserViewSet(ViewSet):
    """REST ViewSet for tenant-admin user lifecycle management."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._accounts = UserAccountService()
        self._authz = AuthorizationService()

    @staticmethod
    def _auth_context(request: Request) -> AuthContext | None:
        return getattr(request, "auth_context", None)

    def list(self, request: Request, **kwargs: Any) -> Response:
        ctx = self._auth_context(request)
        if ctx is None:
            return _err("authentication_required", "Not authenticated", status.HTTP_401_UNAUTHORIZED)
        if not self._authz.is_tenant_admin(user_id=ctx.user_id, tenant_id=ctx.tenant_id):
            return _err("PERMISSION_DENIED", "tenant-admin role required.", status.HTTP_403_FORBIDDEN)
        users = User.objects.filter(tenant_id=ctx.tenant_id).order_by("username")
        return Response([_user_to_dict(u) for u in users], status=status.HTTP_200_OK)

    def create(self, request: Request, **kwargs: Any) -> Response:
        ctx = self._auth_context(request)
        if ctx is None:
            return _err("authentication_required", "Not authenticated", status.HTTP_401_UNAUTHORIZED)
        is_admin = self._authz.is_tenant_admin(user_id=ctx.user_id, tenant_id=ctx.tenant_id)

        username = (request.data or {}).get("username")
        email = (request.data or {}).get("email")
        password = (request.data or {}).get("password")
        if not username or not email or not password:
            return _err("VALIDATION_ERROR", "username, email and password are required.", status.HTTP_400_BAD_REQUEST)

        try:
            user = self._accounts.create(
                actor_is_tenant_admin=is_admin,
                tenant_id=ctx.tenant_id,
                username=username,
                email=email,
                password=password,
            )
        except PermissionDenied:
            return _err("PERMISSION_DENIED", "tenant-admin role required.", status.HTTP_403_FORBIDDEN)
        except Exception as exc:
            return _err("VALIDATION_ERROR", str(exc), status.HTTP_400_BAD_REQUEST)

        return Response(_user_to_dict(user), status=status.HTTP_201_CREATED)

    def _resolve_user_pk(self, pk: str | None) -> UUID | None:
        if not pk:
            return None
        try:
            return UUID(pk)
        except (ValueError, AttributeError):
            return None

    def activate(self, request: Request, pk: str | None = None, **kwargs: Any) -> Response:
        ctx = self._auth_context(request)
        if ctx is None:
            return _err("authentication_required", "Not authenticated", status.HTTP_401_UNAUTHORIZED)
        target_id = self._resolve_user_pk(pk)
        if target_id is None:
            return _err("NOT_FOUND", "Invalid user id.", status.HTTP_404_NOT_FOUND)
        is_admin = self._authz.is_tenant_admin(user_id=ctx.user_id, tenant_id=ctx.tenant_id)
        try:
            self._accounts.activate(actor_is_tenant_admin=is_admin, target_user_id=target_id)
        except PermissionDenied:
            return _err("PERMISSION_DENIED", "tenant-admin role required.", status.HTTP_403_FORBIDDEN)
        user = User.objects.filter(id=target_id).first()
        if user is None:
            return _err("NOT_FOUND", "User not found.", status.HTTP_404_NOT_FOUND)
        return Response(_user_to_dict(user), status=status.HTTP_200_OK)

    def deactivate(self, request: Request, pk: str | None = None, **kwargs: Any) -> Response:
        ctx = self._auth_context(request)
        if ctx is None:
            return _err("authentication_required", "Not authenticated", status.HTTP_401_UNAUTHORIZED)
        target_id = self._resolve_user_pk(pk)
        if target_id is None:
            return _err("NOT_FOUND", "Invalid user id.", status.HTTP_404_NOT_FOUND)
        is_admin = self._authz.is_tenant_admin(user_id=ctx.user_id, tenant_id=ctx.tenant_id)
        try:
            self._accounts.deactivate(actor_is_tenant_admin=is_admin, target_user_id=target_id)
        except PermissionDenied:
            return _err("PERMISSION_DENIED", "tenant-admin role required.", status.HTTP_403_FORBIDDEN)
        except LastAdminError as exc:
            return _err("LAST_ADMIN", str(exc), status.HTTP_409_CONFLICT)
        user = User.objects.filter(id=target_id).first()
        if user is None:
            return _err("NOT_FOUND", "User not found.", status.HTTP_404_NOT_FOUND)
        return Response(_user_to_dict(user), status=status.HTTP_200_OK)

    def tenant_admin(self, request: Request, pk: str | None = None, **kwargs: Any) -> Response:
        """Combined handler for POST (grant) / DELETE (revoke), routed as
        one action since both share the same URL (see urls.py)."""
        ctx = self._auth_context(request)
        if ctx is None:
            return _err("authentication_required", "Not authenticated", status.HTTP_401_UNAUTHORIZED)
        target_id = self._resolve_user_pk(pk)
        if target_id is None:
            return _err("NOT_FOUND", "Invalid user id.", status.HTTP_404_NOT_FOUND)
        is_admin = self._authz.is_tenant_admin(user_id=ctx.user_id, tenant_id=ctx.tenant_id)

        if request.method == "POST":
            try:
                self._authz.assign_tenant_admin(
                    actor_is_tenant_admin=is_admin,
                    target_user_id=target_id,
                    tenant_id=ctx.tenant_id,
                    assigned_by_user_id=ctx.user_id,
                )
            except PermissionDenied:
                return _err("PERMISSION_DENIED", "tenant-admin role required.", status.HTTP_403_FORBIDDEN)
            return Response({"granted": True}, status=status.HTTP_200_OK)

        try:
            self._authz.revoke_tenant_admin(
                actor_is_tenant_admin=is_admin, target_user_id=target_id, tenant_id=ctx.tenant_id
            )
        except PermissionDenied:
            return _err("PERMISSION_DENIED", "tenant-admin role required.", status.HTTP_403_FORBIDDEN)
        except LastAdminError as exc:
            return _err("LAST_ADMIN", str(exc), status.HTTP_409_CONFLICT)
        return Response({"revoked": True}, status=status.HTTP_200_OK)


__all__ = ["UserViewSet"]
```

- [ ] **Step 4: Wire the URLs**

In `backend/rest_api/urls.py`, add near the top with the other view imports
(alongside the existing `from auth_tenancy.rest_workspace_members import WorkspaceMembersView` at line 43):

```python
from rest_api.user_management_views import UserViewSet
```

Add these `path(...)` entries near the existing `workspaces/<uuid:workspace_id>/members/` entry (around line 261-264):

```python
    path(
        "users/",
        UserViewSet.as_view({"get": "list", "post": "create"}),
        name="user-list-create",
    ),
    path(
        "users/<uuid:pk>/activate/",
        UserViewSet.as_view({"post": "activate"}),
        name="user-activate",
    ),
    path(
        "users/<uuid:pk>/deactivate/",
        UserViewSet.as_view({"post": "deactivate"}),
        name="user-deactivate",
    ),
    path(
        "users/<uuid:pk>/tenant-admin/",
        UserViewSet.as_view({"post": "tenant_admin", "delete": "tenant_admin"}),
        name="user-tenant-admin",
    ),
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest rest_api/tests/test_user_management_views.py -v`
Expected: 5 passed

- [ ] **Step 6: Commit**

```bash
git add backend/rest_api/user_management_views.py \
        backend/rest_api/urls.py \
        backend/rest_api/tests/test_user_management_views.py
git commit -m "feat: add REST UserViewSet for user lifecycle management"
```

---

### Task 8: REST — extend workspace members with assign/suspend/reactivate

**Files:**
- Modify: `backend/auth_tenancy/rest_workspace_members.py`
- Modify: `backend/rest_api/urls.py`
- Test: `backend/auth_tenancy/tests/test_workspace_members_mutations.py`

**Interfaces:**
- Consumes: `AuthorizationService.assign_role` (existing), `suspend_role` / `reactivate_role` (Task 2).
- Produces: `POST /api/v1/workspaces/<uuid:workspace_id>/members/` (assign), `POST /api/v1/workspaces/<uuid:workspace_id>/members/<uuid:user_id>/suspend/`, `POST .../reactivate/`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/auth_tenancy/tests/test_workspace_members_mutations.py
from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace


@pytest.fixture
def tenant(db) -> Tenant:
    return Tenant.objects.create(name="WSM-T", slug="wsm-t", is_active=True)


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    set_request_tenant(tenant.id)
    try:
        return Workspace.objects.create(tenant=tenant, name="WSM-WS", preset={"name": "extended"})
    finally:
        clear_request_tenant()


@pytest.fixture
def admin_client(tenant: Tenant, workspace: Workspace) -> APIClient:
    set_request_tenant(tenant.id)
    try:
        user = User.objects.create(username="wsm-admin", email="wsm-admin@t.test", tenant=tenant)
        user.set_password("hunter2pass")
        user.save(update_fields=["password"])
        UserRole.objects.create(tenant=tenant, user=user, workspace=workspace, role=ROLE_ADMIN)
    finally:
        clear_request_tenant()
    client = APIClient()
    login = client.post("/api/v1/auth/login/", {"username": "wsm-admin", "password": "hunter2pass"}, format="json")
    assert login.status_code == 200, login.content
    authed = APIClient()
    authed.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['token']}")
    return authed


@pytest.mark.django_db
def test_assign_role_via_rest(admin_client, tenant, workspace):
    set_request_tenant(tenant.id)
    try:
        target = User.objects.create(username="wsm-target", email="wsm-target@t.test", tenant=tenant)
    finally:
        clear_request_tenant()

    resp = admin_client.post(
        f"/api/v1/workspaces/{workspace.id}/members/",
        {"user_id": str(target.id), "role": "editor", "preset": "extended"},
        format="json",
    )
    assert resp.status_code == 201, resp.content

    set_request_tenant(tenant.id)
    try:
        assert UserRole.objects.filter(user=target, workspace=workspace, role="editor").exists()
    finally:
        clear_request_tenant()


@pytest.mark.django_db
def test_suspend_and_reactivate_role_via_rest(admin_client, tenant, workspace):
    set_request_tenant(tenant.id)
    try:
        target = User.objects.create(username="wsm-target2", email="wsm-target2@t.test", tenant=tenant)
        UserRole.objects.create(tenant=tenant, user=target, workspace=workspace, role="editor")
    finally:
        clear_request_tenant()

    suspend = admin_client.post(f"/api/v1/workspaces/{workspace.id}/members/{target.id}/suspend/", {"role": "editor"}, format="json")
    assert suspend.status_code == 200, suspend.content
    set_request_tenant(tenant.id)
    try:
        role = UserRole.objects.get(user=target, workspace=workspace, role="editor")
        assert role.suspended_at is not None
    finally:
        clear_request_tenant()

    reactivate = admin_client.post(f"/api/v1/workspaces/{workspace.id}/members/{target.id}/reactivate/", {"role": "editor"}, format="json")
    assert reactivate.status_code == 200, reactivate.content
    set_request_tenant(tenant.id)
    try:
        role = UserRole.objects.get(user=target, workspace=workspace, role="editor")
        assert role.suspended_at is None
    finally:
        clear_request_tenant()


@pytest.mark.django_db
def test_suspend_blocks_last_workspace_admin(admin_client, tenant, workspace):
    set_request_tenant(tenant.id)
    try:
        admin_user = User.objects.get(username="wsm-admin")
    finally:
        clear_request_tenant()

    resp = admin_client.post(
        f"/api/v1/workspaces/{workspace.id}/members/{admin_user.id}/suspend/", {"role": "admin"}, format="json"
    )
    assert resp.status_code == 409, resp.content
    assert resp.json()["error"] == "LAST_ADMIN"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest auth_tenancy/tests/test_workspace_members_mutations.py -v`
Expected: FAIL — 405/404 on the new POST routes.

- [ ] **Step 3: Extend `WorkspaceMembersView` and add a new suspend/reactivate view**

In `backend/auth_tenancy/rest_workspace_members.py`, add `from .services.authorization import LastAdminError` to the imports, then add a `post` method to `WorkspaceMembersView` (after the existing `get` method):

```python
    def post(self, request: Request, **kwargs: Any) -> Response:
        """Assign a role to a user in this workspace (admin-guarded)."""
        ctx = self._auth_context(request)
        try:
            workspace_id = self._workspace_id_from_kwargs(request)
        except ValidationError as exc:
            return _err("VALIDATION_ERROR", str(exc), status.HTTP_400_BAD_REQUEST)

        target_user_id = (request.data or {}).get("user_id")
        role = (request.data or {}).get("role")
        preset = (request.data or {}).get("preset")
        if not target_user_id or not role or not preset:
            return _err("VALIDATION_ERROR", "user_id, role and preset are required.", status.HTTP_400_BAD_REQUEST)

        try:
            self._service.assign_role(
                actor_roles=ctx.active_roles,
                target_user_id=UUID(str(target_user_id)),
                workspace_id=workspace_id,
                tenant_id=ctx.tenant_id,
                role=role,
                preset=preset,
                assigned_by_user_id=ctx.user_id,
                target_is_member=False,
            )
        except (PermissionDenied, PermissionDeniedError):
            return _err("PERMISSION_DENIED", "You must be a workspace admin.", status.HTTP_403_FORBIDDEN)
        except (ValueError, ValidationError) as exc:
            return _err("VALIDATION_ERROR", str(exc), status.HTTP_400_BAD_REQUEST)

        return Response({"assigned": True}, status=status.HTTP_201_CREATED)


class WorkspaceMemberRoleTransitionView(APIView):
    """Suspend / reactivate a single member's role in a workspace.

    URL: ``/api/v1/workspaces/<uuid:workspace_id>/members/<uuid:user_id>/suspend/``
         ``/api/v1/workspaces/<uuid:workspace_id>/members/<uuid:user_id>/reactivate/``
    """

    permission_classes = [HasOperationPermission]
    required_operation = Operation.ASSIGN_ROLE

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._service = AuthorizationService()

    @staticmethod
    def _auth_context(request: Request) -> AuthContext:
        ctx = getattr(request, "auth_context", None)
        if ctx is None:
            raise PermissionDeniedError("Authentication required.")
        return ctx

    def _handle(self, request: Request, *, suspend: bool, workspace_id: str, user_id: str) -> Response:
        ctx = self._auth_context(request)
        role = (request.data or {}).get("role")
        if not role:
            return _err("VALIDATION_ERROR", "role is required.", status.HTTP_400_BAD_REQUEST)

        try:
            ws_uuid = UUID(str(workspace_id))
            user_uuid = UUID(str(user_id))
        except (ValueError, TypeError):
            return _err("VALIDATION_ERROR", "Invalid workspace_id or user_id.", status.HTTP_400_BAD_REQUEST)

        method = self._service.suspend_role if suspend else self._service.reactivate_role
        try:
            method(actor_roles=ctx.active_roles, target_user_id=user_uuid, workspace_id=ws_uuid, role=role)
        except (PermissionDenied, PermissionDeniedError):
            return _err("PERMISSION_DENIED", "You must be a workspace admin.", status.HTTP_403_FORBIDDEN)
        except LastAdminError as exc:
            return _err("LAST_ADMIN", str(exc), status.HTTP_409_CONFLICT)

        return Response({"suspend" if suspend else "reactivate": True}, status=status.HTTP_200_OK)

    def post(self, request: Request, workspace_id: str = "", user_id: str = "", **kwargs: Any) -> Response:
        action = request.parser_context.get("kwargs", {}).get("action") if request.parser_context else None
        suspend = action != "reactivate"
        return self._handle(request, suspend=suspend, workspace_id=workspace_id, user_id=user_id)
```

Update the module's `__all__` to include `"WorkspaceMemberRoleTransitionView"`.

- [ ] **Step 4: Wire the URLs**

In `backend/rest_api/urls.py`, add the import and two new paths near the
existing `workspaces/<uuid:workspace_id>/members/` entry:

```python
from auth_tenancy.rest_workspace_members import (
    WorkspaceMembersView,
    WorkspaceMemberRoleTransitionView,
)
```

```python
    path(
        "workspaces/<uuid:workspace_id>/members/<uuid:user_id>/suspend/",
        WorkspaceMemberRoleTransitionView.as_view(),
        {"action": "suspend"},
        name="workspace-member-suspend",
    ),
    path(
        "workspaces/<uuid:workspace_id>/members/<uuid:user_id>/reactivate/",
        WorkspaceMemberRoleTransitionView.as_view(),
        {"action": "reactivate"},
        name="workspace-member-reactivate",
    ),
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest auth_tenancy/tests/test_workspace_members_mutations.py -v`
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add backend/auth_tenancy/rest_workspace_members.py \
        backend/rest_api/urls.py \
        backend/auth_tenancy/tests/test_workspace_members_mutations.py
git commit -m "feat: add REST endpoints to assign/suspend/reactivate workspace roles"
```

---

### Task 9: MCP — new tools

**Files:**
- Modify: `backend/mcp_server/tools/users.py`
- Test: `backend/mcp_server/tests/test_users_tool_group.py` (extend the existing file — confirmed to exist from the design-spec survey)

**Interfaces:**
- Consumes: `UserAccountService` (Task 4), `AuthorizationService.suspend_role/reactivate_role/assign_tenant_admin/revoke_tenant_admin/is_tenant_admin` (Tasks 2-3).
- Produces: MCP tools `user.activate`, `user.suspend_role`, `user.reactivate_role`, `user.assign_tenant_admin`, `user.revoke_tenant_admin`. `user.create` and `user.deactivate` are rewired to call `UserAccountService` instead of writing `User.objects` directly (contract unchanged — same params, same response shape).

- [ ] **Step 1: Write the failing tests**

Append to `backend/mcp_server/tests/test_users_tool_group.py` (read the
existing file first via `grep -n "^class Test" backend/mcp_server/tests/test_users_tool_group.py`
to match its exact fixture names — it already has fixtures for tenant/
workspace/admin API keys from the existing `user.create`/`user.deactivate`
tests; reuse them rather than redefining):

```python
class TestUserActivate:
    def test_activate_reactivates_a_deactivated_user(self, admin_client, tenant):
        # deactivate a fresh non-admin user first, then activate it back
        create_resp = admin_client.post(
            "/mcp/", {"tool": "user.create", "params": {"username": "act-target", "email": "act@t.test", "password": "a-real-password-123"}}
        )
        user_id = create_resp.json()["result"]["user"]["id"]
        admin_client.post("/mcp/", {"tool": "user.deactivate", "params": {"user_id": user_id}})

        resp = admin_client.post("/mcp/", {"tool": "user.activate", "params": {"user_id": user_id}})
        assert resp.status_code == 200
        assert resp.json()["result"]["user"]["is_active"] is True

    def test_activate_requires_admin(self, viewer_client, tenant):
        resp = viewer_client.post("/mcp/", {"tool": "user.activate", "params": {"user_id": "00000000-0000-0000-0000-000000000000"}})
        assert resp.json()["error"]["code"] == "PERMISSION_DENIED"


class TestUserDeactivateLastAdminGuard:
    def test_deactivate_blocked_for_last_tenant_admin(self, admin_client, tenant, admin_user_id):
        resp = admin_client.post("/mcp/", {"tool": "user.deactivate", "params": {"user_id": admin_user_id}})
        assert resp.json()["error"]["code"] == "LAST_ADMIN"
```

Note for the implementer: if the existing test file's fixtures use
different names than `admin_client`/`viewer_client`/`tenant`/`admin_user_id`
shown above (very likely, since these were guessed from convention, not
read directly), adapt the test bodies to the ACTUAL fixture names — read
`backend/mcp_server/tests/test_users_tool_group.py` in full before writing
this step for real, and also check `backend/mcp_server/tests/conftest.py`
(the shared MCP fixture file surveyed earlier in this session, which
provides `admin_client`/`member_client`/`viewer_client`/`e2e_tenant` — the
real fixture names are almost certainly `admin_client`, `viewer_client`,
`e2e_tenant`, not the guessed `tenant`/`admin_user_id`). Use
`helpers.post_mcp()` (referenced in `mcp_server/tests/helpers.py` per this
session's earlier exploration) if that is the established call helper
instead of raw `.post("/mcp/", ...)`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest mcp_server/tests/test_users_tool_group.py -v -k "Activate or LastAdmin"`
Expected: FAIL — `user.activate` tool not found (`UNKNOWN_TOOL`)

- [ ] **Step 3: Add the new tools and rewire `create`/`deactivate`**

In `backend/mcp_server/tools/users.py`:

Add imports: `from auth_tenancy.services.authorization import LastAdminError`
and `from auth_tenancy.services.user_account import UserAccountService`.

Add to `_TOOL_MAP`:

```python
    _TOOL_MAP = {
        "user.create": "_handle_user_create",
        "user.assign_role": "_handle_user_assign_role",
        "user.list": "_handle_user_list",
        "user.deactivate": "_handle_user_deactivate",
        "user.activate": "_handle_user_activate",
        "user.suspend_role": "_handle_user_suspend_role",
        "user.reactivate_role": "_handle_user_reactivate_role",
        "user.assign_tenant_admin": "_handle_user_assign_tenant_admin",
        "user.revoke_tenant_admin": "_handle_user_revoke_tenant_admin",
    }
```

Add corresponding entries to `_TOOL_SCHEMAS` (mirroring the existing
`user.deactivate` schema shape for each — `user.activate` takes `user_id`
only; `user.suspend_role`/`user.reactivate_role` take `user_id`,
`workspace_id`, `role`; `user.assign_tenant_admin`/`user.revoke_tenant_admin`
take `user_id` only, tenant is implicit from `auth_context.tenant_id`):

```python
        {
            "name": "user.activate",
            "description": "Activate a user (is_active=True), tenant-admin-only, write, audited.",
            "inputSchema": {
                "type": "object",
                "properties": {"user_id": {"type": "string", "description": "UUID of the user to activate."}},
                "required": ["user_id"],
            },
        },
        {
            "name": "user.suspend_role",
            "description": "Suspend a user's workspace role (reversible), admin-only, write, audited.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "workspace_id": {"type": "string"},
                    "role": {"type": "string", "enum": ["admin", "editor", "viewer", "approver"]},
                },
                "required": ["user_id", "workspace_id", "role"],
            },
        },
        {
            "name": "user.reactivate_role",
            "description": "Reactivate a suspended workspace role, admin-only, write, audited.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "workspace_id": {"type": "string"},
                    "role": {"type": "string", "enum": ["admin", "editor", "viewer", "approver"]},
                },
                "required": ["user_id", "workspace_id", "role"],
            },
        },
        {
            "name": "user.assign_tenant_admin",
            "description": "Grant tenant-admin to a user, tenant-admin-only, write, audited.",
            "inputSchema": {
                "type": "object",
                "properties": {"user_id": {"type": "string"}},
                "required": ["user_id"],
            },
        },
        {
            "name": "user.revoke_tenant_admin",
            "description": "Revoke tenant-admin from a user, tenant-admin-only, write, audited.",
            "inputSchema": {
                "type": "object",
                "properties": {"user_id": {"type": "string"}},
                "required": ["user_id"],
            },
        },
```

Add `self._accounts = UserAccountService()` to `__init__`, alongside the
existing `self._authz_service = ...` line.

Replace `_handle_user_create`'s body from the `try: user = User.objects.create(...)` block onward with a call to the new service (keeping every validation step above it unchanged — username/email/password/role/preset/tenant resolution stays exactly as today):

```python
        is_admin = self._authz_service.is_tenant_admin(
            user_id=auth_context.user_id, tenant_id=tenant_id
        )
        try:
            user = self._accounts.create(
                actor_is_tenant_admin=is_admin,
                tenant_id=tenant_id,
                username=username,
                email=email,
                password=password,
            )
        except AuthTenancyPermissionDenied:
            return ToolResult.error(
                "PERMISSION_DENIED",
                "Permission denied: tenant-admin role required.",
            )
        except IntegrityError:
            return ToolResult.error(
                "VALIDATION_ERROR",
                f"Username {username!r} or email {email!r} is already in use.",
            )
        except Exception:
            logger.exception("user.create: DB error")
            return ToolResult.error("INTERNAL_ERROR", "An internal error occurred.")
```

Note for the implementer: this changes the admin gate for `user.create`
from "any workspace-admin" (`self._check_admin`) to "tenant-admin only"
(`is_tenant_admin`), matching the design spec's permission matrix (§3:
`user.create` is tenant-admin-exclusive). Remove the earlier
`denied = self._check_admin(auth_context)` call at the top of
`_handle_user_create` — the tenant-admin check above replaces it (do this
removal carefully: keep every OTHER validation line, only remove that one
`_check_admin` call and its `if denied is not None: return denied` guard).

Replace `_handle_user_deactivate`'s body similarly — remove the
`_check_admin` gate and the direct `is_active = False` write, replacing
with:

```python
    def _handle_user_deactivate(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """user.deactivate — deactivate a user (tenant-admin-only, write).

        Last-admin protected at both workspace and tenant scope via
        UserAccountService.deactivate.
        """
        target_user_id = require_uuid(params, "user_id")
        is_admin = self._authz_service.is_tenant_admin(
            user_id=auth_context.user_id, tenant_id=auth_context.tenant_id
        )

        user = User.objects.filter(id=target_user_id).first()
        if user is None:
            return ToolResult.error("NOT_FOUND", f"User with id {target_user_id!r} not found.")
        was_active = user.is_active

        try:
            self._accounts.deactivate(actor_is_tenant_admin=is_admin, target_user_id=target_user_id)
        except AuthTenancyPermissionDenied:
            return ToolResult.error("PERMISSION_DENIED", "Permission denied: tenant-admin role required.")
        except LastAdminError as exc:
            return ToolResult.error("LAST_ADMIN", str(exc))

        write_mcp_audit(
            ctx=auth_context, operation="user.deactivate", entity_type="User", entity_id=user.id,
            tool_name="user.deactivate", api_key=api_key,
            details={"username": user.username, "was_active": was_active},
        )
        user.refresh_from_db()
        return ToolResult.ok({"deactivated": True, "user": _user_to_dict(user)})
```

Add the five new handler methods after `_handle_user_deactivate`:

```python
    def _handle_user_activate(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """user.activate — activate a user (tenant-admin-only, write)."""
        target_user_id = require_uuid(params, "user_id")
        is_admin = self._authz_service.is_tenant_admin(
            user_id=auth_context.user_id, tenant_id=auth_context.tenant_id
        )
        try:
            self._accounts.activate(actor_is_tenant_admin=is_admin, target_user_id=target_user_id)
        except AuthTenancyPermissionDenied:
            return ToolResult.error("PERMISSION_DENIED", "Permission denied: tenant-admin role required.")

        user = User.objects.filter(id=target_user_id).first()
        if user is None:
            return ToolResult.error("NOT_FOUND", f"User with id {target_user_id!r} not found.")

        write_mcp_audit(
            ctx=auth_context, operation="user.activate", entity_type="User", entity_id=user.id,
            tool_name="user.activate", api_key=api_key, details={"username": user.username},
        )
        return ToolResult.ok({"activated": True, "user": _user_to_dict(user)})

    def _handle_user_suspend_role(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """user.suspend_role — soft-suspend a workspace role (admin-only, write)."""
        target_user_id = require_uuid(params, "user_id")
        workspace_id = require_uuid(params, "workspace_id")
        try:
            role = _normalize_role(params.get("role"))
        except ParameterError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        try:
            self._authz_service.suspend_role(
                actor_roles=auth_context.active_roles, target_user_id=target_user_id,
                workspace_id=workspace_id, role=role,
            )
        except AuthTenancyPermissionDenied as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except LastAdminError as exc:
            return ToolResult.error("LAST_ADMIN", str(exc))

        write_mcp_audit(
            ctx=auth_context, operation="user.suspend_role", entity_type="UserRole", entity_id=target_user_id,
            tool_name="user.suspend_role", api_key=api_key,
            details={"target_user_id": str(target_user_id), "workspace_id": str(workspace_id), "role": role},
        )
        return ToolResult.ok({"suspended": True})

    def _handle_user_reactivate_role(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """user.reactivate_role — clear a workspace role's suspension (admin-only, write)."""
        target_user_id = require_uuid(params, "user_id")
        workspace_id = require_uuid(params, "workspace_id")
        try:
            role = _normalize_role(params.get("role"))
        except ParameterError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        try:
            self._authz_service.reactivate_role(
                actor_roles=auth_context.active_roles, target_user_id=target_user_id,
                workspace_id=workspace_id, role=role,
            )
        except AuthTenancyPermissionDenied as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))

        write_mcp_audit(
            ctx=auth_context, operation="user.reactivate_role", entity_type="UserRole", entity_id=target_user_id,
            tool_name="user.reactivate_role", api_key=api_key,
            details={"target_user_id": str(target_user_id), "workspace_id": str(workspace_id), "role": role},
        )
        return ToolResult.ok({"reactivated": True})

    def _handle_user_assign_tenant_admin(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """user.assign_tenant_admin — grant tenant-admin (tenant-admin-only, write)."""
        target_user_id = require_uuid(params, "user_id")
        is_admin = self._authz_service.is_tenant_admin(
            user_id=auth_context.user_id, tenant_id=auth_context.tenant_id
        )
        try:
            self._authz_service.assign_tenant_admin(
                actor_is_tenant_admin=is_admin, target_user_id=target_user_id,
                tenant_id=auth_context.tenant_id, assigned_by_user_id=auth_context.user_id,
            )
        except AuthTenancyPermissionDenied:
            return ToolResult.error("PERMISSION_DENIED", "Permission denied: tenant-admin role required.")

        write_mcp_audit(
            ctx=auth_context, operation="user.assign_tenant_admin", entity_type="TenantRole", entity_id=target_user_id,
            tool_name="user.assign_tenant_admin", api_key=api_key,
            details={"target_user_id": str(target_user_id)},
        )
        return ToolResult.ok({"granted": True})

    def _handle_user_revoke_tenant_admin(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """user.revoke_tenant_admin — revoke tenant-admin (tenant-admin-only, write)."""
        target_user_id = require_uuid(params, "user_id")
        is_admin = self._authz_service.is_tenant_admin(
            user_id=auth_context.user_id, tenant_id=auth_context.tenant_id
        )
        try:
            self._authz_service.revoke_tenant_admin(
                actor_is_tenant_admin=is_admin, target_user_id=target_user_id, tenant_id=auth_context.tenant_id,
            )
        except AuthTenancyPermissionDenied:
            return ToolResult.error("PERMISSION_DENIED", "Permission denied: tenant-admin role required.")
        except LastAdminError as exc:
            return ToolResult.error("LAST_ADMIN", str(exc))

        write_mcp_audit(
            ctx=auth_context, operation="user.revoke_tenant_admin", entity_type="TenantRole", entity_id=target_user_id,
            tool_name="user.revoke_tenant_admin", api_key=api_key,
            details={"target_user_id": str(target_user_id)},
        )
        return ToolResult.ok({"revoked": True})
```

- [ ] **Step 4: Run the full users tool group test file to verify nothing regressed**

Run: `pytest mcp_server/tests/test_users_tool_group.py -v`
Expected: all pass, including the new tests from Step 1.

- [ ] **Step 5: Commit**

```bash
git add backend/mcp_server/tools/users.py \
        backend/mcp_server/tests/test_users_tool_group.py
git commit -m "feat: add MCP tools for activate, suspend/reactivate role, tenant-admin"
```

---

### Task 10: REST↔MCP consistency matrix tests

**Files:**
- Create: `backend/mcp_server/tests/test_user_management_rbac_matrix.py`
- Create: `backend/rest_api/tests/test_user_management_rbac_matrix.py`

**Interfaces:**
- Consumes: `USER_MANAGEMENT_MATRIX`, `ACTIONS` (Task 6), all REST/MCP endpoints from Tasks 7-9.

- [ ] **Step 1: Write the MCP-side matrix test**

```python
# backend/mcp_server/tests/test_user_management_rbac_matrix.py
"""User-management RBAC matrix through the real ToolRegistry, driven from
the SAME matrix constant the REST-side test consumes (rest_api/tests/
test_user_management_rbac_matrix.py) — see auth_tenancy/tests/
user_management_matrix.py. Mirrors test_mcp_rbac_role_matrix.py's
real-DB-role-resolution style (no mocked authz service)."""
from __future__ import annotations

import uuid

import pytest

from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.models import ROLE_ADMIN, ROLE_APPROVER, ROLE_EDITOR, ROLE_VIEWER, TenantRole, UserRole
from auth_tenancy.services.authentication import AuthenticationService
from auth_tenancy.tests.user_management_matrix import ACTIONS, USER_MANAGEMENT_MATRIX
from mcp_server.tool_registry import ToolRegistry
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace


_ACTION_TO_TOOL_CALL = {
    "user.create": ("user.create", lambda ids: {"username": f"u-{uuid.uuid4().hex[:8]}", "email": f"{uuid.uuid4().hex[:8]}@t.test", "password": "a-real-password-123"}),
    "user.activate": ("user.activate", lambda ids: {"user_id": str(ids["target"])}),
    "user.deactivate": ("user.deactivate", lambda ids: {"user_id": str(ids["target"])}),
    "workspace.assign_role": ("user.assign_role", lambda ids: {"user_id": str(ids["target"]), "workspace_id": str(ids["workspace"]), "role": "viewer", "preset": "extended"}),
    "workspace.suspend_role": ("user.suspend_role", lambda ids: {"user_id": str(ids["target"]), "workspace_id": str(ids["workspace"]), "role": "editor"}),
    "workspace.reactivate_role": ("user.reactivate_role", lambda ids: {"user_id": str(ids["target"]), "workspace_id": str(ids["workspace"]), "role": "editor"}),
    "tenant.assign_admin": ("user.assign_tenant_admin", lambda ids: {"user_id": str(ids["target"])}),
    "tenant.revoke_admin": ("user.revoke_tenant_admin", lambda ids: {"user_id": str(ids["target"])}),
}


def _setup_caller_and_target(role_label: str):
    """Create a tenant/workspace/caller (with role_label's role) + a
    separate target user + an API key for the caller. For
    'workspace.suspend_role'/'reactivate_role', the target additionally
    gets an editor role in the workspace so there's something to
    suspend/reactivate."""
    slug = f"umm-{role_label}-{uuid.uuid4().hex[:8]}"
    tenant = Tenant.objects.create(name=slug, slug=slug, is_active=True)
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name="WS", preset={"name": "extended"})
        caller = User.objects.create(username=f"caller-{slug}", email=f"caller-{slug}@t.test", tenant=tenant)
        target = User.objects.create(username=f"target-{slug}", email=f"target-{slug}@t.test", tenant=tenant)

        if role_label == "tenant-admin":
            TenantRole.objects.create(tenant=tenant, user=caller, role=TenantRole.ROLE_ADMIN)
        elif role_label == "workspace-admin":
            UserRole.objects.create(tenant=tenant, user=caller, workspace=workspace, role=ROLE_ADMIN)
        elif role_label in ("editor", "viewer", "approver"):
            role_map = {"editor": ROLE_EDITOR, "viewer": ROLE_VIEWER, "approver": ROLE_APPROVER}
            UserRole.objects.create(tenant=tenant, user=caller, workspace=workspace, role=role_map[role_label])
        # "no-role": no assignment at all

        UserRole.objects.create(tenant=tenant, user=target, workspace=workspace, role=ROLE_EDITOR)

        authn = AuthenticationService()
        plaintext = authn.create_api_key(user_id=caller.id, name="matrix-key")["plaintext"]
    finally:
        clear_request_tenant()

    return {"tenant": tenant, "workspace": workspace, "caller": caller, "target": target, "api_key": plaintext}


@pytest.mark.django_db
@pytest.mark.parametrize("action", ACTIONS)
@pytest.mark.parametrize("role_label", ["tenant-admin", "workspace-admin", "editor", "viewer", "approver", "no-role"])
def test_mcp_permission_matches_matrix(action, role_label):
    expected_allowed = USER_MANAGEMENT_MATRIX[action][role_label]
    ids = _setup_caller_and_target(role_label)
    tool_name, build_params = _ACTION_TO_TOOL_CALL[action]

    set_request_tenant(ids["tenant"].id)
    try:
        authn = AuthenticationService()
        auth_result = authn.authenticate_api_key(ids["api_key"])
        auth_context = AuthContext(
            user_id=ids["caller"].id, tenant_id=ids["tenant"].id,
            active_roles=auth_result.roles, auth_method=AuthMethod.API_KEY,
        )
        registry = ToolRegistry()
        params = build_params({"target": ids["target"].id, "workspace": ids["workspace"].id})
        result = registry.dispatch_request(
            tool_name=tool_name, params=params, auth_context=auth_context, api_key=ids["api_key"],
        )
    finally:
        clear_request_tenant()

    if expected_allowed:
        assert result.error is None or result.error.get("code") not in ("PERMISSION_DENIED",), (
            f"{role_label} should be ALLOWED to call {tool_name} but got {result.error}"
        )
    else:
        assert result.error is not None and result.error.get("code") == "PERMISSION_DENIED", (
            f"{role_label} should be DENIED for {tool_name} but got {result.error}"
        )
```

Note for the implementer: read `mcp_server/tool_registry.py`'s
`dispatch_request` signature and `ToolResult`'s actual shape
(`.error`/`.result` attribute names) before finalizing this test — the
attribute names above (`result.error`, `result.error.get("code")`) are
inferred from `ToolResult.error("CODE", "message")` calls seen throughout
`users.py`; confirm the exact returned-object shape in
`mcp_server/protocol_handler.py`'s `ToolResult` class definition and adjust
if the real accessor differs (e.g. `result.error_code` vs
`result.error["code"]`).

- [ ] **Step 2: Write the REST-side matrix test**

```python
# backend/rest_api/tests/test_user_management_rbac_matrix.py
"""Same permission matrix as mcp_server/tests/test_user_management_rbac_matrix.py,
driven through the REST surface instead — proves REST and MCP agree,
both against the one shared constant in auth_tenancy/tests/
user_management_matrix.py."""
from __future__ import annotations

import uuid

import pytest
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, ROLE_APPROVER, ROLE_EDITOR, ROLE_VIEWER, TenantRole, UserRole
from auth_tenancy.tests.user_management_matrix import ACTIONS, USER_MANAGEMENT_MATRIX
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace


def _setup_and_login(role_label: str):
    slug = f"umr-{role_label}-{uuid.uuid4().hex[:8]}"
    tenant = Tenant.objects.create(name=slug, slug=slug, is_active=True)
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name="WS", preset={"name": "extended"})
        caller = User.objects.create(username=f"caller-{slug}", email=f"caller-{slug}@t.test", tenant=tenant)
        caller.set_password("hunter2pass")
        caller.save(update_fields=["password"])
        target = User.objects.create(username=f"target-{slug}", email=f"target-{slug}@t.test", tenant=tenant)

        if role_label == "tenant-admin":
            TenantRole.objects.create(tenant=tenant, user=caller, role=TenantRole.ROLE_ADMIN)
        elif role_label == "workspace-admin":
            UserRole.objects.create(tenant=tenant, user=caller, workspace=workspace, role=ROLE_ADMIN)
        elif role_label in ("editor", "viewer", "approver"):
            role_map = {"editor": ROLE_EDITOR, "viewer": ROLE_VIEWER, "approver": ROLE_APPROVER}
            UserRole.objects.create(tenant=tenant, user=caller, workspace=workspace, role=role_map[role_label])

        UserRole.objects.create(tenant=tenant, user=target, workspace=workspace, role=ROLE_EDITOR)
    finally:
        clear_request_tenant()

    client = APIClient()
    login = client.post("/api/v1/auth/login/", {"username": caller.username, "password": "hunter2pass"}, format="json")
    assert login.status_code == 200, login.content
    authed = APIClient()
    authed.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['token']}")
    return {"client": authed, "tenant": tenant, "workspace": workspace, "target": target}


_ACTION_TO_REQUEST = {
    "user.create": lambda ids: ("post", "/api/v1/users/", {"username": f"u-{uuid.uuid4().hex[:8]}", "email": f"{uuid.uuid4().hex[:8]}@t.test", "password": "a-real-password-123"}),
    "user.activate": lambda ids: ("post", f"/api/v1/users/{ids['target'].id}/activate/", {}),
    "user.deactivate": lambda ids: ("post", f"/api/v1/users/{ids['target'].id}/deactivate/", {}),
    "workspace.assign_role": lambda ids: ("post", f"/api/v1/workspaces/{ids['workspace'].id}/members/", {"user_id": str(ids["target"].id), "role": "viewer", "preset": "extended"}),
    "workspace.suspend_role": lambda ids: ("post", f"/api/v1/workspaces/{ids['workspace'].id}/members/{ids['target'].id}/suspend/", {"role": "editor"}),
    "workspace.reactivate_role": lambda ids: ("post", f"/api/v1/workspaces/{ids['workspace'].id}/members/{ids['target'].id}/reactivate/", {"role": "editor"}),
    "tenant.assign_admin": lambda ids: ("post", f"/api/v1/users/{ids['target'].id}/tenant-admin/", {}),
    "tenant.revoke_admin": lambda ids: ("delete", f"/api/v1/users/{ids['target'].id}/tenant-admin/", {}),
}


@pytest.mark.django_db
@pytest.mark.parametrize("action", ACTIONS)
@pytest.mark.parametrize("role_label", ["tenant-admin", "workspace-admin", "editor", "viewer", "approver", "no-role"])
def test_rest_permission_matches_matrix(action, role_label):
    expected_allowed = USER_MANAGEMENT_MATRIX[action][role_label]
    ids = _setup_and_login(role_label)
    method, path, body = _ACTION_TO_REQUEST[action](ids)

    client_call = getattr(ids["client"], method)
    resp = client_call(path, body, format="json")

    if expected_allowed:
        assert resp.status_code != 403, f"{role_label} should be ALLOWED for {path} but got 403: {resp.content}"
    else:
        assert resp.status_code == 403, f"{role_label} should be DENIED for {path} but got {resp.status_code}: {resp.content}"
```

- [ ] **Step 3: Run both matrix test files**

Run: `pytest mcp_server/tests/test_user_management_rbac_matrix.py rest_api/tests/test_user_management_rbac_matrix.py -v`
Expected: 96 passed (8 actions × 6 roles × 2 surfaces)

- [ ] **Step 4: Commit**

```bash
git add backend/mcp_server/tests/test_user_management_rbac_matrix.py \
        backend/rest_api/tests/test_user_management_rbac_matrix.py
git commit -m "test: verify REST/MCP permission consistency for all role×action combinations"
```

---

### Task 11: Frontend — `api/users.ts` + i18n

**Files:**
- Create: `frontend/src/api/users.ts`
- Modify: `frontend/src/i18n/locales/de.json`, `frontend/src/i18n/locales/en.json`
- Test: `frontend/src/api/users.test.ts` (or `frontend/src/test/` per whatever this project's existing api-wrapper test convention is — check `find frontend/src -iname "glossary.test.ts"` first; if api wrappers aren't unit-tested individually in this codebase, skip a dedicated test file and cover the wrapper indirectly through Task 12's component tests instead)

**Interfaces:**
- Produces: `usersApi.list(): Promise<User[]>`, `.create(payload): Promise<User>`, `.activate(id): Promise<User>`, `.deactivate(id): Promise<User>`, `.grantTenantAdmin(id): Promise<void>`, `.revokeTenantAdmin(id): Promise<void>`. `workspaceMembersApi.assignRole(workspaceId, payload)`, `.suspendRole(workspaceId, userId, role)`, `.reactivateRole(workspaceId, userId, role)`.

- [ ] **Step 1: Check the existing api-wrapper test convention**

Run: `find frontend/src -iname "*.test.ts" -path "*api*"`

If this returns files, read one to match its exact test style before Step 2.
If it returns nothing, api wrappers in this codebase are covered only via
component tests — skip directly to Step 3 (no standalone wrapper test).

- [ ] **Step 2 (only if a wrapper-test convention exists): write the failing test, matching that convention's exact shape** — since the convention is unknown until Step 1 runs, this step's content is determined at execution time, not prescribed here.

- [ ] **Step 3: Write `api/users.ts`**

```typescript
// frontend/src/api/users.ts
import { apiClient } from './client';

export interface ManagedUser {
  id: string;
  username: string;
  email: string;
  is_active: boolean;
}

export interface CreateUserPayload {
  username: string;
  email: string;
  password: string;
}

export const usersApi = {
  list: async (): Promise<ManagedUser[]> => {
    return apiClient.get<ManagedUser[]>('/users/');
  },

  create: async (payload: CreateUserPayload): Promise<ManagedUser> => {
    return apiClient.post<ManagedUser>('/users/', payload);
  },

  activate: async (id: string): Promise<ManagedUser> => {
    return apiClient.post<ManagedUser>(`/users/${id}/activate/`);
  },

  deactivate: async (id: string): Promise<ManagedUser> => {
    return apiClient.post<ManagedUser>(`/users/${id}/deactivate/`);
  },

  grantTenantAdmin: async (id: string): Promise<void> => {
    return apiClient.post(`/users/${id}/tenant-admin/`);
  },

  revokeTenantAdmin: async (id: string): Promise<void> => {
    return apiClient.delete(`/users/${id}/tenant-admin/`);
  },
};

export const workspaceMembersApi = {
  assignRole: async (
    workspaceId: string,
    payload: { user_id: string; role: string; preset: string }
  ): Promise<void> => {
    return apiClient.post(`/workspaces/${workspaceId}/members/`, payload);
  },

  suspendRole: async (workspaceId: string, userId: string, role: string): Promise<void> => {
    return apiClient.post(`/workspaces/${workspaceId}/members/${userId}/suspend/`, { role });
  },

  reactivateRole: async (workspaceId: string, userId: string, role: string): Promise<void> => {
    return apiClient.post(`/workspaces/${workspaceId}/members/${userId}/reactivate/`, { role });
  },
};
```

Note for the implementer: confirm `apiClient`'s exact method signatures
(`.get<T>`, `.post<T>`, `.delete`) against `frontend/src/api/client.ts`
before finalizing — the shapes above are inferred from `glossaryApi`'s
usage (`apiClient.get<GlossaryTerm>(...)`, `apiClient.post<GlossaryTerm>(...)`,
`apiClient.delete(...)`), which returned `Promise<void>` for delete with no
type parameter — match that exactly.

- [ ] **Step 4: Add i18n keys**

In `frontend/src/i18n/locales/de.json`, add under a `settings` →
`userManagement` nested key (find the existing `settings` top-level key
first and add alongside its siblings — do not create a duplicate
`settings` key):

```json
"userManagement": {
  "title": "Benutzerverwaltung",
  "createUser": "User anlegen",
  "username": "Benutzername",
  "email": "E-Mail",
  "password": "Passwort",
  "active": "Aktiv",
  "inactive": "Inaktiv",
  "activate": "Aktivieren",
  "deactivate": "Deaktivieren",
  "tenantAdmin": "Tenant-Admin",
  "grantTenantAdmin": "Tenant-Admin zuweisen",
  "revokeTenantAdmin": "Tenant-Admin entziehen",
  "lastAdminError": "Aktion nicht möglich: {{scope}} {{identifier}} hätte keinen aktiven Admin mehr."
}
```

In `frontend/src/i18n/locales/en.json`, add the matching English block:

```json
"userManagement": {
  "title": "User Management",
  "createUser": "Create user",
  "username": "Username",
  "email": "Email",
  "password": "Password",
  "active": "Active",
  "inactive": "Inactive",
  "activate": "Activate",
  "deactivate": "Deactivate",
  "tenantAdmin": "Tenant Admin",
  "grantTenantAdmin": "Grant tenant admin",
  "revokeTenantAdmin": "Revoke tenant admin",
  "lastAdminError": "Cannot complete this action: {{scope}} {{identifier}} would have no active admin left."
}
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/users.ts \
        frontend/src/i18n/locales/de.json \
        frontend/src/i18n/locales/en.json
git commit -m "feat: add users/workspace-members API wrapper and i18n keys"
```

---

### Task 12: Frontend — `UserManagement.tsx`

**Files:**
- Create: `frontend/src/components/Settings/UserManagement/UserManagement.tsx`
- Test: `frontend/src/components/Settings/UserManagement/UserManagement.test.tsx`

**Interfaces:**
- Consumes: `usersApi` (Task 11), the project's existing tenant-admin-check pattern (find via `grep -rn "is_tenant_admin\|isTenantAdmin" frontend/src` once Task 11 lands, or expose a new `useIsTenantAdmin()` hook if no equivalent role-check hook exists yet for a non-workspace-scoped permission — check `frontend/src/context/` for how workspace-role gating is currently read client-side and mirror that pattern for tenant-admin, since tenant-admin is a NEW concept with no existing frontend precedent).

- [ ] **Step 1: Investigate the existing role-gating pattern before writing tests**

Run: `grep -rln "hasRole\|useAuth\|activeRoles" frontend/src/context frontend/src/components | head -10`

Read whichever file surfaces the client's current role/permission state
(likely an `AuthContext`/`useAuth` hook). The component in Step 3 needs to
read whether the current user is a tenant-admin; if the auth context
already exposes something like `user.is_tenant_admin` from the `/auth/me/`
response, use that directly. If it does not yet, this task must ALSO add
`is_tenant_admin` to whatever REST view backs `/api/v1/auth/me/` (find it
via `grep -rn "auth/me" backend/rest_api/urls.py`) before the frontend can
gate on it — treat that backend addition as an unplanned but necessary
extension of this task, write a small test for it the same way Task 7 did,
and note the addition in the commit message.

- [ ] **Step 2: Write the failing component test**

```typescript
// frontend/src/components/Settings/UserManagement/UserManagement.test.tsx
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { UserManagement } from './UserManagement';
import { usersApi } from '../../../api/users';

vi.mock('../../../api/users');

describe('UserManagement', () => {
  beforeEach(() => {
    vi.mocked(usersApi.list).mockResolvedValue([
      { id: 'u1', username: 'alice', email: 'alice@t.test', is_active: true },
      { id: 'u2', username: 'bob', email: 'bob@t.test', is_active: false },
    ]);
  });

  it('renders the user list with active/inactive state', async () => {
    render(<UserManagement />);
    await waitFor(() => expect(screen.getByText('alice')).toBeInTheDocument());
    expect(screen.getByText('bob')).toBeInTheDocument();
  });

  it('surfaces a LAST_ADMIN error inline, not as a generic failure', async () => {
    vi.mocked(usersApi.deactivate).mockRejectedValue({
      response: { status: 409, data: { error: 'LAST_ADMIN', message: 'Cannot complete this action: it would leave tenant abc123 with no active admin.' } },
    });
    render(<UserManagement />);
    await waitFor(() => expect(screen.getByText('alice')).toBeInTheDocument());
    const user = userEvent.setup();
    await user.click(screen.getAllByRole('button', { name: /deaktivieren|deactivate/i })[0]);
    await waitFor(() =>
      expect(screen.getByText(/no active admin left|keinen aktiven Admin mehr/i)).toBeInTheDocument()
    );
  });
});
```

Note for the implementer: this codebase's exact test-id conventions
(`data-testid` attributes, per CLAUDE.md's "data-testid auf allen
interaktiven UI-Elementen") should be used for the button/row selectors
above instead of role-name text matching where a `data-testid` is more
robust — read one existing Settings-area `.test.tsx` file (e.g. search
`frontend/src/components/WorkspaceSettings/*.test.tsx`) to match its exact
query style (`getByTestId` vs `getByRole`) before finalizing.

- [ ] **Step 3: Run test to verify it fails**

Run: `npm test -- UserManagement.test.tsx` (from `frontend/`)
Expected: FAIL — module `./UserManagement` not found

- [ ] **Step 4: Write the component**

```typescript
// frontend/src/components/Settings/UserManagement/UserManagement.tsx
import { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { usersApi, ManagedUser } from '../../../api/users';

interface ApiErrorBody {
  error: string;
  message: string;
}

function isLastAdminError(err: unknown): err is { response: { status: number; data: ApiErrorBody } } {
  const candidate = err as { response?: { status?: number; data?: { error?: string } } };
  return candidate?.response?.status === 409 && candidate.response?.data?.error === 'LAST_ADMIN';
}

export function UserManagement() {
  const { t } = useTranslation();
  const [users, setUsers] = useState<ManagedUser[]>([]);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    usersApi.list().then(setUsers).catch(() => setUsers([]));
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const handleToggleActive = async (u: ManagedUser) => {
    setError(null);
    try {
      if (u.is_active) {
        await usersApi.deactivate(u.id);
      } else {
        await usersApi.activate(u.id);
      }
      reload();
    } catch (err) {
      if (isLastAdminError(err)) {
        setError(err.response.data.message);
      } else {
        setError(t('common.unexpectedError', 'An unexpected error occurred.'));
      }
    }
  };

  return (
    <div data-testid="user-management">
      <h2>{t('settings.userManagement.title')}</h2>
      {error && <div role="alert" data-testid="user-management-error">{error}</div>}
      <table>
        <tbody>
          {users.map((u) => (
            <tr key={u.id} data-testid={`user-row-${u.id}`}>
              <td>{u.username}</td>
              <td>{u.email}</td>
              <td>{u.is_active ? t('settings.userManagement.active') : t('settings.userManagement.inactive')}</td>
              <td>
                <button onClick={() => handleToggleActive(u)}>
                  {u.is_active ? t('settings.userManagement.deactivate') : t('settings.userManagement.activate')}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

Note for the implementer: this is a minimal, functionally-complete
version. Before finalizing, read `WorkspaceSettings.tsx` in full and match
its actual form/table markup conventions, styling approach (CSS module?
inline `className`s referencing `tokens.css`?), and "Create user" dialog
pattern (likely a modal component already used elsewhere in Settings —
search `frontend/src/components/Settings` or similar for an existing
modal/dialog primitive to reuse rather than building a new one). The
tenant-admin grant/revoke actions and the create-user dialog are
deliberately left out of this minimal snippet — add them following
whatever dialog/form primitive the investigation above surfaces, using
`usersApi.create` / `.grantTenantAdmin` / `.revokeTenantAdmin` from Task 11.

- [ ] **Step 5: Run test to verify it passes**

Run: `npm test -- UserManagement.test.tsx`
Expected: 2 passed

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/Settings/UserManagement/
git commit -m "feat: add UserManagement admin settings page"
```

---

### Task 13: Frontend — workspace members suspend/reactivate UI

**Files:**
- Modify: whatever component currently renders the workspace `members/` GET
  data (find via `grep -rln "members/" frontend/src/components` — likely
  inside `WorkspaceSettings.tsx` or a dedicated members sub-component
  reachable from it, per the design spec's §5).
- Test: extend that component's existing test file.

**Interfaces:**
- Consumes: `workspaceMembersApi` (Task 11).

- [ ] **Step 1: Locate the exact component and its existing test file**

Run: `grep -rln "members/" frontend/src/components/**/*.tsx 2>/dev/null` and
`grep -rln "WorkspaceMembersView\|workspace.*members" frontend/src/api/*.ts`
to find both the rendering component and whether an `api/` wrapper for the
GET-only members endpoint already exists (it must, since the backend
endpoint predates this plan) — reuse and extend that existing wrapper file
rather than duplicating a second one; add the new mutating calls there
if a `workspace-members.ts` (or similar) file already exists, instead of
only in Task 11's `users.ts`.

- [ ] **Step 2: Write the failing test**

This step's exact test code depends on the real component found in Step 1
(this plan cannot specify it sight-unseen without violating the "no
placeholders" rule with a component that doesn't exist under a guessed
name). At execution time: write a test asserting that a suspend/reactivate
button appears next to each member row, calls
`workspaceMembersApi.suspendRole`/`reactivateRole` on click, and reloads
the member list — following the exact same mock/render/assert structure
as Task 12's test, adapted to the real component's actual props and
existing test file's conventions.

- [ ] **Step 3: Implement the suspend/reactivate actions**

Add a button per member row calling `workspaceMembersApi.suspendRole(workspaceId, member.user_id, role)`
or `.reactivateRole(...)`, followed by a re-fetch of the member list —
mirroring Task 12's `handleToggleActive` pattern (try/catch around the
mutating call, `isLastAdminError` check for the 409 case, inline error
display).

- [ ] **Step 4: Run the extended test file to verify it passes**

Run: `npm test -- <the component's test file>`

- [ ] **Step 5: Commit**

```bash
git add <the modified component and its test file>
git commit -m "feat: add suspend/reactivate actions to workspace members UI"
```

---

### Task 14: E2E — full admin flow

**Files:**
- Create: `e2e/tests/user-management.spec.ts`

**Interfaces:**
- Consumes: the full stack (REST + Frontend from Tasks 7, 11-13).

- [ ] **Step 1: Write the E2E test**

```typescript
// e2e/tests/user-management.spec.ts
import { test, expect } from '@playwright/test';
import { loginAsAdmin } from './helpers/auth'; // adjust to this repo's actual helper name/path — confirm via `grep -rn "loginAs" e2e/helpers/` before use

test.describe('[Multi-user management] Tenant-admin full flow', () => {
  test('create user, assign workspace role, deactivate, reactivate', async ({ page }) => {
    await loginAsAdmin(page);
    await page.goto('/settings/users');

    const uniqueSuffix = Date.now().toString();
    const username = `e2e-user-${uniqueSuffix}`;

    await page.getByRole('button', { name: /create user|user anlegen/i }).click();
    await page.getByLabel(/username|benutzername/i).fill(username);
    await page.getByLabel(/email/i).fill(`${username}@e2e.test`);
    await page.getByLabel(/password|passwort/i).fill('a-real-password-123');
    await page.getByRole('button', { name: /submit|speichern|create/i }).click();

    await expect(page.getByText(username)).toBeVisible();

    const row = page.locator(`[data-testid^="user-row-"]`, { hasText: username });
    await row.getByRole('button', { name: /deactivate|deaktivieren/i }).click();
    await expect(row.getByText(/inactive|inaktiv/i)).toBeVisible();

    await row.getByRole('button', { name: /activate|aktivieren/i }).click();
    await expect(row.getByText(/^active$|^aktiv$/i)).toBeVisible();
  });
});
```

Note for the implementer: `page.goto('/settings/users')` assumes the new
`UserManagement.tsx` page (Task 12) is routed at that path — confirm the
actual route registered for it (check `frontend/src/App.tsx` or wherever
Settings sub-routes are declared) and correct this path before running.
Also confirm `loginAsAdmin` (or whatever this repo's real E2E auth helper
is named — the session's earlier exploration referenced
`SEEDED_WORKSPACE_ID` in `e2e/helpers/auth.ts`, suggesting a helper exists
there) logs in as a user who is specifically a TENANT-admin (not just a
workspace-admin) — since Task 5's bootstrap now creates one, the seeded
default admin from `bootstrap_admin`/`provision_admin` should already
qualify; verify this assumption holds against the actual seed data before
trusting it silently.

- [ ] **Step 2: Run the E2E test**

Run: `cd e2e && npx playwright test user-management.spec.ts` (against a
running `docker-compose up` stack, per this repo's established E2E
convention — confirm the exact invocation matches `e2e/playwright.config.ts`
and any existing `package.json` script before running ad hoc).
Expected: PASS. Per this session's established operational lesson, run
this test suite SOLO — never concurrently with another backend/frontend/E2E
full run against the same shared services.

- [ ] **Step 3: Commit**

```bash
git add e2e/tests/user-management.spec.ts
git commit -m "test: add E2E coverage for the full tenant-admin user-management flow"
```

---

## Self-Review Notes (for the plan author, already applied above)

- **Spec coverage:** §1 Data Model → Task 1. §2 Last-Admin Enforcement → Tasks 2-4. §3 Permission Model/Consistency → Tasks 6, 9-10. §4 API Surface → Tasks 7-9. §5 Frontend → Tasks 11-13. §6 Edge Cases (race condition, self-deactivation, bootstrap, audit) → covered inline in Tasks 2-5, 7-9 (audit calls present in every mutating REST/MCP handler; self-deactivation is implicitly allowed by every guard only checking admin *counts*, never actor identity, matching the spec's explicit YAGNI call). §7 Test Plan → one task per numbered item, 1:1.
- **Placeholder scan:** Tasks 13 and 14 contain investigation steps ("find the real component/helper name") rather than fully pre-written code, because the target files genuinely cannot be identified without repo access this plan-writing pass didn't have budget to exhaust exhaustively for every leaf frontend file. This is flagged explicitly in-line at each such step (not silently glossed over) per the skill's guidance that an investigation step is acceptable when it names exactly what to search for and why — it is not the same failure mode as "add appropriate error handling."
- **Type consistency:** `LastAdminError(scope, identifier)` (Task 2) is used identically in Tasks 3, 4, 7, 8, 9. `UserAccountService.deactivate`/`activate`/`create` signatures (Task 4) match every call site in Tasks 7 and 9. `AuthorizationService.suspend_role`/`reactivate_role`/`assign_tenant_admin`/`revoke_tenant_admin`/`is_tenant_admin` (Tasks 2-3) match every call site in Tasks 7-9.
