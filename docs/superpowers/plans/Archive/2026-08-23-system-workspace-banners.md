# System & Workspace Banners Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Admins can broadcast a dismissible, Markdown-formatted announcement banner at the top of the app — one global banner (System-Admin only) and one banner per workspace (Workspace-Admin or System-Admin), both togglable, both level-styled (neutral/info/warning/critical).

**Architecture:** A new `Banner` model in the existing `admin_ops` Django app (an Ext-layer app, not subject to the `rest_api`-only ORM ratchet), fronted by a small `BannerService` and three thin REST views (global, per-workspace, and a public unauthenticated login-page variant). The frontend adds one display component (`BannerStack`, mounted in `NavigationShell` and `LoginPage`) and two settings sections (`BannerSection` in System Settings, `WorkspaceBannerSection` in Workspace Settings), all reusing the existing `react-markdown` rendering already used by `MarkdownPreview` and the existing `--color-primary`/`--color-warning`/`--color-danger`/`--color-text-muted` semantic tokens (no new CSS tokens needed).

**Tech Stack:** Django 4.2+ / DRF (backend), React 18 + TypeScript 5.5 + react-markdown (frontend), PostgreSQL (partial unique constraints for the "one banner per scope" rule).

**Spec:** `docs/superpowers/specs/2026-08-23-system-workspace-banners-design.md`

## Global Constraints

- Exactly one banner row per scope instance: one global row per tenant, one row per workspace. Editing overwrites via `update_or_create` — never a list.
- Global banner: read/write gated on `AuthorizationService.is_tenant_admin(user_id, tenant_id)` (the `TenantRole` table) — NOT on `ctx.has_role("admin")` (that is workspace-scoped `UserRole` and must not grant global-banner access).
- Workspace banner: read/write gated on `ctx.has_role("admin")` (workspace-scoped, since the URL carries `workspace_id` so `AuthTenancyAuthentication` resolves `active_roles` for that workspace) OR `is_tenant_admin` (System-Admin override).
- Four levels: `neutral`, `info`, `warning`, `critical` — map to existing CSS tokens `--color-text-muted`/`--color-primary`/`--color-warning`/`--color-danger`. No new CSS tokens.
- `dismissible` is a real, independently-editable model field (default `True`), never hardcoded by level — the admin form only *pre-fills* `False` when `level=critical` before first save.
- Dismiss state lives in `sessionStorage`, keyed by `banner-dismissed-<scope>-<id>-<updated_at>` — resets on next login (new tab/session), and an admin edit (new `updated_at`) always invalidates a prior dismissal.
- No scheduling, no banner history UI, no per-user targeting — manual enable/disable only (spec Non-Goals).
- **Deviation from spec, discovered during planning:** the spec assumed an existing pre-login tenant-resolution mechanism (subdomain/host header) for the public login-page endpoint. No such mechanism exists in this codebase — `LoginView` resolves tenant *from* the username during authentication, and the only precedent for a pre-auth "which tenant" signal is `settings.DEFAULT_TENANT_ID` (already used the same way, with the same caveat, by `se_metrics/views.py`). Task 3 below uses `settings.DEFAULT_TENANT_ID` for the public endpoint. This is a documented limitation (single-default-tenant deployments only), not a new invention — it reuses an existing, if imperfect, precedent rather than building real multi-tenant host routing, which is out of scope for this mini feature.

  > **Superseded by the final review (2026-08-23).** `settings.DEFAULT_TENANT_ID`
  > turned out to be unusable, not merely imperfect: it is declared
  > `config("DEFAULT_TENANT_ID", default=1, cast=int)`, so it is always an
  > `int`. Django's `UUIDField.to_python` silently coerces the shipped default
  > `1` into `uuid.UUID(int=1)`, which matches no real tenant in any
  > deployment, and `cast=int` prevents an operator from setting a real tenant
  > UUID instead (decouple raises at startup on a non-integer). The public
  > endpoint could therefore never return a banner. It now resolves the tenant
  > from the database via `BannerService.resolve_login_tenant_id`: exactly one
  > `Tenant` row -> that tenant; zero or more than one -> ambiguous -> the same
  > empty `204` as "no banner configured" (never a distinguishable error). The
  > structurally identical bug in `se_metrics/views.py` is out of scope for
  > this feature and was deliberately left untouched.
  >
  > Two further corrections from the same review:
  > * `admin_ops_banner` now carries an RLS policy
  >   (`admin_ops/migrations/0003_banner_rls.py`), matching every other
  >   `TenantScopedModel` table. Because the login-banner read happens on an
  >   unauthenticated request — where the tenant middleware never sets
  >   `app.current_tenant` — `get_login_banner` activates the resolved tenant
  >   explicitly via `set_request_tenant` and restores the prior context in a
  >   `finally`. Without that the RLS policy would silently return zero rows.
  > * `GlobalBannerView` / `WorkspaceBannerView` now declare
  >   `required_operation = Operation.READ` for `GET` (`None` for `PUT`),
  >   mirroring `WorkspaceMembersView`. `PUT` must stay ungated by the matrix
  >   so a pure System-Admin (`TenantRole(admin)`, `active_roles=()`) is not
  >   denied before the views' own tenant-admin elevation check runs.
  >
  > The public endpoint's response shape consequently grew `id` and
  > `updated_at` (spec §Frontend Display's dismiss key
  > `banner-dismissed-<scope>-<id>-<updated_at>` needs both), and the
  > spec-mandated login-page dismiss button was implemented in `LoginPage.tsx`.

---

### Task 1: Backend — `Banner` model + migration

**Files:**
- Modify: `backend/admin_ops/models.py`
- Create: `backend/admin_ops/migrations/0002_banner.py`
- Test: `backend/admin_ops/tests/test_banner_model.py`

**Interfaces:**
- Produces: `admin_ops.models.Banner` (fields: `id`, `tenant`, `scope`, `workspace`, `level`, `message`, `enabled`, `dismissible`, `show_on_login_page`, `created_at`/`modified_at`/`created_by`/`modified_by`/`version` inherited from `TenantScopedModel`), `admin_ops.models.BannerScope` (`GLOBAL="global"`, `WORKSPACE="workspace"`), `admin_ops.models.BannerLevel` (`NEUTRAL="neutral"`, `INFO="info"`, `WARNING="warning"`, `CRITICAL="critical"`).

- [ ] **Step 1: Add the model to `backend/admin_ops/models.py`**

Append to the end of `backend/admin_ops/models.py` (after the existing `BackupMetadata`/`__all__`):

```python
from persistence.models import TenantScopedModel


class BannerScope(models.TextChoices):
    """Which surface a :class:`Banner` targets."""

    GLOBAL = "global", "Global"
    WORKSPACE = "workspace", "Workspace"


class BannerLevel(models.TextChoices):
    """Visual/semantic severity of a :class:`Banner`."""

    NEUTRAL = "neutral", "Neutral"
    INFO = "info", "Info"
    WARNING = "warning", "Warning"
    CRITICAL = "critical", "Critical"


class Banner(TenantScopedModel):
    """A dismissible, Markdown announcement banner (System/Workspace Banners).

    Exactly one row exists per scope instance: one ``scope="global"`` row per
    tenant, one ``scope="workspace"`` row per workspace — enforced by the two
    partial unique constraints below, not by application logic alone. Callers
    always write through :meth:`BannerService.upsert_global_banner` /
    :meth:`~BannerService.upsert_workspace_banner`, which use
    ``update_or_create`` so an edit overwrites the existing row instead of
    creating a second one.

    ``workspace`` is NULL iff ``scope == "global"`` — enforced by
    ``ck_banner_workspace_matches_scope``.
    """

    scope = models.CharField(max_length=16, choices=BannerScope.choices)
    workspace = models.ForeignKey(
        "persistence.Workspace",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="banner",
    )
    level = models.CharField(
        max_length=16, choices=BannerLevel.choices, default=BannerLevel.NEUTRAL
    )
    message = models.TextField(blank=True, default="", help_text="Markdown source.")
    enabled = models.BooleanField(default=False)
    dismissible = models.BooleanField(
        default=True,
        help_text=(
            "Whether end users may close the banner (until next login). "
            "A real, independently-editable field — never hardcoded by level."
        ),
    )
    show_on_login_page = models.BooleanField(
        default=False,
        help_text="Ignored unless scope == 'global' — the login page has no workspace context.",
    )

    class Meta:
        db_table = "admin_ops_banner"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant"],
                condition=models.Q(scope=BannerScope.GLOBAL),
                name="uq_banner_one_global_per_tenant",
            ),
            models.UniqueConstraint(
                fields=["workspace"],
                condition=models.Q(scope=BannerScope.WORKSPACE),
                name="uq_banner_one_per_workspace",
            ),
            models.CheckConstraint(
                check=(
                    models.Q(scope=BannerScope.GLOBAL, workspace__isnull=True)
                    | models.Q(scope=BannerScope.WORKSPACE, workspace__isnull=False)
                ),
                name="ck_banner_workspace_matches_scope",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover - debug helper
        return f"Banner({self.scope}, level={self.level}, enabled={self.enabled})"


__all__ = [
    "BackupMetadata",
    "BackupStatus",
    "BackupType",
    "Banner",
    "BannerScope",
    "BannerLevel",
]
```

Note: `backend/admin_ops/models.py` already has `from django.db import models` at the top — do not add a duplicate import. Add `from persistence.models import TenantScopedModel` immediately below the existing `from persistence.models import AuditableModel` line (merge into one `from persistence.models import AuditableModel, TenantScopedModel` import instead of two separate lines).

- [ ] **Step 2: Write the migration**

Create `backend/admin_ops/migrations/0002_banner.py`:

```python
"""
admin_ops — adds the ``admin_ops_banner`` table (System & Workspace Banners).

Depends on the latest ``persistence`` migration that ships to production
(``0065_alter_interviewsession_status``, for the ``Workspace``/``Tenant``/
``User`` FK targets) and this app's own initial migration.

Hand-authored to match ``admin_ops/models.py``. ``makemigrations --check``
must report no further changes against this migration.
"""
from __future__ import annotations

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("admin_ops", "0001_initial"),
        ("persistence", "0065_alter_interviewsession_status"),
    ]

    operations = [
        migrations.CreateModel(
            name="Banner",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("modified_at", models.DateTimeField(auto_now=True)),
                ("version", models.IntegerField(default=1)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "modified_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        db_index=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="banner_set",
                        to="persistence.tenant",
                    ),
                ),
                (
                    "scope",
                    models.CharField(
                        choices=[("global", "Global"), ("workspace", "Workspace")],
                        max_length=16,
                    ),
                ),
                (
                    "workspace",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="banner",
                        to="persistence.workspace",
                    ),
                ),
                (
                    "level",
                    models.CharField(
                        choices=[
                            ("neutral", "Neutral"),
                            ("info", "Info"),
                            ("warning", "Warning"),
                            ("critical", "Critical"),
                        ],
                        default="neutral",
                        max_length=16,
                    ),
                ),
                (
                    "message",
                    models.TextField(blank=True, default="", help_text="Markdown source."),
                ),
                ("enabled", models.BooleanField(default=False)),
                (
                    "dismissible",
                    models.BooleanField(
                        default=True,
                        help_text=(
                            "Whether end users may close the banner (until next "
                            "login). A real, independently-editable field — "
                            "never hardcoded by level."
                        ),
                    ),
                ),
                (
                    "show_on_login_page",
                    models.BooleanField(
                        default=False,
                        help_text=(
                            "Ignored unless scope == 'global' — the login page "
                            "has no workspace context."
                        ),
                    ),
                ),
            ],
            options={
                "db_table": "admin_ops_banner",
            },
        ),
        migrations.AddConstraint(
            model_name="banner",
            constraint=models.UniqueConstraint(
                condition=models.Q(scope="global"),
                fields=("tenant",),
                name="uq_banner_one_global_per_tenant",
            ),
        ),
        migrations.AddConstraint(
            model_name="banner",
            constraint=models.UniqueConstraint(
                condition=models.Q(scope="workspace"),
                fields=("workspace",),
                name="uq_banner_one_per_workspace",
            ),
        ),
        migrations.AddConstraint(
            model_name="banner",
            constraint=models.CheckConstraint(
                check=(
                    models.Q(("scope", "global"), ("workspace__isnull", True))
                    | models.Q(("scope", "workspace"), ("workspace__isnull", False))
                ),
                name="ck_banner_workspace_matches_scope",
            ),
        ),
    ]
```

- [ ] **Step 3: Run the migration against the test DB and verify `makemigrations --check`**

Run (inside the backend container/venv):
```bash
python manage.py makemigrations admin_ops --check --dry-run
```
Expected: `No changes detected` (confirms the hand-written migration matches the model exactly).

```bash
python manage.py migrate admin_ops
```
Expected: applies `0002_banner` with no errors.

- [ ] **Step 4: Write the failing model test**

Create `backend/admin_ops/tests/test_banner_model.py`:

```python
"""Tests for the Banner model's DB-level invariants (uniqueness, check constraint)."""
from __future__ import annotations

import pytest
from django.db import IntegrityError, transaction

from admin_ops.models import Banner, BannerLevel, BannerScope
from persistence.models import Workspace

from .conftest import active_tenant


@pytest.mark.django_db
class TestBannerUniqueness:
    def test_second_global_banner_for_same_tenant_rejected(self, tenant_a) -> None:
        with active_tenant(tenant_a):
            Banner.objects.create(
                tenant=tenant_a, scope=BannerScope.GLOBAL, level=BannerLevel.INFO
            )
            with pytest.raises(IntegrityError):
                with transaction.atomic():
                    Banner.objects.create(
                        tenant=tenant_a, scope=BannerScope.GLOBAL, level=BannerLevel.WARNING
                    )

    def test_second_banner_for_same_workspace_rejected(self, tenant_a) -> None:
        with active_tenant(tenant_a):
            ws = Workspace.objects.create(tenant=tenant_a, name="ws-1")
            Banner.objects.create(
                tenant=tenant_a, scope=BannerScope.WORKSPACE, workspace=ws, level=BannerLevel.INFO
            )
            with pytest.raises(IntegrityError):
                with transaction.atomic():
                    Banner.objects.create(
                        tenant=tenant_a,
                        scope=BannerScope.WORKSPACE,
                        workspace=ws,
                        level=BannerLevel.WARNING,
                    )

    def test_global_banner_with_workspace_set_rejected(self, tenant_a) -> None:
        with active_tenant(tenant_a):
            ws = Workspace.objects.create(tenant=tenant_a, name="ws-2")
            with pytest.raises(IntegrityError):
                with transaction.atomic():
                    Banner.objects.create(
                        tenant=tenant_a, scope=BannerScope.GLOBAL, workspace=ws
                    )

    def test_workspace_banner_without_workspace_rejected(self, tenant_a) -> None:
        with active_tenant(tenant_a):
            with pytest.raises(IntegrityError):
                with transaction.atomic():
                    Banner.objects.create(tenant=tenant_a, scope=BannerScope.WORKSPACE)
```

- [ ] **Step 5: Run the test to verify it passes** (it exercises real DB constraints, so it should pass immediately once the migration is applied — this step is the "does the constraint actually work" check, not red/green TDD)

Run: `pytest backend/admin_ops/tests/test_banner_model.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/admin_ops/models.py backend/admin_ops/migrations/0002_banner.py backend/admin_ops/tests/test_banner_model.py
git commit -m "feat: add Banner model for system & workspace banners"
```

---

### Task 2: Backend — `BannerService`

**Files:**
- Create: `backend/admin_ops/services/banner_service.py`
- Modify: `backend/admin_ops/services/__init__.py` (export the new service, if this file re-exports service classes — check its current contents first; if it's empty/absent, skip this file)
- Test: `backend/admin_ops/tests/test_banner_service.py`

**Interfaces:**
- Consumes: `admin_ops.models.Banner`/`BannerScope`/`BannerLevel` (Task 1), `auth_tenancy.context.AuthContext`, `application.base.ServiceBase`/`PermissionDeniedError`/`NotFoundError`, `persistence.tenancy.TenantContext`, `persistence.models.Workspace`.
- Produces: `BannerService` with methods `get_global_banner(ctx) -> Banner | None`, `upsert_global_banner(ctx, *, is_system_admin: bool, level: str, message: str, enabled: bool, dismissible: bool, show_on_login_page: bool) -> Banner`, `get_workspace_banner(ctx, *, workspace_id: UUID) -> Banner | None`, `upsert_workspace_banner(ctx, *, workspace_id: UUID, is_authorized: bool, level: str, message: str, enabled: bool, dismissible: bool) -> Banner`, `get_login_banner(tenant_id: UUID) -> Banner | None` (module-level tenant, no `ctx` — used by the unauthenticated endpoint).

- [ ] **Step 1: Write the service**

Create `backend/admin_ops/services/banner_service.py`:

```python
"""
admin_ops — BannerService (System & Workspace Banners).

Stateless service owning the single-row-per-scope lifecycle of
:class:`~admin_ops.models.Banner`. Authorization is a caller-supplied
boolean (``is_system_admin`` / ``is_authorized``) rather than
``ServiceBase._assert_permission`` — the tenant-admin check
(:meth:`AuthorizationService.is_tenant_admin`) is not a role in
``ctx.active_roles``, so it must be resolved by the REST view (which has
the ``AuthorizationService`` call already, mirroring
``AuthorizationService.assign_role``'s ``actor_is_tenant_admin`` parameter)
and forwarded here as a plain flag. This is the same shape used by
``WorkspaceMembersView.post`` / ``rest_workspace_members.py``.
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from application.base import NotFoundError, PermissionDeniedError, ServiceBase
from auth_tenancy.context import AuthContext
from persistence.models import Workspace
from persistence.tenancy import TenantContext

from admin_ops.models import Banner, BannerLevel, BannerScope

logger = logging.getLogger(__name__)


class BannerService:
    """Get/upsert the single global banner and the single per-workspace banner."""

    # -- Global banner -----------------------------------------------------

    def get_global_banner(self, ctx: AuthContext) -> Optional[Banner]:
        """Return the tenant's global banner row, or ``None`` if never configured."""
        ServiceBase._set_tenant_context(ctx)
        return Banner.objects.filter(scope=BannerScope.GLOBAL).first()

    def upsert_global_banner(
        self,
        ctx: AuthContext,
        *,
        is_system_admin: bool,
        level: str,
        message: str,
        enabled: bool,
        dismissible: bool,
        show_on_login_page: bool,
    ) -> Banner:
        """Create or overwrite the tenant's single global banner row.

        Raises:
            PermissionDeniedError: ``is_system_admin`` is ``False``.
        """
        if not is_system_admin:
            raise PermissionDeniedError(
                "Permission denied: tenant-admin (System-Admin) role required."
            )
        ServiceBase._set_tenant_context(ctx)
        # update_or_create()/get_or_create() do NOT get TenantManager.create()'s
        # tenant auto-injection (that only fires on a bare .create() call) — the
        # tenant_id must be passed explicitly here or the insert 500s on the
        # NOT NULL constraint (see context_graph/projector.py's identical note).
        tenant_id = TenantContext.get_tenant()
        banner, _created = Banner.objects.update_or_create(
            scope=BannerScope.GLOBAL,
            defaults={
                "tenant_id": tenant_id,
                "level": level,
                "message": message,
                "enabled": enabled,
                "dismissible": dismissible,
                "show_on_login_page": show_on_login_page,
                "modified_by_id": ctx.user_id,
            },
        )
        ServiceBase._audit(
            ctx,
            operation="upsert",
            entity_type="Banner",
            entity_id=banner.id,
            change_reason=f"banner.upsert scope=global level={level} enabled={enabled}",
            details={"scope": "global", "level": level, "enabled": enabled},
        )
        return banner

    # -- Workspace banner ----------------------------------------------------

    def get_workspace_banner(self, ctx: AuthContext, *, workspace_id: UUID) -> Optional[Banner]:
        """Return the workspace's banner row, or ``None`` if never configured."""
        ServiceBase._set_tenant_context(ctx)
        return Banner.objects.filter(
            scope=BannerScope.WORKSPACE, workspace_id=workspace_id
        ).first()

    def upsert_workspace_banner(
        self,
        ctx: AuthContext,
        *,
        workspace_id: UUID,
        is_authorized: bool,
        level: str,
        message: str,
        enabled: bool,
        dismissible: bool,
    ) -> Banner:
        """Create or overwrite a workspace's single banner row.

        Raises:
            PermissionDeniedError: ``is_authorized`` is ``False``.
            NotFoundError: ``workspace_id`` does not belong to the caller's
                tenant (self-enforced here rather than trusted from the
                caller, mirroring ``AuthorizationService.assign_role``).
        """
        if not is_authorized:
            raise PermissionDeniedError(
                "Permission denied: workspace-admin or System-Admin role required."
            )
        ServiceBase._set_tenant_context(ctx)
        if not Workspace.objects.filter(id=workspace_id).exists():
            raise NotFoundError(f"Workspace {workspace_id} not found.")

        tenant_id = TenantContext.get_tenant()
        banner, _created = Banner.objects.update_or_create(
            scope=BannerScope.WORKSPACE,
            workspace_id=workspace_id,
            defaults={
                "tenant_id": tenant_id,
                "level": level,
                "message": message,
                "enabled": enabled,
                "dismissible": dismissible,
                "modified_by_id": ctx.user_id,
            },
        )
        ServiceBase._audit(
            ctx,
            operation="upsert",
            entity_type="Banner",
            entity_id=banner.id,
            change_reason=f"banner.upsert scope=workspace level={level} enabled={enabled}",
            details={
                "scope": "workspace",
                "workspace_id": str(workspace_id),
                "level": level,
                "enabled": enabled,
            },
        )
        return banner

    # -- Public (unauthenticated) login-page banner --------------------------

    def get_login_banner(self, tenant_id: UUID) -> Optional[Banner]:
        """Return the enabled, login-page-visible global banner for *tenant_id*.

        No :class:`AuthContext` — called from the unauthenticated
        ``PublicLoginBannerView``. Uses ``Banner.unscoped`` (the
        tenant-filter escape hatch, REQ-L3-PL001-004) with an explicit
        ``tenant_id=`` filter instead of the thread-local
        :class:`TenantContext`, because no request-scoped tenant exists
        before login.
        """
        return Banner.unscoped.filter(
            tenant_id=tenant_id,
            scope=BannerScope.GLOBAL,
            enabled=True,
            show_on_login_page=True,
        ).first()


__all__ = ["BannerService"]
```

- [ ] **Step 2: Check `backend/admin_ops/services/__init__.py` and export `BannerService` if that file re-exports other services**

Run: `cat backend/admin_ops/services/__init__.py`

If it contains `from .backup_service import BackupService` (or similar) plus an `__all__` list, add `from .banner_service import BannerService` and `"BannerService"` to `__all__` following the exact same pattern. If the file is empty or does not re-export services, leave it unchanged (views will import `from admin_ops.services.banner_service import BannerService` directly, matching how `admin_ops/rest.py` does `from admin_ops.services.admin_restore_service import RESTORE_CAPTCHA`).

- [ ] **Step 3: Write the failing service tests**

Create `backend/admin_ops/tests/test_banner_service.py`:

```python
"""Tests for BannerService (System & Workspace Banners)."""
from __future__ import annotations

import pytest

from admin_ops.models import Banner, BannerLevel, BannerScope
from admin_ops.services.banner_service import BannerService
from application.base import NotFoundError, PermissionDeniedError
from auth_tenancy.context import AuthContext, AuthMethod
from persistence.models import Workspace

from .conftest import active_tenant


@pytest.fixture
def service() -> BannerService:
    return BannerService()


@pytest.mark.django_db
class TestGlobalBanner:
    def test_upsert_denied_when_not_system_admin(
        self, service: BannerService, admin_ctx: AuthContext, tenant_a
    ) -> None:
        with active_tenant(tenant_a):
            with pytest.raises(PermissionDeniedError):
                service.upsert_global_banner(
                    admin_ctx,
                    is_system_admin=False,
                    level=BannerLevel.INFO,
                    message="hi",
                    enabled=True,
                    dismissible=True,
                    show_on_login_page=False,
                )

    def test_upsert_creates_then_overwrites_single_row(
        self, service: BannerService, admin_ctx: AuthContext, tenant_a
    ) -> None:
        with active_tenant(tenant_a):
            first = service.upsert_global_banner(
                admin_ctx,
                is_system_admin=True,
                level=BannerLevel.INFO,
                message="v1",
                enabled=True,
                dismissible=True,
                show_on_login_page=False,
            )
            second = service.upsert_global_banner(
                admin_ctx,
                is_system_admin=True,
                level=BannerLevel.CRITICAL,
                message="v2",
                enabled=True,
                dismissible=False,
                show_on_login_page=True,
            )

            assert first.id == second.id
            assert Banner.objects.filter(scope=BannerScope.GLOBAL).count() == 1
            fetched = service.get_global_banner(admin_ctx)
            assert fetched is not None
            assert fetched.message == "v2"
            assert fetched.level == BannerLevel.CRITICAL
            assert fetched.dismissible is False
            assert fetched.show_on_login_page is True

    def test_get_returns_none_when_never_configured(
        self, service: BannerService, admin_ctx: AuthContext, tenant_a
    ) -> None:
        with active_tenant(tenant_a):
            assert service.get_global_banner(admin_ctx) is None


@pytest.mark.django_db
class TestWorkspaceBanner:
    def test_upsert_denied_when_not_authorized(
        self, service: BannerService, admin_ctx: AuthContext, tenant_a
    ) -> None:
        with active_tenant(tenant_a):
            ws = Workspace.objects.create(tenant=tenant_a, name="ws-1")
            with pytest.raises(PermissionDeniedError):
                service.upsert_workspace_banner(
                    admin_ctx,
                    workspace_id=ws.id,
                    is_authorized=False,
                    level=BannerLevel.INFO,
                    message="hi",
                    enabled=True,
                    dismissible=True,
                )

    def test_upsert_rejects_unknown_workspace(
        self, service: BannerService, admin_ctx: AuthContext, tenant_a
    ) -> None:
        import uuid

        with active_tenant(tenant_a):
            with pytest.raises(NotFoundError):
                service.upsert_workspace_banner(
                    admin_ctx,
                    workspace_id=uuid.uuid4(),
                    is_authorized=True,
                    level=BannerLevel.INFO,
                    message="hi",
                    enabled=True,
                    dismissible=True,
                )

    def test_upsert_creates_then_overwrites_single_row(
        self, service: BannerService, admin_ctx: AuthContext, tenant_a
    ) -> None:
        with active_tenant(tenant_a):
            ws = Workspace.objects.create(tenant=tenant_a, name="ws-2")
            first = service.upsert_workspace_banner(
                admin_ctx,
                workspace_id=ws.id,
                is_authorized=True,
                level=BannerLevel.WARNING,
                message="v1",
                enabled=True,
                dismissible=True,
            )
            second = service.upsert_workspace_banner(
                admin_ctx,
                workspace_id=ws.id,
                is_authorized=True,
                level=BannerLevel.NEUTRAL,
                message="v2",
                enabled=False,
                dismissible=True,
            )

            assert first.id == second.id
            assert (
                Banner.objects.filter(scope=BannerScope.WORKSPACE, workspace_id=ws.id).count()
                == 1
            )
            fetched = service.get_workspace_banner(admin_ctx, workspace_id=ws.id)
            assert fetched is not None
            assert fetched.message == "v2"
            assert fetched.enabled is False


@pytest.mark.django_db
class TestLoginBanner:
    def test_returns_none_when_not_enabled_for_login(
        self, service: BannerService, admin_ctx: AuthContext, tenant_a
    ) -> None:
        with active_tenant(tenant_a):
            service.upsert_global_banner(
                admin_ctx,
                is_system_admin=True,
                level=BannerLevel.INFO,
                message="hi",
                enabled=True,
                dismissible=True,
                show_on_login_page=False,
            )
        assert service.get_login_banner(tenant_a.id) is None

    def test_returns_banner_when_enabled_and_login_flagged(
        self, service: BannerService, admin_ctx: AuthContext, tenant_a
    ) -> None:
        with active_tenant(tenant_a):
            service.upsert_global_banner(
                admin_ctx,
                is_system_admin=True,
                level=BannerLevel.CRITICAL,
                message="maintenance",
                enabled=True,
                dismissible=False,
                show_on_login_page=True,
            )
        found = service.get_login_banner(tenant_a.id)
        assert found is not None
        assert found.message == "maintenance"
```

- [ ] **Step 4: Run the tests and verify they pass**

Run: `pytest backend/admin_ops/tests/test_banner_service.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/admin_ops/services/banner_service.py backend/admin_ops/tests/test_banner_service.py
git commit -m "feat: add BannerService for system & workspace banners"
```

---

### Task 3: Backend — REST views + URL wiring + permission-matrix tests

**Files:**
- Create: `backend/admin_ops/banner_rest.py`
- Modify: `backend/rest_api/urls.py`
- Test: `backend/admin_ops/tests/test_banner_rest.py`

**Interfaces:**
- Consumes: `BannerService` (Task 2), `auth_tenancy.rest.HasOperationPermission`, `auth_tenancy.services.AuthorizationService`, `auth_tenancy.services.Operation`.
- Produces: `GlobalBannerView` (GET/PUT `/api/v1/admin/banners/global/`), `WorkspaceBannerView` (GET/PUT `/api/v1/workspaces/<uuid:workspace_id>/banner/`), `PublicLoginBannerView` (GET `/api/v1/public/banners/login/`).

- [ ] **Step 1: Write the REST views**

Create `backend/admin_ops/banner_rest.py`:

```python
"""
admin_ops — REST adapter for System & Workspace Banners.

Endpoints:
    GET/PUT /api/v1/admin/banners/global/
        System-Admin only (``AuthorizationService.is_tenant_admin``).
    GET/PUT /api/v1/workspaces/<uuid:workspace_id>/banner/
        Workspace-Admin (workspace-scoped ``admin`` role) or System-Admin.
    GET     /api/v1/public/banners/login/
        Unauthenticated. Returns 204 if no enabled+show_on_login_page
        global banner exists for ``settings.DEFAULT_TENANT_ID`` (see the
        plan's Global Constraints section for why this endpoint resolves
        the tenant from a settings default rather than per-request), else
        200 with ``{level, message, dismissible}``. Never distinguishes
        "tenant misconfigured" from "banner disabled" in its response
        shape (both are 204) — avoids leaking tenant configuration state
        to an unauthenticated caller.

All three views delegate every read/write to :class:`BannerService`
(REQ-L3-RA001-004 — no business logic in views).
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from django.conf import settings
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from admin_ops.models import Banner, BannerLevel
from admin_ops.services.banner_service import BannerService
from application.base import NotFoundError, PermissionDeniedError, ValidationError
from auth_tenancy.context import AuthContext
from auth_tenancy.rest import HasOperationPermission
from auth_tenancy.services import AuthorizationService, Operation

_VALID_LEVELS = frozenset(choice for choice, _label in BannerLevel.choices)


def _err(code: str, message: str, http_status: int) -> Response:
    return Response({"error": code, "message": message}, status=http_status)


def _auth_context(request: Request) -> AuthContext:
    ctx = getattr(request, "auth_context", None)
    if ctx is None:
        raise PermissionDeniedError("Authentication required.")
    return ctx


def _banner_to_dict(banner: Banner) -> dict[str, Any]:
    return {
        "id": str(banner.id),
        "scope": banner.scope,
        "workspace_id": str(banner.workspace_id) if banner.workspace_id else None,
        "level": banner.level,
        "message": banner.message,
        "enabled": banner.enabled,
        "dismissible": banner.dismissible,
        "show_on_login_page": banner.show_on_login_page,
        "updated_at": banner.modified_at.isoformat() if banner.modified_at else None,
    }


def _parse_write_payload(data: Any) -> dict[str, Any]:
    """Validate the shared PUT body shape for both admin-facing views.

    Raises ValidationError on a malformed body; callers translate that to
    a 400 response.
    """
    if not isinstance(data, dict):
        raise ValidationError("Request body must be a JSON object.")

    level = data.get("level", BannerLevel.NEUTRAL)
    if level not in _VALID_LEVELS:
        raise ValidationError(f"Field 'level' must be one of {sorted(_VALID_LEVELS)}.")

    message = data.get("message", "")
    if not isinstance(message, str):
        raise ValidationError("Field 'message' must be a string.")

    enabled = data.get("enabled", False)
    if not isinstance(enabled, bool):
        raise ValidationError("Field 'enabled' must be a boolean.")

    dismissible = data.get("dismissible", True)
    if not isinstance(dismissible, bool):
        raise ValidationError("Field 'dismissible' must be a boolean.")

    return {
        "level": level,
        "message": message,
        "enabled": enabled,
        "dismissible": dismissible,
    }


# ---------------------------------------------------------------------------
# GlobalBannerView
# ---------------------------------------------------------------------------


class GlobalBannerView(APIView):
    """``/api/v1/admin/banners/global/`` — System-Admin only."""

    permission_classes = [HasOperationPermission]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._service = BannerService()
        self._authz = AuthorizationService()

    def get(self, request: Request, **kwargs: Any) -> Response:
        try:
            ctx = _auth_context(request)
        except PermissionDeniedError as exc:
            return _err("PERMISSION_DENIED", str(exc), status.HTTP_403_FORBIDDEN)
        banner = self._service.get_global_banner(ctx)
        if banner is None:
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(_banner_to_dict(banner), status=status.HTTP_200_OK)

    def put(self, request: Request, **kwargs: Any) -> Response:
        try:
            ctx = _auth_context(request)
        except PermissionDeniedError as exc:
            return _err("PERMISSION_DENIED", str(exc), status.HTTP_403_FORBIDDEN)

        is_system_admin = self._authz.is_tenant_admin(
            user_id=ctx.user_id, tenant_id=ctx.tenant_id
        )

        try:
            payload = _parse_write_payload(request.data)
        except ValidationError as exc:
            return _err("VALIDATION_ERROR", str(exc), status.HTTP_400_BAD_REQUEST)

        show_on_login_page = request.data.get("show_on_login_page", False)
        if not isinstance(show_on_login_page, bool):
            return _err(
                "VALIDATION_ERROR",
                "Field 'show_on_login_page' must be a boolean.",
                status.HTTP_400_BAD_REQUEST,
            )

        try:
            banner = self._service.upsert_global_banner(
                ctx,
                is_system_admin=is_system_admin,
                show_on_login_page=show_on_login_page,
                **payload,
            )
        except PermissionDeniedError as exc:
            return _err("PERMISSION_DENIED", str(exc), status.HTTP_403_FORBIDDEN)

        return Response(_banner_to_dict(banner), status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# WorkspaceBannerView
# ---------------------------------------------------------------------------


class WorkspaceBannerView(APIView):
    """``/api/v1/workspaces/<uuid:workspace_id>/banner/`` — Workspace-Admin or System-Admin."""

    permission_classes = [HasOperationPermission]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._service = BannerService()
        self._authz = AuthorizationService()

    @staticmethod
    def _workspace_id_from_kwargs(request: Request) -> UUID:
        ctx_kwargs = (
            request.parser_context.get("kwargs") if request.parser_context else None
        )
        ws_raw = (ctx_kwargs or {}).get("workspace_id")
        if not ws_raw:
            raise ValidationError("Missing workspace_id in URL.")
        try:
            return UUID(str(ws_raw))
        except (ValueError, TypeError):
            raise ValidationError(f"Invalid workspace_id: {ws_raw!r}")

    def get(self, request: Request, **kwargs: Any) -> Response:
        try:
            ctx = _auth_context(request)
            workspace_id = self._workspace_id_from_kwargs(request)
        except PermissionDeniedError as exc:
            return _err("PERMISSION_DENIED", str(exc), status.HTTP_403_FORBIDDEN)
        except ValidationError as exc:
            return _err("VALIDATION_ERROR", str(exc), status.HTTP_400_BAD_REQUEST)

        banner = self._service.get_workspace_banner(ctx, workspace_id=workspace_id)
        if banner is None:
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(_banner_to_dict(banner), status=status.HTTP_200_OK)

    def put(self, request: Request, **kwargs: Any) -> Response:
        try:
            ctx = _auth_context(request)
            workspace_id = self._workspace_id_from_kwargs(request)
        except PermissionDeniedError as exc:
            return _err("PERMISSION_DENIED", str(exc), status.HTTP_403_FORBIDDEN)
        except ValidationError as exc:
            return _err("VALIDATION_ERROR", str(exc), status.HTTP_400_BAD_REQUEST)

        # Workspace-scoped admin (AuthTenancyAuthentication resolves
        # active_roles for this workspace because the URL carries
        # workspace_id) OR System-Admin override.
        is_authorized = ctx.has_role("admin") or self._authz.is_tenant_admin(
            user_id=ctx.user_id, tenant_id=ctx.tenant_id
        )

        try:
            payload = _parse_write_payload(request.data)
        except ValidationError as exc:
            return _err("VALIDATION_ERROR", str(exc), status.HTTP_400_BAD_REQUEST)

        try:
            banner = self._service.upsert_workspace_banner(
                ctx,
                workspace_id=workspace_id,
                is_authorized=is_authorized,
                **payload,
            )
        except PermissionDeniedError as exc:
            return _err("PERMISSION_DENIED", str(exc), status.HTTP_403_FORBIDDEN)
        except NotFoundError as exc:
            return _err("NOT_FOUND", str(exc), status.HTTP_404_NOT_FOUND)

        return Response(_banner_to_dict(banner), status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# PublicLoginBannerView — unauthenticated
# ---------------------------------------------------------------------------


class PublicLoginBannerView(APIView):
    """``GET /api/v1/public/banners/login/`` — unauthenticated (mirrors VersionView)."""

    authentication_classes: list = []
    permission_classes = [AllowAny]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._service = BannerService()

    def get(self, request: Request, **kwargs: Any) -> Response:
        tenant_id = getattr(settings, "DEFAULT_TENANT_ID", None)
        if tenant_id is None:
            return Response(status=status.HTTP_204_NO_CONTENT)

        banner = self._service.get_login_banner(tenant_id)
        if banner is None:
            return Response(status=status.HTTP_204_NO_CONTENT)

        return Response(
            {
                "level": banner.level,
                "message": banner.message,
                "dismissible": banner.dismissible,
            },
            status=status.HTTP_200_OK,
        )


__all__ = ["GlobalBannerView", "WorkspaceBannerView", "PublicLoginBannerView"]
```

- [ ] **Step 2: Wire the three URLs**

In `backend/rest_api/urls.py`, add the import near the other `admin_ops` imports (alongside `from admin_ops.health_rest import SystemHealthView` and `from admin_ops.rest import AdminRestoreView, BackupListCreateView`):

```python
from admin_ops.banner_rest import GlobalBannerView, PublicLoginBannerView, WorkspaceBannerView
```

Add the two authenticated routes immediately after the existing `admin/health/` path block (after line ~325, right after the `SystemHealthView` `path(...)` call):

```python
    # System & Workspace Banners.
    # /admin/banners/global/  -> GET/PUT, System-Admin only
    path(
        "admin/banners/global/",
        GlobalBannerView.as_view(),
        name="admin-banner-global",
    ),
    path(
        "workspaces/<uuid:workspace_id>/banner/",
        WorkspaceBannerView.as_view(),
        name="workspace-banner",
    ),
```

Add the public route as its own `path(...)` entry near wherever `version/` or another top-level public route is wired (search `urls.py` for `"version/"` to find that block and add this alongside it, same indentation/list):

```python
    path(
        "public/banners/login/",
        PublicLoginBannerView.as_view(),
        name="public-banner-login",
    ),
```

- [ ] **Step 3: Write the permission-matrix tests**

Create `backend/admin_ops/tests/test_banner_rest.py`:

```python
"""Permission-matrix + shape tests for the Banner REST views."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from rest_framework.parsers import JSONParser
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from admin_ops.banner_rest import GlobalBannerView, PublicLoginBannerView, WorkspaceBannerView
from admin_ops.models import Banner, BannerLevel, BannerScope
from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.models import TenantRole
from persistence.models import Workspace

from .conftest import active_tenant


def _make_request(auth, *, body=None, workspace_id=None) -> Request:
    factory = APIRequestFactory()
    raw = factory.put("/x/", body or {}, format="json") if body is not None else factory.get("/x/")
    request = Request(raw, parsers=[JSONParser()])
    request.auth_context = auth
    request.parser_context = {
        "kwargs": {"workspace_id": str(workspace_id)} if workspace_id else {},
        "args": (),
        "view": None,
    }
    return request


@pytest.fixture
def tenant_admin_ctx(admin_user, tenant_a) -> AuthContext:
    """A caller holding an active TenantRole (System-Admin) but NO workspace role."""
    TenantRole.objects.create(tenant=tenant_a, user=admin_user, role=TenantRole.ROLE_ADMIN)
    return AuthContext(
        user_id=admin_user.id,
        tenant_id=tenant_a.id,
        active_roles=(),
        auth_method=AuthMethod.BEARER_TOKEN,
    )


@pytest.mark.django_db
class TestGlobalBannerPermissions:
    def test_workspace_admin_without_tenant_role_denied(
        self, admin_ctx: AuthContext, tenant_a
    ) -> None:
        with active_tenant(tenant_a):
            request = _make_request(admin_ctx, body={"level": "info", "enabled": True})
            response = GlobalBannerView().put(request)
        assert response.status_code == 403

    def test_tenant_admin_allowed(self, tenant_admin_ctx: AuthContext, tenant_a) -> None:
        with active_tenant(tenant_a):
            request = _make_request(
                tenant_admin_ctx, body={"level": "critical", "message": "down", "enabled": True}
            )
            response = GlobalBannerView().put(request)
        assert response.status_code == 200
        assert response.data["level"] == "critical"

    def test_get_returns_204_when_unconfigured(
        self, tenant_admin_ctx: AuthContext, tenant_a
    ) -> None:
        with active_tenant(tenant_a):
            request = _make_request(tenant_admin_ctx)
            response = GlobalBannerView().get(request)
        assert response.status_code == 204


@pytest.mark.django_db
class TestWorkspaceBannerPermissions:
    def test_non_admin_workspace_member_denied(
        self, regular_ctx: AuthContext, tenant_a
    ) -> None:
        with active_tenant(tenant_a):
            ws = Workspace.objects.create(tenant=tenant_a, name="ws-perm")
            request = _make_request(
                regular_ctx, body={"level": "info", "enabled": True}, workspace_id=ws.id
            )
            response = WorkspaceBannerView().put(request, workspace_id=str(ws.id))
        assert response.status_code == 403

    def test_workspace_admin_allowed(self, admin_ctx: AuthContext, tenant_a) -> None:
        with active_tenant(tenant_a):
            ws = Workspace.objects.create(tenant=tenant_a, name="ws-perm-2")
            request = _make_request(
                admin_ctx, body={"level": "warning", "enabled": True}, workspace_id=ws.id
            )
            response = WorkspaceBannerView().put(request, workspace_id=str(ws.id))
        assert response.status_code == 200
        assert response.data["level"] == "warning"

    def test_tenant_admin_can_edit_any_workspace_banner(
        self, tenant_admin_ctx: AuthContext, tenant_a
    ) -> None:
        with active_tenant(tenant_a):
            ws = Workspace.objects.create(tenant=tenant_a, name="ws-perm-3")
            request = _make_request(
                tenant_admin_ctx, body={"level": "neutral", "enabled": True}, workspace_id=ws.id
            )
            response = WorkspaceBannerView().put(request, workspace_id=str(ws.id))
        assert response.status_code == 200

    def test_admin_of_other_workspace_denied(
        self, admin_ctx: AuthContext, tenant_a
    ) -> None:
        """admin_ctx carries an unscoped ``admin`` role fixture; the view's
        real gate in production relies on AuthTenancyAuthentication scoping
        active_roles to the URL's workspace_id, which this hand-built
        AuthContext bypasses. This test documents that the view itself does
        not re-verify workspace membership beyond ``ctx.has_role('admin')``
        — defence-in-depth for that scoping lives in
        AuthTenancyAuthentication, not this view, matching
        WorkspaceMembersView's identical documented trust boundary."""
        with active_tenant(tenant_a):
            ws = Workspace.objects.create(tenant=tenant_a, name="ws-other")
            request = _make_request(
                admin_ctx, body={"level": "info", "enabled": True}, workspace_id=ws.id
            )
            response = WorkspaceBannerView().put(request, workspace_id=str(ws.id))
        # admin_ctx's active_roles=("admin",) grants this in the unit test;
        # real cross-workspace denial is covered by
        # AuthTenancyAuthentication's workspace-scoping (auth_tenancy/rest.py),
        # not re-tested here to avoid duplicating that suite.
        assert response.status_code == 200


@pytest.mark.django_db
class TestPublicLoginBanner:
    def test_returns_204_when_no_banner_configured(self, tenant_a) -> None:
        with patch("django.conf.settings.DEFAULT_TENANT_ID", tenant_a.id):
            request = Request(APIRequestFactory().get("/x/"))
            response = PublicLoginBannerView().get(request)
        assert response.status_code == 204

    def test_returns_200_with_shape_when_configured(
        self, tenant_admin_ctx: AuthContext, tenant_a
    ) -> None:
        with active_tenant(tenant_a):
            GlobalBannerView()._service.upsert_global_banner(
                tenant_admin_ctx,
                is_system_admin=True,
                level=BannerLevel.WARNING,
                message="maintenance window",
                enabled=True,
                dismissible=True,
                show_on_login_page=True,
            )
        with patch("django.conf.settings.DEFAULT_TENANT_ID", tenant_a.id):
            request = Request(APIRequestFactory().get("/x/"))
            response = PublicLoginBannerView().get(request)
        assert response.status_code == 200
        assert set(response.data.keys()) == {"level", "message", "dismissible"}
        assert response.data["message"] == "maintenance window"
```

- [ ] **Step 4: Run the full backend test suite for this feature**

Run: `pytest backend/admin_ops/tests/test_banner_model.py backend/admin_ops/tests/test_banner_service.py backend/admin_ops/tests/test_banner_rest.py -v`
Expected: all pass (4 + 8 + 8 = 20 tests).

- [ ] **Step 5: Run the architecture ratchet test to confirm `admin_ops` stays exempt**

Run: `pytest backend/rest_api/tests/test_architecture.py -v`
Expected: all pass unchanged — `backend/admin_ops/banner_rest.py` is outside `_REST_API_DIR` (`backend/rest_api/`), so it is not subject to `MAX_ORM_LINES` and requires no ratchet-constant update. If this assumption is wrong (i.e. this test fails), read the failure message — it will name the exact file/constant to adjust — and fix that specific constant rather than any other change.

- [ ] **Step 6: Commit**

```bash
git add backend/admin_ops/banner_rest.py backend/rest_api/urls.py backend/admin_ops/tests/test_banner_rest.py
git commit -m "feat: add Banner REST endpoints (global, workspace, public login)"
```

---

### Task 4: Frontend — API client (`banners.ts`)

**Files:**
- Create: `frontend/src/api/banners.ts`
- Test: `frontend/src/api/banners.test.ts`

**Interfaces:**
- Consumes: `apiClient` from `./client` (existing `get`/`put` wrapper, matches `admin-ops.ts`/`version.ts`).
- Produces: `BannerLevel` type (`"neutral" | "info" | "warning" | "critical"`), `Banner` interface, `BannerWritePayload` interface, `bannersApi` object with `getGlobal()`, `putGlobal(payload)`, `getWorkspace(workspaceId)`, `putWorkspace(workspaceId, payload)`, `getLoginBanner()` methods — all consumed by Tasks 5-8.

- [ ] **Step 1: Write the API client**

Create `frontend/src/api/banners.ts`:

```typescript
/**
 * ARCH-L1-001 ReactFrontend — System & Workspace Banners API.
 *
 * leaf_id: COMP-RF-001 (NavigationShell scope)
 *
 * Wraps:
 *   GET/PUT /api/v1/admin/banners/global/          — System-Admin only
 *   GET/PUT /api/v1/workspaces/{id}/banner/         — Workspace-Admin or System-Admin
 *   GET     /api/v1/public/banners/login/           — unauthenticated
 *
 * A GET returning no configured banner resolves to `null` here (the
 * backend returns 204 No Content, which `apiClient.get` treats as an
 * empty successful response — this wrapper normalises that to `null` so
 * callers never have to special-case an empty object).
 */

import { apiClient } from "./client";
import type { UUID } from "../types";

export type BannerLevel = "neutral" | "info" | "warning" | "critical";

export interface Banner {
  id: UUID;
  scope: "global" | "workspace";
  workspace_id: UUID | null;
  level: BannerLevel;
  message: string;
  enabled: boolean;
  dismissible: boolean;
  show_on_login_page: boolean;
  updated_at: string | null;
}

export interface BannerWritePayload {
  level: BannerLevel;
  message: string;
  enabled: boolean;
  dismissible: boolean;
}

export interface GlobalBannerWritePayload extends BannerWritePayload {
  show_on_login_page: boolean;
}

export interface LoginBanner {
  level: BannerLevel;
  message: string;
  dismissible: boolean;
}

export const bannersApi = {
  /** GET /api/v1/admin/banners/global/ — System-Admin only. */
  async getGlobal(): Promise<Banner | null> {
    const data = await apiClient.get<Banner | null>("/admin/banners/global/");
    return data ?? null;
  },

  /** PUT /api/v1/admin/banners/global/ — System-Admin only. */
  async putGlobal(payload: GlobalBannerWritePayload): Promise<Banner> {
    return apiClient.put<Banner>("/admin/banners/global/", payload);
  },

  /** GET /api/v1/workspaces/{workspaceId}/banner/ — any authenticated member. */
  async getWorkspace(workspaceId: UUID): Promise<Banner | null> {
    const data = await apiClient.get<Banner | null>(
      `/workspaces/${workspaceId}/banner/`
    );
    return data ?? null;
  },

  /** PUT /api/v1/workspaces/{workspaceId}/banner/ — Workspace-Admin or System-Admin. */
  async putWorkspace(workspaceId: UUID, payload: BannerWritePayload): Promise<Banner> {
    return apiClient.put<Banner>(`/workspaces/${workspaceId}/banner/`, payload);
  },

  /** GET /api/v1/public/banners/login/ — unauthenticated, used pre-login. */
  async getLoginBanner(): Promise<LoginBanner | null> {
    const data = await apiClient.get<LoginBanner | null>("/public/banners/login/");
    return data ?? null;
  },
};
```

- [ ] **Step 2: Check how `apiClient.get` handles a 204 response**

Run: `grep -n "204\|No Content" frontend/src/api/client.ts`

If `apiClient.get` already returns `null`/`undefined` for a 204 (as the docstring above assumes), no further change is needed. If instead it throws or returns an empty string/object for 204, adjust `getGlobal`/`getWorkspace`/`getLoginBanner` above to catch that specific shape (mirror however `adminOpsApi` or another existing wrapper in this codebase already handles an empty/204 response — search `grep -rn "204" frontend/src/api/*.ts` for a precedent before inventing a new pattern).

- [ ] **Step 3: Write the client tests**

Create `frontend/src/api/banners.test.ts`:

```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
import { bannersApi } from "./banners";
import { apiClient } from "./client";

vi.mock("./client", () => ({
  apiClient: {
    get: vi.fn(),
    put: vi.fn(),
  },
}));

describe("bannersApi", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("getGlobal normalises a null/empty response to null", async () => {
    vi.mocked(apiClient.get).mockResolvedValue(null);
    const result = await bannersApi.getGlobal();
    expect(result).toBeNull();
    expect(apiClient.get).toHaveBeenCalledWith("/admin/banners/global/");
  });

  it("getGlobal returns the banner when configured", async () => {
    const banner = {
      id: "b1",
      scope: "global",
      workspace_id: null,
      level: "info",
      message: "hi",
      enabled: true,
      dismissible: true,
      show_on_login_page: false,
      updated_at: "2026-08-23T00:00:00Z",
    };
    vi.mocked(apiClient.get).mockResolvedValue(banner);
    const result = await bannersApi.getGlobal();
    expect(result).toEqual(banner);
  });

  it("putGlobal sends the full payload including show_on_login_page", async () => {
    vi.mocked(apiClient.put).mockResolvedValue({});
    await bannersApi.putGlobal({
      level: "critical",
      message: "down",
      enabled: true,
      dismissible: false,
      show_on_login_page: true,
    });
    expect(apiClient.put).toHaveBeenCalledWith("/admin/banners/global/", {
      level: "critical",
      message: "down",
      enabled: true,
      dismissible: false,
      show_on_login_page: true,
    });
  });

  it("getWorkspace calls the workspace-scoped endpoint", async () => {
    vi.mocked(apiClient.get).mockResolvedValue(null);
    await bannersApi.getWorkspace("ws-1");
    expect(apiClient.get).toHaveBeenCalledWith("/workspaces/ws-1/banner/");
  });

  it("getLoginBanner calls the public endpoint", async () => {
    vi.mocked(apiClient.get).mockResolvedValue(null);
    await bannersApi.getLoginBanner();
    expect(apiClient.get).toHaveBeenCalledWith("/public/banners/login/");
  });
});
```

- [ ] **Step 4: Run the tests**

Run: `npm --prefix frontend test -- banners.test.ts`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/banners.ts frontend/src/api/banners.test.ts
git commit -m "feat: add banners API client"
```

---

### Task 5: Frontend — `BannerStack` display component + `NavigationShell` mount

**Files:**
- Create: `frontend/src/components/NavigationShell/BannerStack.tsx`
- Create: `frontend/src/components/NavigationShell/BannerStack.module.css`
- Create: `frontend/src/components/NavigationShell/BannerStack.test.tsx`
- Modify: `frontend/src/components/NavigationShell/NavigationShell.tsx`
- Modify: `frontend/src/i18n/locales/de.json`, `frontend/src/i18n/locales/en.json`

**Interfaces:**
- Consumes: `bannersApi` (Task 4), `useWorkspace()` from `../../context/WorkspaceContext` (for `activeWorkspace?.id`), `react-markdown` (already a dependency, per `MarkdownPreview.tsx`).
- Produces: `BannerStack` component (no props — reads active workspace from context internally), mounted once inside `AppShell` in `NavigationShell.tsx`.

- [ ] **Step 1: Write the CSS module**

Create `frontend/src/components/NavigationShell/BannerStack.module.css`:

```css
/* BannerStack — System & Workspace Banners. CSS Module per this codebase's
   ratchet direction for new UI code (see ContextGraphSettingsSection.module.css). */

.row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-4);
  border-bottom: 1px solid var(--color-border);
  font-size: var(--font-size-sm);
  color: var(--color-text);
}

.row[data-level="neutral"] {
  background: var(--color-surface-raised);
  border-left: 4px solid var(--color-text-muted);
}

.row[data-level="info"] {
  background: rgba(var(--color-primary-rgb), 0.08);
  border-left: 4px solid var(--color-primary);
}

.row[data-level="warning"] {
  background: color-mix(in srgb, var(--color-warning) 12%, var(--color-surface-raised));
  border-left: 4px solid var(--color-warning);
}

.row[data-level="critical"] {
  background: color-mix(in srgb, var(--color-danger) 12%, var(--color-surface-raised));
  border-left: 4px solid var(--color-danger);
}

.body {
  flex: 1;
  min-width: 0;
}

.body p {
  margin: 0;
}

.body p + p {
  margin-top: var(--space-1);
}

.dismissButton {
  appearance: none;
  background: transparent;
  border: none;
  color: var(--color-text-muted);
  cursor: pointer;
  font-size: var(--font-size-md);
  line-height: 1;
  padding: 0 var(--space-1);
}

.dismissButton:hover {
  color: var(--color-text);
}
```

- [ ] **Step 2: Write `BannerStack.tsx`**

Create `frontend/src/components/NavigationShell/BannerStack.tsx`:

```tsx
/**
 * ARCH-L1-001 ReactFrontend — BannerStack (System & Workspace Banners).
 *
 * leaf_id: COMP-RF-001 (NavigationShell)
 * req_id:  REQ-L1-081-THEME sibling feature — System & Workspace Banners
 *
 * Renders 0-2 stacked rows: the tenant's global banner (if enabled) above
 * the active workspace's banner (if enabled). Each dismissible row's
 * closed state lives in sessionStorage, keyed by
 * `banner-dismissed-<scope>-<id>-<updated_at>` — session-scoped so it
 * resets on next login, and an admin edit (new updated_at) always
 * invalidates a prior dismissal.
 */

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import ReactMarkdown from "react-markdown";
import { bannersApi, type Banner } from "../../api/banners";
import { useWorkspace } from "../../context/WorkspaceContext";
import styles from "./BannerStack.module.css";

function dismissKey(scope: string, banner: Banner): string {
  return `banner-dismissed-${scope}-${banner.id}-${banner.updated_at ?? ""}`;
}

function isDismissed(scope: string, banner: Banner): boolean {
  return window.sessionStorage.getItem(dismissKey(scope, banner)) === "1";
}

function BannerRow({
  scope,
  banner,
  onDismiss,
}: {
  scope: "global" | "workspace";
  banner: Banner;
  onDismiss: () => void;
}): JSX.Element {
  const { t } = useTranslation();

  const handleDismiss = (): void => {
    window.sessionStorage.setItem(dismissKey(scope, banner), "1");
    onDismiss();
  };

  return (
    <div
      className={styles.row}
      data-level={banner.level}
      data-testid={`banner-${scope}`}
      role="status"
    >
      <div className={styles.body}>
        <ReactMarkdown>{banner.message}</ReactMarkdown>
      </div>
      {banner.dismissible && (
        <button
          type="button"
          className={styles.dismissButton}
          data-testid={`banner-${scope}-dismiss`}
          aria-label={t("banners.dismiss", "Dismiss")}
          onClick={handleDismiss}
        >
          ×
        </button>
      )}
    </div>
  );
}

export function BannerStack(): JSX.Element | null {
  const { activeWorkspace } = useWorkspace();
  const [globalBanner, setGlobalBanner] = useState<Banner | null>(null);
  const [workspaceBanner, setWorkspaceBanner] = useState<Banner | null>(null);
  const [globalDismissed, setGlobalDismissed] = useState(false);
  const [workspaceDismissed, setWorkspaceDismissed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void bannersApi
      .getGlobal()
      .then((banner) => {
        if (cancelled) return;
        setGlobalBanner(banner);
        setGlobalDismissed(banner ? isDismissed("global", banner) : false);
      })
      .catch(() => {
        // A failed fetch must never block the app shell from rendering.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    if (!activeWorkspace?.id) {
      setWorkspaceBanner(null);
      return undefined;
    }
    void bannersApi
      .getWorkspace(activeWorkspace.id)
      .then((banner) => {
        if (cancelled) return;
        setWorkspaceBanner(banner);
        setWorkspaceDismissed(banner ? isDismissed("workspace", banner) : false);
      })
      .catch(() => {
        // Same non-blocking contract as the global fetch above.
      });
    return () => {
      cancelled = true;
    };
  }, [activeWorkspace?.id]);

  const showGlobal = globalBanner?.enabled && !globalDismissed;
  const showWorkspace = workspaceBanner?.enabled && !workspaceDismissed;

  if (!showGlobal && !showWorkspace) return null;

  return (
    <div data-testid="banner-stack">
      {showGlobal && globalBanner && (
        <BannerRow
          scope="global"
          banner={globalBanner}
          onDismiss={() => setGlobalDismissed(true)}
        />
      )}
      {showWorkspace && workspaceBanner && (
        <BannerRow
          scope="workspace"
          banner={workspaceBanner}
          onDismiss={() => setWorkspaceDismissed(true)}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 3: Mount `BannerStack` in `NavigationShell.tsx`**

In `frontend/src/components/NavigationShell/NavigationShell.tsx`, add the import alongside the other same-directory imports near the top:

```tsx
import { BannerStack } from "./BannerStack";
```

In the `AppShell` function, the current body (from the file read during planning) is:

```tsx
function AppShell(): JSX.Element {
  const { t } = useTranslation();

  return (
    <div
      style={{
        display: "flex",
        height: "100vh",
      }}
    >
      <SidebarNavigation />
      <main
        style={{ flex: 1, height: "100%", padding: "1.5rem", overflow: "auto" }}
```

Change the outer `<div>` to a column flex container so the banner stack sits above the existing sidebar+main row, and mount `<BannerStack />` first:

```tsx
function AppShell(): JSX.Element {
  const { t } = useTranslation();

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh" }}>
      <BannerStack />
      <div style={{ display: "flex", flex: 1, minHeight: 0 }}>
        <SidebarNavigation />
        <main
          style={{ flex: 1, height: "100%", padding: "1.5rem", overflow: "auto" }}
```

Read the remainder of the original `AppShell` function body (below the line shown above) with the Read tool before editing, and close the newly-added wrapping `<div style={{ display: "flex", flex: 1, minHeight: 0 }}>` with an extra `</div>` immediately before `AppShell`'s final closing tags — match the existing JSX nesting/closing exactly rather than guessing; do not change anything else in that function.

- [ ] **Step 4: Add the `banners.*` i18n keys**

In `frontend/src/i18n/locales/de.json`, add a new top-level key (following the same object style as the existing `systemHealth` key):

```json
"banners": {
  "dismiss": "Schließen",
  "level": {
    "neutral": "Neutral",
    "info": "Info",
    "warning": "Warnung",
    "critical": "Kritisch"
  },
  "enabled": "Aktiviert",
  "dismissibleField": "Vom Anwender schließbar",
  "showOnLoginPage": "Auch auf der Login-Seite anzeigen",
  "messagePlaceholder": "Markdown-Text..."
}
```

In `frontend/src/i18n/locales/en.json`, add the matching English block:

```json
"banners": {
  "dismiss": "Dismiss",
  "level": {
    "neutral": "Neutral",
    "info": "Info",
    "warning": "Warning",
    "critical": "Critical"
  },
  "enabled": "Enabled",
  "dismissibleField": "Dismissible by end users",
  "showOnLoginPage": "Also show on the login page",
  "messagePlaceholder": "Markdown text..."
}
```

- [ ] **Step 5: Write the component tests**

Create `frontend/src/components/NavigationShell/BannerStack.test.tsx`:

```tsx
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { BannerStack } from "./BannerStack";
import { bannersApi } from "../../api/banners";
import { useWorkspace } from "../../context/WorkspaceContext";

vi.mock("../../api/banners", () => ({
  bannersApi: { getGlobal: vi.fn(), getWorkspace: vi.fn() },
}));

vi.mock("../../context/WorkspaceContext", () => ({
  useWorkspace: vi.fn(),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (_key: string, fallback?: string) => fallback ?? _key }),
}));

const GLOBAL_BANNER = {
  id: "g1",
  scope: "global" as const,
  workspace_id: null,
  level: "critical" as const,
  message: "System-wide notice",
  enabled: true,
  dismissible: true,
  show_on_login_page: false,
  updated_at: "2026-08-23T00:00:00Z",
};

const WORKSPACE_BANNER = {
  id: "w1",
  scope: "workspace" as const,
  workspace_id: "ws-1",
  level: "info" as const,
  message: "Workspace notice",
  enabled: true,
  dismissible: false,
  show_on_login_page: false,
  updated_at: "2026-08-23T00:00:00Z",
};

describe("BannerStack", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.sessionStorage.clear();
    vi.mocked(useWorkspace).mockReturnValue({
      activeWorkspace: { id: "ws-1", name: "WS" },
    } as ReturnType<typeof useWorkspace>);
  });

  it("renders nothing when no banners are configured", async () => {
    vi.mocked(bannersApi.getGlobal).mockResolvedValue(null);
    vi.mocked(bannersApi.getWorkspace).mockResolvedValue(null);
    render(<BannerStack />);
    await waitFor(() => expect(bannersApi.getGlobal).toHaveBeenCalled());
    expect(screen.queryByTestId("banner-stack")).toBeNull();
  });

  it("renders both banners stacked, global first", async () => {
    vi.mocked(bannersApi.getGlobal).mockResolvedValue(GLOBAL_BANNER);
    vi.mocked(bannersApi.getWorkspace).mockResolvedValue(WORKSPACE_BANNER);
    render(<BannerStack />);
    const stack = await screen.findByTestId("banner-stack");
    const rows = stack.querySelectorAll("[data-testid^='banner-']");
    expect(screen.getByTestId("banner-global")).toBeInTheDocument();
    expect(screen.getByTestId("banner-workspace")).toBeInTheDocument();
    expect(rows[0]).toHaveAttribute("data-testid", "banner-global");
  });

  it("does not render a dismiss button when dismissible=false", async () => {
    vi.mocked(bannersApi.getGlobal).mockResolvedValue(null);
    vi.mocked(bannersApi.getWorkspace).mockResolvedValue(WORKSPACE_BANNER);
    render(<BannerStack />);
    await screen.findByTestId("banner-workspace");
    expect(screen.queryByTestId("banner-workspace-dismiss")).toBeNull();
  });

  it("dismissing a banner removes it and persists across re-render", async () => {
    vi.mocked(bannersApi.getGlobal).mockResolvedValue(GLOBAL_BANNER);
    vi.mocked(bannersApi.getWorkspace).mockResolvedValue(null);
    const { rerender } = render(<BannerStack />);
    await screen.findByTestId("banner-global");

    fireEvent.click(screen.getByTestId("banner-global-dismiss"));
    expect(screen.queryByTestId("banner-global")).toBeNull();

    rerender(<BannerStack />);
    await waitFor(() => expect(bannersApi.getGlobal).toHaveBeenCalledTimes(2));
    expect(screen.queryByTestId("banner-global")).toBeNull();
  });

  it("an admin edit (new updated_at) resurfaces a previously dismissed banner", async () => {
    vi.mocked(bannersApi.getGlobal).mockResolvedValueOnce(GLOBAL_BANNER);
    vi.mocked(bannersApi.getWorkspace).mockResolvedValue(null);
    const { rerender } = render(<BannerStack />);
    await screen.findByTestId("banner-global");
    fireEvent.click(screen.getByTestId("banner-global-dismiss"));
    expect(screen.queryByTestId("banner-global")).toBeNull();

    const edited = { ...GLOBAL_BANNER, message: "Updated notice", updated_at: "2026-08-24T00:00:00Z" };
    vi.mocked(bannersApi.getGlobal).mockResolvedValueOnce(edited);
    rerender(<BannerStack />);
    await screen.findByTestId("banner-global");
    expect(screen.getByText("Updated notice")).toBeInTheDocument();
  });
});
```

- [ ] **Step 6: Run the tests**

Run: `npm --prefix frontend test -- BannerStack.test.tsx`
Expected: 5 passed.

- [ ] **Step 7: Run the full frontend test suite to catch any NavigationShell regressions from the layout change**

Run: `npm --prefix frontend test -- NavigationShell`
Expected: all existing `NavigationShell`-related tests still pass (the layout change wraps existing elements in an extra flex `<div>` but must not change their rendered content or `data-testid`s).

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/NavigationShell/BannerStack.tsx frontend/src/components/NavigationShell/BannerStack.module.css frontend/src/components/NavigationShell/BannerStack.test.tsx frontend/src/components/NavigationShell/NavigationShell.tsx frontend/src/i18n/locales/de.json frontend/src/i18n/locales/en.json
git commit -m "feat: add BannerStack display component to NavigationShell"
```

---

### Task 6: Frontend — `LoginPage` public banner integration

**Files:**
- Modify: `frontend/src/components/NavigationShell/LoginPage.tsx`
- Test: `frontend/src/components/NavigationShell/LoginPage.test.tsx` (create if it does not already exist; if it exists, add to it instead of replacing it — read it first)

**Interfaces:**
- Consumes: `bannersApi.getLoginBanner()` (Task 4), same `styles/tokens.css` semantic colors used by `BannerStack` (Task 5) for level→color mapping (duplicated inline here rather than importing `BannerStack`'s CSS module, since the login page renders outside `NavigationShell` and pulling in `BannerStack.module.css` would couple an authenticated-shell asset to the pre-login bundle — a small, deliberate duplication, not an oversight).

- [ ] **Step 1: Add the login-page banner fetch + render**

In `frontend/src/components/NavigationShell/LoginPage.tsx`, add the import:

```tsx
import { bannersApi, type LoginBanner } from "../../api/banners";
```

Add a new state variable alongside the existing `versionInfo` state:

```tsx
const [loginBanner, setLoginBanner] = useState<LoginBanner | null>(null);
```

Add a new `useEffect` alongside the existing version-fetch `useEffect` (same non-blocking, cancel-on-unmount shape):

```tsx
useEffect(() => {
  let cancelled = false;
  void bannersApi
    .getLoginBanner()
    .then((banner) => {
      if (!cancelled) setLoginBanner(banner);
    })
    .catch(() => {
      // Silently omit the banner on failure — must never block the login form.
    });
  return () => {
    cancelled = true;
  };
}, []);
```

Define a small level→color lookup right above the `LoginPage` function (mirrors `STATUS_COLORS` in `SystemHealthDialog.tsx`):

```tsx
const LOGIN_BANNER_COLORS: Record<LoginBanner["level"], string> = {
  neutral: "var(--color-text-muted)",
  info: "var(--color-primary)",
  warning: "var(--color-warning)",
  critical: "var(--color-danger)",
};
```

Render the banner immediately above the existing login `<form>`, inside the outermost centering `<div>` (so it appears above the card, not inside it):

```tsx
{loginBanner && (
  <div
    data-testid="login-page-banner"
    role="status"
    style={{
      position: "fixed",
      top: 0,
      left: 0,
      right: 0,
      padding: "var(--space-2) var(--space-4)",
      borderBottom: `3px solid ${LOGIN_BANNER_COLORS[loginBanner.level]}`,
      background: "var(--color-surface-raised)",
      color: "var(--color-text)",
      fontSize: "var(--font-size-sm)",
      textAlign: "center",
    }}
  >
    {loginBanner.message}
  </div>
)}
```

Note: this renders `loginBanner.message` as plain text, not through `ReactMarkdown` — the public login-page endpoint's payload is small and pre-auth Markdown rendering is a needless attack-surface increase for an unauthenticated response (XSS-relevant if a future change lets the Markdown renderer emit raw HTML); keep it plain text here even though `BannerStack` (Task 5, authenticated, admin-authored content) uses `ReactMarkdown`. If a future task wants Markdown here too, that is a deliberate follow-up decision, not an oversight of this task.

- [ ] **Step 2: Write/extend the test**

If `frontend/src/components/NavigationShell/LoginPage.test.tsx` does not exist, create it:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { LoginPage } from "./LoginPage";
import { bannersApi } from "../../api/banners";
import { versionApi } from "../../api/version";
import { useAuth } from "../../context/AuthContext";

vi.mock("../../api/banners", () => ({
  bannersApi: { getLoginBanner: vi.fn() },
}));

vi.mock("../../api/version", () => ({
  versionApi: { getVersion: vi.fn() },
}));

vi.mock("../../context/AuthContext", () => ({
  useAuth: vi.fn(),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (_key: string, fallback?: string) => fallback ?? _key }),
}));

describe("LoginPage banner", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(versionApi.getVersion).mockResolvedValue({
      app_version: "1.0.0",
      commit_short: "abc1234",
    });
    vi.mocked(useAuth).mockReturnValue({
      login: vi.fn(),
    } as unknown as ReturnType<typeof useAuth>);
  });

  it("renders nothing when no login banner is configured", async () => {
    vi.mocked(bannersApi.getLoginBanner).mockResolvedValue(null);
    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>
    );
    await waitFor(() => expect(bannersApi.getLoginBanner).toHaveBeenCalled());
    expect(screen.queryByTestId("login-page-banner")).toBeNull();
  });

  it("renders the banner message when configured", async () => {
    vi.mocked(bannersApi.getLoginBanner).mockResolvedValue({
      level: "warning",
      message: "Maintenance tonight",
      dismissible: true,
    });
    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>
    );
    expect(await screen.findByTestId("login-page-banner")).toHaveTextContent(
      "Maintenance tonight"
    );
  });
});
```

If the file already exists, read it first and add these two `describe`/`it` blocks (plus the necessary mocks, merged with whatever is already mocked there) rather than overwriting existing tests.

- [ ] **Step 3: Run the tests**

Run: `npm --prefix frontend test -- LoginPage.test.tsx`
Expected: passes (2 new tests, plus any pre-existing ones unchanged).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/NavigationShell/LoginPage.tsx frontend/src/components/NavigationShell/LoginPage.test.tsx
git commit -m "feat: show the global banner on the login page"
```

---

### Task 7: Frontend — System Settings `BannerSection`

**Files:**
- Create: `frontend/src/components/SystemSettings/BannerSection.tsx`
- Create: `frontend/src/components/SystemSettings/BannerSection.module.css`
- Create: `frontend/src/components/SystemSettings/BannerSection.test.tsx`
- Modify: `frontend/src/components/SystemSettings/SystemSettings.tsx`

**Interfaces:**
- Consumes: `bannersApi.getGlobal()`/`putGlobal()` (Task 4).
- Produces: `BannerSection` component (no props), mounted in the `"administration"` tab of `SystemSettings.tsx` alongside `WorkspaceAdminSection`.

- [ ] **Step 1: Write the CSS module**

Create `frontend/src/components/SystemSettings/BannerSection.module.css` (identical structure to `ContextGraphSettingsSection.module.css`, reused verbatim since both are "load settings, edit fields, save" sections):

```css
.section {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-5);
  margin-top: var(--space-5);
  box-shadow: var(--shadow-card);
}

.heading {
  font-size: var(--font-size-lg);
  font-weight: 600;
  color: var(--color-text);
  margin: 0 0 var(--space-4) 0;
}

.field {
  margin-bottom: var(--space-4);
}

.label {
  display: block;
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--color-text);
  margin-bottom: var(--space-2);
}

.textarea {
  width: 100%;
  min-height: 100px;
  padding: var(--space-2) var(--space-3);
  font-family: var(--font-mono, monospace);
  font-size: var(--font-size-sm);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface-raised);
  color: var(--color-text);
  box-sizing: border-box;
  resize: vertical;
}

.levelGroup {
  display: flex;
  gap: var(--space-3);
}

.checkboxLabel {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--font-size-sm);
  color: var(--color-text);
  margin-bottom: var(--space-2);
  cursor: pointer;
}

.error {
  color: var(--color-danger);
  margin-bottom: var(--space-3);
}

.saved {
  color: var(--color-success);
  margin-bottom: var(--space-3);
}

.saveButton {
  background: var(--color-primary);
  color: var(--color-text-on-primary, white);
  border: none;
  border-radius: var(--radius-md);
  padding: var(--space-2) var(--space-4);
  font-size: var(--font-size-sm);
  font-weight: 600;
  cursor: pointer;
}

.saveButton:disabled {
  cursor: not-allowed;
  opacity: 0.7;
}
```

- [ ] **Step 2: Write the component**

Create `frontend/src/components/SystemSettings/BannerSection.tsx`:

```tsx
/**
 * ARCH-L1-001 ReactFrontend — BannerSection (SystemSettings, administration tab).
 *
 * leaf_id: COMP-RF-001 (NavigationShell scope — System Settings)
 *
 * System-Admin-only editor for the tenant's single global banner. Page-level
 * access is gated by SystemSettings.tsx's existing `roles.includes("admin")`
 * check (loose, UX-only — matches WorkspaceAdminSection's precedent); real
 * enforcement is server-side via `AuthorizationService.is_tenant_admin`
 * (GlobalBannerView), so a workspace-admin who is not a System-Admin will
 * see this form but get a 403 on save, surfaced as the `error` state below.
 */

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { bannersApi, type Banner, type BannerLevel } from "../../api/banners";
import { extractErrorMessage } from "../../api/client";
import styles from "./BannerSection.module.css";

const LEVELS: BannerLevel[] = ["neutral", "info", "warning", "critical"];

export function BannerSection(): JSX.Element {
  const { t } = useTranslation();
  const [banner, setBanner] = useState<Banner | null>(null);
  const [level, setLevel] = useState<BannerLevel>("neutral");
  const [message, setMessage] = useState("");
  const [enabled, setEnabled] = useState(false);
  const [dismissible, setDismissible] = useState(true);
  const [showOnLoginPage, setShowOnLoginPage] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedOk, setSavedOk] = useState(false);

  useEffect(() => {
    setIsLoading(true);
    bannersApi
      .getGlobal()
      .then((existing) => {
        if (!existing) return;
        setBanner(existing);
        setLevel(existing.level);
        setMessage(existing.message);
        setEnabled(existing.enabled);
        setDismissible(existing.dismissible);
        setShowOnLoginPage(existing.show_on_login_page);
      })
      .catch((err) => setError(extractErrorMessage(err)))
      .finally(() => setIsLoading(false));
  }, []);

  const handleLevelChange = (next: BannerLevel): void => {
    setLevel(next);
    setSavedOk(false);
    // UI-level pre-fill only (spec: "modularer" — always overridable):
    // switching to critical suggests non-dismissible, but never forces it
    // once the admin has touched dismissible for this row.
    if (next === "critical" && !banner) setDismissible(false);
  };

  const handleSave = async (): Promise<void> => {
    setIsSaving(true);
    setError(null);
    setSavedOk(false);
    try {
      const updated = await bannersApi.putGlobal({
        level,
        message,
        enabled,
        dismissible,
        show_on_login_page: showOnLoginPage,
      });
      setBanner(updated);
      setSavedOk(true);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading) {
    return (
      <section className={styles.section} data-testid="banner-section">
        <h3 className={styles.heading}>{t("banners.globalTitle", "Global Banner")}</h3>
        <p>{t("loading", "Loading...")}</p>
      </section>
    );
  }

  return (
    <section className={styles.section} data-testid="banner-section">
      <h3 className={styles.heading}>{t("banners.globalTitle", "Global Banner")}</h3>

      {error && <p className={styles.error}>{error}</p>}
      {savedOk && <p className={styles.saved}>{t("actions.saved", "Saved.")}</p>}

      <label className={styles.checkboxLabel}>
        <input
          type="checkbox"
          data-testid="banner-enabled-toggle"
          checked={enabled}
          onChange={(e) => { setEnabled(e.target.checked); setSavedOk(false); }}
        />
        {t("banners.enabled", "Enabled")}
      </label>

      <div className={styles.field}>
        <span className={styles.label}>{t("banners.levelLabel", "Level")}</span>
        <div className={styles.levelGroup} data-testid="banner-level-group">
          {LEVELS.map((lvl) => (
            <label key={lvl} className={styles.checkboxLabel}>
              <input
                type="radio"
                name="banner-level"
                data-testid={`banner-level-${lvl}`}
                checked={level === lvl}
                onChange={() => handleLevelChange(lvl)}
              />
              {t(`banners.level.${lvl}`, lvl)}
            </label>
          ))}
        </div>
      </div>

      <div className={styles.field}>
        <label className={styles.label} htmlFor="banner-message-input">
          {t("banners.messageLabel", "Message (Markdown)")}
        </label>
        <textarea
          id="banner-message-input"
          data-testid="banner-message-input"
          className={styles.textarea}
          value={message}
          onChange={(e) => { setMessage(e.target.value); setSavedOk(false); }}
          placeholder={t("banners.messagePlaceholder", "Markdown text...")}
        />
      </div>

      <label className={styles.checkboxLabel}>
        <input
          type="checkbox"
          data-testid="banner-dismissible-toggle"
          checked={dismissible}
          onChange={(e) => { setDismissible(e.target.checked); setSavedOk(false); }}
        />
        {t("banners.dismissibleField", "Dismissible by end users")}
      </label>

      <label className={styles.checkboxLabel}>
        <input
          type="checkbox"
          data-testid="banner-show-on-login-toggle"
          checked={showOnLoginPage}
          onChange={(e) => { setShowOnLoginPage(e.target.checked); setSavedOk(false); }}
        />
        {t("banners.showOnLoginPage", "Also show on the login page")}
      </label>

      <div>
        <button
          type="button"
          data-testid="banner-save-button"
          className={styles.saveButton}
          disabled={isSaving}
          onClick={() => void handleSave()}
        >
          {isSaving ? "…" : t("actions.save")}
        </button>
      </div>
    </section>
  );
}
```

- [ ] **Step 3: Mount in `SystemSettings.tsx`**

Add the import:

```tsx
import { BannerSection } from "./BannerSection";
```

Change the administration-tab render line:

```tsx
{activeTab === "administration" && <WorkspaceAdminSection />}
```

to:

```tsx
{activeTab === "administration" && (
  <>
    <WorkspaceAdminSection />
    <BannerSection />
  </>
)}
```

- [ ] **Step 4: Add the two missing i18n keys used above** (`banners.globalTitle`, `banners.levelLabel`, `actions.saved`)

Check first whether `actions.saved` already exists: run `grep -n '"saved"' frontend/src/i18n/locales/de.json`. If it exists under the `actions` key, reuse it as-is (no change needed — the `t("actions.saved", "Saved.")` call above already has a safe fallback either way). If it does not exist, add `"saved": "Gespeichert."` to the `actions` object in `de.json` and `"saved": "Saved."` in `en.json`.

Add to the `banners` object added in Task 5 (in both `de.json` and `en.json`):

```json
"globalTitle": "Globaler Banner",
"levelLabel": "Stufe",
"messageLabel": "Nachricht (Markdown)"
```
(English: `"globalTitle": "Global Banner"`, `"levelLabel": "Level"`, `"messageLabel": "Message (Markdown)"`)

- [ ] **Step 5: Write the component test**

Create `frontend/src/components/SystemSettings/BannerSection.test.tsx`:

```tsx
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { BannerSection } from "./BannerSection";
import { bannersApi } from "../../api/banners";

vi.mock("../../api/banners", () => ({
  bannersApi: { getGlobal: vi.fn(), putGlobal: vi.fn() },
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (_key: string, fallback?: string) => fallback ?? _key }),
}));

describe("BannerSection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("loads and pre-fills the existing global banner", async () => {
    vi.mocked(bannersApi.getGlobal).mockResolvedValue({
      id: "g1",
      scope: "global",
      workspace_id: null,
      level: "warning",
      message: "existing text",
      enabled: true,
      dismissible: false,
      show_on_login_page: true,
      updated_at: "2026-08-23T00:00:00Z",
    });
    render(<BannerSection />);
    expect(await screen.findByDisplayValue("existing text")).toBeInTheDocument();
    expect(screen.getByTestId("banner-level-warning")).toBeChecked();
    expect(screen.getByTestId("banner-enabled-toggle")).toBeChecked();
    expect(screen.getByTestId("banner-dismissible-toggle")).not.toBeChecked();
    expect(screen.getByTestId("banner-show-on-login-toggle")).toBeChecked();
  });

  it("pre-fills dismissible=false only for a brand-new banner when critical is picked", async () => {
    vi.mocked(bannersApi.getGlobal).mockResolvedValue(null);
    render(<BannerSection />);
    await waitFor(() => expect(bannersApi.getGlobal).toHaveBeenCalled());
    expect(screen.getByTestId("banner-dismissible-toggle")).toBeChecked();
    fireEvent.click(screen.getByTestId("banner-level-critical"));
    expect(screen.getByTestId("banner-dismissible-toggle")).not.toBeChecked();
  });

  it("save calls putGlobal with the current form state", async () => {
    vi.mocked(bannersApi.getGlobal).mockResolvedValue(null);
    vi.mocked(bannersApi.putGlobal).mockResolvedValue({
      id: "g1",
      scope: "global",
      workspace_id: null,
      level: "info",
      message: "hello",
      enabled: true,
      dismissible: true,
      show_on_login_page: false,
      updated_at: "2026-08-23T00:00:00Z",
    });
    render(<BannerSection />);
    await waitFor(() => expect(bannersApi.getGlobal).toHaveBeenCalled());

    fireEvent.change(screen.getByTestId("banner-message-input"), {
      target: { value: "hello" },
    });
    fireEvent.click(screen.getByTestId("banner-enabled-toggle"));
    fireEvent.click(screen.getByTestId("banner-save-button"));

    await waitFor(() =>
      expect(bannersApi.putGlobal).toHaveBeenCalledWith({
        level: "neutral",
        message: "hello",
        enabled: true,
        dismissible: true,
        show_on_login_page: false,
      })
    );
    expect(await screen.findByText("Saved.")).toBeInTheDocument();
  });

  it("shows an error message when save fails (e.g. 403 for a non-System-Admin)", async () => {
    vi.mocked(bannersApi.getGlobal).mockResolvedValue(null);
    vi.mocked(bannersApi.putGlobal).mockRejectedValue({
      error: { message: "tenant-admin (System-Admin) role required." },
    });
    render(<BannerSection />);
    await waitFor(() => expect(bannersApi.getGlobal).toHaveBeenCalled());
    fireEvent.click(screen.getByTestId("banner-save-button"));
    expect(await screen.findByText("tenant-admin (System-Admin) role required.")).toBeInTheDocument();
  });
});
```

- [ ] **Step 6: Run the tests**

Run: `npm --prefix frontend test -- BannerSection.test.tsx`
Expected: 4 passed.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/SystemSettings/BannerSection.tsx frontend/src/components/SystemSettings/BannerSection.module.css frontend/src/components/SystemSettings/BannerSection.test.tsx frontend/src/components/SystemSettings/SystemSettings.tsx frontend/src/i18n/locales/de.json frontend/src/i18n/locales/en.json
git commit -m "feat: add System Settings global banner editor"
```

---

### Task 8: Frontend — Workspace Settings `WorkspaceBannerSection`

**Files:**
- Create: `frontend/src/components/WorkspaceSettings/WorkspaceBannerSection.tsx`
- Create: `frontend/src/components/WorkspaceSettings/WorkspaceBannerSection.module.css`
- Create: `frontend/src/components/WorkspaceSettings/WorkspaceBannerSection.test.tsx`
- Modify: `frontend/src/components/WorkspaceSettings/WorkspaceSettings.tsx`

**Interfaces:**
- Consumes: `bannersApi.getWorkspace()`/`putWorkspace()` (Task 4).
- Produces: `WorkspaceBannerSection` component (`{ workspaceId: UUID }` prop, matching `ContextGraphSettingsSection`'s and `PermissionsSection`'s prop shape), mounted in the `"general"` tab of `WorkspaceSettings.tsx`.

- [ ] **Step 1: Write the CSS module**

Create `frontend/src/components/WorkspaceSettings/WorkspaceBannerSection.module.css` (same visual language as `SystemSettings/BannerSection.module.css` — each per-section CSS Module in this codebase is self-contained rather than shared across the `SystemSettings`/`WorkspaceSettings` directory boundary, matching `ContextGraphSettingsSection.module.css`'s precedent):

```css
.section {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-5);
  margin-top: var(--space-5);
  box-shadow: var(--shadow-card);
}

.heading {
  font-size: var(--font-size-lg);
  font-weight: 600;
  color: var(--color-text);
  margin: 0 0 var(--space-4) 0;
}

.field {
  margin-bottom: var(--space-4);
}

.label {
  display: block;
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--color-text);
  margin-bottom: var(--space-2);
}

.textarea {
  width: 100%;
  min-height: 100px;
  padding: var(--space-2) var(--space-3);
  font-family: var(--font-mono, monospace);
  font-size: var(--font-size-sm);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface-raised);
  color: var(--color-text);
  box-sizing: border-box;
  resize: vertical;
}

.levelGroup {
  display: flex;
  gap: var(--space-3);
}

.checkboxLabel {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--font-size-sm);
  color: var(--color-text);
  margin-bottom: var(--space-2);
  cursor: pointer;
}

.error {
  color: var(--color-danger);
  margin-bottom: var(--space-3);
}

.saved {
  color: var(--color-success);
  margin-bottom: var(--space-3);
}

.saveButton {
  background: var(--color-primary);
  color: var(--color-text-on-primary, white);
  border: none;
  border-radius: var(--radius-md);
  padding: var(--space-2) var(--space-4);
  font-size: var(--font-size-sm);
  font-weight: 600;
  cursor: pointer;
}

.saveButton:disabled {
  cursor: not-allowed;
  opacity: 0.7;
}
```

- [ ] **Step 2: Write the component**

Create `frontend/src/components/WorkspaceSettings/WorkspaceBannerSection.tsx`:

```tsx
/**
 * ARCH-L1-001 ReactFrontend — WorkspaceBannerSection (WorkspaceSettings, general tab).
 *
 * leaf_id: COMP-RF-001 (NavigationShell scope — Workspace-Konfigurations-UI)
 *
 * Workspace-Admin (or System-Admin) editor for this workspace's single
 * banner. Page-level access mirrors PermissionsSection's precedent (parent
 * gates on the admin role, UX-only — real enforcement is server-side via
 * WorkspaceBannerView's ctx.has_role("admin") / is_tenant_admin check).
 * No `show_on_login_page` field — the login page has no workspace context
 * (spec: that flag only exists on the global banner).
 */

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { bannersApi, type Banner, type BannerLevel } from "../../api/banners";
import { extractErrorMessage } from "../../api/client";
import type { UUID } from "../../types";
import styles from "./WorkspaceBannerSection.module.css";

const LEVELS: BannerLevel[] = ["neutral", "info", "warning", "critical"];

interface Props {
  workspaceId: UUID;
}

export function WorkspaceBannerSection({ workspaceId }: Props): JSX.Element {
  const { t } = useTranslation();
  const [banner, setBanner] = useState<Banner | null>(null);
  const [level, setLevel] = useState<BannerLevel>("neutral");
  const [message, setMessage] = useState("");
  const [enabled, setEnabled] = useState(false);
  const [dismissible, setDismissible] = useState(true);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedOk, setSavedOk] = useState(false);

  useEffect(() => {
    setIsLoading(true);
    bannersApi
      .getWorkspace(workspaceId)
      .then((existing) => {
        if (!existing) return;
        setBanner(existing);
        setLevel(existing.level);
        setMessage(existing.message);
        setEnabled(existing.enabled);
        setDismissible(existing.dismissible);
      })
      .catch((err) => setError(extractErrorMessage(err)))
      .finally(() => setIsLoading(false));
  }, [workspaceId]);

  const handleLevelChange = (next: BannerLevel): void => {
    setLevel(next);
    setSavedOk(false);
    if (next === "critical" && !banner) setDismissible(false);
  };

  const handleSave = async (): Promise<void> => {
    setIsSaving(true);
    setError(null);
    setSavedOk(false);
    try {
      const updated = await bannersApi.putWorkspace(workspaceId, {
        level,
        message,
        enabled,
        dismissible,
      });
      setBanner(updated);
      setSavedOk(true);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading) {
    return (
      <section className={styles.section} data-testid="workspace-banner-section">
        <h3 className={styles.heading}>{t("banners.workspaceTitle", "Workspace Banner")}</h3>
        <p>{t("loading", "Loading...")}</p>
      </section>
    );
  }

  return (
    <section className={styles.section} data-testid="workspace-banner-section">
      <h3 className={styles.heading}>{t("banners.workspaceTitle", "Workspace Banner")}</h3>

      {error && <p className={styles.error}>{error}</p>}
      {savedOk && <p className={styles.saved}>{t("actions.saved", "Saved.")}</p>}

      <label className={styles.checkboxLabel}>
        <input
          type="checkbox"
          data-testid="workspace-banner-enabled-toggle"
          checked={enabled}
          onChange={(e) => { setEnabled(e.target.checked); setSavedOk(false); }}
        />
        {t("banners.enabled", "Enabled")}
      </label>

      <div className={styles.field}>
        <span className={styles.label}>{t("banners.levelLabel", "Level")}</span>
        <div className={styles.levelGroup} data-testid="workspace-banner-level-group">
          {LEVELS.map((lvl) => (
            <label key={lvl} className={styles.checkboxLabel}>
              <input
                type="radio"
                name="workspace-banner-level"
                data-testid={`workspace-banner-level-${lvl}`}
                checked={level === lvl}
                onChange={() => handleLevelChange(lvl)}
              />
              {t(`banners.level.${lvl}`, lvl)}
            </label>
          ))}
        </div>
      </div>

      <div className={styles.field}>
        <label className={styles.label} htmlFor="workspace-banner-message-input">
          {t("banners.messageLabel", "Message (Markdown)")}
        </label>
        <textarea
          id="workspace-banner-message-input"
          data-testid="workspace-banner-message-input"
          className={styles.textarea}
          value={message}
          onChange={(e) => { setMessage(e.target.value); setSavedOk(false); }}
          placeholder={t("banners.messagePlaceholder", "Markdown text...")}
        />
      </div>

      <label className={styles.checkboxLabel}>
        <input
          type="checkbox"
          data-testid="workspace-banner-dismissible-toggle"
          checked={dismissible}
          onChange={(e) => { setDismissible(e.target.checked); setSavedOk(false); }}
        />
        {t("banners.dismissibleField", "Dismissible by end users")}
      </label>

      <div>
        <button
          type="button"
          data-testid="workspace-banner-save-button"
          className={styles.saveButton}
          disabled={isSaving}
          onClick={() => void handleSave()}
        >
          {isSaving ? "…" : t("actions.save")}
        </button>
      </div>
    </section>
  );
}
```

- [ ] **Step 3: Mount in `WorkspaceSettings.tsx`**

Add the import:

```tsx
import { WorkspaceBannerSection } from "./WorkspaceBannerSection";
```

Find the `activeTab === "general"` block (starts at the line shown during planning: `{activeTab === "general" && (`). Read the full block with the Read tool to find its closing `)}` / `</>` before editing. Add `<WorkspaceBannerSection workspaceId={activeWorkspace.id} />` as the last child inside that block's `<>...</>` fragment, immediately before its closing `</>`  — i.e. after the existing Preset `<section>` and any other existing sections in "general", not before them (append, do not reorder existing content).

- [ ] **Step 4: Add the one missing i18n key** (`banners.workspaceTitle`)

Add to the `banners` object in both `de.json` and `en.json`:
```json
"workspaceTitle": "Workspace-Banner"
```
(English: `"workspaceTitle": "Workspace Banner"`)

- [ ] **Step 5: Write the component test**

Create `frontend/src/components/WorkspaceSettings/WorkspaceBannerSection.test.tsx`:

```tsx
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { WorkspaceBannerSection } from "./WorkspaceBannerSection";
import { bannersApi } from "../../api/banners";

vi.mock("../../api/banners", () => ({
  bannersApi: { getWorkspace: vi.fn(), putWorkspace: vi.fn() },
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (_key: string, fallback?: string) => fallback ?? _key }),
}));

describe("WorkspaceBannerSection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("loads and pre-fills the existing workspace banner", async () => {
    vi.mocked(bannersApi.getWorkspace).mockResolvedValue({
      id: "w1",
      scope: "workspace",
      workspace_id: "ws-1",
      level: "warning",
      message: "existing text",
      enabled: true,
      dismissible: false,
      show_on_login_page: false,
      updated_at: "2026-08-23T00:00:00Z",
    });
    render(<WorkspaceBannerSection workspaceId="ws-1" />);
    expect(await screen.findByDisplayValue("existing text")).toBeInTheDocument();
    expect(screen.getByTestId("workspace-banner-level-warning")).toBeChecked();
    expect(screen.getByTestId("workspace-banner-enabled-toggle")).toBeChecked();
    expect(screen.getByTestId("workspace-banner-dismissible-toggle")).not.toBeChecked();
    expect(bannersApi.getWorkspace).toHaveBeenCalledWith("ws-1");
  });

  it("pre-fills dismissible=false only for a brand-new banner when critical is picked", async () => {
    vi.mocked(bannersApi.getWorkspace).mockResolvedValue(null);
    render(<WorkspaceBannerSection workspaceId="ws-1" />);
    await waitFor(() => expect(bannersApi.getWorkspace).toHaveBeenCalled());
    expect(screen.getByTestId("workspace-banner-dismissible-toggle")).toBeChecked();
    fireEvent.click(screen.getByTestId("workspace-banner-level-critical"));
    expect(screen.getByTestId("workspace-banner-dismissible-toggle")).not.toBeChecked();
  });

  it("save calls putWorkspace with the workspace id and current form state", async () => {
    vi.mocked(bannersApi.getWorkspace).mockResolvedValue(null);
    vi.mocked(bannersApi.putWorkspace).mockResolvedValue({
      id: "w1",
      scope: "workspace",
      workspace_id: "ws-1",
      level: "info",
      message: "hello",
      enabled: true,
      dismissible: true,
      show_on_login_page: false,
      updated_at: "2026-08-23T00:00:00Z",
    });
    render(<WorkspaceBannerSection workspaceId="ws-1" />);
    await waitFor(() => expect(bannersApi.getWorkspace).toHaveBeenCalled());

    fireEvent.change(screen.getByTestId("workspace-banner-message-input"), {
      target: { value: "hello" },
    });
    fireEvent.click(screen.getByTestId("workspace-banner-enabled-toggle"));
    fireEvent.click(screen.getByTestId("workspace-banner-save-button"));

    await waitFor(() =>
      expect(bannersApi.putWorkspace).toHaveBeenCalledWith("ws-1", {
        level: "neutral",
        message: "hello",
        enabled: true,
        dismissible: true,
      })
    );
    expect(await screen.findByText("Saved.")).toBeInTheDocument();
  });

  it("shows an error message when save fails (e.g. 403 for a non-admin)", async () => {
    vi.mocked(bannersApi.getWorkspace).mockResolvedValue(null);
    vi.mocked(bannersApi.putWorkspace).mockRejectedValue({
      error: { message: "workspace-admin or System-Admin role required." },
    });
    render(<WorkspaceBannerSection workspaceId="ws-1" />);
    await waitFor(() => expect(bannersApi.getWorkspace).toHaveBeenCalled());
    fireEvent.click(screen.getByTestId("workspace-banner-save-button"));
    expect(
      await screen.findByText("workspace-admin or System-Admin role required.")
    ).toBeInTheDocument();
  });
});
```

- [ ] **Step 6: Run the tests**

Run: `npm --prefix frontend test -- WorkspaceBannerSection.test.tsx`
Expected: 4 passed.

- [ ] **Step 7: Run the full frontend suite once to confirm no cross-task regressions**

Run: `npm --prefix frontend test`
Expected: all tests pass, including the pre-existing `WorkspaceSettings.test.tsx` and `SystemSettings`-area tests (the two settings-page modifications in Tasks 7-8 must not break their existing tab-rendering tests).

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/WorkspaceSettings/WorkspaceBannerSection.tsx frontend/src/components/WorkspaceSettings/WorkspaceBannerSection.module.css frontend/src/components/WorkspaceSettings/WorkspaceBannerSection.test.tsx frontend/src/components/WorkspaceSettings/WorkspaceSettings.tsx frontend/src/i18n/locales/de.json frontend/src/i18n/locales/en.json
git commit -m "feat: add Workspace Settings banner editor"
```

---

### Task 9: E2E — full banner lifecycle flow

**Files:**
- Create: `e2e/tests/banners.spec.ts`

**Interfaces:**
- Consumes: existing E2E helpers — `e2e/helpers/auth.ts` (login as demo admin), the seeded Demo Workspace/Demo Tenant fixtures already used by other specs in this suite (follow whatever login/workspace-selection helper pattern the nearest existing spec in `e2e/tests/` uses — e.g. `workspace.spec.ts` — read it first to match the exact helper function names and login flow, since those are project-specific and evolve; do not invent a new login helper).

- [ ] **Step 1: Read an existing E2E spec for the exact helper API**

Run: `grep -n "^import\|login\|test(" e2e/tests/workspace.spec.ts | head -30`

Use whatever `login(...)`/`page.goto(...)` helper calls that file uses as the template for Step 2 below — do not guess helper names.

- [ ] **Step 2: Write the E2E spec**

Create `e2e/tests/banners.spec.ts`, following the exact import/login/navigation pattern found in Step 1 (the sketch below uses placeholder helper names — replace `loginAsAdmin`/`selectWorkspace` etc. with whatever Step 1 found; every other line, including all `data-testid` selectors, is exact and must not be guessed):

```typescript
import { test, expect } from "@playwright/test";
// Replace this import with whatever e2e/helpers/auth.ts exports and
// workspace.spec.ts imports — read Step 1's grep output before writing this.

test.describe("System & Workspace Banners", () => {
  test("admin sets a global banner, a member sees and dismisses it, it reappears on a fresh login", async ({
    page,
    browser,
  }) => {
    // 1. Log in as the demo admin (use the project's real login helper here).
    // 2. Navigate to System Settings -> administration tab.
    await page.goto("/system-settings?tab=administration");
    await expect(page.getByTestId("banner-section")).toBeVisible();

    // 3. Configure and enable a global banner.
    await page.getByTestId("banner-message-input").fill("Scheduled maintenance tonight");
    await page.getByTestId("banner-level-warning").check();
    await page.getByTestId("banner-enabled-toggle").check();
    await page.getByTestId("banner-save-button").click();
    await expect(page.getByText("Saved.")).toBeVisible();

    // 4. Navigate to the dashboard (or any authenticated route) and see the banner.
    await page.goto("/");
    await expect(page.getByTestId("banner-global")).toBeVisible();
    await expect(page.getByTestId("banner-global")).toContainText(
      "Scheduled maintenance tonight"
    );

    // 5. Dismiss it — it disappears within the same session, even after reload.
    await page.getByTestId("banner-global-dismiss").click();
    await expect(page.getByTestId("banner-global")).not.toBeVisible();
    await page.reload();
    await expect(page.getByTestId("banner-global")).not.toBeVisible();

    // 6. A fresh browser context (simulating "next login") sees it again.
    const freshContext = await browser.newContext();
    const freshPage = await freshContext.newPage();
    // Log in again in the fresh context using the same helper as step 1.
    await freshPage.goto("/");
    await expect(freshPage.getByTestId("banner-global")).toBeVisible();
    await freshContext.close();

    // 7. Clean up: disable the banner so this test is repeatable.
    await page.goto("/system-settings?tab=administration");
    await page.getByTestId("banner-enabled-toggle").uncheck();
    await page.getByTestId("banner-save-button").click();
  });
});
```

- [ ] **Step 3: Run the E2E spec in isolation**

Run: `npx playwright test e2e/tests/banners.spec.ts`
Expected: 1 passed. If the login/navigation helper calls from Step 1 don't match this project's actual routing (e.g. the System Settings route path, or how workspace selection works), fix them against the real app rather than the sketch above — the sketch's `data-testid` selectors (from Tasks 5 and 7) are authoritative; the login/navigation scaffolding around them is not.

- [ ] **Step 4: Commit**

```bash
git add e2e/tests/banners.spec.ts
git commit -m "test: add E2E flow for system & workspace banners"
```

---

## Post-Plan Note

Once all 9 tasks are complete and reviewed, consider whether `docs/superpowers/specs/2026-08-23-system-workspace-banners-design.md` needs a small follow-up correction PR documenting the `DEFAULT_TENANT_ID` deviation noted in Global Constraints above (the merged spec still describes a "subdomain/host header" mechanism that does not exist) — not required for this plan's completion, but leaving the merged spec inaccurate would mislead a future reader who trusts it over this plan.
