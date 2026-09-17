"""Regression: Requirement creation must reject an empty/whitespace-only title.

leaf_id : COMP-RA-001 (RequirementViewSet)
req_id  : REQ-L2-RA-001 (POST /requirements/), REQ-L2-RA-009 (error envelope)

SYSTEMAUDIT_2026-08-18 §4 BUG-02: "Formular akzeptiert leeres Titel-Feld;
Backend legt den Datensatz trotzdem an." Root-cause verification (this file):
the REST create path (``RequirementSerializer`` -> ``title =
SanitizedCharField(max_length=500)``) already rejects a blank or
whitespace-only ``title`` with a 400 today, via DRF ``CharField``'s own
``allow_blank=False`` default (which fires *before*
``SanitizedCharField.to_internal_value`` ever runs) — no application code
change was needed for this endpoint. This file locks that guarantee in with
an explicit real-DB test, since none previously existed for this exact case
(only the "missing key entirely" and "HTML/JS-URI content" variants were
covered elsewhere).
"""
from __future__ import annotations

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Requirement, Tenant, User, Workspace

_SECRET = "test-secret-not-a-real-key-bug02"

_JWT_OVERRIDES = dict(
    AUTH_JWT_SECRET=_SECRET,
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
)


@pytest.fixture
def bug02_env(db):
    """Tenant + admin (password login capable) + one workspace."""
    tenant = Tenant.objects.create(name="Bug02 T", slug="bug02-t", is_active=True)
    admin = User.objects.create(
        username="bug02admin", email="bug02admin@t.test", tenant=tenant
    )
    admin.set_password("bug02pass123")
    admin.save(update_fields=["password"])

    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="Bug02 WS", preset={"name": "standard"}
        )
        from auth_tenancy.models import ROLE_ADMIN, UserRole

        UserRole.objects.create(
            tenant=tenant, user=admin, workspace=workspace, role=ROLE_ADMIN
        )
        yield {"tenant": tenant, "admin": admin, "workspace": workspace}
    finally:
        clear_request_tenant()


def _authed_client() -> APIClient:
    resp = APIClient().post(
        "/api/v1/auth/login/",
        {"username": "bug02admin", "password": "bug02pass123"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.json()['token']}")
    return client


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_create_with_empty_title_returns_400_and_creates_nothing(bug02_env):
    """BUG-02: ``title=""`` must be rejected — never persisted."""
    client = _authed_client()
    before = Requirement.objects.count()

    resp = client.post(
        "/api/v1/requirements/",
        {"workspace_id": str(bug02_env["workspace"].id), "title": ""},
        format="json",
    )

    assert resp.status_code == 400, resp.content
    body = resp.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    fields = {d["field"] for d in body["error"]["details"]}
    assert "title" in fields
    assert Requirement.objects.count() == before


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_create_with_whitespace_only_title_returns_400_and_creates_nothing(bug02_env):
    """BUG-02: ``title="   "`` (whitespace-only) must be rejected the same way
    as a genuinely empty string — DRF's ``trim_whitespace`` default folds it
    into the same blank check."""
    client = _authed_client()
    before = Requirement.objects.count()

    resp = client.post(
        "/api/v1/requirements/",
        {"workspace_id": str(bug02_env["workspace"].id), "title": "   "},
        format="json",
    )

    assert resp.status_code == 400, resp.content
    body = resp.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    fields = {d["field"] for d in body["error"]["details"]}
    assert "title" in fields
    assert Requirement.objects.count() == before


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_create_with_missing_title_key_returns_400_and_creates_nothing(bug02_env):
    """BUG-02 sibling case: the ``title`` key entirely absent from the
    payload — DRF's ``required=True`` default rejects this distinctly from
    the blank-string case (different error code, same outcome: no 201)."""
    client = _authed_client()
    before = Requirement.objects.count()

    resp = client.post(
        "/api/v1/requirements/",
        {"workspace_id": str(bug02_env["workspace"].id)},
        format="json",
    )

    assert resp.status_code == 400, resp.content
    assert Requirement.objects.count() == before


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_create_with_real_title_still_returns_201(bug02_env):
    """Control: the guard above must not collaterally reject real titles."""
    client = _authed_client()

    resp = client.post(
        "/api/v1/requirements/",
        {
            "workspace_id": str(bug02_env["workspace"].id),
            "title": "The system shall log all failed login attempts",
        },
        format="json",
    )

    assert resp.status_code == 201, resp.content
    assert resp.json()["title"] == "The system shall log all failed login attempts"
