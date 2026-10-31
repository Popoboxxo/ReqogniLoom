"""REST through-path: an Issue is linked to a Requirement via ``references``.

Plan F, F1.1-T1 (``docs/plans/2026-10-21-plan-f-dokumente-baselines.md``):
after consolidating the Issue/Risk link path onto the central link-type
catalog, a user creates an Issue link through the *generic* surface —
``POST /api/v1/trace-links/`` — not through a private ``create_tracelink``
helper. The public contract is unchanged (those helpers were never exposed).

The endpoint resolves the Issue's own id to its backing Artifact id, so the
body carries the user-facing Issue id, exactly as ``GET /api/v1/issues/{id}/``
returns it.
"""
from __future__ import annotations

import uuid

import pytest
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
from link_types.workspace_store import provision_workspace_link_types
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import (
    Artifact,
    Issue,
    Requirement,
    Tenant,
    TraceLink,
    User,
    Workspace,
)

pytestmark = pytest.mark.django_db

_PASSWORD = "hunter2pass"


def _scenario() -> tuple[Tenant, User, Workspace]:
    """Tenant + admin user + extended workspace with a provisioned catalog."""
    suffix = uuid.uuid4().hex[:8]
    tenant = Tenant.objects.create(
        name=f"IR-{suffix}", slug=f"ir-{suffix}", is_active=True
    )
    user = User.objects.create(
        username=f"ir-{suffix}", email=f"ir-{suffix}@t.test", tenant=tenant
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])

    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="IR WS", preset={"name": "extended"}
        )
        # Link validation is always-on: an unprovisioned workspace rejects
        # every trace link.
        provision_workspace_link_types(workspace_id=workspace.id, tenant_id=tenant.id)
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_ADMIN
        )
    finally:
        clear_request_tenant()
    return tenant, user, workspace


def _issue(tenant: Tenant, workspace: Workspace, title: str) -> Issue:
    set_request_tenant(tenant.id)
    try:
        artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="Issue"
        )
        return Issue.objects.create(
            tenant=tenant,
            workspace_id=workspace.id,
            artifact=artifact,
            title=title,
            severity="high",
        )
    finally:
        clear_request_tenant()


def _requirement(tenant: Tenant, workspace: Workspace, title: str) -> Requirement:
    set_request_tenant(tenant.id)
    try:
        artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="Requirement"
        )
        return Requirement.objects.create(
            tenant=tenant,
            workspace=workspace,
            artifact=artifact,
            title=title,
            description="rest through-path fixture",
        )
    finally:
        clear_request_tenant()


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


def test_post_trace_link_issue_references_201() -> None:
    tenant, user, workspace = _scenario()
    issue = _issue(tenant, workspace, "Login button broken")
    requirement = _requirement(tenant, workspace, "Login form shall validate")

    resp = _client(user).post(
        "/api/v1/trace-links/",
        {
            "source_id": str(issue.id),
            "target_id": str(requirement.id),
            "link_type": "references",
            "rationale": "blocks",
        },
        format="json",
    )

    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert body["link_type"] == "references"
    assert body["rationale"] == "blocks"
    # The Issue's own id was resolved to its backing Artifact id.
    assert body["source_id"] == str(issue.artifact_id)
    assert body["target_id"] == str(requirement.artifact_id)

    # The request middleware clears the thread-local tenant context again, so
    # the assertion query has to re-activate it.
    set_request_tenant(tenant.id)
    try:
        link = TraceLink.objects.get(id=body["id"])
        assert link.source.artifact_type == "Issue"
        assert link.target.artifact_type == "Requirement"
    finally:
        clear_request_tenant()
