"""GH-829 — TestCase PATCH must accept and apply the write-only
``change_reason`` field.

``TestCaseSerializer`` never declared ``change_reason``, so the unknown-key
guard added for #580 (``TestCaseSerializer.validate()``) rejected every PATCH
that carried the field with HTTP 400. Even if the key had slipped past that
guard, DRF would have silently dropped it from ``validated_data`` because it
was not a declared field — the same silent-drop class as the Adr/Risk/Issue
#290 bug, different entity.

These tests drive the real HTTP + serializer + service + audit stack on
purpose: the bug lived exactly in the seam between those layers, so any mock
would hide it.
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

_JWT_OVERRIDES = {
    "AUTH_JWT_SECRET": _SECRET,
    "AUTH_JWT_ISSUER": "reqflow",
    "AUTH_JWT_AUDIENCE": "reqflow-api",
    "AUTH_JWT_TTL_SECONDS": 3600,
}


@pytest.fixture
def tc_env(db):
    """Tenant + admin + one workspace on the standard preset."""
    tenant = Tenant.objects.create(name="TC829 T", slug="tc829-t", is_active=True)
    admin = User.objects.create(
        username="tc829admin", email="tc829admin@t.test", tenant=tenant
    )
    admin.set_password("tc829pass123")
    admin.save(update_fields=["password"])
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="TC829 WS", preset={"name": "standard"}
        )
        UserRole.objects.create(
            tenant=tenant, user=admin, workspace=workspace, role=ROLE_ADMIN
        )
        yield {"tenant": tenant, "workspace": workspace, "admin": admin}
    finally:
        clear_request_tenant()


def _client(tc_env: dict) -> APIClient:
    client = APIClient()
    resp = client.post(
        "/api/v1/auth/login/",
        {"username": "tc829admin", "password": "tc829pass123"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.json()['token']}")
    return client


def _create(client: APIClient, payload: dict[str, Any]) -> dict:
    resp = client.post("/api/v1/testcases/", payload, format="json")
    assert resp.status_code == 201, resp.content
    return resp.json()


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_patch_change_reason_is_accepted_and_audited(tc_env):
    """PATCH with change_reason → 200, and the reason reaches the audit trail."""
    from audit.models import AuditEntry

    client = _client(tc_env)
    created = _create(
        client,
        {"workspace_id": str(tc_env["workspace"].id), "title": "GH-829 TC"},
    )

    resp = client.patch(
        f"/api/v1/testcases/{created['id']}/",
        {"description": "edited", "change_reason": "because the test was wrong"},
        format="json",
    )

    assert resp.status_code == 200, resp.content
    entry = (
        AuditEntry.objects.filter(entity_id=created["id"], op="update")
        .order_by("-timestamp")
        .first()
    )
    assert entry is not None, "no audit entry recorded for the update"
    assert entry.change_reason == "because the test was wrong"


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_change_reason_is_declared_write_only_on_testcase_serializer(tc_env):
    """Root-cause guard: DRF must collect the field, and it must stay write-only."""
    from rest_api import serializers as s

    field = s.TestCaseSerializer().fields["change_reason"]
    assert field.write_only is True
    assert field.required is False


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_patch_unknown_field_is_still_rejected(tc_env):
    """The #580 guard must keep rejecting genuinely unknown keys with 400."""
    client = _client(tc_env)
    created = _create(
        client,
        {"workspace_id": str(tc_env["workspace"].id), "title": "GH-829 TC 2"},
    )

    resp = client.patch(
        f"/api/v1/testcases/{created['id']}/",
        {"acceptance_criteria": "Given/When/Then"},
        format="json",
    )

    assert resp.status_code == 400, resp.content
