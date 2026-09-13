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


def test_risk_keeps_owner_hidden_until_awms_migration(env) -> None:
    """Risk stays outside the rollout gate: its legacy ``owner`` column wins.

    Attribut v3 WS2 (#936) deliberately leaves Risk on ``visible=false``: its
    legacy free-text ``Risk.owner`` CharField still shadows the Artifact-level
    ``owner`` Actor FK whenever a Risk instance is accessed, so the two cannot
    be wired cleanly until the AWMS migration (WS7, #940) retires the column.
    The carrier itself already exists on the Artifact row.
    """
    from attribute_definitions.schema import stored_attributes
    from attribute_definitions.workspace_definition_store import (
        WorkspaceAttributeDefinitionStore,
    )

    tenant, _, workspace, _, _ = env
    row = WorkspaceAttributeDefinitionStore().resolve(
        tenant.id, workspace.id, "Risk", "standard"
    )
    by_name = {a["name"]: a for a in stored_attributes(row.definition_json)}

    assert by_name["owner"]["visible"] is False
    assert by_name["owner"]["editable"] is False
    assert by_name["owner"]["type"] == "actor"
    assert by_name["reporter"]["visible"] is False
    assert by_name["priority"]["visible"] is False
    # The carrier still exists on the Artifact row.
    assert Artifact._meta.get_field("owner") is not None


def test_system_fields_round_trip_for_every_wired_type() -> None:
    """REST+MCP round-trip of owner/reporter/priority for every wired type.

    Drives the same real stacks as the contract matrix (``APIClient`` + JWT and
    ``ToolRegistry.dispatch_request`` + ``reqlo_*`` API key) but asserts the
    three system fields explicitly per item type, so a regression names the
    exact transport/type instead of only failing the aggregate ratchet.
    ``Risk`` is excluded on purpose: WS2 leaves it hidden until the AWMS
    migration (WS7, #940) retires its legacy ``owner`` column.
    """
    from attribute_definitions.schema import SYSTEM_FIELDS_ENABLED_ITEM_TYPES
    from attribute_definitions.tests.test_transport_contract_matrix import (
        _JWT_OVERRIDES,
        _McpTransport,
        _RestTransport,
        _SPECS,
        _build_env,
        _payload,
        _token,
    )
    from django.test import override_settings

    with override_settings(**_JWT_OVERRIDES):
        env = _build_env()
        workspace = env.workspaces["standard"]
        owner = {"kind": "user", "id": env.admin_actor_id}
        reporter = {"kind": "user", "id": env.admin_actor_id}
        priority = "high"

        failures: list[str] = []
        for item_type in sorted(SYSTEM_FIELDS_ENABLED_ITEM_TYPES - {"Risk"}):
            spec = _SPECS[item_type]
            for transport in (
                _RestTransport(env.rest_client),
                _McpTransport(env.registry, env.api_key),
            ):
                token = _token(f"sft{item_type[:4]}")
                payload = _payload(env, "standard", item_type, spec, None, None, token)
                payload.update(owner=owner, reporter=reporter, priority=priority)
                created = transport.create(item_type, spec, payload, workspace)
                if not created.ok:
                    failures.append(
                        f"{item_type}/{transport.name}: create failed: {created.error}"
                    )
                    continue
                read = transport.read(
                    item_type, spec, created.entity_id or "", workspace
                )
                if not read.ok:
                    failures.append(
                        f"{item_type}/{transport.name}: read failed: {read.error}"
                    )
                    continue
                body = read.data if isinstance(read.data, dict) else {}
                for name, expected in (
                    ("owner", owner),
                    ("reporter", reporter),
                    ("priority", priority),
                ):
                    if body.get(name) != expected:
                        failures.append(
                            f"{item_type}/{transport.name}: {name} "
                            f"wrote {expected!r}, read {body.get(name)!r}"
                        )

        assert not failures, "System-field round-trip failures:\n" + "\n".join(failures)
