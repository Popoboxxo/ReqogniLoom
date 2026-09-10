"""Layer-2 seam for the link-type catalog (ADR-01)."""
from __future__ import annotations

import json
import uuid

import pytest

from application.link_type_facade import LinkTypeFacade
from link_types.builtin import builtin_definition
from persistence.errors import PermissionDeniedError, ValidationError
from persistence.tenancy import TenantContext


@pytest.fixture
def env(db):
    from auth_tenancy.context import AuthContext, AuthMethod
    from link_types.workspace_store import provision_workspace_link_types
    from persistence.models import Tenant, Workspace

    tenant = Tenant.objects.create(name="facade")
    TenantContext.set_tenant(tenant.id)
    ws = Workspace.objects.create(tenant=tenant, name="ws")
    provision_workspace_link_types(workspace_id=ws.id, tenant_id=tenant.id)

    admin = AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        workspace_id=ws.id,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )
    viewer = AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        workspace_id=ws.id,
        active_roles=("viewer",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )
    yield {"tenant": tenant, "workspace": ws, "admin": admin, "viewer": viewer}
    TenantContext.clear_tenant()


@pytest.mark.django_db
def test_list_global_returns_the_eight_seeded_types(env):
    rows = LinkTypeFacade().list_global(env["admin"])
    assert {row["key"] for row in rows} == {
        "derives-from",
        "decomposes",
        "allocated-to",
        "verifies",
        "decides",
        "mitigates",
        "references",
        "diagram-ref",
    }


@pytest.mark.django_db
def test_every_returned_row_is_json_serializable(env):
    """The MCP transport uses stdlib json.dumps — a UUID here is a 500."""
    rows = LinkTypeFacade().list_global(env["admin"])
    json.dumps(rows)
    rows = LinkTypeFacade().list_workspace(env["admin"], env["workspace"].id)
    json.dumps(rows)


@pytest.mark.django_db
def test_workspace_rows_carry_the_customization_flag(env):
    rows = LinkTypeFacade().list_workspace(env["admin"], env["workspace"].id)
    assert all(row["is_customized"] is False for row in rows)
    assert all("definition" in row for row in rows)


@pytest.mark.django_db
def test_a_non_admin_cannot_write_the_global_scope(env):
    definition = builtin_definition("mitigates")
    with pytest.raises(PermissionDeniedError):
        LinkTypeFacade().update_global(env["viewer"], "mitigates", definition)


@pytest.mark.django_db
def test_a_non_admin_may_still_read(env):
    assert LinkTypeFacade().list_workspace(env["viewer"], env["workspace"].id)


@pytest.mark.django_db
def test_create_global_accepts_a_tenant_invented_key(env):
    definition = builtin_definition("mitigates")
    definition["built_in"] = False
    row = LinkTypeFacade().create_global(env["admin"], "conflicts-with", definition)
    assert row["key"] == "conflicts-with"
    assert row["definition"]["built_in"] is False


@pytest.mark.django_db
def test_update_global_reports_how_many_workspaces_it_propagated_to(env):
    changed = builtin_definition("mitigates")
    changed["impact_weight"] = 0.9
    row = LinkTypeFacade().update_global(env["admin"], "mitigates", changed)
    assert row["propagated_to"] == 1


@pytest.mark.django_db
def test_update_workspace_marks_the_row_customized(env):
    changed = builtin_definition("mitigates")
    changed["impact_weight"] = 0.7
    row = LinkTypeFacade().update_workspace(
        env["admin"], env["workspace"].id, "mitigates", changed
    )
    assert row["is_customized"] is True


@pytest.mark.django_db
def test_reset_workspace_clears_the_flag(env):
    changed = builtin_definition("mitigates")
    changed["impact_weight"] = 0.7
    LinkTypeFacade().update_workspace(
        env["admin"], env["workspace"].id, "mitigates", changed
    )
    row = LinkTypeFacade().reset_workspace(
        env["admin"], env["workspace"].id, "mitigates"
    )
    assert row["is_customized"] is False
    assert row["definition"]["impact_weight"] == 0.5


@pytest.mark.django_db
def test_an_invalid_definition_is_rejected_at_the_facade(env):
    bad = builtin_definition("mitigates")
    bad["suspect_rule"] = "invent-something"
    with pytest.raises(ValidationError, match="suspect_rule"):
        LinkTypeFacade().update_global(env["admin"], "mitigates", bad)


@pytest.mark.django_db
def test_writes_are_audited(env):
    from audit.models import AuditEntry

    changed = builtin_definition("mitigates")
    changed["impact_weight"] = 0.9
    LinkTypeFacade().update_global(env["admin"], "mitigates", changed)

    assert AuditEntry.objects.filter(entity_type="GlobalLinkTypeDefinition").exists()
