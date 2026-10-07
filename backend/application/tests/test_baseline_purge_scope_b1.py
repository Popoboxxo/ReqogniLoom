"""Review B1 — baseline purge must be authorised against its own workspace.

The purge route (``DELETE /api/v1/baselines/{pk}/purge/``) names no workspace,
so the auth seam may hand the facade either roles scoped to the baseline's
workspace (object-scope seam enabled) or the tenant-wide role union (seam
disabled, or a direct/service caller). A facade gate that trusts only
``ctx.active_roles`` would then let an ``admin`` of workspace A remove a
workspace-B baseline of the same tenant. These tests pin the workspace-scoped
re-authorisation at the facade.
"""
from __future__ import annotations

import uuid

import pytest

from application.base import PermissionDeniedError
from application.baseline_facade import BaselineFacade
from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.models import ROLE_ADMIN, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, Tenant, User, Workspace

pytestmark = pytest.mark.django_db


def _env() -> tuple[Tenant, User, Workspace, Workspace]:
    """Tenant + user (``admin`` in workspace A only) + workspaces A and B."""
    slug = f"b1purge-{uuid.uuid4().hex[:8]}"
    tenant = Tenant.objects.create(name=f"T-{slug}", slug=slug, is_active=True)
    user = User.objects.create(
        username=f"u-{slug}", email=f"{slug}@t.test", tenant=tenant
    )
    set_request_tenant(tenant.id)
    try:
        ws_admin = Workspace.objects.create(
            tenant=tenant, name=f"A-{slug}", preset={"name": "extended"}
        )
        ws_other = Workspace.objects.create(
            tenant=tenant, name=f"B-{slug}", preset={"name": "extended"}
        )
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=ws_admin, role=ROLE_ADMIN
        )
    finally:
        clear_request_tenant()
    return tenant, user, ws_admin, ws_other


def _baseline(tenant: Tenant, workspace: Workspace) -> uuid.UUID:
    from baseline.models import BaselineSnapshot

    set_request_tenant(tenant.id)
    try:
        artifact = Artifact.unscoped.create(
            workspace=workspace, artifact_type="generic", tenant=tenant
        )
        return BaselineSnapshot.unscoped.create(
            workspace_id=workspace.id,
            name=f"bl-{uuid.uuid4().hex[:8]}",
            scope="document",
            artifact=artifact,
            tenant=tenant,
        ).id
    finally:
        clear_request_tenant()


def _ctx(tenant: Tenant, user: User) -> AuthContext:
    """An *unscoped* context carrying the tenant-wide role union.

    ``workspace_id=None`` is the shape a direct/service caller passes when the
    object-scope seam did not bind the request to a workspace.
    """
    return AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
        workspace_id=None,
    )


def test_unscoped_admin_cannot_purge_foreign_workspace_baseline() -> None:
    from baseline.models import BaselineSnapshot

    tenant, user, _ws_admin, ws_other = _env()
    baseline_other = _baseline(tenant, ws_other)

    with pytest.raises(PermissionDeniedError):
        BaselineFacade().purge_baseline(baseline_other, _ctx(tenant, user))

    assert BaselineSnapshot.unscoped.filter(pk=baseline_other).exists()


def test_same_workspace_admin_still_succeeds() -> None:
    from baseline.models import BaselineSnapshot

    tenant, user, ws_admin, _ws_other = _env()
    baseline = _baseline(tenant, ws_admin)

    BaselineFacade().purge_baseline(baseline, _ctx(tenant, user))

    assert not BaselineSnapshot.unscoped.filter(pk=baseline).exists()
