"""#399 — baseline drift marking on the REST surface.

Cluster-5 spec section 6.3: the membership endpoint, the additive
``baseline_drift`` summary on ``retrieve``, and the write-only
``affected_item_ids`` prefill of the drift badge's "raise change request"
shortcut. The service-level semantics (drift verdicts, tenant-context
save/restore) live in ``application/tests/test_baseline_drift_399.py``.
"""
from __future__ import annotations

import uuid

import pytest

from persistence.models import Artifact, Requirement, User

pytestmark = pytest.mark.django_db


@pytest.fixture
def drift_env(authed_client, tenant, workspace):
    """A baselined requirement in the shared REST fixture workspace."""
    from application.baseline_facade import BaselineFacade
    from auth_tenancy.context import AuthContext, AuthMethod
    from persistence.middleware import clear_request_tenant, set_request_tenant

    set_request_tenant(tenant.id)
    try:
        user = User.objects.filter(tenant=tenant).first()
        ctx = AuthContext(
            user_id=user.id,
            tenant_id=tenant.id,
            active_roles=("admin",),
            auth_method=AuthMethod.BEARER_TOKEN,
            workspace_id=workspace.id,
        )
        artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="Requirement"
        )
        req = Requirement.objects.create(
            tenant=tenant, artifact=artifact, title="Baselined req"
        )
        BaselineFacade().create_baseline(
            scope="project",
            workspace_id=workspace.id,
            name="REST-B1",
            ctx=ctx,
            override_reason="fixture baseline for drift marking test",
        )
    finally:
        clear_request_tenant()
    return authed_client, tenant, workspace, artifact, req


def _patch_title(client, req, title="Renamed via REST"):
    return client.patch(
        f"/api/v1/requirements/{req.id}/",
        {"title": title, "change_reason": "rename"},
        format="json",
    )


def test_membership_endpoint_reports_drift(drift_env):
    """AC-D1-1 (REST half)."""
    client, tenant, workspace, artifact, req = drift_env

    patch = _patch_title(client, req)
    assert patch.status_code == 200, patch.content

    resp = client.get(f"/api/v1/artifacts/{artifact.id}/baseline-membership/")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["artifact_id"] == str(artifact.id)
    assert body["drifted"] is True
    assert len(body["memberships"]) == 1
    entry = body["memberships"][0]
    assert entry["baseline_name"] == "REST-B1"
    assert entry["scope"] == "project"
    assert entry["drifted"] is True
    assert entry["drift_known"] is True
    assert entry["baselined_at"]


def test_membership_endpoint_is_undrifted_without_an_edit(drift_env):
    """AC-D1-2 (REST half)."""
    client, tenant, workspace, artifact, req = drift_env

    resp = client.get(f"/api/v1/artifacts/{artifact.id}/baseline-membership/")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["drifted"] is False
    assert body["memberships"][0]["drifted"] is False


def test_membership_endpoint_is_empty_without_baseline(authed_client, tenant, workspace):
    """AC-D1-3 (REST half)."""
    from persistence.middleware import clear_request_tenant, set_request_tenant

    set_request_tenant(tenant.id)
    try:
        artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="Requirement"
        )
    finally:
        clear_request_tenant()

    resp = authed_client.get(f"/api/v1/artifacts/{artifact.id}/baseline-membership/")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["memberships"] == []
    assert body["drifted"] is False


def test_membership_endpoint_404_for_an_unknown_artifact(authed_client):
    resp = authed_client.get(
        f"/api/v1/artifacts/{uuid.uuid4()}/baseline-membership/"
    )
    assert resp.status_code == 404, resp.content


def test_membership_endpoint_is_tenant_scoped(authed_client, tenant, workspace):
    """AC-D1-7: another tenant's artifact is invisible (404, never metadata)."""
    from persistence.middleware import clear_request_tenant, set_request_tenant
    from persistence.models import Tenant, Workspace

    other = Tenant.objects.create(
        name="other-tenant-399", slug=f"other-399-{uuid.uuid4().hex[:8]}"
    )
    set_request_tenant(other.id)
    try:
        other_ws = Workspace.objects.create(tenant=other, name="other-ws-399")
        other_artifact = Artifact.objects.create(
            tenant=other, workspace=other_ws, artifact_type="Requirement"
        )
    finally:
        clear_request_tenant()

    resp = authed_client.get(
        f"/api/v1/artifacts/{other_artifact.id}/baseline-membership/"
    )
    assert resp.status_code == 404, resp.content


def test_requirement_retrieve_carries_the_drift_summary(drift_env):
    client, tenant, workspace, artifact, req = drift_env

    before = client.get(f"/api/v1/requirements/{req.id}/")
    assert before.status_code == 200, before.content
    assert before.json()["baseline_drift"] == {"drifted": False, "count": 0}

    assert _patch_title(client, req).status_code == 200

    after = client.get(f"/api/v1/requirements/{req.id}/")
    assert after.json()["baseline_drift"] == {"drifted": True, "count": 1}


def test_change_request_prefill_accepts_affected_item_ids(drift_env):
    """AC-D1-11 (contract half): write-only prefill from the drift badge."""
    client, tenant, workspace, artifact, req = drift_env

    resp = client.post(
        "/api/v1/change-requests/",
        {
            "workspace_id": str(workspace.id),
            "title": "Align baselined requirement",
            "affected_item_ids": [str(artifact.id)],
        },
        format="json",
    )
    assert resp.status_code == 201, resp.content
    assert "affected_item_ids" not in resp.json()


def test_change_request_prefill_rejects_an_unknown_item(drift_env):
    client, tenant, workspace, artifact, req = drift_env

    resp = client.post(
        "/api/v1/change-requests/",
        {
            "workspace_id": str(workspace.id),
            "title": "Bad prefill",
            "affected_item_ids": [str(uuid.uuid4())],
        },
        format="json",
    )
    assert resp.status_code == 400, resp.content
