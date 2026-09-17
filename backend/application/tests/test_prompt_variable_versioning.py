"""Scope/version helpers for PromptVariable (mirrors prompt_template_versioning)."""
from __future__ import annotations

import pytest

from application.prompt_variable_versioning import (
    deactivate_variable_scope,
    get_active_variable,
    list_active_variables,
    publish_new_variable_version,
)
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant_workspace():
    from persistence.models import Tenant, Workspace

    tenant = Tenant.objects.create(name="PVV Tenant", slug="pvv-tenant")
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name="PVV WS")
        yield tenant, workspace
    finally:
        TenantContext.clear_tenant()


def _publish(tenant_id, value: str, **kwargs):
    return publish_new_variable_version(
        tenant_id=tenant_id,
        name=kwargs.pop("name", "max_breadth"),
        kind=kwargs.pop("kind", "config"),
        var_type=kwargs.pop("var_type", "int"),
        description=kwargs.pop("description", "Max children per level."),
        default_value=value,
        **kwargs,
    )


def test_returns_none_when_nothing_published(tenant_workspace):
    tenant, _ws = tenant_workspace

    assert get_active_variable(tenant_id=tenant.id, name="max_breadth") is None


def test_publishing_creates_version_one(tenant_workspace):
    tenant, _ws = tenant_workspace

    row = _publish(tenant.id, "5")

    assert row.version == 1
    assert row.is_active is True


def test_republishing_bumps_the_version_and_deactivates_the_prior_row(tenant_workspace):
    tenant, _ws = tenant_workspace
    _publish(tenant.id, "5")

    second = _publish(tenant.id, "8")

    assert second.version == 2
    active = get_active_variable(tenant_id=tenant.id, name="max_breadth")
    assert active is not None
    assert active.default_value == "8"


def test_workspace_none_selects_the_tenant_wide_scope(tenant_workspace):
    tenant, workspace = tenant_workspace
    _publish(tenant.id, "9", workspace_id=workspace.id)

    assert get_active_variable(tenant_id=tenant.id, name="max_breadth") is None
    scoped = get_active_variable(
        tenant_id=tenant.id, name="max_breadth", workspace_id=workspace.id
    )
    assert scoped is not None
    assert scoped.default_value == "9"


def test_list_without_workspace_filter_returns_every_scope(tenant_workspace):
    tenant, workspace = tenant_workspace
    _publish(tenant.id, "5")
    _publish(tenant.id, "9", workspace_id=workspace.id)

    rows = list_active_variables(tenant_id=tenant.id)

    assert len(rows) == 2


def test_list_with_workspace_filter_returns_only_that_workspace(tenant_workspace):
    tenant, workspace = tenant_workspace
    _publish(tenant.id, "5")
    _publish(tenant.id, "9", workspace_id=workspace.id)

    rows = list_active_variables(tenant_id=tenant.id, workspace_id=workspace.id)

    assert [r.default_value for r in rows] == ["9"]


def test_deactivate_reports_whether_a_row_was_active(tenant_workspace):
    tenant, _ws = tenant_workspace
    _publish(tenant.id, "5")

    assert deactivate_variable_scope(tenant_id=tenant.id, name="max_breadth") is True
    assert deactivate_variable_scope(tenant_id=tenant.id, name="max_breadth") is False
    assert get_active_variable(tenant_id=tenant.id, name="max_breadth") is None
