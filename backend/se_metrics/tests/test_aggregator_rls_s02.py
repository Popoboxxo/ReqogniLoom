"""EXT-006 — title resolution must arm the RLS GUC and restore the caller context.

``_resolve_requirement_titles`` used ``TenantContext.set_tenant`` only: the ORM
manager was scoped but the PostgreSQL ``app.current_tenant`` variable stayed
empty, so under the application role every Requirement was RLS-hidden and the
dashboard rendered the 8-character id fallback. It also left the thread-local
tenant armed for whatever ran next on a reused connection.
"""
from __future__ import annotations

import uuid

import pytest

from persistence.models import Artifact, Requirement, Tenant, Workspace
from persistence.tests.rls_app_role import app_role
from persistence.tenancy import TenantContext
from se_metrics.aggregator import _resolve_requirement_titles
from se_metrics.types import VolatileRequirement

pytestmark = pytest.mark.django_db(transaction=True)

_TITLE = "Login must support two-factor auth"


@pytest.fixture(autouse=True)
def _clean_tenant_state():
    """Never leak a thread-local tenant or connection GUC across these tests."""
    from persistence.middleware import clear_request_tenant

    TenantContext.clear_tenant()
    clear_request_tenant()
    yield
    TenantContext.clear_tenant()
    clear_request_tenant()


def _seed_requirement() -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Create tenant/workspace/requirement as the superuser test connection."""
    tenant_id = uuid.uuid4()
    TenantContext.set_tenant(tenant_id)
    try:
        tenant = Tenant.objects.create(
            id=tenant_id,
            name="Aggregator RLS Tenant",
            slug=f"agg-rls-{tenant_id.hex[:8]}",
        )
        workspace = Workspace.objects.create(tenant=tenant, name="Aggregator WS")
        artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="Requirement"
        )
        requirement = Requirement.objects.create(
            tenant=tenant, artifact=artifact, title=_TITLE
        )
    finally:
        TenantContext.clear_tenant()
    return tenant_id, workspace.id, requirement.id


def test_title_resolution_leaves_a_cleared_context_unset() -> None:
    """A direct caller with no tenant must still find the context unset after."""
    tenant_id, _workspace_id, requirement_id = _seed_requirement()
    entries = [VolatileRequirement(requirement_id=str(requirement_id), change_count=1)]

    _resolve_requirement_titles(entries, tenant_id)

    assert not TenantContext.is_set()


def test_real_title_resolved_under_app_role(app_role) -> None:
    """RLS must let the arms-aware lookup see the real Requirement row."""
    tenant_id, _workspace_id, requirement_id = _seed_requirement()
    entries = [VolatileRequirement(requirement_id=str(requirement_id), change_count=1)]

    with app_role():
        _resolve_requirement_titles(entries, tenant_id)

    assert entries[0].title == _TITLE
    assert entries[0].title != str(requirement_id)[:8]
