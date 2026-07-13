"""
REQ-016 — Custom Fields (workspace-wide definitions + per-artifact values).

Covers:
- CustomFieldDefinition / CustomFieldValue model constraints.
- CustomFieldDefinition CRUD REST endpoints (admin-gated writes, open reads).
- Per-artifact value read/upsert with type + required validation and round-trip
  persistence across requests.

Uses the same JWT + APIClient pattern as test_llm_settings.py.
"""
from __future__ import annotations

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, ROLE_EDITOR, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import (
    Artifact,
    CustomFieldDefinition,
    CustomFieldValue,
    Tenant,
    User,
    Workspace,
)

_SECRET = "test-secret-not-a-real-key"

_JWT_OVERRIDES = dict(
    AUTH_JWT_SECRET=_SECRET,
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
)


@pytest.fixture
def cf_env(db):
    """A tenant with an admin, an editor, a workspace and one artifact."""
    tenant = Tenant.objects.create(name="CF T", slug="cf-t", is_active=True)
    admin = User.objects.create(username="cfadmin", email="cfadmin@t.test", tenant=tenant)
    admin.set_password("cfpass123")
    admin.save(update_fields=["password"])
    editor = User.objects.create(username="cfeditor", email="cfeditor@t.test", tenant=tenant)
    editor.set_password("cfpass123")
    editor.save(update_fields=["password"])
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="CF WS", preset={"name": "standard"}
        )
        artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="requirement"
        )
        UserRole.objects.create(
            tenant=tenant, user=admin, workspace=workspace, role=ROLE_ADMIN
        )
        UserRole.objects.create(
            tenant=tenant, user=editor, workspace=workspace, role=ROLE_EDITOR
        )
        yield {
            "tenant": tenant,
            "workspace": workspace,
            "artifact": artifact,
        }
    finally:
        clear_request_tenant()


def _login(client: APIClient, username: str) -> str:
    resp = client.post(
        "/api/v1/auth/login/",
        {"username": username, "password": "cfpass123"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    return resp.json()["token"]


def _auth(client: APIClient, token: str) -> None:
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")


def _admin_client(cf_env) -> APIClient:
    client = APIClient()
    _auth(client, _login(client, "cfadmin"))
    return client


def _defs_url(cf_env) -> str:
    return f"/api/v1/workspaces/{cf_env['workspace'].id}/custom-field-definitions/"


def _values_url(cf_env) -> str:
    return f"/api/v1/artifacts/{cf_env['artifact'].id}/custom-field-values/"


# ---------------------------------------------------------------------------
# Model constraints
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_definition_name_unique_per_workspace(cf_env):
    """Two definitions with the same name in one workspace violate the constraint."""
    from django.db import IntegrityError, transaction

    set_request_tenant(cf_env["tenant"].id)
    CustomFieldDefinition.objects.create(
        tenant=cf_env["tenant"], workspace=cf_env["workspace"], name="Priority"
    )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            CustomFieldDefinition.objects.create(
                tenant=cf_env["tenant"], workspace=cf_env["workspace"], name="Priority"
            )


@pytest.mark.django_db
def test_value_unique_per_definition_and_artifact(cf_env):
    """One artifact cannot hold two values for the same definition."""
    from django.db import IntegrityError, transaction

    set_request_tenant(cf_env["tenant"].id)
    definition = CustomFieldDefinition.objects.create(
        tenant=cf_env["tenant"], workspace=cf_env["workspace"], name="Owner"
    )
    CustomFieldValue.objects.create(
        tenant=cf_env["tenant"],
        definition=definition,
        artifact=cf_env["artifact"],
        value="alice",
    )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            CustomFieldValue.objects.create(
                tenant=cf_env["tenant"],
                definition=definition,
                artifact=cf_env["artifact"],
                value="bob",
            )


# ---------------------------------------------------------------------------
# Definition CRUD endpoints
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_admin_creates_text_definition(cf_env):
    client = _admin_client(cf_env)
    resp = client.post(
        _defs_url(cf_env),
        {"name": "Reviewer", "field_type": "text", "is_required": True},
        format="json",
    )
    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert body["name"] == "Reviewer"
    assert body["field_type"] == "text"
    assert body["is_required"] is True
    assert body["options"] == []


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_dropdown_definition_requires_options(cf_env):
    client = _admin_client(cf_env)
    resp = client.post(
        _defs_url(cf_env),
        {"name": "Severity", "field_type": "dropdown", "options": []},
        format="json",
    )
    assert resp.status_code == 400, resp.content


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_dropdown_definition_with_options_ok(cf_env):
    client = _admin_client(cf_env)
    resp = client.post(
        _defs_url(cf_env),
        {"name": "Severity", "field_type": "dropdown", "options": ["low", "high"]},
        format="json",
    )
    assert resp.status_code == 201, resp.content
    assert resp.json()["options"] == ["low", "high"]


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_non_admin_cannot_create_definition(cf_env):
    client = APIClient()
    _auth(client, _login(client, "cfeditor"))
    resp = client.post(
        _defs_url(cf_env), {"name": "Nope"}, format="json"
    )
    assert resp.status_code == 403, resp.content


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_list_definitions_ordered(cf_env):
    client = _admin_client(cf_env)
    client.post(_defs_url(cf_env), {"name": "Beta", "order": 2}, format="json")
    client.post(_defs_url(cf_env), {"name": "Alpha", "order": 1}, format="json")
    resp = client.get(_defs_url(cf_env))
    assert resp.status_code == 200
    names = [d["name"] for d in resp.json()]
    assert names == ["Alpha", "Beta"]


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_editor_can_list_definitions(cf_env):
    """Non-admins may read definitions (needed to render artifact forms)."""
    _admin_client(cf_env).post(_defs_url(cf_env), {"name": "Team"}, format="json")
    client = APIClient()
    _auth(client, _login(client, "cfeditor"))
    resp = client.get(_defs_url(cf_env))
    assert resp.status_code == 200
    assert len(resp.json()) == 1


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_patch_and_delete_definition(cf_env):
    client = _admin_client(cf_env)
    created = client.post(_defs_url(cf_env), {"name": "Temp"}, format="json").json()
    pk = created["id"]

    patch = client.patch(
        f"/api/v1/custom-field-definitions/{pk}/",
        {"name": "Renamed", "is_required": True},
        format="json",
    )
    assert patch.status_code == 200, patch.content
    assert patch.json()["name"] == "Renamed"
    assert patch.json()["is_required"] is True

    delete = client.delete(f"/api/v1/custom-field-definitions/{pk}/")
    assert delete.status_code == 204
    assert client.get(_defs_url(cf_env)).json() == []


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_duplicate_name_returns_400(cf_env):
    client = _admin_client(cf_env)
    client.post(_defs_url(cf_env), {"name": "Dup"}, format="json")
    resp = client.post(_defs_url(cf_env), {"name": "Dup"}, format="json")
    assert resp.status_code == 400, resp.content


# ---------------------------------------------------------------------------
# Value read/upsert endpoints
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_get_values_returns_definitions_with_empty_values(cf_env):
    client = _admin_client(cf_env)
    client.post(_defs_url(cf_env), {"name": "Owner"}, format="json")
    resp = client.get(_values_url(cf_env))
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["name"] == "Owner"
    assert rows[0]["value"] == ""
    assert rows[0]["id"] is None


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_put_values_persists_across_reload(cf_env):
    client = _admin_client(cf_env)
    definition = client.post(
        _defs_url(cf_env), {"name": "Owner"}, format="json"
    ).json()

    put = client.put(
        _values_url(cf_env),
        [{"definition_id": definition["id"], "value": "alice"}],
        format="json",
    )
    assert put.status_code == 200, put.content

    # Re-fetch via a fresh request: value must persist.
    reget = client.get(_values_url(cf_env))
    row = reget.json()[0]
    assert row["value"] == "alice"
    assert row["id"] is not None


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_put_required_empty_value_rejected(cf_env):
    client = _admin_client(cf_env)
    definition = client.post(
        _defs_url(cf_env), {"name": "Owner", "is_required": True}, format="json"
    ).json()
    resp = client.put(
        _values_url(cf_env),
        [{"definition_id": definition["id"], "value": ""}],
        format="json",
    )
    assert resp.status_code == 400, resp.content


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_put_number_value_validated(cf_env):
    client = _admin_client(cf_env)
    definition = client.post(
        _defs_url(cf_env), {"name": "Estimate", "field_type": "number"}, format="json"
    ).json()

    bad = client.put(
        _values_url(cf_env),
        [{"definition_id": definition["id"], "value": "not-a-number"}],
        format="json",
    )
    assert bad.status_code == 400, bad.content

    ok = client.put(
        _values_url(cf_env),
        [{"definition_id": definition["id"], "value": "42"}],
        format="json",
    )
    assert ok.status_code == 200, ok.content


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_put_dropdown_value_validated(cf_env):
    client = _admin_client(cf_env)
    definition = client.post(
        _defs_url(cf_env),
        {"name": "Severity", "field_type": "dropdown", "options": ["low", "high"]},
        format="json",
    ).json()

    bad = client.put(
        _values_url(cf_env),
        [{"definition_id": definition["id"], "value": "medium"}],
        format="json",
    )
    assert bad.status_code == 400, bad.content

    ok = client.put(
        _values_url(cf_env),
        [{"definition_id": definition["id"], "value": "high"}],
        format="json",
    )
    assert ok.status_code == 200, ok.content


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_put_empty_value_clears_existing(cf_env):
    client = _admin_client(cf_env)
    definition = client.post(
        _defs_url(cf_env), {"name": "Owner"}, format="json"
    ).json()
    client.put(
        _values_url(cf_env),
        [{"definition_id": definition["id"], "value": "alice"}],
        format="json",
    )
    # Clearing the value removes the stored row.
    client.put(
        _values_url(cf_env),
        [{"definition_id": definition["id"], "value": ""}],
        format="json",
    )
    reget = client.get(_values_url(cf_env))
    assert reget.json()[0]["value"] == ""
    assert reget.json()[0]["id"] is None
