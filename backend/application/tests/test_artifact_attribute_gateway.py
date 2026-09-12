"""Interface guards for the ArtifactAttributeGateway skeleton (WS0 #941).

Locks the public surface and the shared payload contract (AUC, spec section 11)
so WS1 wires against a stable interface. No database, no Django app registry
required: the definition facade is injected as a fake.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from application.artifact_attribute_gateway import (
    ArtifactAttributeGateway,
    AttributeCarrier,
    AttributeValues,
)
from auth_tenancy.context import AuthContext, AuthMethod


class _FakeDefinitions:
    """Records delegation without touching the ORM."""

    def __init__(self) -> None:
        self.resolved: list[tuple[str, UUID]] = []
        self.validated: list[tuple[Any, ...]] = []

    def resolve(
        self, ctx: AuthContext, item_type: str, workspace_id: UUID
    ) -> dict[str, Any]:
        self.resolved.append((item_type, workspace_id))
        return {"item_type": item_type, "attributes": [], "sections": []}

    def validate_artifact_fields(
        self,
        ctx: AuthContext,
        item_type: str,
        workspace_id: UUID,
        changed_fields: dict[str, Any],
        existing: dict[str, Any] | None,
    ) -> None:
        self.validated.append((item_type, workspace_id, changed_fields, existing))


class _FakeArtifact:
    def __init__(self) -> None:
        self.id = uuid4()
        self.custom_fields: dict[str, Any] = {}


def _ctx() -> AuthContext:
    return AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )


def test_interface_surface_and_carriers() -> None:
    """The five AUC operations exist; the six carriers are the shared vocabulary."""
    for name in ("resolve_definition", "discover", "read", "write", "validate"):
        assert callable(getattr(ArtifactAttributeGateway, name))
    assert {c.value for c in AttributeCarrier} == {
        "core",
        "extended",
        "system",
        "link",
        "widget",
        "entity",
    }


def test_to_payload_nests_extended_under_custom_fields() -> None:
    """The one wire shape REST bodies and MCP params share."""
    values = AttributeValues(core={"title": "t"}, extended={"probe": 1})
    assert values.to_payload() == {"title": "t", "custom_fields": {"probe": 1}}


def test_resolve_definition_delegates() -> None:
    definitions = _FakeDefinitions()
    gateway = ArtifactAttributeGateway(definitions=definitions)  # type: ignore[arg-type]
    workspace_id = uuid4()

    result = gateway.resolve_definition(_ctx(), "Requirement", workspace_id)

    assert result["item_type"] == "Requirement"
    assert definitions.resolved == [("Requirement", workspace_id)]


def test_validate_delegates_to_the_single_validation_path() -> None:
    definitions = _FakeDefinitions()
    gateway = ArtifactAttributeGateway(definitions=definitions)  # type: ignore[arg-type]
    workspace_id = uuid4()
    payload = {"title": "t", "custom_fields": {"probe": "v"}}

    gateway.validate(_ctx(), "Requirement", workspace_id, payload, None)

    assert definitions.validated == [("Requirement", workspace_id, payload, None)]


def test_ws1_operations_are_not_implemented_yet() -> None:
    """Discovery/read/write stay unimplemented until WS1 wires them."""
    gateway = ArtifactAttributeGateway(definitions=_FakeDefinitions())  # type: ignore[arg-type]
    ctx = _ctx()
    workspace_id = uuid4()
    artifact = _FakeArtifact()

    with pytest.raises(NotImplementedError):
        gateway.discover(ctx, "Requirement", workspace_id)
    with pytest.raises(NotImplementedError):
        gateway.read(ctx, "Requirement", artifact)  # type: ignore[arg-type]
    with pytest.raises(NotImplementedError):
        gateway.write(  # type: ignore[arg-type]
            ctx, "Requirement", artifact, AttributeValues()
        )
