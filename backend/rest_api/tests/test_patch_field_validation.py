"""PATCH payload validation for workflow-backed entity ViewSets.

Covers two related regressions in the shared
``WorkflowTransitionsMixin._validate_patch_payload`` seam:

* **#263 (critical, data loss).** The UI detail panels resend the whole form,
  including the read-only ``status`` mirror. The previous guard rejected *any*
  PATCH carrying ``status`` with HTTP 400, so every other field in the same
  request — the description the user actually typed — was discarded. A PATCH
  that carries an *unchanged* status must therefore be accepted and the
  remaining fields persisted.

* **#269 / finding 5 (silent ignore + version inflation).** Unknown fields and
  protected fields (``workspace_id``, ``is_admin``, ...) were dropped by DRF
  without a word, yet the request still bumped ``version``. They must now fail
  with a field-level 400 and leave the entity untouched.

Real DB + JWT throughout (no mocked services): the bugs live in the interaction
between the view, the serializer and the service, which mocks would hide.
"""
from __future__ import annotations

from typing import Any

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace

_SECRET = "test-secret-not-a-real-key"

_JWT_OVERRIDES = dict(
    AUTH_JWT_SECRET=_SECRET,
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
)


@pytest.fixture
def patch_env(db):
    """Tenant + admin + two workspaces (the second one is the illegal move target)."""
    tenant = Tenant.objects.create(name="PV T", slug="pv-t", is_active=True)
    admin = User.objects.create(username="pvadmin", email="pvadmin@t.test", tenant=tenant)
    admin.set_password("pvpass123")
    admin.save(update_fields=["password"])
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="PV WS", preset={"name": "standard"}
        )
        other_workspace = Workspace.objects.create(
            tenant=tenant, name="PV WS 2", preset={"name": "standard"}
        )
        for ws in (workspace, other_workspace):
            UserRole.objects.create(
                tenant=tenant, user=admin, workspace=ws, role=ROLE_ADMIN
            )
        yield {
            "tenant": tenant,
            "workspace": workspace,
            "other_workspace": other_workspace,
        }
    finally:
        clear_request_tenant()


def _client(patch_env: dict) -> APIClient:
    client = APIClient()
    resp = client.post(
        "/api/v1/auth/login/",
        {"username": "pvadmin", "password": "pvpass123"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.json()['token']}")
    return client


def _create_need(client: APIClient, workspace_id: Any) -> dict:
    resp = client.post(
        "/api/v1/needs/",
        {
            "workspace_id": str(workspace_id),
            "title": "PATCH validation need",
            "description": "original description",
        },
        format="json",
    )
    assert resp.status_code == 201, resp.content
    return resp.json()


def _field_errors(payload: dict) -> set[str]:
    """Collect the field names carried by a standard error envelope."""
    details = payload.get("error", {}).get("details") or []
    return {d.get("field") for d in details if isinstance(d, dict)}


# ---------------------------------------------------------------------------
# #263 — a PATCH carrying an unchanged status must not discard the other fields
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_patch_with_unchanged_status_persists_other_fields(patch_env):
    """#263: the critical data-loss case — status echoed back verbatim."""
    client = _client(patch_env)
    need = _create_need(client, patch_env["workspace"].id)

    resp = client.patch(
        f"/api/v1/needs/{need['id']}/",
        {"description": "PERSISTENZ-TEST-2", "status": need["status"]},
        format="json",
    )

    assert resp.status_code == 200, resp.content
    assert resp.json()["description"] == "PERSISTENZ-TEST-2"
    # ... and it is actually persisted, not just echoed by the serializer.
    fresh = client.get(f"/api/v1/needs/{need['id']}/")
    assert fresh.json()["description"] == "PERSISTENZ-TEST-2"
    assert fresh.json()["status"] == need["status"]


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_patch_with_changed_status_is_rejected_field_level(patch_env):
    """A real status change still has to go through POST .../transitions/."""
    client = _client(patch_env)
    need = _create_need(client, patch_env["workspace"].id)

    resp = client.patch(
        f"/api/v1/needs/{need['id']}/",
        {"description": "should not be saved", "status": "approved"},
        format="json",
    )

    assert resp.status_code == 400, resp.content
    assert "status" in _field_errors(resp.json())
    # The rejection is atomic: nothing was written.
    fresh = client.get(f"/api/v1/needs/{need['id']}/")
    assert fresh.json()["description"] == "original description"


# ---------------------------------------------------------------------------
# #269 finding 5 — unknown / protected fields
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_patch_unknown_field_is_rejected_and_does_not_bump_version(patch_env):
    """#269: ``nonexistent_field_xyz`` used to return 200 and inflate version."""
    client = _client(patch_env)
    need = _create_need(client, patch_env["workspace"].id)
    version_before = need["version"]

    resp = client.patch(
        f"/api/v1/needs/{need['id']}/",
        {"nonexistent_field_xyz": "hallo"},
        format="json",
    )

    assert resp.status_code == 400, resp.content
    assert "nonexistent_field_xyz" in _field_errors(resp.json())
    fresh = client.get(f"/api/v1/needs/{need['id']}/")
    assert fresh.json()["version"] == version_before


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_patch_workspace_id_move_is_rejected(patch_env):
    """#269: a cross-workspace move must not be silently swallowed."""
    client = _client(patch_env)
    need = _create_need(client, patch_env["workspace"].id)

    resp = client.patch(
        f"/api/v1/needs/{need['id']}/",
        {"workspace_id": str(patch_env["other_workspace"].id)},
        format="json",
    )

    assert resp.status_code == 400, resp.content
    assert "workspace_id" in _field_errors(resp.json())
    fresh = client.get(f"/api/v1/needs/{need['id']}/")
    assert fresh.json()["workspace_id"] == str(patch_env["workspace"].id)


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_patch_is_admin_mass_assignment_is_rejected(patch_env):
    """#269: privilege-shaped keys must fail loudly, not be dropped."""
    client = _client(patch_env)
    need = _create_need(client, patch_env["workspace"].id)

    resp = client.patch(
        f"/api/v1/needs/{need['id']}/", {"is_admin": True}, format="json"
    )

    assert resp.status_code == 400, resp.content
    assert "is_admin" in _field_errors(resp.json())


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_patch_readonly_version_is_rejected(patch_env):
    """``version`` is server-owned; a client-supplied value must not be ignored."""
    client = _client(patch_env)
    need = _create_need(client, patch_env["workspace"].id)

    resp = client.patch(
        f"/api/v1/needs/{need['id']}/", {"version": 99}, format="json"
    )

    assert resp.status_code == 400, resp.content
    assert "version" in _field_errors(resp.json())


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_patch_glossary_with_wrong_field_name_is_rejected(patch_env):
    """#269: glossary uses ``term``; a ``title`` PATCH returned a hollow 200."""
    client = _client(patch_env)
    created = client.post(
        "/api/v1/glossary/",
        {
            "workspace_id": str(patch_env["workspace"].id),
            "term": "QA-Term",
            "definition": "original definition",
        },
        format="json",
    )
    assert created.status_code == 201, created.content
    term = created.json()

    resp = client.patch(
        f"/api/v1/glossary/{term['id']}/", {"title": "wrong field"}, format="json"
    )

    assert resp.status_code == 400, resp.content
    assert "title" in _field_errors(resp.json())
    fresh = client.get(f"/api/v1/glossary/{term['id']}/")
    assert fresh.json()["term"] == "QA-Term"


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_patch_status_on_entity_without_status_field_points_at_transitions(patch_env):
    """Glossary is workflow-backed but exposes no ``status``.

    The error must still name the transitions endpoint rather than claim the
    field does not exist — status *is* a concept here, it is just not writable.
    """
    client = _client(patch_env)
    created = client.post(
        "/api/v1/glossary/",
        {
            "workspace_id": str(patch_env["workspace"].id),
            "term": "Status-Term",
            "definition": "d",
        },
        format="json",
    )
    assert created.status_code == 201, created.content

    resp = client.patch(
        f"/api/v1/glossary/{created.json()['id']}/",
        {"status": "approved"},
        format="json",
    )

    assert resp.status_code == 400, resp.content
    assert "status" in _field_errors(resp.json())
    assert "transitions" in resp.json()["error"]["message"]


# ---------------------------------------------------------------------------
# Guard rails — the legitimate payloads the UI sends must keep working
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_patch_accepts_the_payload_the_ui_sends(patch_env):
    """custom_fields / change_reason are part of every UI save and stay valid."""
    client = _client(patch_env)
    need = _create_need(client, patch_env["workspace"].id)

    resp = client.patch(
        f"/api/v1/needs/{need['id']}/",
        {
            "title": "UI title",
            "description": "UI description",
            "category": "",
            "moscow_priority": None,
            "custom_fields": {},
            "change_reason": "edited via UI",
        },
        format="json",
    )

    assert resp.status_code == 200, resp.content
    assert resp.json()["title"] == "UI title"


# ---------------------------------------------------------------------------
# #269 finding 5 — ``version`` is a change counter, not a request counter
#
# Rejecting unknown/protected keys removes the *reported* repro, but a PATCH
# that re-sends a known field with its current value still reached the service.
# The bump is now gated on a real value change in the service layer
# (application.artifact_service.has_field_changes).
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_patch_resending_identical_values_does_not_bump_version(patch_env):
    """A no-op PATCH must leave ``version`` alone.

    The UI detail panels resend the whole form on every save, so re-sending
    unchanged values is the common case, not an edge case. Bumping ``version``
    for it made the baseline diff engine report revisions between identical
    snapshots.
    """
    client = _client(patch_env)
    need = _create_need(client, patch_env["workspace"].id)
    version_before = need["version"]

    resp = client.patch(
        f"/api/v1/needs/{need['id']}/",
        {"title": need["title"], "description": need["description"]},
        format="json",
    )

    assert resp.status_code == 200, resp.content
    assert resp.json()["version"] == version_before
    fresh = client.get(f"/api/v1/needs/{need['id']}/")
    assert fresh.json()["version"] == version_before


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_patch_with_a_real_change_still_bumps_version(patch_env):
    """The counterpart guard: gating must not disable versioning altogether."""
    client = _client(patch_env)
    need = _create_need(client, patch_env["workspace"].id)
    version_before = need["version"]

    resp = client.patch(
        f"/api/v1/needs/{need['id']}/",
        {"description": "genuinely different"},
        format="json",
    )

    assert resp.status_code == 200, resp.content
    fresh = client.get(f"/api/v1/needs/{need['id']}/")
    assert fresh.json()["version"] == version_before + 1
    assert fresh.json()["description"] == "genuinely different"


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_patch_status_echo_alone_does_not_bump_version(patch_env):
    """A status-only echo is accepted-and-ignored (#263), so it changes nothing.

    Without the service-level gate this slipped past the payload validation and
    still incremented ``version``.
    """
    client = _client(patch_env)
    need = _create_need(client, patch_env["workspace"].id)
    version_before = need["version"]

    resp = client.patch(
        f"/api/v1/needs/{need['id']}/",
        {"status": need["status"]},
        format="json",
    )

    assert resp.status_code == 200, resp.content
    fresh = client.get(f"/api/v1/needs/{need['id']}/")
    assert fresh.json()["version"] == version_before
