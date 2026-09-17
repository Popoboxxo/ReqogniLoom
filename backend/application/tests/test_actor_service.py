"""ActorService + gateway actor adapter (Attribut v3 WS2, #936).

Database-backed: the service's whole job is uniqueness and existence against the
real ``pl_actor`` table, so a mocked ORM would test nothing. The gateway
round-trip at the end exercises the WS2 value adapter on a real ``Artifact``
(owner FK in, wire value form out) with the definition facade injected, keeping
the test focused on the adapter rather than the definition store.
"""
from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from application.actor_service import ActorService
from application.artifact_attribute_gateway import ArtifactAttributeGateway, AttributeValues
from auth_tenancy.context import AuthContext, AuthMethod
from persistence.errors import NotFoundError, ValidationError
from persistence.models import Actor, Artifact, Tenant, User, Workspace

pytestmark = pytest.mark.django_db


def _ctx(*, tenant_id: Any, roles: tuple[str, ...] = ("admin",)) -> AuthContext:
    return AuthContext(
        user_id=uuid4(),
        tenant_id=tenant_id,
        active_roles=roles,
        auth_method=AuthMethod.BEARER_TOKEN,
    )


@pytest.fixture
def tenant() -> Tenant:
    suffix = uuid4().hex[:8]
    return Tenant.objects.create(name=f"actor-{suffix}", slug=f"actor-{suffix}")


@pytest.fixture
def user(tenant: Tenant) -> User:
    return User.objects.create(
        username=f"actor-user-{uuid4().hex[:8]}",
        email="actor-user@example.com",
        tenant=tenant,
        first_name="Anna",
        last_name="Admin",
    )


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    return Workspace.unscoped.create(
        tenant=tenant, name=f"actor-ws-{uuid4().hex[:6]}", preset={"name": "standard"}
    )


# ---------------------------------------------------------------------------
# External actors
# ---------------------------------------------------------------------------


def test_get_or_create_external_is_case_insensitive_and_idempotent(tenant: Tenant) -> None:
    service = ActorService()
    ctx = _ctx(tenant_id=tenant.id)

    first = service.get_or_create_external(ctx, "Frau Mueller (TUEV)")
    second = service.get_or_create_external(ctx, "  frau mueller (tuev) ")

    assert first.id == second.id
    assert first.kind == Actor.Kind.EXTERNAL
    assert first.user_id is None
    assert Actor.objects.filter(kind=Actor.Kind.EXTERNAL).count() == 1


def test_get_or_create_external_rejects_an_empty_name(tenant: Tenant) -> None:
    service = ActorService()
    with pytest.raises(ValidationError):
        service.get_or_create_external(_ctx(tenant_id=tenant.id), "   ")


# ---------------------------------------------------------------------------
# User actors
# ---------------------------------------------------------------------------


def test_get_or_create_for_user_reuses_the_actor(tenant: Tenant, user: User) -> None:
    service = ActorService()
    ctx = _ctx(tenant_id=tenant.id)

    first = service.get_or_create_for_user(ctx, user.id)
    second = service.get_or_create_for_user(ctx, user.id)

    assert first.id == second.id
    assert first.kind == Actor.Kind.USER
    assert first.user_id == user.id
    assert first.display_name == "Anna Admin"


def test_get_or_create_for_user_unknown_user_raises(tenant: Tenant) -> None:
    service = ActorService()
    with pytest.raises(NotFoundError):
        service.get_or_create_for_user(_ctx(tenant_id=tenant.id), uuid4())


def test_resolve_reference_accepts_an_actor_id_or_a_user_id(
    tenant: Tenant, user: User
) -> None:
    service = ActorService()
    ctx = _ctx(tenant_id=tenant.id)

    actor = service.get_or_create_for_user(ctx, user.id)
    assert service.resolve_reference(ctx, actor.id).id == actor.id
    # A raw user id resolves to the same actor (documented "user-or-actor-uuid").
    assert service.resolve_reference(ctx, user.id).id == actor.id


def test_resolve_reference_unknown_id_raises(tenant: Tenant) -> None:
    service = ActorService()
    with pytest.raises(NotFoundError):
        service.resolve_reference(_ctx(tenant_id=tenant.id), uuid4())


# ---------------------------------------------------------------------------
# validate_actor_value
# ---------------------------------------------------------------------------


def test_validate_actor_value_accepts_a_user_by_actor_id(
    tenant: Tenant, user: User
) -> None:
    service = ActorService()
    ctx = _ctx(tenant_id=tenant.id)
    actor = service.get_or_create_for_user(ctx, user.id)

    resolved = service.validate_actor_value(
        ctx, {"kind": "user", "id": str(actor.id)}, multiple=False, allow_external=False
    )

    assert [a.id for a in resolved] == [actor.id]


def test_validate_actor_value_rejects_external_when_disallowed(tenant: Tenant) -> None:
    service = ActorService()
    with pytest.raises(ValidationError):
        service.validate_actor_value(
            _ctx(tenant_id=tenant.id),
            {"kind": "external", "name": "External Person"},
            multiple=False,
            allow_external=False,
        )


def test_validate_actor_value_multiple_resolves_every_item(
    tenant: Tenant, user: User
) -> None:
    service = ActorService()
    ctx = _ctx(tenant_id=tenant.id)
    actor = service.get_or_create_for_user(ctx, user.id)

    resolved = service.validate_actor_value(
        ctx,
        {
            "multiple": True,
            "items": [
                {"kind": "user", "id": str(actor.id)},
                {"kind": "external", "name": "Frau Mueller (TUEV)"},
            ],
        },
        multiple=True,
        allow_external=True,
    )

    assert [a.kind for a in resolved] == [Actor.Kind.USER, Actor.Kind.EXTERNAL]


def test_validate_actor_value_rejects_unknown_user(tenant: Tenant) -> None:
    service = ActorService()
    with pytest.raises(NotFoundError):
        service.validate_actor_value(
            _ctx(tenant_id=tenant.id),
            {"kind": "user", "id": str(uuid4())},
            multiple=False,
            allow_external=False,
        )


# ---------------------------------------------------------------------------
# Gateway adapter round-trip (spec sections 3/4)
# ---------------------------------------------------------------------------


class _StubDefinitions:
    """Definition facade that returns one fixed owner/priority definition."""

    def __init__(self, attributes: list[dict[str, Any]]) -> None:
        self._attributes = attributes

    def resolve(self, ctx: Any, item_type: str, workspace_id: Any) -> dict[str, Any]:
        return {
            "item_type": item_type,
            "preset": "standard",
            "attributes": list(self._attributes),
            "sections": [{"name": "general", "order": 0, "visible": True, "layout": "full"}],
        }

    def validate_artifact_fields(self, *args: Any, **kwargs: Any) -> None:
        return None


def _actor_attribute(name: str, **over: Any) -> dict[str, Any]:
    base = {
        "name": name,
        "kind": "core",
        "type": "actor",
        "section": "general",
        "order": 0,
        "visible": True,
        "editable": True,
        "required": False,
        "label": {"de": name, "en": name},
        "options": [],
        "validation": {},
        "widget_key": None,
        "fields": [],
        "multiple": False,
        "allow_external": False,
    }
    base.update(over)
    return base


def test_gateway_owner_round_trip_uses_the_actor_wire_form(
    tenant: Tenant, user: User, workspace: Workspace
) -> None:
    service = ActorService()
    ctx = _ctx(tenant_id=tenant.id)
    actor = service.get_or_create_for_user(ctx, user.id)

    artifact = Artifact.unscoped.create(
        tenant=tenant,
        workspace=workspace,
        artifact_type="Requirement",
    )
    gateway = ArtifactAttributeGateway(
        definitions=_StubDefinitions([_actor_attribute("owner")])  # type: ignore[arg-type]
    )

    values = AttributeValues(core={"owner": {"kind": "user", "id": str(actor.id)}})
    result = gateway.write(ctx, "Requirement", artifact, values)

    artifact.refresh_from_db()
    assert artifact.owner_id == actor.id
    assert result.core["owner"] == {"kind": "user", "id": str(actor.id)}


def test_gateway_external_owner_is_created_on_write(
    tenant: Tenant, workspace: Workspace
) -> None:
    ctx = _ctx(tenant_id=tenant.id)
    artifact = Artifact.unscoped.create(
        tenant=tenant,
        workspace=workspace,
        artifact_type="Requirement",
    )
    gateway = ArtifactAttributeGateway(
        definitions=_StubDefinitions(  # type: ignore[arg-type]
            [_actor_attribute("reporter", allow_external=True)]
        )
    )

    result = gateway.write(
        ctx,
        "Requirement",
        artifact,
        AttributeValues(core={"reporter": {"kind": "external", "name": "TUEV Pruefer"}}),
    )

    artifact.refresh_from_db()
    assert artifact.reporter is not None
    assert artifact.reporter.kind == Actor.Kind.EXTERNAL
    assert result.core["reporter"] == {"kind": "external", "name": "TUEV Pruefer"}
