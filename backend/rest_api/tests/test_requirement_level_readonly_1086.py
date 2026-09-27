"""ADR-005 / #1086 — ``Requirement.level`` and ``parent_id`` over REST.

The wave makes ``level`` a **derived, read-only** field and fixes the
``parent_id`` silent drop. Both are REST contract changes, and both are the
same failure class: a request that *looks* accepted and does nothing. So the
tests here pin three things per field:

* a client-sent value is **refused with a field-level 4xx**, never silently
  dropped (the defect being removed);
* an unchanged **echo** is accepted, so a detail panel that resends the whole
  form keeps the user's other edits — the #263 contract that ``status``
  established, and reusing it for ``level`` rather than inventing a second
  rule;
* the derived value is reported truthfully in the response body, including
  right after a create and right after a re-parent.

Extended-preset coverage lives here too: with ``level`` no longer writable, a
``mandatory`` flag for it in the stage matrix would 400 **every** create in that
preset with a message the client cannot act on.
"""
from __future__ import annotations

from typing import Any

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, Requirement, Tenant, User, Workspace

_SECRET = "test-secret-not-a-real-key"

_JWT_OVERRIDES = dict(
    AUTH_JWT_SECRET=_SECRET,
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
)


def _env(preset: str = "standard"):
    """Tenant + admin + one workspace on *preset*."""

    def _fixture(db):
        tenant = Tenant.objects.create(
            name=f"L1086 {preset}", slug=f"l1086-{preset}", is_active=True
        )
        admin = User.objects.create(
            username=f"l1086admin-{preset}",
            email=f"l1086-{preset}@t.test",
            tenant=tenant,
        )
        admin.set_password("l1086pass123")
        admin.save(update_fields=["password"])
        set_request_tenant(tenant.id)
        try:
            workspace = Workspace.objects.create(
                tenant=tenant, name=f"L1086 WS {preset}", preset={"name": preset}
            )
            UserRole.objects.create(
                tenant=tenant, user=admin, workspace=workspace, role=ROLE_ADMIN
            )
            yield {
                "tenant": tenant,
                "workspace": workspace,
                "username": admin.username,
            }
        finally:
            clear_request_tenant()

    return _fixture


standard_env = pytest.fixture(_env("standard"))
extended_env = pytest.fixture(_env("extended"))


def _client(env: dict) -> APIClient:
    client = APIClient()
    resp = client.post(
        "/api/v1/auth/login/",
        {"username": env["username"], "password": "l1086pass123"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.json()['token']}")
    return client


def _create(
    client: APIClient, workspace_id: Any, title: str = "Req", **extra
) -> dict:
    resp = client.post(
        "/api/v1/requirements/",
        {"workspace_id": str(workspace_id), "title": title, **extra},
        format="json",
    )
    assert resp.status_code == 201, resp.content
    return resp.json()


def _field_errors(body: dict) -> set[str]:
    details = body.get("error", {}).get("details", [])
    return {d.get("field") for d in details if isinstance(d, dict)}


def _stored_level(env: dict, requirement_id: str) -> int | None:
    return Requirement.unscoped.get(id=requirement_id).level


# ---------------------------------------------------------------------------
# level is read-only
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_create_with_a_level_is_refused_with_a_field_error(standard_env):
    client = _client(standard_env)
    resp = client.post(
        "/api/v1/requirements/",
        {
            "workspace_id": str(standard_env["workspace"].id),
            "title": "Req with a level",
            "level": 3,
        },
        format="json",
    )
    assert resp.status_code == 400, resp.content
    assert "level" in _field_errors(resp.json())
    assert "derived" in resp.json()["error"]["message"].lower()


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_create_rejection_is_atomic(standard_env):
    """Nothing is written when the derived field is refused."""
    client = _client(standard_env)
    before = Requirement.unscoped.filter(tenant_id=standard_env["tenant"].id).count()
    client.post(
        "/api/v1/requirements/",
        {
            "workspace_id": str(standard_env["workspace"].id),
            "title": "Never created",
            "level": 1,
        },
        format="json",
    )
    after = Requirement.unscoped.filter(tenant_id=standard_env["tenant"].id).count()
    assert after == before


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_patch_with_a_different_level_is_refused(standard_env):
    client = _client(standard_env)
    requirement = _create(client, standard_env["workspace"].id)
    assert requirement["level"] == 1, "a root is the top of the cascade"

    resp = client.patch(
        f"/api/v1/requirements/{requirement['id']}/",
        {"level": 4},
        format="json",
    )
    assert resp.status_code == 400, resp.content
    assert "level" in _field_errors(resp.json())
    assert _stored_level(standard_env, requirement["id"]) == 1


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_patch_with_a_different_level_writes_nothing_else(standard_env):
    """The rejection is atomic: the rest of the payload must not land."""
    client = _client(standard_env)
    requirement = _create(client, standard_env["workspace"].id)

    client.patch(
        f"/api/v1/requirements/{requirement['id']}/",
        {"description": "should not be saved", "level": 2},
        format="json",
    )
    fresh = client.get(f"/api/v1/requirements/{requirement['id']}/").json()
    assert fresh["description"] == ""
    assert fresh["level"] == 1


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_patch_with_an_unchanged_level_echo_is_accepted(standard_env):
    """#263's contract, reused: an echoed read-only field must not cost the
    user the rest of their edit. The detail panels resend the whole form."""
    client = _client(standard_env)
    requirement = _create(client, standard_env["workspace"].id)

    resp = client.patch(
        f"/api/v1/requirements/{requirement['id']}/",
        {"description": "PERSISTENZ", "level": requirement["level"]},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    fresh = client.get(f"/api/v1/requirements/{requirement['id']}/").json()
    assert fresh["description"] == "PERSISTENZ"
    assert fresh["level"] == 1


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_the_response_reports_the_derived_level(standard_env):
    """Response fidelity: a 201 must not claim ``level: null`` for a row whose
    derived level is 1. Same class of bug as #344 (``_dto_from_orm``)."""
    client = _client(standard_env)
    root = _create(client, standard_env["workspace"].id, "Root")
    assert root["level"] == 1

    child = _create(
        client,
        standard_env["workspace"].id,
        "Child",
        parent_id=root["artifact_id"],
    )
    assert child["level"] == 2
    assert client.get(f"/api/v1/requirements/{child['id']}/").json()["level"] == 2


# ---------------------------------------------------------------------------
# parent_id is applied, not discarded
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_patch_applies_parent_id(standard_env):
    """The AUC break this wave closes: a PATCH with ``parent_id`` used to
    answer 200 and move nothing."""
    client = _client(standard_env)
    root = _create(client, standard_env["workspace"].id, "Root")
    other = _create(client, standard_env["workspace"].id, "Other root")
    child = _create(
        client,
        standard_env["workspace"].id,
        "Child",
        parent_id=root["artifact_id"],
    )
    assert child["level"] == 2

    resp = client.patch(
        f"/api/v1/requirements/{child['id']}/",
        {"parent_id": other["artifact_id"]},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    assert resp.json()["parent_id"] == other["artifact_id"]
    assert _stored_level(standard_env, child["id"]) == 2, "still one below a root"


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_patch_reparent_reshifts_the_whole_subtree(standard_env):
    """A multi-level move: the moved node and everything below it follow."""
    client = _client(standard_env)
    deep_root = _create(client, standard_env["workspace"].id, "Deep root")
    mid = _create(
        client,
        standard_env["workspace"].id,
        "Mid",
        parent_id=deep_root["artifact_id"],
    )
    leaf = _create(
        client,
        standard_env["workspace"].id,
        "Leaf",
        parent_id=mid["artifact_id"],
    )
    assert [deep_root["level"], mid["level"], leaf["level"]] == [1, 2, 3]

    shallow_root = _create(client, standard_env["workspace"].id, "Shallow root")
    # Detach mid to the top of the cascade, then hang the leaf one level lower.
    resp = client.patch(
        f"/api/v1/requirements/{leaf['id']}/",
        {"parent_id": shallow_root["artifact_id"]},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    assert resp.json()["level"] == 2

    resp = client.patch(
        f"/api/v1/requirements/{mid['id']}/",
        {"parent_id": None},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    assert resp.json()["level"] == 1, "an explicit null detaches to the top"
    assert _stored_level(standard_env, leaf["id"]) == 2


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_patch_omitting_parent_id_leaves_the_hierarchy_alone(standard_env):
    client = _client(standard_env)
    root = _create(client, standard_env["workspace"].id, "Root")
    child = _create(
        client,
        standard_env["workspace"].id,
        "Child",
        parent_id=root["artifact_id"],
    )
    resp = client.patch(
        f"/api/v1/requirements/{child['id']}/",
        {"title": "Renamed only"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    assert resp.json()["parent_id"] == root["artifact_id"]
    assert resp.json()["level"] == 2


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_patch_parent_cycle_is_refused(standard_env):
    client = _client(standard_env)
    root = _create(client, standard_env["workspace"].id, "Root")
    child = _create(
        client,
        standard_env["workspace"].id,
        "Child",
        parent_id=root["artifact_id"],
    )
    resp = client.patch(
        f"/api/v1/requirements/{root['id']}/",
        {"parent_id": child["artifact_id"]},
        format="json",
    )
    assert resp.status_code == 400, resp.content
    assert client.get(f"/api/v1/requirements/{root['id']}/").json()["level"] == 1


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_patch_parent_from_another_workspace_is_refused(standard_env):
    client = _client(standard_env)
    mine = _create(client, standard_env["workspace"].id, "Mine")

    set_request_tenant(standard_env["tenant"].id)
    other_ws = Workspace.objects.create(
        tenant=standard_env["tenant"], name="Other", preset={"name": "standard"}
    )
    # Built at the ORM level: the admin has no role in the other workspace, and
    # this test is about the *re-parent* guard, not about RBAC.
    other_artifact = Artifact.objects.create(
        tenant=standard_env["tenant"],
        workspace=other_ws,
        artifact_type="Requirement",
    )
    theirs = Requirement.objects.create(
        tenant=standard_env["tenant"],
        artifact=other_artifact,
        workspace=other_ws,
        title="Theirs",
    )

    resp = client.patch(
        f"/api/v1/requirements/{mine['id']}/",
        {"parent_id": str(other_artifact.id)},
        format="json",
    )
    assert resp.status_code == 400, resp.content
    assert _stored_level(standard_env, mine["id"]) == 1
    assert theirs.artifact_id == other_artifact.id


# ---------------------------------------------------------------------------
# The extended preset must not demand a derived field
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_extended_preset_create_does_not_require_a_level(extended_env):
    """With ``level`` read-only, a ``mandatory`` flag for it would 400 *every*
    create in the extended preset with a message the client cannot act on."""
    client = _client(extended_env)
    requirement = _create(
        client,
        extended_env["workspace"].id,
        "Extended req",
        description="d",
        acceptance_criteria="ac",
        verification_method="Test",
        change_reason="initial",
    )
    assert requirement["level"] == 1


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_extended_preset_definition_marks_level_read_only(extended_env):
    """The attribute definition must not render an editable control for a
    derived field — a control whose save can never round-trip is exactly the
    class ``READ_ONLY_MODEL_FIELDS`` exists to close. Nor may it *demand* the
    field, which would 400 every extended create."""
    from django.core.management import call_command

    from attribute_definitions.workspace_definition_store import (
        WorkspaceAttributeDefinitionStore,
    )
    from persistence.tenancy import TenantContext

    tenant = extended_env["tenant"]
    workspace = extended_env["workspace"]
    TenantContext.set_tenant(tenant.id)
    try:
        call_command("bootstrap_attribute_definitions")
        definition = WorkspaceAttributeDefinitionStore().resolve(
            tenant.id, workspace.id, "Requirement", "extended"
        )
    finally:
        TenantContext.clear_tenant()
    level = next(
        attribute
        for attribute in definition.definition_json["attributes"]
        if attribute["name"] == "level"
    )
    assert level["editable"] is False
    assert level["stage_mandatory"] is False
    # ... but it is still rendered, because it is the only L4 filter the
    # TRACE-P5 / ARCH-003 / VERIF-P8 rules have.
    assert level["visible"] is True
