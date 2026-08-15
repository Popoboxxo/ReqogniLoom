"""REST contract for the SE-Auditor baseline gate override (GH-513).

GH-490 made the gate fail closed; GH-451 left most findings unfixable from the
Auditor UI. Together they deadlocked every workspace with at least one BLOCKER:
no baseline, no release, no correction path. The escape hatch is an explicit
``override_reason`` — this module pins the HTTP contract around it:

  * blocked responses carry a *distinct* error code so a client can offer the
    override instead of showing a dead validation error;
  * the override needs approval authority (403 for an Editor);
  * an accepted override creates the baseline and leaves the waiver visible.
"""
from __future__ import annotations

import uuid

import pytest
from rest_framework.test import APIRequestFactory

from rest_api.views import BaselineViewSet


@pytest.fixture(autouse=True)
def _clear_preset_cache():
    """The preset tier is cached process-wide; keep tests independent."""
    yield
    from presets import gate

    with gate._cache_lock:
        gate._tier_cache.clear()


def _auth_context(user_id: uuid.UUID, tenant_id: uuid.UUID, *, roles=("admin",)):
    from auth_tenancy.context import AuthContext, AuthMethod

    return AuthContext(
        user_id=user_id,
        tenant_id=tenant_id,
        active_roles=roles,
        auth_method=AuthMethod.BEARER_TOKEN,
    )


def _broken_extended_workspace():
    """An Extended workspace with a guaranteed TRACE-P1 BLOCKER.

    Same shape as ``application/tests/test_baseline_audit_gate.py``: a
    Requirement without any upstream link is the smallest reproducible
    "workspace the auditor declares broken".
    """
    from persistence.models import Artifact, Requirement, Tenant, User, Workspace
    from persistence.tenancy import TenantContext

    tenant = Tenant.objects.create(
        id=uuid.uuid4(),
        name="gh513-tenant",
        slug=f"gh513-{uuid.uuid4().hex[:8]}",
    )
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            id=uuid.uuid4(),
            tenant=tenant,
            name=f"gh513-ws-{uuid.uuid4().hex[:6]}",
            preset={"name": "extended"},
        )
        user = User.objects.create(
            id=uuid.uuid4(),
            tenant=tenant,
            username=f"gh513-{uuid.uuid4().hex[:8]}",
            email="gh513@example.com",
        )
        artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="requirement"
        )
        Requirement.objects.create(
            tenant=tenant, artifact=artifact, title="Orphan requirement"
        )
    finally:
        TenantContext.clear_tenant()
    return tenant, workspace, user


def _post(workspace, ctx, body):
    from persistence.tenancy import TenantContext

    factory = APIRequestFactory()
    req = factory.post(
        f"/api/v1/workspaces/{workspace.id}/baselines/", data=body, format="json"
    )
    req.auth_context = ctx
    view = BaselineViewSet.as_view({"post": "create"})
    # A direct view() call bypasses persistence.middleware, which is what sets
    # the thread-local tenant in production (see test_baseline_workspace_routing).
    TenantContext.set_tenant(workspace.tenant_id)
    try:
        return view(req, workspace_pk=str(workspace.id))
    finally:
        TenantContext.clear_tenant()


@pytest.mark.django_db
def test_blocked_creation_answers_a_distinct_error_code() -> None:
    _, workspace, user = _broken_extended_workspace()
    ctx = _auth_context(user.id, workspace.tenant_id)

    response = _post(workspace, ctx, {"scope": "project", "name": "gh513-blocked"})

    assert response.status_code == 400
    assert response.data["error"]["code"] == "SE_AUDITOR_BLOCKED"
    # The message must name the way out, not just the verdict.
    assert "override_reason" in response.data["error"]["message"]


@pytest.mark.django_db
def test_editor_override_is_rejected_with_403() -> None:
    _, workspace, user = _broken_extended_workspace()
    ctx = _auth_context(user.id, workspace.tenant_id, roles=("editor",))

    response = _post(
        workspace,
        ctx,
        {
            "scope": "project",
            "name": "gh513-editor",
            "override_reason": "We need the baseline for tomorrow's demo.",
        },
    )

    assert response.status_code == 403
    assert response.data["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.django_db
def test_admin_override_creates_the_baseline_and_keeps_the_waiver_visible() -> None:
    _, workspace, user = _broken_extended_workspace()
    ctx = _auth_context(user.id, workspace.tenant_id)

    response = _post(
        workspace,
        ctx,
        {
            "scope": "project",
            "name": "gh513-waived",
            "description": "Beta cut",
            "override_reason": "Open trace findings accepted for the beta cut (GH-513).",
        },
    )

    assert response.status_code == 201, response.data
    assert "SE-Auditor override" in response.data["description"]
    assert "TRACE-P1" in response.data["description"]
    # write_only: the justification is not echoed back as its own field.
    assert "override_reason" not in response.data


@pytest.mark.django_db
def test_blank_override_reason_still_blocks() -> None:
    """An empty string must not be mistaken for a granted waiver."""
    _, workspace, user = _broken_extended_workspace()
    ctx = _auth_context(user.id, workspace.tenant_id)

    response = _post(
        workspace,
        ctx,
        {"scope": "project", "name": "gh513-blank", "override_reason": "   "},
    )

    assert response.status_code == 400
    assert response.data["error"]["code"] == "SE_AUDITOR_BLOCKED"
