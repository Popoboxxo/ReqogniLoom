"""``artifact_id`` parity for the artifact-backed governance entities (#1763).

leaf_id : COMP-RA-AD, COMP-RA-RK, COMP-RA-IS, COMP-RA-MG
req_id  : REQ-L2-RA-001, REQ-L2-TE-020, REQ-L1-029

The Inspector's comment panel addresses comments by **Artifact**, not by the
per-type entity id (see the frontend ``RightSidebar`` fix that split
``entityId`` from ``artifactId``). Requirement, ArchitectureElement and
TestCase responses already expose the backing Artifact id through their DTOs;
Adr, Risk, Issue and MainGoal did not, so their comment tabs fell back to
"not available" even though the rows do have a backing Artifact.

These are the four regression cases: each entity is created through the real
middleware stack (JWT, RBAC, service layer, test database) and the response
must carry an ``artifact_id`` that matches the row's actual backing Artifact —
not merely a present-but-null key.
"""
from __future__ import annotations

import uuid

import pytest
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Adr, Issue, MainGoal, Risk, Tenant, User, Workspace

pytestmark = pytest.mark.django_db

_PASSWORD = "hunter2pass"


def _scenario() -> tuple[Tenant, User, Workspace]:
    """Create a tenant, one admin user and one Extended-preset workspace."""
    suffix = uuid.uuid4().hex[:8]
    tenant = Tenant.objects.create(
        name=f"T-{suffix}", slug=f"ai-{suffix}", is_active=True
    )
    user = User.objects.create(
        username=f"ai-{suffix}", email=f"ai-{suffix}@t.test", tenant=tenant
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])

    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="AI WS", preset={"name": "extended"}
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


def _stored_artifact_id(tenant: Tenant, model, entity_id: str):
    """Read the backing Artifact id straight from the row (bypass the DTO)."""
    set_request_tenant(tenant.id)
    try:
        return model.objects.get(id=entity_id).artifact_id
    finally:
        clear_request_tenant()


def _assert_artifact_id_matches(tenant: Tenant, model, body: dict) -> None:
    assert "artifact_id" in body, "the DTO must ship the backing Artifact id"
    assert body["artifact_id"] is not None, "every new entity gets an Artifact"
    stored = _stored_artifact_id(tenant, model, body["id"])
    assert stored is not None, "the service layer must have created the Artifact"
    assert body["artifact_id"] == str(stored)


def test_adr_response_carries_the_backing_artifact_id() -> None:
    tenant, user, workspace = _scenario()
    client = _client(user)

    resp = client.post(
        "/api/v1/adrs/",
        {
            "workspace_id": str(workspace.id),
            "title": "Artifact id parity",
            "description": "the inspector comment tab needs this",
        },
        format="json",
    )
    assert resp.status_code == 201, resp.content
    body = resp.json()
    _assert_artifact_id_matches(tenant, Adr, body)

    detail = client.get(f"/api/v1/adrs/{body['id']}/")
    assert detail.status_code == 200, detail.content
    assert detail.json()["artifact_id"] == body["artifact_id"]


def test_risk_response_carries_the_backing_artifact_id() -> None:
    tenant, user, workspace = _scenario()
    client = _client(user)

    resp = client.post(
        "/api/v1/risks/",
        {
            "workspace_id": str(workspace.id),
            "title": "Artifact id parity",
            "probability": "high",
            "impact": "medium",
        },
        format="json",
    )
    assert resp.status_code == 201, resp.content
    body = resp.json()
    _assert_artifact_id_matches(tenant, Risk, body)

    detail = client.get(f"/api/v1/risks/{body['id']}/")
    assert detail.status_code == 200, detail.content
    assert detail.json()["artifact_id"] == body["artifact_id"]


def test_issue_response_carries_the_backing_artifact_id() -> None:
    tenant, user, workspace = _scenario()
    client = _client(user)

    resp = client.post(
        "/api/v1/issues/",
        {
            "workspace_id": str(workspace.id),
            "title": "Artifact id parity",
            "severity": "low",
            "category": "defect",
        },
        format="json",
    )
    assert resp.status_code == 201, resp.content
    body = resp.json()
    _assert_artifact_id_matches(tenant, Issue, body)

    detail = client.get(f"/api/v1/issues/{body['id']}/")
    assert detail.status_code == 200, detail.content
    assert detail.json()["artifact_id"] == body["artifact_id"]


def test_main_goal_response_carries_the_backing_artifact_id() -> None:
    tenant, user, workspace = _scenario()
    client = _client(user)

    resp = client.post(
        "/api/v1/main-goals/",
        {
            "workspace_id": str(workspace.id),
            "content": "the product shall delight its users",
        },
        format="json",
    )
    assert resp.status_code == 201, resp.content
    body = resp.json()
    _assert_artifact_id_matches(tenant, MainGoal, body)

    detail = client.get(f"/api/v1/main-goals/{body['id']}/")
    assert detail.status_code == 200, detail.content
    assert detail.json()["artifact_id"] == body["artifact_id"]
