"""POST /api/v1/workspaces/ honours every field its schema advertises.

SYSTEMAUDIT_2026-08-29, REST finding 2: ``WorkspaceSerializer`` is the declared
request body for the create endpoint, so the published OpenAPI schema promised
``theme``, ``goals_enabled``, ``goals_ai_enabled``, ``decomposition_link_type``,
``default_link_type`` and ``ai_prompts`` as writable — while the handler
forwarded only ``name``/``preset``/``terminology_profile``/``language`` to the
service. A client that created a configured workspace in one call got a 201 and
model defaults back, with nothing to tell it half the payload was discarded.

Resolution, and what these tests pin:

* the five real configuration fields are now processed at create time
  (option a — they are already accepted by PATCH, so create/PATCH agree);
* ``ai_prompts`` is declared ``read_only`` (option b) — it is superseded by the
  versioned ``PromptTemplate`` model (#119) and has no write path on create or
  PATCH, so the schema now says so instead of promising one.
"""
from __future__ import annotations

import uuid

import pytest
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace

pytestmark = pytest.mark.django_db

_PASSWORD = "hunter2pass"


def _admin_client() -> APIClient:
    """A tenant admin with an existing workspace (create needs a role somewhere)."""
    slug = f"wscreate-{uuid.uuid4().hex[:8]}"
    tenant = Tenant.objects.create(name=f"T-{slug}", slug=slug, is_active=True)
    user = User.objects.create(
        username=f"user-{slug}", email=f"{slug}@t.test", tenant=tenant
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])

    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name=f"Seed {slug}", preset={"tier": "standard"}
        )
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_ADMIN
        )
    finally:
        clear_request_tenant()

    client = APIClient()
    resp = client.post(
        "/api/v1/auth/login/",
        {"username": user.username, "password": _PASSWORD},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.json()['token']}")
    return client


def test_create_applies_every_advertised_configuration_field() -> None:
    """The regression itself: all of these used to be silently dropped."""
    client = _admin_client()

    resp = client.post(
        "/api/v1/workspaces/",
        {
            "name": f"Configured WS {uuid.uuid4().hex[:6]}",
            "preset": "standard",
            "theme": "light",
            "goals_enabled": True,
            "goals_ai_enabled": True,
            "decomposition_link_type": "derives-from",
            "default_link_type": "satisfies",
        },
        format="json",
    )

    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert body["theme"] == "light"
    assert body["goals_enabled"] is True
    assert body["goals_ai_enabled"] is True
    assert body["decomposition_link_type"] == "derives-from"
    assert body["default_link_type"] == "satisfies"

    # Persisted, not merely echoed by the serializer.
    fresh = client.get(f"/api/v1/workspaces/{body['id']}/")
    assert fresh.status_code == 200, fresh.content
    assert fresh.json()["theme"] == "light"
    assert fresh.json()["goals_enabled"] is True
    assert fresh.json()["goals_ai_enabled"] is True
    assert fresh.json()["decomposition_link_type"] == "derives-from"
    assert fresh.json()["default_link_type"] == "satisfies"


def test_create_without_configuration_fields_keeps_defaults() -> None:
    """Omitting them must not write the serializer's defaults as explicit choices."""
    client = _admin_client()

    resp = client.post(
        "/api/v1/workspaces/",
        {"name": f"Plain WS {uuid.uuid4().hex[:6]}", "preset": "standard"},
        format="json",
    )

    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert body["theme"] == "dark"
    assert body["goals_enabled"] is False
    assert body["goals_ai_enabled"] is False
    assert body["decomposition_link_type"] == "parent-child"
    assert body["default_link_type"] == "derives-from"


def test_ai_prompts_is_declared_read_only() -> None:
    """No write path exists, so the schema must not advertise one (#119)."""
    from rest_api.serializers import WorkspaceSerializer

    assert WorkspaceSerializer().fields["ai_prompts"].read_only is True


def test_create_ignores_ai_prompts_without_pretending_to_store_it() -> None:
    """A client sending the read-only field still gets the stored value back."""
    client = _admin_client()

    resp = client.post(
        "/api/v1/workspaces/",
        {
            "name": f"Prompt WS {uuid.uuid4().hex[:6]}",
            "preset": "standard",
            "ai_prompts": {"l1": "ignored"},
        },
        format="json",
    )

    assert resp.status_code == 201, resp.content
    assert resp.json()["ai_prompts"] == {}
