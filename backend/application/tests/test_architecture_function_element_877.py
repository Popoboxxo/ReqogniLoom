"""B3-T1 (#877): ``element_type='function'`` is a first-class architecture type.

``element_type`` is a free-vocabulary field (REQ-006 / D5) and the
``ElementType`` enum only supplies built-in defaults, so adding ``function``
must need no migration and no field change — creating an element with that
type has to round-trip through the service into the stored row unchanged.
"""
from __future__ import annotations

import pytest

from application.architecture_service import ArchitectureService
from auth_tenancy.context import AuthContext, AuthMethod
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User
from persistence.models import Workspace as PersistenceWorkspace
from persistence.tenancy import TenantContext


@pytest.fixture
def arch_ctx(db):
    """Tenant + workspace + editor AuthContext with the TenantContext active."""
    tenant = Tenant.objects.create(
        name="Arch Function", slug="arch-function", is_active=True
    )
    user = User.objects.create(
        username="archfuncuser", email="archfunc@t.test", tenant=tenant
    )
    set_request_tenant(tenant.id)
    TenantContext.set_tenant(tenant.id)
    workspace = PersistenceWorkspace.objects.create(
        tenant=tenant, name="arch-function-ws"
    )
    ctx = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
        api_key_id=None,
    )
    try:
        yield ctx, workspace
    finally:
        TenantContext.clear_tenant()
        clear_request_tenant()


def test_create_function_element(arch_ctx):
    ctx, ws = arch_ctx
    svc = ArchitectureService()

    root = svc.create_architecture_element(
        workspace_id=ws.id, title="System", ctx=ctx
    )
    function_el = svc.create_architecture_element(
        workspace_id=ws.id,
        title="Provide Power",
        ctx=ctx,
        element_type="function",
        parent_id=root.id,
    )

    stored = svc.get_architecture_element(function_el.id, ctx)
    assert stored.element_type == "function"
