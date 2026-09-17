"""``notify_assigned`` — the ``assigned`` producer (re-scope §5, from Task 11).

Its beam point is the attribute gateway, not an ``assignment.py``, so this file
pins the producer's own semantics: fires only on a *changed* owner, only for an
internal actor, never for the acting user, and never raises.
"""
from __future__ import annotations

import uuid

import pytest
from unittest.mock import patch

from application.models import Notification
from application.notification_service import notify_assigned
from auth_tenancy.context import AuthContext, AuthMethod
from persistence.models import Actor, Tenant, User

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(name="T", slug=f"t-{uuid.uuid4().hex[:8]}")


def _user(tenant: Tenant, label: str) -> User:
    return User.objects.create(
        username=f"{label}-{uuid.uuid4().hex[:6]}",
        email=f"{label}{uuid.uuid4().hex[:6]}@example.com",
        tenant=tenant,
    )


@pytest.fixture
def alice(tenant: Tenant) -> User:
    return _user(tenant, "alice")


@pytest.fixture
def bob(tenant: Tenant) -> User:
    return _user(tenant, "bob")


@pytest.fixture
def ctx(alice: User, tenant: Tenant) -> AuthContext:
    return AuthContext(
        user_id=alice.pk,
        tenant_id=tenant.pk,
        active_roles=("editor",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )


@pytest.fixture
def bob_actor(tenant: Tenant, bob: User) -> Actor:
    return Actor.unscoped.create(
        tenant=tenant, kind=Actor.Kind.USER, user=bob, display_name="Bob"
    )


def test_fires_for_a_changed_internal_owner(ctx, tenant, bob, bob_actor) -> None:
    written = notify_assigned(
        ctx=ctx,
        artifact_id=None,
        owner=bob_actor,
        previous_owner_id=None,
    )

    assert written == 1
    row = Notification.unscoped.get()
    assert row.user_id == bob.pk
    assert row.kind == Notification.KIND_ASSIGNED
    assert row.tenant_id == tenant.pk


def test_does_not_fire_when_the_owner_id_is_unchanged(ctx, bob_actor) -> None:
    written = notify_assigned(
        ctx=ctx,
        artifact_id=None,
        owner=bob_actor,
        previous_owner_id=bob_actor.id,
    )

    assert written == 0
    assert Notification.unscoped.count() == 0


def test_does_not_fire_for_an_external_actor(ctx, tenant) -> None:
    """An external placeholder has no login and therefore no notification feed."""
    external = Actor.unscoped.create(
        tenant=tenant, kind=Actor.Kind.EXTERNAL, display_name="Frau Mueller (TUEV)"
    )

    written = notify_assigned(
        ctx=ctx,
        artifact_id=None,
        owner=external,
        previous_owner_id=None,
    )

    assert written == 0
    assert Notification.unscoped.count() == 0


def test_does_not_fire_for_a_cleared_owner(ctx, bob_actor) -> None:
    """Removing the owner is not an assignment — only ``notify_assigned``'s
    caller reaches this with ``owner=None``, and nothing may be written."""
    written = notify_assigned(
        ctx=ctx,
        artifact_id=None,
        owner=None,
        previous_owner_id=bob_actor.id,
    )

    assert written == 0
    assert Notification.unscoped.count() == 0


def test_excludes_the_acting_user(ctx, tenant, alice) -> None:
    """Self-assignment is not a notification."""
    alice_actor = Actor.unscoped.create(
        tenant=tenant, kind=Actor.Kind.USER, user=alice, display_name="Alice"
    )

    written = notify_assigned(
        ctx=ctx,
        artifact_id=None,
        owner=alice_actor,
        previous_owner_id=None,
    )

    assert written == 0
    assert Notification.unscoped.count() == 0


def test_failure_is_swallowed_and_returns_zero(ctx, bob_actor) -> None:
    """The producer must never break the attribute write it reacts to."""
    with patch("application.notification_service.create_notifications") as create:
        create.side_effect = RuntimeError("notification store down")
        written = notify_assigned(
            ctx=ctx,
            artifact_id=None,
            owner=bob_actor,
            previous_owner_id=None,
        )

    assert written == 0


# ---------------------------------------------------------------------------
# The binding seam (§5): the attribute gateway, not an assignment.py
# ---------------------------------------------------------------------------


class _StubDefinitions:
    """Definition facade double: one visible, editable ``owner`` attribute."""

    def resolve(self, ctx, item_type, workspace_id):
        return {
            "item_type": item_type,
            "preset": "standard",
            "attributes": [
                {
                    "name": "owner",
                    "kind": "core",
                    "type": "actor",
                    "section": "general",
                    "order": 0,
                    "visible": True,
                    "editable": True,
                    "required": False,
                    "label": {"de": "owner", "en": "owner"},
                    "options": [],
                    "validation": {},
                    "widget_key": None,
                    "fields": [],
                    "multiple": False,
                    "allow_external": False,
                }
            ],
            "sections": [
                {"name": "general", "order": 0, "visible": True, "layout": "full"}
            ],
        }

    def validate_artifact_fields(self, *args, **kwargs) -> None:
        return None


def test_gateway_write_fires_the_assigned_notification_only_on_a_change(
    ctx, tenant, bob, bob_actor
) -> None:
    """Setting ``owner`` through the one gateway (REST + MCP share it) notifies
    the new owner once; re-writing the same owner does not notify again."""
    from application.artifact_attribute_gateway import ArtifactAttributeGateway, AttributeValues
    from persistence.models import Artifact, Workspace

    workspace = Workspace.unscoped.create(tenant=tenant, name="W")
    artifact = Artifact.unscoped.create(
        tenant=tenant, workspace=workspace, artifact_type="Requirement"
    )
    gateway = ArtifactAttributeGateway(definitions=_StubDefinitions())  # type: ignore[arg-type]
    payload = AttributeValues(core={"owner": {"kind": "user", "id": str(bob_actor.id)}})

    gateway.write(ctx, "Requirement", artifact, payload)
    artifact.refresh_from_db()
    assert artifact.owner_id == bob_actor.id

    rows = Notification.unscoped.filter(kind=Notification.KIND_ASSIGNED)
    assert rows.count() == 1
    assert rows.get().user_id == bob.pk

    # Same owner again: the cheap id comparison short-circuits, no second row.
    gateway.write(ctx, "Requirement", artifact, payload)
    assert Notification.unscoped.filter(kind=Notification.KIND_ASSIGNED).count() == 1
