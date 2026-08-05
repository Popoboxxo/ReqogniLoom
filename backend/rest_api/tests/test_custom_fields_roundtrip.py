"""custom_fields / change_reason must survive a REST write (#290).

Both fields used to be accepted with HTTP 200/201 and then silently dropped,
for two *different* reasons that produced the same user-visible symptom:

* ``custom_fields`` was declared on ``CustomFieldsSerializerMixin``, a plain
  mixin. DRF's ``SerializerMetaclass`` only harvests declared fields from bases
  that expose ``_declared_fields``, which a plain mixin never does — so the key
  never reached ``validated_data`` and the ``if "custom_fields" in data:``
  branches in ``rest_api.views`` were unreachable.

* ``change_reason`` was simply never declared on the Adr/Risk/Issue
  serializers, although all three ViewSets forward
  ``data.get("change_reason")`` into the service, which records it on the audit
  event. Every edit therefore logged ``None``.

The tests drive the real HTTP + serializer + service + DB stack on purpose: the
bug lived exactly in the seam between those layers, so any mock would hide it.
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
    tenant = Tenant.objects.create(name="CF T", slug="cf-t", is_active=True)
    admin = User.objects.create(username="cfadmin", email="cfadmin@t.test", tenant=tenant)
    admin.set_password("cfpass123")
    admin.save(update_fields=["password"])
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="CF WS", preset={"name": "standard"}
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
        {"username": "cfadmin", "password": "cfpass123"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.json()['token']}")
    return client


def _create(client: APIClient, path: str, payload: dict[str, Any]) -> dict:
    resp = client.post(path, payload, format="json")
    assert resp.status_code == 201, (path, resp.content)
    return resp.json()


# ---------------------------------------------------------------------------
# #290 — custom_fields round-trips through create and PATCH
#
# Parametrized over every serializer that mixes in CustomFieldsSerializerMixin
# and whose service accepts a ``custom_fields`` kwarg, because the metaclass bug
# hit all of them identically.
# ---------------------------------------------------------------------------


def _entity_payloads(workspace_id: Any) -> dict[str, tuple[str, dict[str, Any]]]:
    ws = str(workspace_id)
    return {
        "requirement": (
            "/api/v1/requirements/",
            {"workspace_id": ws, "title": "CF requirement"},
        ),
        "need": (
            "/api/v1/needs/",
            {"workspace_id": ws, "title": "CF need"},
        ),
        "architecture": (
            "/api/v1/architecture/",
            {"workspace_id": ws, "title": "CF element", "element_type": "block"},
        ),
        "testcase": (
            "/api/v1/testcases/",
            {"workspace_id": ws, "title": "CF testcase"},
        ),
    }


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
@pytest.mark.parametrize(
    "entity", ["requirement", "need", "architecture", "testcase"]
)
def test_custom_fields_survive_create(cf_env, entity):
    """POST with custom_fields must persist them, not drop them silently."""
    client = _client(cf_env)
    path, payload = _entity_payloads(cf_env["workspace"].id)[entity]
    created = _create(
        client, path, {**payload, "custom_fields": {"owner": "alice", "sprint": 7}}
    )

    assert created["custom_fields"] == {"owner": "alice", "sprint": 7}
    # Re-read: proves it reached the DB rather than being echoed by the
    # serializer from the request payload.
    fresh = client.get(f"{path}{created['id']}/")
    assert fresh.status_code == 200, fresh.content
    assert fresh.json()["custom_fields"] == {"owner": "alice", "sprint": 7}


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
@pytest.mark.parametrize(
    "entity", ["requirement", "need", "architecture", "testcase"]
)
def test_custom_fields_survive_patch(cf_env, entity):
    """The reported repro: editing a custom field in the UI and saving."""
    client = _client(cf_env)
    path, payload = _entity_payloads(cf_env["workspace"].id)[entity]
    created = _create(
        client, path, {**payload, "custom_fields": {"owner": "alice"}}
    )

    resp = client.patch(
        f"{path}{created['id']}/",
        {"custom_fields": {"owner": "bob", "reviewed": True}},
        format="json",
    )

    assert resp.status_code == 200, resp.content
    assert resp.json()["custom_fields"] == {"owner": "bob", "reviewed": True}
    fresh = client.get(f"{path}{created['id']}/")
    assert fresh.json()["custom_fields"] == {"owner": "bob", "reviewed": True}


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_patch_without_custom_fields_leaves_them_untouched(cf_env):
    """REQ-L2-AS-037: an unrelated PATCH must not wipe the stored map.

    The service distinguishes "omitted" from "cleared" via a sentinel; now that
    the field is really registered, that distinction is reachable and has to
    keep working.
    """
    client = _client(cf_env)
    created = _create(
        client,
        "/api/v1/requirements/",
        {
            "workspace_id": str(cf_env["workspace"].id),
            "title": "CF requirement",
            "custom_fields": {"owner": "alice"},
        },
    )

    resp = client.patch(
        f"/api/v1/requirements/{created['id']}/",
        {"description": "unrelated edit"},
        format="json",
    )

    assert resp.status_code == 200, resp.content
    fresh = client.get(f"/api/v1/requirements/{created['id']}/")
    assert fresh.json()["custom_fields"] == {"owner": "alice"}


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_custom_fields_can_be_cleared_explicitly(cf_env):
    """Sending an empty map clears — distinct from omitting the key."""
    client = _client(cf_env)
    created = _create(
        client,
        "/api/v1/requirements/",
        {
            "workspace_id": str(cf_env["workspace"].id),
            "title": "CF requirement",
            "custom_fields": {"owner": "alice"},
        },
    )

    resp = client.patch(
        f"/api/v1/requirements/{created['id']}/",
        {"custom_fields": {}},
        format="json",
    )

    assert resp.status_code == 200, resp.content
    fresh = client.get(f"/api/v1/requirements/{created['id']}/")
    assert fresh.json()["custom_fields"] == {}


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_invalid_custom_fields_are_rejected_at_the_serializer(cf_env):
    """Registering the field also activates ``validate_custom_fields``.

    While the field was inert, the flat-map rules in
    ``persistence.custom_fields`` were only enforced at the service boundary.
    A nested value must now fail with a field-level 400.
    """
    client = _client(cf_env)

    resp = client.post(
        "/api/v1/requirements/",
        {
            "workspace_id": str(cf_env["workspace"].id),
            "title": "CF requirement",
            "custom_fields": {"nested": {"not": "allowed"}},
        },
        format="json",
    )

    assert resp.status_code == 400, resp.content
    details = resp.json().get("error", {}).get("details") or []
    assert "custom_fields" in {d.get("field") for d in details}


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
@pytest.mark.parametrize(
    "payload",
    [
        {"ok\x00key": "value"},
        {"key": "val\x00ue"},
    ],
    ids=["nul-in-key", "nul-in-value"],
)
def test_custom_fields_reject_nul_bytes(cf_env, payload):
    """QIRK-003 for the JSON map: must be a 400, never a 500.

    Postgres cannot store NUL inside a jsonb string, and the existing top-level
    NUL screen in ``PresetAwareSerializerMixin.validate`` only inspects string
    attrs — it cannot see inside a dict. Before #290 this was unreachable from
    REST because custom_fields was never written at all; making the field real
    opens the path, so the flat-map validator has to cover it.
    """
    client = _client(cf_env)

    resp = client.post(
        "/api/v1/requirements/",
        {
            "workspace_id": str(cf_env["workspace"].id),
            "title": "CF requirement",
            "custom_fields": payload,
        },
        format="json",
    )

    assert resp.status_code == 400, resp.content


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_custom_fields_change_bumps_version(cf_env):
    """custom_fields lives on the Artifact, outside the entity snapshot.

    #269 finding 5 gates the version bump on a real change; the gate has to
    account for this side-channel or custom-field-only edits would look like
    no-ops.
    """
    client = _client(cf_env)
    created = _create(
        client,
        "/api/v1/requirements/",
        {"workspace_id": str(cf_env["workspace"].id), "title": "CF requirement"},
    )
    version_before = created["version"]

    resp = client.patch(
        f"/api/v1/requirements/{created['id']}/",
        {"custom_fields": {"owner": "alice"}},
        format="json",
    )

    assert resp.status_code == 200, resp.content
    fresh = client.get(f"/api/v1/requirements/{created['id']}/")
    assert fresh.json()["version"] == version_before + 1

    # Re-sending the identical map is a no-op and must not bump again.
    again = client.patch(
        f"/api/v1/requirements/{created['id']}/",
        {"custom_fields": {"owner": "alice"}},
        format="json",
    )
    assert again.status_code == 200, again.content
    fresh2 = client.get(f"/api/v1/requirements/{created['id']}/")
    assert fresh2.json()["version"] == version_before + 1


# ---------------------------------------------------------------------------
# #290 (related pattern) — change_reason on Adr / Risk / Issue
# ---------------------------------------------------------------------------


def _change_reason_payloads(workspace_id: Any) -> dict[str, tuple[str, dict[str, Any]]]:
    ws = str(workspace_id)
    return {
        "adr": ("/api/v1/adrs/", {"workspace_id": ws, "title": "CR adr"}),
        "risk": ("/api/v1/risks/", {"workspace_id": ws, "title": "CR risk"}),
        "issue": ("/api/v1/issues/", {"workspace_id": ws, "title": "CR issue"}),
    }


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
@pytest.mark.parametrize("entity", ["adr", "risk", "issue"])
def test_change_reason_reaches_the_audit_trail(cf_env, entity):
    """The ViewSets always forwarded change_reason; the serializer ate it."""
    from audit.models import AuditEntry

    client = _client(cf_env)
    path, payload = _change_reason_payloads(cf_env["workspace"].id)[entity]
    created = _create(client, path, payload)

    resp = client.patch(
        f"{path}{created['id']}/",
        {"description": "edited", "change_reason": "because the ADR was wrong"},
        format="json",
    )

    assert resp.status_code == 200, resp.content
    entry = (
        AuditEntry.objects.filter(entity_id=created["id"], op="update")
        .order_by("-timestamp")
        .first()
    )
    assert entry is not None, "no audit entry recorded for the update"
    assert entry.change_reason == "because the ADR was wrong"


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
@pytest.mark.parametrize("entity", ["adr", "risk", "issue"])
def test_change_reason_is_declared_on_the_serializer(cf_env, entity):
    """Guards the root cause directly, not just its downstream symptom.

    A future refactor could reintroduce the bug by moving the declaration onto
    a plain mixin again; this assertion fails immediately if DRF stops
    collecting the field.
    """
    from rest_api import serializers as s

    serializer_cls = {
        "adr": s.AdrSerializer,
        "risk": s.RiskSerializer,
        "issue": s.IssueSerializer,
    }[entity]
    assert "change_reason" in serializer_cls().fields


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
@pytest.mark.parametrize(
    "serializer_name",
    [
        "ArtifactSerializer",
        "RequirementSerializer",
        "StakeholderNeedSerializer",
        "ArchitectureElementSerializer",
        "TestCaseSerializer",
    ],
)
def test_custom_fields_is_a_registered_drf_field(cf_env, serializer_name):
    """The #290 root cause in one assertion: it used to be ``False`` for all."""
    from rest_api import serializers as s

    assert "custom_fields" in getattr(s, serializer_name)().fields
