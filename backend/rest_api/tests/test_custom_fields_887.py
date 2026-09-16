"""#887 — custom_fields round-trip for ChangeRequest / Goal / GlossaryTerm.

The original Gap #7 class (``68e924c2``, Risk/Adr/Issue) was a serializer that
never mixed in ``CustomFieldsSerializerMixin`` *and* a service layer that never
accepted a ``custom_fields`` kwarg, so an admin-managed ``kind="extended"``
attribute definition was silently discarded on artifact save: 200/201 on the
wire, nothing in the DB, no error. This module pins the same acceptance
criteria for the three bootstrapped types #887 reports — the serializers, the
services and both transports now carry the map:

* POST with ``custom_fields`` persists and is echoed back.
* GET re-reads the value from the DB (not from the request payload).
* The type's update path round-trips it: an in-place PATCH for ChangeRequest /
  GlossaryTerm, an appended lineage version for Goal (``partial_update`` 405s
  by design — see ``GoalViewSet``).
* ``custom_fields`` is an allowed key; an actually unknown key is still a 400
  (the #915/#916 unknown/read-only rejection must not swallow it).

The tests drive the real HTTP + serializer + service + DB stack: the bug lived
in the seam between those layers, so a mock would hide it.
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
def cf_env(db):
    """Tenant + admin + one workspace on the standard preset."""
    tenant = Tenant.objects.create(name="CF887 T", slug="cf887-t", is_active=True)
    admin = User.objects.create(
        username="cf887admin", email="cf887admin@t.test", tenant=tenant
    )
    admin.set_password("cfpass123")
    admin.save(update_fields=["password"])
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant,
            name="CF887 WS",
            preset={"name": "standard"},
            # GoalViewSet.create() 403s unless the workspace opts in.
            goals_enabled=True,
        )
        UserRole.objects.create(
            tenant=tenant, user=admin, workspace=workspace, role=ROLE_ADMIN
        )
        yield {"tenant": tenant, "workspace": workspace, "admin": admin}
    finally:
        clear_request_tenant()


def _client(cf_env: dict) -> APIClient:
    client = APIClient()
    resp = client.post(
        "/api/v1/auth/login/",
        {"username": "cf887admin", "password": "cfpass123"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.json()['token']}")
    return client


# ---------------------------------------------------------------------------
# Root cause guard: the mixin must stay declared on all three serializers
# ---------------------------------------------------------------------------


def test_three_types_declare_custom_fields_as_a_drf_field() -> None:
    """A future refactor moving the field onto a plain mixin regresses #290.

    ``metaclass=SerializerMetaclass`` on ``CustomFieldsSerializerMixin`` is
    load-bearing: without it DRF never collects ``custom_fields`` and the key
    silently vanishes from ``validated_data`` again.
    """
    from rest_api import serializers as s

    for serializer_cls in (
        s.ChangeRequestSerializer,
        s.GoalSerializer,
        s.GlossaryTermSerializer,
    ):
        assert "custom_fields" in serializer_cls().fields, serializer_cls.__name__


# ---------------------------------------------------------------------------
# Create + read + update round-trip per entity type
# ---------------------------------------------------------------------------


def _create(client: APIClient, path: str, payload: dict[str, Any]) -> dict:
    resp = client.post(path, payload, format="json")
    assert resp.status_code == 201, (path, resp.content)
    return resp.json()


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_change_request_custom_fields_round_trip(cf_env):
    """ChangeRequest: POST -> GET -> PATCH -> GET."""
    client = _client(cf_env)
    ws = str(cf_env["workspace"].id)

    created = _create(
        client,
        "/api/v1/change-requests/",
        {"workspace_id": ws, "title": "CR887", "custom_fields": {"owner": "alice"}},
    )
    assert created["custom_fields"] == {"owner": "alice"}

    fresh = client.get(f"/api/v1/change-requests/{created['id']}/")
    assert fresh.status_code == 200, fresh.content
    assert fresh.json()["custom_fields"] == {"owner": "alice"}

    patched = client.patch(
        f"/api/v1/change-requests/{created['id']}/",
        {"custom_fields": {"owner": "bob", "reviewed": True}},
        format="json",
    )
    assert patched.status_code == 200, patched.content
    assert patched.json()["custom_fields"] == {"owner": "bob", "reviewed": True}

    fresh = client.get(f"/api/v1/change-requests/{created['id']}/")
    assert fresh.json()["custom_fields"] == {"owner": "bob", "reviewed": True}


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_glossary_term_custom_fields_round_trip(cf_env):
    """GlossaryTerm: POST -> GET -> PATCH -> GET."""
    client = _client(cf_env)
    ws = str(cf_env["workspace"].id)

    created = _create(
        client,
        "/api/v1/glossary/",
        {
            "workspace_id": ws,
            "term": "Term887",
            "definition": "def",
            "custom_fields": {"owner": "alice"},
        },
    )
    assert created["custom_fields"] == {"owner": "alice"}

    fresh = client.get(f"/api/v1/glossary/{created['id']}/")
    assert fresh.status_code == 200, fresh.content
    assert fresh.json()["custom_fields"] == {"owner": "alice"}

    patched = client.patch(
        f"/api/v1/glossary/{created['id']}/",
        {"custom_fields": {"owner": "bob", "reviewed": True}},
        format="json",
    )
    assert patched.status_code == 200, patched.content
    assert patched.json()["custom_fields"] == {"owner": "bob", "reviewed": True}

    fresh = client.get(f"/api/v1/glossary/{created['id']}/")
    assert fresh.json()["custom_fields"] == {"owner": "bob", "reviewed": True}


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_goal_custom_fields_round_trip_across_lineage_versions(cf_env):
    """Goal: POST -> GET -> append a new lineage version -> GET.

    Goal is immutable-row-per-version: the in-place PATCH is a clean 405 by
    design (``GoalViewSet.partial_update``), so its update path is a POST that
    carries ``lineage_id`` and the new ``custom_fields`` map.
    """
    client = _client(cf_env)
    ws = str(cf_env["workspace"].id)

    created = _create(
        client,
        "/api/v1/goals/",
        {"workspace_id": ws, "title": "G887", "custom_fields": {"owner": "alice"}},
    )
    assert created["custom_fields"] == {"owner": "alice"}

    fresh = client.get(f"/api/v1/goals/{created['id']}/")
    assert fresh.status_code == 200, fresh.content
    assert fresh.json()["custom_fields"] == {"owner": "alice"}

    # The documented Goal update path: a new version, not an in-place PATCH.
    patched = _create(
        client,
        "/api/v1/goals/",
        {
            "workspace_id": ws,
            "title": "G887 v2",
            "lineage_id": created["lineage_id"],
            "custom_fields": {"owner": "bob", "reviewed": True},
        },
    )
    assert patched["sequence_number"] == 2
    assert patched["custom_fields"] == {"owner": "bob", "reviewed": True}

    fresh = client.get(f"/api/v1/goals/{patched['id']}/")
    assert fresh.json()["custom_fields"] == {"owner": "bob", "reviewed": True}


# ---------------------------------------------------------------------------
# Strict field rejection (#915/#916) must keep custom_fields legal
# ---------------------------------------------------------------------------

_STRICTNESS_CASES = [
    ("/api/v1/change-requests/", {"title": "CR887"}),
    ("/api/v1/goals/", {"title": "G887"}),
    ("/api/v1/glossary/", {"term": "Term887", "definition": "def"}),
]


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
@pytest.mark.parametrize("path,payload", _STRICTNESS_CASES)
def test_unknown_field_is_rejected_but_custom_fields_is_allowed(cf_env, path, payload):
    """#851/#915/#916: only truly unknown keys are a 400."""
    client = _client(cf_env)
    body = {"workspace_id": str(cf_env["workspace"].id), **payload}

    accepted = client.post(
        path, {**body, "custom_fields": {"owner": "alice"}}, format="json"
    )
    assert accepted.status_code == 201, accepted.content

    rejected = client.post(path, {**body, "totally_unknown": "x"}, format="json")
    assert rejected.status_code == 400, rejected.content
    details = rejected.json().get("error", {}).get("details") or []
    assert "totally_unknown" in {d.get("field") for d in details}
