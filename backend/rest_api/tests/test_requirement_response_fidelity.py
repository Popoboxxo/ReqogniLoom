"""Requirement REST responses must report the values that are actually stored.

Issue #344. ``_dto_from_orm`` (``rest_api/views.py``) omitted ``type``,
``complexity_fibonacci`` and ``verification_method``. Since
``RequirementSerializer.type`` declares ``default='SyReq'``, DRF substituted
that default on *representation*, so every REST response claimed
``type: "SyReq"`` regardless of what the service had persisted — a silent lie
that the UI reads back into the edit form and echoes on the next save, thereby
reverting a real classification on an unrelated description edit.

Real DB + JWT (no mocked service): the defect lives in the view/serializer
seam, which a mocked service would hide.
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
def fidelity_env(db):
    """Tenant + admin + one standard-preset workspace."""
    tenant = Tenant.objects.create(name="RF T", slug="rf-t", is_active=True)
    admin = User.objects.create(username="rfadmin", email="rfadmin@t.test", tenant=tenant)
    admin.set_password("rfpass123")
    admin.save(update_fields=["password"])
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="RF WS", preset={"name": "standard"}
        )
        UserRole.objects.create(
            tenant=tenant, user=admin, workspace=workspace, role=ROLE_ADMIN
        )
        yield {"tenant": tenant, "workspace": workspace}
    finally:
        clear_request_tenant()


def _client(fidelity_env: dict) -> APIClient:
    client = APIClient()
    resp = client.post(
        "/api/v1/auth/login/",
        {"username": "rfadmin", "password": "rfpass123"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.json()['token']}")
    return client


def _create_requirement(client: APIClient, workspace_id: Any) -> dict:
    resp = client.post(
        "/api/v1/requirements/",
        {
            "workspace_id": str(workspace_id),
            "title": "Response fidelity requirement",
            "description": "original description",
        },
        format="json",
    )
    assert resp.status_code == 201, resp.content
    return resp.json()


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_patch_response_reports_the_stored_type(fidelity_env):
    """A changed ``type`` must be echoed back, not masked by the field default."""
    client = _client(fidelity_env)
    requirement = _create_requirement(client, fidelity_env["workspace"].id)

    resp = client.patch(
        f"/api/v1/requirements/{requirement['id']}/",
        {"type": "UseCase"},
        format="json",
    )

    assert resp.status_code == 200, resp.content
    assert resp.json()["type"] == "UseCase"


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_get_reports_the_stored_type(fidelity_env):
    """The same value must survive a fresh GET — the UI hydrates its form from it."""
    client = _client(fidelity_env)
    requirement = _create_requirement(client, fidelity_env["workspace"].id)
    client.patch(
        f"/api/v1/requirements/{requirement['id']}/",
        {"type": "FeatureReq"},
        format="json",
    )

    fresh = client.get(f"/api/v1/requirements/{requirement['id']}/")

    assert fresh.status_code == 200, fresh.content
    assert fresh.json()["type"] == "FeatureReq"


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_syreq_type_fields_are_reported(fidelity_env):
    """``complexity_fibonacci`` / ``verification_method`` were missing too.

    They are only rendered for ``type == 'SyReq'`` (serializer
    ``to_representation``), which is exactly the default type here.
    """
    client = _client(fidelity_env)
    requirement = _create_requirement(client, fidelity_env["workspace"].id)

    resp = client.patch(
        f"/api/v1/requirements/{requirement['id']}/",
        {"complexity_fibonacci": 8, "verification_method": "Analysis"},
        format="json",
    )

    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["complexity_fibonacci"] == 8
    assert body["verification_method"] == "Analysis"

    fresh = client.get(f"/api/v1/requirements/{requirement['id']}/").json()
    assert fresh["complexity_fibonacci"] == 8
    assert fresh["verification_method"] == "Analysis"


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_description_only_patch_does_not_revert_the_type(fidelity_env):
    """The end-to-end shape of #344: an unrelated edit must not undo the type.

    With the old response the UI read ``type: "SyReq"`` back into the form and
    echoed it on the next save, silently reverting the classification.
    """
    client = _client(fidelity_env)
    requirement = _create_requirement(client, fidelity_env["workspace"].id)
    client.patch(
        f"/api/v1/requirements/{requirement['id']}/",
        {"type": "UseCase"},
        format="json",
    )

    round_tripped = client.get(f"/api/v1/requirements/{requirement['id']}/").json()
    resp = client.patch(
        f"/api/v1/requirements/{requirement['id']}/",
        {"description": "edited elsewhere", "type": round_tripped["type"]},
        format="json",
    )

    assert resp.status_code == 200, resp.content
    fresh = client.get(f"/api/v1/requirements/{requirement['id']}/").json()
    assert fresh["description"] == "edited elsewhere"
    assert fresh["type"] == "UseCase"


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_demonstration_verification_method_round_trips(fidelity_env):
    """``RequirementSerializer`` omitted the model's 'Demonstration' choice.

    ``persistence.models.VerificationMethod`` (and migration 0041) has carried
    ``Demonstration`` all along, so a ReqIF-imported requirement using it 400'd
    on its next save because the serializer's hard-coded choice list stopped
    one value short of the model's.
    """
    client = _client(fidelity_env)
    requirement = _create_requirement(client, fidelity_env["workspace"].id)

    resp = client.patch(
        f"/api/v1/requirements/{requirement['id']}/",
        {"verification_method": "Demonstration"},
        format="json",
    )

    assert resp.status_code == 200, resp.content
    assert resp.json()["verification_method"] == "Demonstration"

    fresh = client.get(f"/api/v1/requirements/{requirement['id']}/").json()
    assert fresh["verification_method"] == "Demonstration"


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_unrelated_patch_does_not_clear_verification_method(fidelity_env):
    """Issue #409: an unrelated PATCH must not silently NULL out SE fields.

    A partial PATCH that omits ``verification_method``/``complexity_fibonacci``/
    ``level`` must leave the previously stored values untouched — omission from
    the payload means "unchanged", not "clear to NULL". The view used to
    forward ``data.get(...)`` unconditionally, which is ``None`` both when the
    field is genuinely absent and when the field was explicitly nulled,
    collapsing the two cases and wiping the stored value on every unrelated
    edit (e.g. a title-only PATCH).
    """
    client = _client(fidelity_env)
    requirement = _create_requirement(client, fidelity_env["workspace"].id)

    setup = client.patch(
        f"/api/v1/requirements/{requirement['id']}/",
        {
            "complexity_fibonacci": 5,
            "verification_method": "Test",
            "level": 1,
        },
        format="json",
    )
    assert setup.status_code == 200, setup.content
    assert setup.json()["complexity_fibonacci"] == 5
    assert setup.json()["verification_method"] == "Test"
    assert setup.json()["level"] == 1

    # Unrelated edit — does not mention the SE fields at all.
    resp = client.patch(
        f"/api/v1/requirements/{requirement['id']}/",
        {"title": "Renamed, unrelated to SE fields"},
        format="json",
    )

    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["title"] == "Renamed, unrelated to SE fields"
    assert body["complexity_fibonacci"] == 5
    assert body["verification_method"] == "Test"
    assert body["level"] == 1

    fresh = client.get(f"/api/v1/requirements/{requirement['id']}/").json()
    assert fresh["complexity_fibonacci"] == 5
    assert fresh["verification_method"] == "Test"
    assert fresh["level"] == 1


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_explicit_null_still_clears_verification_method(fidelity_env):
    """An explicit ``null`` must still clear the field (unlike omission)."""
    client = _client(fidelity_env)
    requirement = _create_requirement(client, fidelity_env["workspace"].id)
    client.patch(
        f"/api/v1/requirements/{requirement['id']}/",
        {"verification_method": "Test", "complexity_fibonacci": 3},
        format="json",
    )

    resp = client.patch(
        f"/api/v1/requirements/{requirement['id']}/",
        {"verification_method": None, "complexity_fibonacci": None},
        format="json",
    )

    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body.get("verification_method") is None
    assert body.get("complexity_fibonacci") is None


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_create_response_includes_atomicity_warning_for_bundled_title(fidelity_env):
    """#45: a title with 'and'/'or' surfaces a non-blocking hint on create."""
    client = _client(fidelity_env)
    resp = client.post(
        "/api/v1/requirements/",
        {
            "workspace_id": str(fidelity_env["workspace"].id),
            "title": "System shall handle login and logout",
        },
        format="json",
    )
    assert resp.status_code == 201, resp.content
    assert resp.json()["atomicity_warning"] == ["and"]


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_create_response_atomicity_warning_is_null_for_atomic_title(fidelity_env):
    """#45: an atomic title reports no warning, not an empty list."""
    client = _client(fidelity_env)
    resp = client.post(
        "/api/v1/requirements/",
        {
            "workspace_id": str(fidelity_env["workspace"].id),
            "title": "System shall authenticate a user",
        },
        format="json",
    )
    assert resp.status_code == 201, resp.content
    assert resp.json()["atomicity_warning"] is None


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_requirement_response_includes_suspect_field(fidelity_env):
    client = _client(fidelity_env)
    req = _create_requirement(client, fidelity_env["workspace"].id)
    assert "suspect" in req
    assert req["suspect"] is False


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_unknown_field_on_requirement_create_returns_400(fidelity_env):
    """R3 (P0 audit): unrecognised top-level keys must 400, not silently drop.

    Previously ``CustomFieldsSerializerMixin`` had no unknown-key check, so an
    unrecognised field (e.g. a typo) was simply absent from ``validated_data``
    and the create still returned 201 — indistinguishable from success.
    """
    client = _client(fidelity_env)
    resp = client.post(
        "/api/v1/requirements/",
        {
            "workspace_id": str(fidelity_env["workspace"].id),
            "title": "Unknown-field test",
            "not_a_real_field": "should 400",
        },
        format="json",
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    # Requirement create surfaces field-level validation errors under
    # ``error.details`` (``[{"field": ..., "errors": [...]}]``, see
    # RequirementViewSet.create), not in ``error.message`` — same envelope
    # shape pinned by test_testcase_unknown_field_580.py for TestCase.
    rejected_fields = {d["field"] for d in body["error"]["details"]}
    assert "not_a_real_field" in rejected_fields


def test_serializer_choices_match_the_model():
    """Guard the seam itself: no choice list may drift from the model again."""
    from persistence.models import VerificationMethod
    from rest_api.serializers import RequirementSerializer

    serializer_choices = set(
        RequirementSerializer().fields["verification_method"].choices
    )
    assert serializer_choices == set(VerificationMethod.values)
