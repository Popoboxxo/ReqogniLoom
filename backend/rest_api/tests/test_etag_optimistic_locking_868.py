"""HTTP ``ETag`` / ``If-Match`` optimistic locking (GH-868, bundle #923).

Repo-wide there was no ``ETag``/``If-Match`` support, so a client had no
standard-HTTP way to make a write conditional. This suite pins the contract
added by ``rest_api.mixins.etag`` on the three resources named in the bundle:

* GET returns ``ETag: "<version>"``.
* PATCH with a matching ``If-Match`` succeeds and returns the *new* tag.
* PATCH with a stale ``If-Match`` answers 412 PRECONDITION_FAILED and writes
  nothing.
* PATCH without ``If-Match`` keeps the pre-change behaviour exactly
  (last-writer-wins) — the legacy ``expected_version`` path keeps answering 409.
* Precedence when both are present: ``If-Match`` wins.

Real DB + JWT, no mocked services: the guarantee lives in the interaction of
view → service → row lock, and a mocked service is exactly what would hide a
missing enforcement (the same reasoning as ``test_optimistic_locking.py``).
"""
from __future__ import annotations

from datetime import datetime, timezone as dt_timezone
from typing import Any

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace
from rest_api.mixins.etag import compute_etag, parse_if_match_version

_SECRET = "test-secret-not-a-real-key"

_JWT_OVERRIDES = dict(
    AUTH_JWT_SECRET=_SECRET,
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
)


@pytest.fixture
def etag_env(db):
    """Tenant + admin + one workspace, with the admin role scoped to it."""
    tenant = Tenant.objects.create(name="ETag T", slug="etag-t", is_active=True)
    admin = User.objects.create(
        username="etagadmin", email="etagadmin@t.test", tenant=tenant
    )
    admin.set_password("etagpass123")
    admin.save(update_fields=["password"])
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="ETag WS", preset={"name": "standard"}
        )
        UserRole.objects.create(
            tenant=tenant, user=admin, workspace=workspace, role=ROLE_ADMIN
        )
        yield {"tenant": tenant, "admin": admin, "workspace": workspace}
    finally:
        clear_request_tenant()


def _client() -> APIClient:
    client = APIClient()
    resp = client.post(
        "/api/v1/auth/login/",
        {"username": "etagadmin", "password": "etagpass123"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.json()['token']}")
    return client


def _create(client: APIClient, url: str, payload: dict[str, Any]) -> dict:
    resp = client.post(url, payload, format="json")
    assert resp.status_code == 201, resp.content
    return resp.json()


#: The two mutable entities in scope: collection URL and the create payload.
_MUTABLE: dict[str, tuple[str, dict[str, Any]]] = {
    "requirement": ("/api/v1/requirements/", {"title": "ETag requirement"}),
    "testcase": ("/api/v1/testcases/", {"title": "ETag testcase"}),
}


def _mutable_case(etag_env: dict, label: str) -> tuple[str, dict[str, Any]]:
    url, payload = _MUTABLE[label]
    return url, {"workspace_id": str(etag_env["workspace"].id), **payload}


def _baseline(client: APIClient, etag_env: dict) -> dict:
    return _create(
        client,
        "/api/v1/baselines/",
        {
            "workspace_id": str(etag_env["workspace"].id),
            "scope": "project",
            "name": "ETag baseline",
        },
    )


# ---------------------------------------------------------------------------
# Tag derivation (pure)
# ---------------------------------------------------------------------------


def test_compute_etag_uses_the_version_counter():
    class _Row:
        version = 7

    assert compute_etag(_Row()) == '"7"'


def test_compute_etag_falls_back_to_a_timestamp_for_immutable_rows():
    """Baselines have no version counter; ``created_at`` is their stable token."""

    class _BaselineDetail:
        created_at = datetime(2026, 9, 16, 12, 34, 56, tzinfo=dt_timezone.utc)

    assert compute_etag(_BaselineDetail()) == '"2026-09-16T12:34:56+00:00"'


def test_compute_etag_returns_none_when_nothing_is_tagged():
    assert compute_etag(object()) is None


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ('"3"', 3),
        ('  "3"  ', 3),
        ("*", None),
        (None, None),
        ("", None),
        ('W/"3"', None),  # weak tags never satisfy If-Match (strong compare)
        ('"3", "4"', None),  # multi-tag list — falls back to expected_version
        ("3", None),  # unquoted / malformed
        ('"abc"', None),  # not a version
    ],
)
def test_parse_if_match_version(header, expected):
    assert parse_if_match_version(header) == expected


# ---------------------------------------------------------------------------
# GET carries the tag
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("label", sorted(_MUTABLE))
@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_get_returns_etag(etag_env, label):
    client = _client()
    url, payload = _mutable_case(etag_env, label)
    item = _create(client, url, payload)

    resp = client.get(f"{url}{item['id']}/")

    assert resp.status_code == 200, resp.content
    assert resp.headers.get("ETag") == f'"{item["version"]}"', resp.headers


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_get_baseline_returns_etag(etag_env):
    client = _client()
    item = _baseline(client, etag_env)

    resp = client.get(f"/api/v1/baselines/{item['id']}/")

    assert resp.status_code == 200, resp.content
    etag = resp.headers.get("ETag")
    assert etag is not None and etag.startswith('"'), resp.headers


# ---------------------------------------------------------------------------
# PATCH preconditions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("label", sorted(_MUTABLE))
@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_patch_with_matching_if_match_succeeds_and_returns_new_etag(etag_env, label):
    client = _client()
    url, payload = _mutable_case(etag_env, label)
    item = _create(client, url, payload)

    resp = client.patch(
        f"{url}{item['id']}/",
        {"description": "guarded write"},
        format="json",
        HTTP_IF_MATCH=f'"{item["version"]}"',
    )

    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["description"] == "guarded write", label
    # The response carries the *new* tag, so the client can chain the next write.
    assert resp.headers.get("ETag") == f'"{body["version"]}"', resp.headers
    assert body["version"] > item["version"]


@pytest.mark.parametrize("label", sorted(_MUTABLE))
@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_stale_if_match_is_412_and_writes_nothing(etag_env, label):
    client = _client()
    url, payload = _mutable_case(etag_env, label)
    item = _create(client, url, payload)
    stale = f'"{item["version"]}"'

    # Session A commits, bumping the version (and therefore the tag).
    first = client.patch(
        f"{url}{item['id']}/", {"description": "session A"}, format="json"
    )
    assert first.status_code == 200, first.content
    assert first.json()["version"] > item["version"]

    # Session B still holds the tag it read before that save.
    conflict = client.patch(
        f"{url}{item['id']}/",
        {"description": "session B"},
        format="json",
        HTTP_IF_MATCH=stale,
    )

    assert conflict.status_code == 412, conflict.content
    assert conflict.json()["error"]["code"] == "PRECONDITION_FAILED", conflict.content
    # Nothing was written: session A's edit survives.
    fresh = client.get(f"{url}{item['id']}/")
    assert fresh.json()["description"] == "session A", label


@pytest.mark.parametrize("label", sorted(_MUTABLE))
@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_missing_if_match_keeps_last_writer_wins(etag_env, label):
    """Backwards compatibility: no precondition header, no behaviour change."""
    client = _client()
    url, payload = _mutable_case(etag_env, label)
    item = _create(client, url, payload)

    assert (
        client.patch(
            f"{url}{item['id']}/", {"description": "first"}, format="json"
        ).status_code
        == 200
    ), label
    second = client.patch(
        f"{url}{item['id']}/", {"description": "second"}, format="json"
    )

    assert second.status_code == 200, second.content
    assert client.get(f"{url}{item['id']}/").json()["description"] == "second", label


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_if_match_star_is_an_existence_check(etag_env):
    """``If-Match: *`` asserts the resource exists, not a revision (RFC 9110)."""
    client = _client()
    url, payload = _mutable_case(etag_env, "requirement")
    item = _create(client, url, payload)

    resp = client.patch(
        f"{url}{item['id']}/",
        {"description": "any current revision is fine"},
        format="json",
        HTTP_IF_MATCH="*",
    )

    assert resp.status_code == 200, resp.content


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_expected_version_without_if_match_still_answers_409(etag_env):
    """The legacy body mechanism is untouched (no regression on 409)."""
    client = _client()
    url, payload = _mutable_case(etag_env, "requirement")
    item = _create(client, url, payload)
    stale = item["version"]
    assert (
        client.patch(
            f"{url}{item['id']}/", {"description": "session A"}, format="json"
        ).json()["version"]
        > stale
    )

    conflict = client.patch(
        f"{url}{item['id']}/",
        {"description": "session B", "expected_version": stale},
        format="json",
    )

    assert conflict.status_code == 409, conflict.content
    assert conflict.json()["error"]["code"] == "CONFLICT", conflict.content


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_if_match_takes_precedence_over_expected_version(etag_env):
    """Precedence, defined and pinned: the HTTP precondition wins.

    A client that asserts a *current* ``If-Match`` while its legacy body field
    is stale is accepted on the current revision it actually holds — the tag is
    the only assertion an intermediary could have reasoned about.
    """
    client = _client()
    url, payload = _mutable_case(etag_env, "requirement")
    item = _create(client, url, payload)
    stale_body_version = item["version"]
    bumped = client.patch(
        f"{url}{item['id']}/", {"description": "session A"}, format="json"
    ).json()

    resp = client.patch(
        f"{url}{item['id']}/",
        {"description": "session B", "expected_version": stale_body_version},
        format="json",
        HTTP_IF_MATCH=f'"{bumped["version"]}"',
    )

    assert resp.status_code == 200, resp.content
    assert resp.json()["description"] == "session B"


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_stale_if_match_wins_over_a_current_expected_version(etag_env):
    """The other half of the precedence rule: stale tag → 412, not 409/200."""
    client = _client()
    url, payload = _mutable_case(etag_env, "requirement")
    item = _create(client, url, payload)
    stale_tag = f'"{item["version"]}"'
    bumped = client.patch(
        f"{url}{item['id']}/", {"description": "session A"}, format="json"
    ).json()

    resp = client.patch(
        f"{url}{item['id']}/",
        {"description": "session B", "expected_version": bumped["version"]},
        format="json",
        HTTP_IF_MATCH=stale_tag,
    )

    assert resp.status_code == 412, resp.content
    assert resp.json()["error"]["code"] == "PRECONDITION_FAILED", resp.content


# ---------------------------------------------------------------------------
# Baseline: immutable, so the precondition is evaluated before the 405
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_baseline_patch_stale_if_match_is_412(etag_env):
    client = _client()
    item = _baseline(client, etag_env)
    etag = client.get(f"/api/v1/baselines/{item['id']}/").headers.get("ETag")
    assert etag is not None

    resp = client.patch(
        f"/api/v1/baselines/{item['id']}/",
        {"name": "renamed"},
        format="json",
        HTTP_IF_MATCH=f'"{etag[1:-1]}-stale"',
    )

    assert resp.status_code == 412, resp.content
    assert resp.json()["error"]["code"] == "PRECONDITION_FAILED", resp.content


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_baseline_patch_current_if_match_still_405(etag_env):
    """A satisfied precondition must not turn the immutable route into a write."""
    client = _client()
    item = _baseline(client, etag_env)
    etag = client.get(f"/api/v1/baselines/{item['id']}/").headers.get("ETag")
    assert etag is not None

    resp = client.patch(
        f"/api/v1/baselines/{item['id']}/",
        {"name": "renamed"},
        format="json",
        HTTP_IF_MATCH=etag,
    )

    assert resp.status_code == 405, resp.content


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_baseline_patch_without_if_match_is_405(etag_env):
    client = _client()
    item = _baseline(client, etag_env)

    resp = client.patch(
        f"/api/v1/baselines/{item['id']}/", {"name": "renamed"}, format="json"
    )

    assert resp.status_code == 405, resp.content
