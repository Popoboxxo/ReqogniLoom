"""#915 / #916 — read-only and unknown fields fail loudly, never silently.

Two related REST contract bugs, both of the same failure class (a request that
*looks* accepted but does nothing):

**#915 — read-only ``status`` on Requirement PATCH.**
``PATCH /api/v1/requirements/{id}/ {"status": "approved"}`` answered **200** and
changed nothing. ``status`` is workflow-managed and read-only on every artifact
serializer; the deliberate write path is
``POST /api/v1/<entity>/{pk}/transitions/``. The shared guard
(``WorkflowTransitionsMixin._validate_patch_payload``) already refuses a
*differing* status with a field-level 400 pointing at that endpoint — but
``RequirementViewSet._current_status`` read the current state off a ``status``
attribute the persistence row no longer carries (Datenmodell-Konsolidierung
Task 12 dropped the column). It therefore returned ``None`` for every
requirement, which the guard reads as "cannot tell an echo from a change" and
falls back to accepting-and-ignoring the field.

The pinned contract for a known-but-read-only field such as ``status``:

* a **differing** value → **400** naming ``status`` and pointing at
  ``POST .../transitions/`` (never a silent 200); the request is atomic, nothing
  else in the payload is written;
* an **unchanged echo** → **200** and the rest of the payload is saved. This is
  the #263 contract: the UI detail panels resend the whole form, and discarding
  the user's edit because it echoes the read-only status was the worse bug.
* a protected identity field (``id``/``uid``) → **400** naming the field (the
  existing #269 behaviour, re-asserted here so the two rules stay consistent).

**#916 — unknown request fields.**
A key no declared field accepts used to be dropped by DRF while the request
still answered 201/200. :class:`rest_api.serializers.UnknownFieldRejectionMixin`
(#851) closed that for the artifact serializers. These tests pin the remaining
gap on the hand-rolled ``ApiKeyViewSet.create``: ``agent_identity`` (the field
does not exist — ``principal_type``/``agent_label`` do) silently produced a
``user`` principal. A field the endpoint does not understand is now a 400 that
names it.
"""
from __future__ import annotations

from typing import Any

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace

_SECRET = "jwt-signing-key-placeholder"

_JWT_OVERRIDES = dict(
    AUTH_JWT_SECRET=_SECRET,
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
)


@pytest.fixture
def strict_env(db):
    """Tenant + admin + one standard workspace (the same shape as #269's env)."""
    tenant = Tenant.objects.create(name="FS T", slug="fs-t", is_active=True)
    admin = User.objects.create(username="fsadmin", email="fsadmin@t.test", tenant=tenant)
    admin.set_password("fspass123")
    admin.save(update_fields=["password"])
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="FS WS", preset={"name": "standard"}
        )
        UserRole.objects.create(
            tenant=tenant, user=admin, workspace=workspace, role=ROLE_ADMIN
        )
        yield {"tenant": tenant, "workspace": workspace}
    finally:
        clear_request_tenant()


def _client(env: dict) -> APIClient:
    client = APIClient()
    resp = client.post(
        "/api/v1/auth/login/",
        {"username": "fsadmin", "password": "fspass123"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    token = resp.json()["token"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def _create_requirement(client: APIClient, workspace_id: Any) -> dict:
    resp = client.post(
        "/api/v1/requirements/",
        {
            "workspace_id": str(workspace_id),
            "title": "Field-strictness requirement",
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
# #915 — read-only ``status`` must not be silently dropped
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_requirement_patch_with_changed_status_is_rejected(strict_env):
    """A real status change is a 400 naming ``status`` — not a hollow 200 (#915).

    ``status`` is workflow-managed: it only moves through
    ``POST .../transitions/``. The response must name the field and point at
    that path instead of confirming a change that never happened.
    """
    client = _client(strict_env)
    requirement = _create_requirement(client, strict_env["workspace"].id)

    resp = client.patch(
        f"/api/v1/requirements/{requirement['id']}/",
        {"status": "approved", "change_reason": "confirm via REST"},
        format="json",
    )

    assert resp.status_code == 400, resp.content
    assert "status" in _field_errors(resp.json())
    assert "transitions" in resp.json()["error"]["message"]

    # The rejection is atomic and the lifecycle state is untouched.
    fresh = client.get(f"/api/v1/requirements/{requirement['id']}/")
    assert fresh.json()["status"] == requirement["status"]


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_requirement_patch_with_unchanged_status_echo_is_accepted(strict_env):
    """#263 is preserved: an unchanged ``status`` echo still saves the edit.

    Without this the strict rule above would reintroduce the data loss #263
    fixed — the UI resends the whole form, so refusing the echo would throw
    away the description the user actually changed.
    """
    client = _client(strict_env)
    requirement = _create_requirement(client, strict_env["workspace"].id)

    resp = client.patch(
        f"/api/v1/requirements/{requirement['id']}/",
        {
            "description": "edited while echoing status",
            "status": requirement["status"],
            "change_reason": "UI resend",
        },
        format="json",
    )

    assert resp.status_code == 200, resp.content
    assert resp.json()["description"] == "edited while echoing status"
    assert resp.json()["status"] == requirement["status"]
    fresh = client.get(f"/api/v1/requirements/{requirement['id']}/")
    assert fresh.json()["description"] == "edited while echoing status"


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_requirement_patch_protected_identity_fields_are_rejected(strict_env):
    """``id``/``uid`` stay 400-naming-the-field (#269) — the same contract.

    Re-asserted next to the ``status`` rule so the two cannot drift apart: both
    read-only fields are refused explicitly instead of being dropped.
    """
    client = _client(strict_env)
    requirement = _create_requirement(client, strict_env["workspace"].id)

    for field, value in (("id", "00000000-0000-0000-0000-000000000001"), ("uid", "REQ-9999")):
        resp = client.patch(
            f"/api/v1/requirements/{requirement['id']}/",
            {field: value},
            format="json",
        )
        assert resp.status_code == 400, (field, resp.content)
        assert field in _field_errors(resp.json()), (field, resp.content)


# ---------------------------------------------------------------------------
# #916 — unknown request fields must be rejected on both write paths
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_requirement_create_with_unknown_field_is_rejected(strict_env):
    """#916 case 2: the artifact serializer path already refuses it — pinned."""
    client = _client(strict_env)

    resp = client.post(
        "/api/v1/requirements/",
        {
            "workspace_id": str(strict_env["workspace"].id),
            "title": "unknown field on create",
            "not_a_requirement_field": "not a requirement field",
        },
        format="json",
    )

    assert resp.status_code == 400, resp.content
    assert "not_a_requirement_field" in _field_errors(resp.json())


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_requirement_patch_with_unknown_field_is_rejected(strict_env):
    """#916 case 2 on the update path: the key is named, nothing is written."""
    client = _client(strict_env)
    requirement = _create_requirement(client, strict_env["workspace"].id)

    resp = client.patch(
        f"/api/v1/requirements/{requirement['id']}/",
        {"not_a_requirement_field": "not a requirement field"},
        format="json",
    )

    assert resp.status_code == 400, resp.content
    assert "not_a_requirement_field" in _field_errors(resp.json())


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_api_key_create_with_unknown_field_is_rejected(strict_env):
    """#916 case 1: ``agent_identity`` must not silently yield a ``user`` key.

    The field does not exist (``principal_type``/``agent_label`` are the real
    ones). Before the fix the request answered 201 and created a ``user``
    principal — a security-relevant silent default.
    """
    client = _client(strict_env)

    resp = client.post(
        "/api/v1/api-keys/",
        {
            "name": "qa-unknown-field",
            "agent_identity": "x",
            "principal_type": "user",
        },
        format="json",
    )

    assert resp.status_code == 400, resp.content
    assert "agent_identity" in _field_errors(resp.json())


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_api_key_create_with_supported_payload_still_returns_201(strict_env):
    """Positive control: every real API-key field keeps working."""
    client = _client(strict_env)

    resp = client.post(
        "/api/v1/api-keys/",
        {
            "name": "qa-supported-fields",
            "principal_type": "agent",
            "agent_label": "qa-agent",
            "scope": "read",
        },
        format="json",
    )

    assert resp.status_code == 201, resp.content
    assert resp.json()["principal_type"] == "agent"
    assert resp.json()["agent_label"] == "qa-agent"
