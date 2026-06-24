"""
COMP-AT-003 TenantContextService — tests.

Covers REQ-L3-AT003-001 (DB-validated tenant resolution), REQ-L3-AT003-003
(immutable AuthContext) and the cross-tenant isolation guarantee (REQ-L2-AT-008):
a context resolved for tenant A must not expose tenant B's rows.
"""
from __future__ import annotations

import dataclasses

import pytest

from auth_tenancy.context import AuthMethod, IdentityClaims
from auth_tenancy.errors import TenantResolutionError
from auth_tenancy.services.tenant_context import TenantContextService
from persistence.models import Workspace

from .conftest import active_tenant


def _claims_for(user, tenant) -> IdentityClaims:
    return IdentityClaims(
        user_id=user.id,
        tenant_id=tenant.id,
        roles=("editor",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )


@pytest.mark.django_db
def test_resolves_active_tenant(user_a, tenant_a):
    ctx = TenantContextService().resolve_tenant_context(_claims_for(user_a, tenant_a))
    assert ctx.tenant_id == tenant_a.id
    assert ctx.tenant_name == tenant_a.name


@pytest.mark.django_db
def test_unknown_tenant_raises_resolution_error(user_a, tenant_a):
    bad = dataclasses.replace(
        _claims_for(user_a, tenant_a),
        tenant_id="99999999-9999-9999-9999-999999999999",
    )
    with pytest.raises(TenantResolutionError) as exc:
        TenantContextService().resolve_tenant_context(bad)
    assert exc.value.code == "tenant_resolution_failed"
    assert exc.value.status_code == 500


@pytest.mark.django_db
def test_inactive_tenant_raises_resolution_error(user_a, tenant_a):
    tenant_a.is_active = False
    tenant_a.save(update_fields=["is_active"])
    with pytest.raises(TenantResolutionError):
        TenantContextService().resolve_tenant_context(_claims_for(user_a, tenant_a))


@pytest.mark.django_db
def test_auth_context_is_immutable(user_a, tenant_a):
    svc = TenantContextService()
    tctx = svc.resolve_tenant_context(_claims_for(user_a, tenant_a))
    auth = svc.build_auth_context(
        _claims_for(user_a, tenant_a), tctx, ("editor",)
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        auth.tenant_id = "00000000-0000-0000-0000-000000000000"  # type: ignore[misc]


@pytest.mark.django_db
def test_cross_tenant_isolation_via_active_context(
    tenant_a, tenant_b, user_a, user_b
):
    """A workspace created in T1 must be invisible when T2 is active."""
    with active_tenant(tenant_a):
        Workspace.objects.create(tenant=tenant_a, name="A-only", preset={})

    svc = TenantContextService()
    # Activate tenant B via the service path, then query.
    tctx_b = svc.resolve_tenant_context(_claims_for(user_b, tenant_b))
    svc.activate(tctx_b)
    try:
        assert Workspace.objects.filter(name="A-only").count() == 0
    finally:
        svc.deactivate()

    # Sanity: visible under tenant A.
    with active_tenant(tenant_a):
        assert Workspace.objects.filter(name="A-only").count() == 1


@pytest.mark.django_db
def test_api_key_context_carries_api_key_id(user_a, tenant_a):
    svc = TenantContextService()
    claims = IdentityClaims(
        user_id=user_a.id,
        tenant_id=tenant_a.id,
        roles=(),
        auth_method=AuthMethod.API_KEY,
        api_key_id=user_a.id,  # any UUID for the shape test
    )
    tctx = svc.resolve_tenant_context(claims)
    auth = svc.build_auth_context(claims, tctx, ())
    assert auth.auth_method is AuthMethod.API_KEY
    assert auth.api_key_id is not None
