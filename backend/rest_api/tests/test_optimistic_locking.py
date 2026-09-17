"""Optimistic locking (``expected_version`` → 409) across the versioned entities.

SYSTEMAUDIT_2026-08-29, REST finding 1: the ``expected_version`` / 409 contract
existed only for ``ArchitectureElement``. Every other versioned entity accepted
the key (``_ALWAYS_ALLOWED_PATCH_FIELDS`` let it through) and then ignored it,
so a client that had gone stale overwrote a concurrent edit and still got a 200
— the worst shape of the bug, because the client believes it is protected.

Real DB + JWT, no mocked services: the guarantee lives in the interaction of
serializer → view → service → row lock, and a mocked service is exactly what
hid the gap in the first place.

Coverage per entity: stale → 409, current → 200, omitted → 200 (the
backwards-compatible path that must keep working for existing clients).
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
def lock_env(db):
    """Tenant + admin + one workspace, with the admin role scoped to it."""
    tenant = Tenant.objects.create(name="OL T", slug="ol-t", is_active=True)
    admin = User.objects.create(username="oladmin", email="oladmin@t.test", tenant=tenant)
    admin.set_password("olpass123")
    admin.save(update_fields=["password"])
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="OL WS", preset={"name": "standard"}
        )
        UserRole.objects.create(
            tenant=tenant, user=admin, workspace=workspace, role=ROLE_ADMIN
        )
        yield {"tenant": tenant, "admin": admin, "workspace": workspace}
    finally:
        clear_request_tenant()


def _client(_env: dict) -> APIClient:
    client = APIClient()
    resp = client.post(
        "/api/v1/auth/login/",
        {"username": "oladmin", "password": "olpass123"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.json()['token']}")
    return client


def _create(client: APIClient, url: str, payload: dict[str, Any]) -> dict:
    resp = client.post(url, payload, format="json")
    assert resp.status_code == 201, resp.content
    return resp.json()


#: One entry per entity whose service gained the guard: collection URL, create
#: payload, and the name of a plain free-text field the PATCH can move (mostly
#: ``description``, but GlossaryTerm calls it ``definition``). Parametrized
#: rather than copy-pasted so a newly guarded entity is one line away from
#: being covered here too.
_CASES: dict[str, tuple[str, dict[str, Any], str]] = {
    "requirement": ("/api/v1/requirements/", {"title": "OL requirement"}, "description"),
    "testcase": ("/api/v1/testcases/", {"title": "OL testcase"}, "description"),
    "need": ("/api/v1/needs/", {"title": "OL need"}, "description"),
    "adr": (
        "/api/v1/adrs/",
        {"title": "OL adr", "description": "v1", "context": "ctx"},
        "description",
    ),
    "risk": ("/api/v1/risks/", {"title": "OL risk"}, "description"),
    "issue": ("/api/v1/issues/", {"title": "OL issue"}, "description"),
    "change_request": (
        "/api/v1/change-requests/",
        {"title": "OL change request", "description": "v1"},
        "description",
    ),
    "glossary": (
        "/api/v1/glossary/",
        {"term": "OL term", "definition": "v1"},
        "definition",
    ),
}


def _case(lock_env: dict, label: str) -> tuple[str, dict[str, Any], str]:
    url, payload, field = _CASES[label]
    return url, {"workspace_id": str(lock_env["workspace"].id), **payload}, field


@pytest.mark.parametrize("label", sorted(_CASES))
@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_stale_expected_version_conflicts(lock_env, label):
    """A PATCH carrying an outdated ``expected_version`` must answer 409.

    The stale version is manufactured the way it happens in production: one
    session saves (bumping ``version``), a second session still holds the value
    it read before that save.
    """
    client = _client(lock_env)
    url, payload, field = _case(lock_env, label)
    item = _create(client, url, payload)
    stale_version = item["version"]

    # Session A commits a change — this is what makes session B's version stale.
    first = client.patch(
        f"{url}{item['id']}/", {field: "written by session A"}, format="json"
    )
    assert first.status_code == 200, (label, first.content)
    assert first.json()["version"] > stale_version, (
        f"{label}: precondition failed — the first PATCH did not bump version, "
        "so the second one would not be stale and this test would pass vacuously"
    )

    # Session B still believes it holds the newest version.
    conflict = client.patch(
        f"{url}{item['id']}/",
        {field: "written by session B", "expected_version": stale_version},
        format="json",
    )

    assert conflict.status_code == 409, (label, conflict.content)
    # ... and nothing was written: session A's edit survives intact.
    fresh = client.get(f"{url}{item['id']}/")
    assert fresh.json()[field] == "written by session A", label


@pytest.mark.parametrize("label", sorted(_CASES))
@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_current_expected_version_is_accepted(lock_env, label):
    """The happy path: a matching ``expected_version`` writes normally."""
    client = _client(lock_env)
    url, payload, field = _case(lock_env, label)
    item = _create(client, url, payload)

    resp = client.patch(
        f"{url}{item['id']}/",
        {field: "guarded write", "expected_version": item["version"]},
        format="json",
    )

    assert resp.status_code == 200, (label, resp.content)
    fresh = client.get(f"{url}{item['id']}/")
    assert fresh.json()[field] == "guarded write", label


@pytest.mark.parametrize("label", sorted(_CASES))
@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_omitted_expected_version_keeps_last_writer_wins(lock_env, label):
    """Omitting the field must not start rejecting existing clients.

    The guard is opt-in by design (same contract as the ArchitectureElement
    reference implementation): without ``expected_version`` a PATCH from a
    stale client still wins, which is the pre-audit behaviour every current
    caller relies on.
    """
    client = _client(lock_env)
    url, payload, field = _case(lock_env, label)
    item = _create(client, url, payload)

    assert (
        client.patch(
            f"{url}{item['id']}/", {field: "first"}, format="json"
        ).status_code
        == 200
    ), label
    second = client.patch(f"{url}{item['id']}/", {field: "second"}, format="json")

    assert second.status_code == 200, (label, second.content)
    assert client.get(f"{url}{item['id']}/").json()[field] == "second", label


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_architecture_element_reference_behaviour_unchanged(lock_env):
    """The reference implementation must keep answering 409 after the refactor.

    ``ArchitectureService`` now shares ``assert_expected_version`` with the
    other services; this pins the externally visible behaviour that extraction
    had to preserve.
    """
    client = _client(lock_env)
    element = _create(
        client,
        "/api/v1/architecture/",
        {
            "workspace_id": str(lock_env["workspace"].id),
            "title": "OL element",
            "element_type": "block",
        },
    )
    stale_version = element["version"]
    assert (
        client.patch(
            f"/api/v1/architecture/{element['id']}/",
            {"description": "session A"},
            format="json",
        ).status_code
        == 200
    )

    conflict = client.patch(
        f"/api/v1/architecture/{element['id']}/",
        {"description": "session B", "expected_version": stale_version},
        format="json",
    )

    assert conflict.status_code == 409, conflict.content


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_expected_version_below_one_is_a_field_level_400(lock_env):
    """``min_value=1``: version numbering starts at 1, so 0 is never a real read."""
    client = _client(lock_env)
    item = _create(
        client,
        "/api/v1/requirements/",
        {"workspace_id": str(lock_env["workspace"].id), "title": "OL bounds"},
    )

    resp = client.patch(
        f"/api/v1/requirements/{item['id']}/",
        {"description": "x", "expected_version": 0},
        format="json",
    )

    assert resp.status_code == 400, resp.content
    details = resp.json().get("error", {}).get("details") or []
    assert "expected_version" in {d.get("field") for d in details}, resp.content
