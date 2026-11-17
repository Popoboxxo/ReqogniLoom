"""EXT-001 — ``_workspace_enabled`` must arm the DB tenant, not just the ORM one.

Seeded as a superuser (RLS bypass), the workspace toggle row is then read
through the least-privilege application role with no tenant armed. A bare
``TenantContext.set_tenant`` satisfies the ORM manager but leaves
``app.current_tenant`` empty, so RLS hides the row and the function silently
falls back to "feature ON". The fix arms both layers via ``set_request_tenant``.
"""
from __future__ import annotations

import uuid

import pytest

from memory.injection_policy import _workspace_enabled
from persistence.models import Tenant, Workspace
from persistence.tests.rls_app_role import app_role
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db(transaction=True)


def _seed_disabled_workspace() -> tuple[uuid.UUID, uuid.UUID]:
    """Create a tenant + workspace whose memory toggle is explicitly OFF."""
    from memory.models import WorkspaceMemorySettings

    tenant_id = uuid.uuid4()
    TenantContext.set_tenant(tenant_id)
    try:
        tenant = Tenant.objects.create(
            id=tenant_id,
            name="Injection Policy Tenant",
            slug=f"inj-policy-{tenant_id.hex[:8]}",
        )
        workspace = Workspace.objects.create(tenant=tenant, name="Injection WS")
        WorkspaceMemorySettings.objects.create(workspace=workspace, enabled=False)
    finally:
        TenantContext.clear_tenant()
    return tenant_id, workspace.id


def test_disabled_workspace_is_visible_under_app_role(app_role) -> None:
    """RLS must see the seeded ``enabled=False`` row after the fix.

    Pre-fix: the row is hidden -> ``.first()`` is None -> ``True`` (feature ON).
    """
    tenant_id, workspace_id = _seed_disabled_workspace()

    with app_role():
        assert _workspace_enabled(tenant_id, workspace_id) is False

    assert not TenantContext.is_set()
