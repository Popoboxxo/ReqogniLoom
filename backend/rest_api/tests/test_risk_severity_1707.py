"""#1707 — one carrier, one type, a configurable write policy for ``Risk.severity``.

REST-level coverage of the contract: the value is writable on create and on
update as an enum, an omitted value is initialised from the score, a PATCH that
does not mention it never changes it, and a workspace that marks the attribute
``editable="automation"`` refuses client values while still tolerating the
unchanged echo a detail panel resends.

The definition shape (one carrier, ``enum`` type, per-preset visibility) is
covered in ``attribute_definitions/tests/test_risk_severity_1707.py``.
"""
from __future__ import annotations

import uuid

import pytest
from django.core.management import call_command
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace

pytestmark = pytest.mark.django_db

_PASSWORD = "hunter2pass"


def _admin_client(preset: str = "extended") -> tuple[APIClient, Workspace]:
    """Fresh tenant/workspace/admin on *preset*, bootstrapped and logged in."""
    suffix = uuid.uuid4().hex[:8]
    tenant = Tenant.objects.create(
        name=f"Sev-{suffix}", slug=f"sev-{suffix}", is_active=True
    )
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="severity ws", preset={"name": preset}
        )
        user = User.objects.create(
            username=f"sev-{suffix}", email=f"sev-{suffix}@t.test", tenant=tenant
        )
        user.set_password(_PASSWORD)
        user.save(update_fields=["password"])
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_ADMIN
        )
    finally:
        clear_request_tenant()

    call_command("bootstrap_attribute_definitions", tenant=str(tenant.id))

    client = APIClient()
    login = client.post(
        "/api/v1/auth/login/",
        {"username": user.username, "password": _PASSWORD},
        format="json",
    )
    assert login.status_code == 200, login.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['token']}")
    return client, workspace


def _set_severity_policy(workspace: Workspace, *, editable: object) -> None:
    """Rewrite ``severity``'s ``editable`` value in the workspace definition."""
    from application.cache_invalidation import invalidate_workspace_caches
    from attribute_definitions.workspace_definition_store import (
        WorkspaceAttributeDefinitionStore,
    )

    # The bootstrap writes the global defaults; the per-workspace row is
    # materialized on first resolve.
    row = WorkspaceAttributeDefinitionStore().resolve(
        workspace.tenant_id, workspace.id, "Risk", "extended"
    )
    definition = dict(row.definition_json)
    attributes = [dict(attribute) for attribute in definition["attributes"]]
    for attribute in attributes:
        if attribute["name"] == "severity":
            attribute["editable"] = editable
            break
    else:  # pragma: no cover - bootstrap always carries the attribute
        raise AssertionError("severity is absent from the bootstrapped definition")
    definition["attributes"] = attributes
    row.definition_json = definition
    row.save(update_fields=["definition_json", "modified_at"])
    invalidate_workspace_caches(workspace.id)


def _create(client: APIClient, workspace: Workspace, **extra) -> object:
    body = {"workspace_id": str(workspace.id), "title": "Severity risk", **extra}
    return client.post("/api/v1/risks/", body, format="json")


# ---------------------------------------------------------------------------
# Writable enum
# ---------------------------------------------------------------------------


def test_create_with_severity_is_persisted_and_read_back() -> None:
    client, workspace = _admin_client()
    created = _create(client, workspace, severity="high", probability="low", impact="low")

    assert created.status_code == 201, created.content
    body = created.json()
    assert body["severity"] == "high", "the client value wins over the score"
    assert body["risk_score"] == 1, "low x low"

    detail = client.get(f"/api/v1/risks/{body['id']}/")
    assert detail.status_code == 200, detail.content
    assert detail.json()["severity"] == "high"


def test_patch_with_severity_is_writable() -> None:
    client, workspace = _admin_client()
    risk_id = _create(client, workspace, severity="low").json()["id"]

    patched = client.patch(
        f"/api/v1/risks/{risk_id}/", {"severity": "high"}, format="json"
    )

    assert patched.status_code == 200, patched.content
    assert patched.json()["severity"] == "high"


def test_numeric_severity_is_rejected_with_the_enum_message() -> None:
    client, workspace = _admin_client()
    resp = _create(client, workspace, severity=7)

    assert resp.status_code == 400, resp.content
    details = {detail["field"]: detail["errors"] for detail in resp.json()["error"]["details"]}
    assert "severity" in details
    assert any("valid choice" in message for message in details["severity"]), details


def test_omitted_severity_is_initialised_from_the_score() -> None:
    client, workspace = _admin_client()
    created = _create(client, workspace, probability="high", impact="high")

    assert created.status_code == 201, created.content
    body = created.json()
    assert body["risk_score"] == 9
    assert body["severity"] == "high", "9 >= 9 -> high"


def test_patch_without_severity_does_not_touch_it() -> None:
    client, workspace = _admin_client()
    risk_id = _create(client, workspace, severity="high").json()["id"]

    patched = client.patch(
        f"/api/v1/risks/{risk_id}/",
        {"probability": "low", "impact": "low"},
        format="json",
    )

    assert patched.status_code == 200, patched.content
    body = patched.json()
    assert body["risk_score"] == 1, "the score is still recomputed"
    assert body["severity"] == "high", "a manual severity survives a score change"


# ---------------------------------------------------------------------------
# automation policy
# ---------------------------------------------------------------------------


def test_automation_rejects_a_differing_value() -> None:
    client, workspace = _admin_client()
    _set_severity_policy(workspace, editable="automation")

    resp = _create(client, workspace, severity="low", probability="high", impact="high")

    assert resp.status_code == 400, resp.content
    details = {detail["field"]: detail["errors"] for detail in resp.json()["error"]["details"]}
    assert "severity" in details
    assert any("derived automatically" in message for message in details["severity"]), details


def test_automation_derives_the_value_from_the_score() -> None:
    client, workspace = _admin_client()
    _set_severity_policy(workspace, editable="automation")

    created = _create(client, workspace, probability="high", impact="high")

    assert created.status_code == 201, created.content
    assert created.json()["severity"] == "high"


def test_automation_tolerates_the_unchanged_echo_but_refuses_a_change() -> None:
    client, workspace = _admin_client()
    _set_severity_policy(workspace, editable="automation")
    risk_id = _create(client, workspace, probability="high", impact="high").json()["id"]

    echoed = client.patch(
        f"/api/v1/risks/{risk_id}/",
        {"severity": "high", "mitigation_strategy": "mitigate"},
        format="json",
    )
    assert echoed.status_code == 200, echoed.content
    assert echoed.json()["mitigation_strategy"] == "mitigate"

    changed = client.patch(
        f"/api/v1/risks/{risk_id}/", {"severity": "low"}, format="json"
    )
    assert changed.status_code == 400, changed.content


def test_automation_recomputes_severity_when_the_score_changes() -> None:
    client, workspace = _admin_client()
    _set_severity_policy(workspace, editable="automation")
    risk_id = _create(client, workspace, probability="high", impact="high").json()["id"]

    patched = client.patch(
        f"/api/v1/risks/{risk_id}/",
        {"probability": "low", "impact": "low"},
        format="json",
    )

    assert patched.status_code == 200, patched.content
    assert patched.json()["severity"] == "low", "server-derived, not sticky"


@pytest.mark.parametrize("preset", ["minimal", "standard", "extended"])
def test_severity_is_writable_in_every_rigor_preset(preset: str) -> None:
    """The manual default must not depend on the workspace's rigor stage."""
    client, workspace = _admin_client(preset=preset)

    created = _create(client, workspace, severity="medium")

    assert created.status_code == 201, created.content
    assert created.json()["severity"] == "medium"
