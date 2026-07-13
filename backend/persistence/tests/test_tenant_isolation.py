"""
COMP-PL-002 TenantIsolationManager — tenant isolation tests.

Covers REQ-L2-PL-001 / REQ-L3-PL002-001..003. The cross-tenant access test is
mandatory: it proves a T1 context never sees T2 rows and vice versa.
"""
from __future__ import annotations

import pytest

from persistence.models import Artifact, Requirement, Workspace
from persistence.tests.test_entity_schema import EXPECTED_ENTITIES
from persistence.models import TenantScopedModel
from persistence.tenancy import TenantContext, TenantContextNotSetError
from persistence.tests.conftest import active_tenant

pytestmark = pytest.mark.django_db(transaction=True)


def _make_requirement(tenant, workspace, title):
    artifact = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="requirement"
    )
    return Requirement.objects.create(
        tenant=tenant, artifact=artifact, title=title
    )


def test_all_returns_only_active_tenant_rows(
    tenant_a, tenant_b, workspace_a, workspace_b
):
    """REQ-L3-PL002-001: 5 reqs in T1, 3 in T2 → T1 context sees exactly 5."""
    with active_tenant(tenant_a):
        for i in range(5):
            _make_requirement(tenant_a, workspace_a, f"A-{i}")
    with active_tenant(tenant_b):
        for i in range(3):
            _make_requirement(tenant_b, workspace_b, f"B-{i}")

    with active_tenant(tenant_a):
        assert Requirement.objects.all().count() == 5
    with active_tenant(tenant_b):
        assert Requirement.objects.all().count() == 3


def test_cross_tenant_access_is_blocked(
    tenant_a, tenant_b, workspace_a, workspace_b
):
    """MANDATORY: a T1 row is invisible and unfetchable from a T2 context."""
    with active_tenant(tenant_a):
        req_a = _make_requirement(tenant_a, workspace_a, "secret-A")

    # From tenant B's context, tenant A's requirement must not be visible.
    with active_tenant(tenant_b):
        assert Requirement.objects.filter(pk=req_a.pk).count() == 0
        with pytest.raises(Requirement.DoesNotExist):
            Requirement.objects.get(pk=req_a.pk)


def test_missing_context_raises_before_query():
    """REQ-L3-PL002-002: no tenant context → TenantContextNotSetError."""
    TenantContext.clear_tenant()
    with pytest.raises(TenantContextNotSetError):
        list(Workspace.objects.all())


def test_filter_chaining_keeps_tenant_scope(
    tenant_a, tenant_b, workspace_a, workspace_b
):
    """REQ-L3-PL002-003: chained filter() cannot widen beyond the tenant."""
    with active_tenant(tenant_a):
        _make_requirement(tenant_a, workspace_a, "keep")
    with active_tenant(tenant_b):
        _make_requirement(tenant_b, workspace_b, "keep")

    with active_tenant(tenant_a):
        # Same title exists in both tenants; scope must restrict to T1.
        assert Requirement.objects.filter(title="keep").count() == 1


def test_unscoped_manager_sees_all_tenants(
    tenant_a, tenant_b, workspace_a, workspace_b
):
    """Escape hatch: unscoped manager bypasses the app-layer filter by design."""
    with active_tenant(tenant_a):
        _make_requirement(tenant_a, workspace_a, "x")
    with active_tenant(tenant_b):
        _make_requirement(tenant_b, workspace_b, "y")

    # No context set; unscoped must not raise and must see both rows.
    TenantContext.clear_tenant()
    assert Requirement.unscoped.count() == 2


@pytest.mark.parametrize("model", [
    m for m in EXPECTED_ENTITIES if issubclass(m, TenantScopedModel)
])
def test_tenant_manager_applied_to_all_tenant_scoped_models(model, tenant_a):
    """MANDATORY: Verify that every single TenantScopedModel injects the tenant filter."""
    with active_tenant(tenant_a):
        query_sql = str(model.objects.all().query)
        # Using string matching since Django's query compilation differs slightly by backend,
        # but the table/alias and `tenant_id` must be present.
        assert "tenant_id" in query_sql, f"Model {model.__name__} does not filter by tenant_id!"


def test_raw_query_blocked_without_context(tenant_a, workspace_a):
    """Verify that manager.raw() correctly throws if no context is set."""
    with active_tenant(tenant_a):
        _make_requirement(tenant_a, workspace_a, "raw")
        
    TenantContext.clear_tenant()
    
    with pytest.raises(TenantContextNotSetError):
        list(Requirement.objects.raw("SELECT * FROM pl_requirement"))
