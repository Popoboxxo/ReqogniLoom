"""#1483 — a soft-delete's ``change_reason`` must reach the audit trail.

Every ``delete_*`` / ``delete`` service method accepts a ``change_reason``
(body of the DELETE request, or ``?change_reason=`` for clients that cannot
attach a body) and parses it — but until this fix it was passed only to
``workflow.services.outdate(reason=...)``, whose ``reason`` argument has been
inert since the Phase-4 soft-delete refactor (it writes no history entry).
The ``AuditEntry`` written right after it was created without the reason, so
``AuditEntry.change_reason`` stayed NULL for every soft-delete that did carry
one.

These tests drive the real HTTP → view → service → audit stack on purpose: the
bug lived exactly in the seam between those layers, so any mock would hide it.
The assertion is on the exact reason string, not merely on "non-empty" — a
field that silently receives the wrong value is the failure mode being
guarded here.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import quote

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from application.workspace_provisioning import provision_workspace_defaults
from auth_tenancy.models import ROLE_ADMIN, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace

_SECRET = "test-secret-not-a-real-key"

_JWT_OVERRIDES = {
    "AUTH_JWT_SECRET": _SECRET,
    "AUTH_JWT_ISSUER": "reqflow",
    "AUTH_JWT_AUDIENCE": "reqflow-api",
    "AUTH_JWT_TTL_SECONDS": 3600,
}


@pytest.fixture
def sd_env(db):
    """Tenant + admin + one workspace on the standard preset."""
    tenant = Tenant.objects.create(name="SD1483 T", slug="sd1483-t", is_active=True)
    admin = User.objects.create(
        username="sd1483admin", email="sd1483admin@t.test", tenant=tenant
    )
    admin.set_password("sd1483pass123")
    admin.save(update_fields=["password"])
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="SD1483 WS", preset={"name": "standard"}
        )
        # The same seeding the WorkspaceService write path performs: without a
        # WorkflowDefinition for the entity type, workflow.services.outdate()
        # raises before the audit entry is ever reached.
        provision_workspace_defaults(
            workspace_id=workspace.id,
            tenant_id=tenant.id,
            requirement_preset="standard",
        )
        UserRole.objects.create(
            tenant=tenant, user=admin, workspace=workspace, role=ROLE_ADMIN
        )
        yield {"tenant": tenant, "workspace": workspace, "admin": admin}
    finally:
        clear_request_tenant()


def _client(sd_env: dict) -> APIClient:
    client = APIClient()
    resp = client.post(
        "/api/v1/auth/login/",
        {"username": "sd1483admin", "password": "sd1483pass123"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.json()['token']}")
    return client


def _create(client: APIClient, path: str, payload: dict[str, Any]) -> dict:
    resp = client.post(path, payload, format="json")
    assert resp.status_code == 201, resp.content
    return resp.json()


def _delete(client: APIClient, path: str, reason: str) -> Any:
    """DELETE *path* with the reason as a query-string fallback (G1.5/#1407).

    Percent-encoded on purpose: a raw ``#`` in the query string would start a
    URL fragment, so the reason would silently arrive truncated.
    """
    return client.delete(f"{path}?change_reason={quote(reason, safe='')}")


def _delete_audit_reason(entity_id: str) -> str | None:
    """The reason on the latest DELETE audit entry for *entity_id*."""
    from audit.models import AuditEntry

    entry = (
        AuditEntry.objects.filter(entity_id=entity_id, op="delete")
        .order_by("-timestamp")
        .first()
    )
    assert entry is not None, f"no delete audit entry recorded for {entity_id}"
    return entry.change_reason


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_adr_delete_change_reason_is_audited(sd_env):
    """DELETE /api/v1/adrs/{id}/?change_reason=… → 204, reason on the audit row."""
    client = _client(sd_env)
    created = _create(
        client,
        "/api/v1/adrs/",
        {
            "workspace_id": str(sd_env["workspace"].id),
            "title": "ADR #1483",
            "description": "soft-delete reason regression",
        },
    )

    resp = _delete(client, f"/api/v1/adrs/{created['id']}/", "superseded by ADR-0042")

    assert resp.status_code == 204, resp.content
    assert _delete_audit_reason(created["id"]) == "superseded by ADR-0042"


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_risk_delete_change_reason_is_audited(sd_env):
    """DELETE /api/v1/risks/{id}/?change_reason=… → 204, reason on the audit row."""
    client = _client(sd_env)
    created = _create(
        client,
        "/api/v1/risks/",
        {
            "workspace_id": str(sd_env["workspace"].id),
            "title": "Risk #1483",
            "probability": "low",
            "impact": "low",
        },
    )

    resp = _delete(
        client, f"/api/v1/risks/{created['id']}/", "threat retired with the component"
    )

    assert resp.status_code == 204, resp.content
    assert _delete_audit_reason(created["id"]) == "threat retired with the component"


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_issue_delete_change_reason_is_audited(sd_env):
    """DELETE /api/v1/issues/{id}/?change_reason=… → 204, reason on the audit row."""
    client = _client(sd_env)
    created = _create(
        client,
        "/api/v1/issues/",
        {
            "workspace_id": str(sd_env["workspace"].id),
            "title": "Issue #1483",
        },
    )

    resp = _delete(client, f"/api/v1/issues/{created['id']}/", "duplicate of #1471")

    assert resp.status_code == 204, resp.content
    assert _delete_audit_reason(created["id"]) == "duplicate of #1471"


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_glossary_term_delete_change_reason_is_audited(sd_env):
    """DELETE /api/v1/glossary/{id}/?change_reason=… → 204, reason on the audit row.

    This path had no AuditEntry at all before #1483, so the reason had nowhere
    to land (REQ-L2-AS-019).
    """
    client = _client(sd_env)
    created = _create(
        client,
        "/api/v1/glossary/",
        {
            "workspace_id": str(sd_env["workspace"].id),
            "term": "Requirement",
            "definition": "A statement of a need or obligation.",
        },
    )

    resp = _delete(
        client, f"/api/v1/glossary/{created['id']}/", "merged into Stakeholder Need"
    )

    assert resp.status_code == 204, resp.content
    assert _delete_audit_reason(created["id"]) == "merged into Stakeholder Need"


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_requirement_delete_change_reason_is_audited(sd_env):
    """DELETE /api/v1/requirements/{id}/?change_reason=… → 204, reason on the audit row.

    Same-class defect as the four cases above: ``delete_requirement`` enforced
    the preset policy on ``change_reason`` and then dropped it before
    ``_audit(...)``, so the policy was checked but never recorded.
    """
    client = _client(sd_env)
    created = _create(
        client,
        "/api/v1/requirements/",
        {
            "workspace_id": str(sd_env["workspace"].id),
            "title": "Requirement #1483",
            "description": "the system shall survive a soft delete with its reason",
        },
    )

    resp = _delete(
        client, f"/api/v1/requirements/{created['id']}/", "obsoleted by REQ-L1-0042"
    )

    assert resp.status_code == 204, resp.content
    assert _delete_audit_reason(created["id"]) == "obsoleted by REQ-L1-0042"


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_architecture_element_delete_change_reason_is_audited(sd_env):
    """DELETE /api/v1/architecture/{id}/?change_reason=… → 204, reason on the audit row.

    Forwarding case: ``delete_architecture_element`` already wrote the delete
    ``AuditEntry``; only the caller's reason was missing from it, so the entry
    recorded *that* the element was deleted but not *why*.
    """
    client = _client(sd_env)
    created = _create(
        client,
        "/api/v1/architecture/",
        {
            "workspace_id": str(sd_env["workspace"].id),
            "title": "Component #1483",
            "element_type": "component",
        },
    )

    resp = _delete(
        client,
        f"/api/v1/architecture/{created['id']}/",
        "superseded by the block-level split",
    )

    assert resp.status_code == 204, resp.content
    assert (
        _delete_audit_reason(created["id"])
        == "superseded by the block-level split"
    )


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_change_request_delete_change_reason_is_audited(sd_env):
    """DELETE /api/v1/change-requests/{id}/?change_reason=… → 204, reason on the audit row.

    Forwarding case, same shape as the architecture element above.
    """
    client = _client(sd_env)
    created = _create(
        client,
        "/api/v1/change-requests/",
        {
            "workspace_id": str(sd_env["workspace"].id),
            "title": "Change request #1483",
        },
    )

    resp = _delete(
        client,
        f"/api/v1/change-requests/{created['id']}/",
        "withdrawn by the CCB on 2026-10-23",
    )

    assert resp.status_code == 204, resp.content
    assert (
        _delete_audit_reason(created["id"])
        == "withdrawn by the CCB on 2026-10-23"
    )


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_test_case_delete_change_reason_is_audited(sd_env):
    """DELETE /api/v1/testcases/{id}/?change_reason=… → 204, reason on the audit row.

    Forwarding case, same shape as the architecture element above.
    """
    client = _client(sd_env)
    created = _create(
        client,
        "/api/v1/testcases/",
        {
            "workspace_id": str(sd_env["workspace"].id),
            "title": "Test case #1483",
        },
    )

    resp = _delete(
        client,
        f"/api/v1/testcases/{created['id']}/",
        "replaced by the integration-level case",
    )

    assert resp.status_code == 204, resp.content
    assert (
        _delete_audit_reason(created["id"])
        == "replaced by the integration-level case"
    )


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_stakeholder_need_delete_change_reason_is_audited(sd_env):
    """DELETE /api/v1/needs/{id}/?change_reason=… → 204, reason on the audit row.

    Not merely a forwarding defect like the three cases above: this path wrote
    no delete ``AuditEntry`` at all, although it did enforce the preset policy
    on ``change_reason`` — the reason was validated and then silently dropped.
    """
    client = _client(sd_env)
    created = _create(
        client,
        "/api/v1/needs/",
        {
            "workspace_id": str(sd_env["workspace"].id),
            "title": "Need #1483",
        },
    )

    resp = _delete(
        client,
        f"/api/v1/needs/{created['id']}/",
        "covered by the merged stakeholder need",
    )

    assert resp.status_code == 204, resp.content
    assert (
        _delete_audit_reason(created["id"])
        == "covered by the merged stakeholder need"
    )
