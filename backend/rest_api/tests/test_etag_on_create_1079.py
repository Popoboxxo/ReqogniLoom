"""GitHub #1079 — the 201 create response carried no ``ETag``.

#984 added ``with_etag(...)`` to the *detail reads* only, so the surface looked
like this before the fix::

    POST /api/v1/requirements/ {"workspace_id": ..., "title": "..."}  -> 201
        etag: None | version: 1
    GET  /api/v1/requirements/<id>/                                  -> 200
        etag: "1" | version: 1

The value *was* in the body, so this is a consistency/convenience finding, not a
functional break — but a client that wants to follow the create with a
conditional ``PATCH If-Match: "1"`` had no way to get the tag out of the
response that just handed it the ``artifact_id``, and had to look the resource
up first.

Scope note: the fix must cover *every* resource that has a tag on its detail
path, not just requirements. All three in ``ETagMixin``'s scope
(Requirement, TestCase, Baseline) are pinned below; a fourth resource gaining
``with_etag`` on its detail path without its create path is the regression this
suite is shaped against.
"""
from __future__ import annotations

import re
import uuid
from typing import Any

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace

pytestmark = pytest.mark.django_db

_PASSWORD = "etag1079pass"

_JWT_OVERRIDES = dict(
    AUTH_JWT_SECRET="test-secret-not-a-real-key",
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
)

#: collection URL -> (create payload, detail URL template, PATCH-able?)
#: Baselines are immutable (their PATCH route answers 405), so their create
#: response is pinned on the header only, while the other two additionally prove
#: the tag is usable as the very next ``If-Match``.
_RESOURCES: dict[str, dict[str, Any]] = {
    "requirement": {
        "url": "/api/v1/requirements/",
        "payload": {"title": "create-carries-an-etag"},
        "patchable": True,
    },
    "testcase": {
        "url": "/api/v1/testcases/",
        "payload": {"title": "create-carries-an-etag"},
        "patchable": True,
    },
    "baseline": {
        "url": "/api/v1/baselines/",
        "payload": {"scope": "project", "name": "create-carries-an-etag"},
        "patchable": False,
    },
}


@pytest.fixture
def etag_create_env():
    tenant = Tenant.objects.create(
        name="ETagCreate", slug=f"etag-create-{uuid.uuid4().hex[:8]}", is_active=True
    )
    admin = User.objects.create(
        username="etagcreateadmin",
        email="etagcreateadmin@t.test",
        tenant=tenant,
    )
    admin.set_password(_PASSWORD)
    admin.save(update_fields=["password"])
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="ETagCreate WS", preset={"name": "standard"}
        )
        UserRole.objects.create(
            tenant=tenant, user=admin, workspace=workspace, role=ROLE_ADMIN
        )
        yield {"tenant": tenant, "admin": admin, "workspace": workspace}
    finally:
        clear_request_tenant()


def _client() -> APIClient:
    client = APIClient()
    with override_settings(**_JWT_OVERRIDES):
        login = client.post(
            "/api/v1/auth/login/",
            {"username": "etagcreateadmin", "password": _PASSWORD},
            format="json",
        )
    assert login.status_code == 200, login.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['token']}")
    return client


def _create(client: APIClient, env: dict, label: str):
    spec = _RESOURCES[label]
    payload = {"workspace_id": str(env["workspace"].id), **spec["payload"]}
    return client.post(spec["url"], payload, format="json")


#: RFC 9110 entity-tag: an optional weak prefix plus a quoted opaque value.
_ETAG_RE = re.compile(r'^(?:W/)?"[^"\s]*"$')


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.parametrize("label", sorted(_RESOURCES))
def test_create_response_carries_an_etag(etag_create_env, label) -> None:
    """#1079: 201 must carry the same tag the detail GET would have returned."""
    client = _client()

    response = _create(client, etag_create_env, label)

    assert response.status_code == 201, response.content
    etag = response.headers.get("ETag")
    assert etag is not None, (
        f"{label}: the 201 create response carries no ETag, so a client cannot "
        f"start an If-Match write without a lookup first"
    )
    assert _ETAG_RE.match(etag), f"{label}: {etag!r} is not an entity-tag"


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.parametrize("label", sorted(_RESOURCES))
def test_create_etag_matches_the_detail_get(etag_create_env, label) -> None:
    """Same revision, both routes — the tag must not drift between them."""
    client = _client()
    spec = _RESOURCES[label]

    created = _create(client, etag_create_env, label)
    assert created.status_code == 201, created.content

    fetched = client.get(f"{spec['url']}{created.json()['id']}/")

    assert fetched.status_code == 200, fetched.content
    assert created.headers["ETag"] == fetched.headers["ETag"], label


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.parametrize("label", sorted(_RESOURCES))
def test_create_etag_is_usable_as_the_next_if_match(etag_create_env, label) -> None:
    """The point of the fix: the create tag is directly consumable.

    Baseline is excluded — it is immutable, so its PATCH route answers 405 and
    an ``If-Match`` on it is refused before any compare happens.
    """
    if not _RESOURCES[label]["patchable"]:
        pytest.skip(f"{label} is immutable; its PATCH route answers 405 by design")
    client = _client()
    spec = _RESOURCES[label]

    created = _create(client, etag_create_env, label)
    assert created.status_code == 201, created.content
    etag = created.headers["ETag"]

    patched = client.patch(
        f"{spec['url']}{created.json()['id']}/",
        {"description": "written straight after the create"},
        format="json",
        HTTP_IF_MATCH=etag,
    )

    assert patched.status_code == 200, patched.content
    assert patched.json()["description"] == "written straight after the create"
    # The PATCH bumps the revision, so the returned tag must differ.
    assert patched.headers["ETag"] != etag, label


@override_settings(**_JWT_OVERRIDES)
def test_stale_create_etag_is_still_refused(etag_create_env) -> None:
    """Adding a tag must not weaken the precondition it feeds."""
    client = _client()

    created = _create(client, etag_create_env, "requirement")
    assert created.status_code == 201, created.content
    stale = created.headers["ETag"]

    first = client.patch(
        f"/api/v1/requirements/{created.json()['id']}/",
        {"description": "session A"},
        format="json",
    )
    assert first.status_code == 200, first.content

    second = client.patch(
        f"/api/v1/requirements/{created.json()['id']}/",
        {"description": "session B"},
        format="json",
        HTTP_IF_MATCH=stale,
    )

    assert second.status_code == 412, second.content
    assert second.json()["error"]["code"] == "PRECONDITION_FAILED"
