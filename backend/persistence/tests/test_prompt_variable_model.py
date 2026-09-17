"""PromptVariable model — scope uniqueness and defaults (spec §3.1)."""
from __future__ import annotations

import pytest
from django.db import IntegrityError

from persistence.models import (
    PROMPT_VARIABLE_KIND_CONFIG,
    PromptVariable,
    Tenant,
    Workspace,
)
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant_workspace():
    tenant = Tenant.objects.create(name="PV Tenant", slug="pv-tenant")
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name="PV WS")
        yield tenant, workspace
    finally:
        TenantContext.clear_tenant()


def _make(tenant, **kwargs) -> PromptVariable:
    row = PromptVariable(
        tenant_id=tenant.id,
        name=kwargs.pop("name", "max_breadth"),
        kind=kwargs.pop("kind", PROMPT_VARIABLE_KIND_CONFIG),
        var_type=kwargs.pop("var_type", "int"),
        description=kwargs.pop("description", "Max children per level."),
        default_value=kwargs.pop("default_value", "5"),
        **kwargs,
    )
    row.save()
    return row


def test_defaults_are_version_one_and_active(tenant_workspace):
    tenant, _ws = tenant_workspace

    row = _make(tenant)

    assert row.version == 1
    assert row.is_active is True
    assert row.workspace_id is None


def test_second_active_row_for_same_scope_is_rejected(tenant_workspace):
    tenant, _ws = tenant_workspace
    _make(tenant)

    with pytest.raises(IntegrityError):
        _make(tenant)


def test_workspace_row_and_tenant_row_are_different_scopes(tenant_workspace):
    tenant, workspace = tenant_workspace
    _make(tenant)

    scoped = _make(tenant, workspace_id=workspace.id, default_value="9")

    assert scoped.workspace_id == workspace.id
    assert PromptVariable.objects.filter(is_active=True).count() == 2


def test_inactive_row_does_not_block_a_new_active_row(tenant_workspace):
    tenant, _ws = tenant_workspace
    prior = _make(tenant)
    prior.is_active = False
    prior.save(update_fields=["is_active"])

    successor = _make(tenant, version=2, default_value="7")

    assert successor.version == 2
    assert successor.is_active is True


def test_str_reports_scope_and_version(tenant_workspace):
    tenant, _ws = tenant_workspace

    assert "max_breadth" in str(_make(tenant))
