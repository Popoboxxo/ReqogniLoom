"""Workspace optimistic locking over HTTP (GH-868 pattern, issue #1244).

The Workspace detail route is the last versioned entity without the
``ETag``/``If-Match`` half of the optimistic-locking contract; this module pins
it end to end through the real middleware stack:

* ``GET`` emits ``ETag: "<version>"``;
* a PATCH with a matching ``If-Match`` succeeds, advances the version and
  returns the new tag;
* a PATCH with a *stale* ``If-Match`` answers 412 ``PRECONDITION_FAILED`` and
  writes nothing;
* a PATCH with no ``If-Match`` stays last-writer-wins (the documented,
  backward-compatible behaviour);
* the legacy ``expected_version`` body field keeps answering 409 ``CONFLICT``.

It also asserts the generated OpenAPI document declares 412 on the
ETag-enabled PATCH operations (#1244 acceptance criterion).
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

_WS_DETAIL = "/api/v1/workspaces/{pk}/"


def _scenario() -> tuple[Tenant, User, Workspace]:
    suffix = uuid.uuid4().hex[:8]
    tenant = Tenant.objects.create(name=f"ET-{suffix}", slug=f"etag-{suffix}", is_active=True)
    user = User.objects.create(
        username=f"etag-{suffix}", email=f"etag-{suffix}@t.test", tenant=tenant
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])

    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="ETag WS", preset={"name": "standard"}
        )
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_ADMIN
        )
    finally:
        clear_request_tenant()
    return tenant, user, workspace


def _client(user: User) -> APIClient:
    client = APIClient()
    login = client.post(
        "/api/v1/auth/login/",
        {"username": user.username, "password": _PASSWORD},
        format="json",
    )
    assert login.status_code == 200, login.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['token']}")
    return client


def _version(workspace: Workspace) -> int:
    return Workspace.unscoped.get(pk=workspace.pk).version


# ---------------------------------------------------------------------------
# ETag / If-Match
# ---------------------------------------------------------------------------


def test_get_emits_an_etag_header() -> None:
    _, user, workspace = _scenario()

    resp = _client(user).get(_WS_DETAIL.format(pk=workspace.id))

    assert resp.status_code == 200, resp.content
    assert resp["ETag"] == f'"{_version(workspace)}"'


def test_patch_with_matching_if_match_succeeds_and_advances_the_version() -> None:
    _, user, workspace = _scenario()
    client = _client(user)
    etag = client.get(_WS_DETAIL.format(pk=workspace.id))["ETag"]

    resp = client.patch(
        _WS_DETAIL.format(pk=workspace.id),
        {"name": "ETag WS Renamed"},
        format="json",
        HTTP_IF_MATCH=etag,
    )

    assert resp.status_code == 200, resp.content
    assert resp.json()["name"] == "ETag WS Renamed"
    assert resp["ETag"] != etag, "a real write must change the ETag"
    assert resp["ETag"] == f'"{_version(workspace)}"'


def test_patch_with_stale_if_match_returns_412_and_writes_nothing() -> None:
    _, user, workspace = _scenario()
    client = _client(user)
    stale_etag = client.get(_WS_DETAIL.format(pk=workspace.id))["ETag"]

    # A first write advances the version, making stale_etag obsolete.
    first = client.patch(
        _WS_DETAIL.format(pk=workspace.id),
        {"name": "First Rename"},
        format="json",
        HTTP_IF_MATCH=stale_etag,
    )
    assert first.status_code == 200, first.content

    conflict = client.patch(
        _WS_DETAIL.format(pk=workspace.id),
        {"name": "Second Rename"},
        format="json",
        HTTP_IF_MATCH=stale_etag,
    )

    assert conflict.status_code == 412, conflict.content
    assert conflict.json()["error"]["code"] == "PRECONDITION_FAILED"
    # The rejected write must not have landed.
    assert Workspace.unscoped.get(pk=workspace.pk).name == "First Rename"


def test_patch_without_if_match_stays_last_writer_wins() -> None:
    _, user, workspace = _scenario()

    resp = _client(user).patch(
        _WS_DETAIL.format(pk=workspace.id),
        {"name": "No Precondition"},
        format="json",
    )

    assert resp.status_code == 200, resp.content
    assert resp.json()["name"] == "No Precondition"


def test_patch_with_stale_body_expected_version_returns_409() -> None:
    """The legacy body field keeps its 409 CONFLICT contract (not 412)."""
    _, user, workspace = _scenario()
    client = _client(user)

    first = client.patch(
        _WS_DETAIL.format(pk=workspace.id),
        {"name": "First Rename"},
        format="json",
    )
    assert first.status_code == 200, first.content

    stale = client.patch(
        _WS_DETAIL.format(pk=workspace.id),
        {"name": "Second Rename", "expected_version": 1},
        format="json",
    )

    assert stale.status_code == 409, stale.content
    assert stale.json()["error"]["code"] == "CONFLICT"


# ---------------------------------------------------------------------------
# OpenAPI: 412 must be declared on the ETag endpoints
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def openapi_schema() -> dict:
    from drf_spectacular.generators import SchemaGenerator

    return SchemaGenerator().get_schema(request=None, public=True)


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/workspaces/{id}/",
        "/api/v1/requirements/{id}/",
        "/api/v1/test-cases/{id}/",
        "/api/v1/baselines/{id}/",
    ],
)
def test_openapi_declares_412_on_etag_patch_operations(
    openapi_schema: dict, path: str
) -> None:
    assert path in openapi_schema["paths"], (
        f"{path} missing; available workspace paths: "
        f"{sorted(p for p in openapi_schema['paths'] if 'workspace' in p)}"
    )
    assert "412" in openapi_schema["paths"][path]["patch"]["responses"], (
        f"{path} PATCH does not declare a 412 response"
    )
