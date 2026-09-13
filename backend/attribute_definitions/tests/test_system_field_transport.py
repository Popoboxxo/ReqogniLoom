"""Transport read/write of the Artifact system fields (Attribut v3 WS2, #936).

The AUC (spec section 11) requires ``owner``/``reporter``/``priority`` to be
writeable, readable and round-tripping on both transports. These focused tests
pin the two projections the contract matrix exercises end-to-end through HTTP /
JSON-RPC:

* MCP: ``GenericCrudToolGroup`` create/read for a wired item type (Adr), using
  the real service and a bootstrapped definition.
* REST: the ``_adr_to_dict`` + ``AdrSerializer`` projection the ViewSet returns.

They are deliberately smaller than the full matrix; the matrix is the CI gate,
these make the failure local and readable.
"""
from __future__ import annotations

import uuid

import pytest
from django.core.management import call_command

from application.actor_service import ActorService
from application.adr_service import AdrService
from application.artifact_attribute_gateway import AttributeValues, ArtifactAttributeGateway
from auth_tenancy.context import AuthContext, AuthMethod
from mcp_server.tools.generic import GenericCrudToolGroup
from persistence.models import Artifact, Tenant, User, Workspace

pytestmark = pytest.mark.django_db

API_KEY = "reqlo-test"


@pytest.fixture
def env():
    suffix = uuid.uuid4().hex[:8]
    tenant = Tenant.objects.create(name=f"sft-{suffix}", slug=f"sft-{suffix}")
    user = User.objects.create(
        username=f"sft-admin-{suffix}", email=f"sft-{suffix}@t.test", tenant=tenant
    )
    workspace = Workspace.unscoped.create(
        tenant=tenant, name=f"sft-ws-{suffix}", preset={"name": "standard"}
    )
    call_command("bootstrap_attribute_definitions", tenant=str(tenant.id))
    ctx = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("editor", "admin"),
        auth_method=AuthMethod.API_KEY,
        api_key_id=None,
    )
    actor = ActorService().get_or_create_for_user(ctx, user.id)
    return tenant, user, workspace, ctx, str(actor.id)


def test_mcp_generic_adr_round_trips_priority_and_owner(env) -> None:
    _, user, workspace, ctx, actor_id = env
    group = GenericCrudToolGroup("adr", AdrService)

    created = group.execute_tool(
        tool_name="adr.create",
        params={
            "workspace_id": str(workspace.id),
            "title": "System fields ADR",
            "description": "",
            "priority": "high",
            "owner": {"kind": "user", "id": actor_id},
        },
        auth_context=ctx,
        api_key=API_KEY,
    )
    assert created.success is True, created.message
    adr_id = created.data["data"]["id"]
    assert created.data["data"]["priority"] == "high"
    assert created.data["data"]["owner"] == {"kind": "user", "id": actor_id}

    read = group.execute_tool(
        tool_name="adr.read",
        params={"id": adr_id},
        auth_context=ctx,
        api_key=API_KEY,
    )
    assert read.success is True, read.message
    assert read.data["data"]["priority"] == "high"
    assert read.data["data"]["owner"] == {"kind": "user", "id": actor_id}


def test_mcp_generic_adr_update_round_trips_priority(env) -> None:
    _, _, workspace, ctx, actor_id = env
    group = GenericCrudToolGroup("adr", AdrService)

    created = group.execute_tool(
        tool_name="adr.create",
        params={"workspace_id": str(workspace.id), "title": "ADR", "description": ""},
        auth_context=ctx,
        api_key=API_KEY,
    )
    assert created.success is True, created.message
    adr_id = created.data["data"]["id"]

    updated = group.execute_tool(
        tool_name="adr.update",
        params={"id": adr_id, "priority": "critical"},
        auth_context=ctx,
        api_key=API_KEY,
    )
    assert updated.success is True, updated.message
    assert updated.data["data"]["priority"] == "critical"

    read = group.execute_tool(
        tool_name="adr.read",
        params={"id": adr_id},
        auth_context=ctx,
        api_key=API_KEY,
    )
    assert read.data["data"]["priority"] == "critical"


def test_rest_adr_projection_reads_priority_and_owner(env) -> None:
    """The REST DTO + serializer projection must carry the system fields."""
    from rest_api.serializers import AdrSerializer
    from rest_api.views import _adr_to_dict

    _, user, workspace, ctx, actor_id = env
    adr = AdrService().create_adr(
        workspace_id=workspace.id, title="REST ADR", description="", ctx=ctx
    )
    ArtifactAttributeGateway().write(
        ctx,
        "Adr",
        adr,
        AttributeValues(
            core={
                "priority": "medium",
                "owner": {"kind": "user", "id": actor_id},
            }
        ),
    )

    data = AdrSerializer(_adr_to_dict(adr)).data

    assert data["priority"] == "medium"
    assert data["owner"] == {"kind": "user", "id": actor_id}
    assert data["reporter"] is None


def test_definition_exposes_actor_type_for_owner_after_bootstrap(env) -> None:
    """The wired item type seeds owner/reporter as visible, editable actors."""
    from attribute_definitions.workspace_definition_store import (
        WorkspaceAttributeDefinitionStore,
    )
    from attribute_definitions.schema import stored_attributes

    tenant, _, workspace, _, _ = env
    row = WorkspaceAttributeDefinitionStore().resolve(
        tenant.id, workspace.id, "Adr", "standard"
    )
    by_name = {a["name"]: a for a in stored_attributes(row.definition_json)}

    owner = by_name["owner"]
    assert owner["type"] == "actor"
    assert owner["visible"] is True
    assert owner["editable"] is True
    assert owner["multiple"] is False
    assert owner["allow_external"] is False
    assert by_name["priority"]["visible"] is True


def test_unwired_item_type_keeps_owner_hidden(env) -> None:
    """Requirement is not in the rollout gate: its system fields stay hidden."""
    from attribute_definitions.schema import stored_attributes
    from attribute_definitions.workspace_definition_store import (
        WorkspaceAttributeDefinitionStore,
    )

    tenant, _, workspace, _, _ = env
    row = WorkspaceAttributeDefinitionStore().resolve(
        tenant.id, workspace.id, "Requirement", "standard"
    )
    by_name = {a["name"]: a for a in stored_attributes(row.definition_json)}

    assert by_name["owner"]["visible"] is False
    assert by_name["owner"]["editable"] is False
    assert by_name["owner"]["type"] == "actor"
    # The carrier still exists on the Artifact row.
    assert Artifact._meta.get_field("owner") is not None
