"""REST contract for per-blocker SE-Auditor waivers (GH-821).

Issue #821 reported the dead end from the API consumer's side: the gate blocked
with 47 findings, and the only documented exit accepted *all* of them at once
via ``override_reason``. These tests pin the HTTP contract of the per-finding
counterpart on the *existing* baseline create surface (no parallel endpoint):

  * ``waived_findings`` on ``POST /api/v1/workspaces/<id>/baselines/`` accepts
    individual findings, each with its own mandatory reason, and leaves the
    suppression visible on the created baseline;
  * findings that remain unwaived still produce ``SE_AUDITOR_BLOCKED``;
  * an unusable waiver is a plain ``VALIDATION_ERROR`` (400), never a 500;
  * the same approval authority as ``override_reason`` is required (403).
"""
from __future__ import annotations

import uuid

import pytest
from rest_framework.test import APIRequestFactory

from baseline.models import BaselineGateWaiver
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
    """An Extended workspace with guaranteed TRACE-P1 BLOCKER(s).

    Same shape as ``test_baseline_audit_gate_override_513.py`` and
    ``application/tests/test_baseline_audit_gate.py``: a Requirement without any
    upstream link is the smallest reproducible "workspace the auditor declares
    broken".
    """
    from persistence.models import Artifact, Requirement, Tenant, User, Workspace
    from persistence.tenancy import TenantContext

    tenant = Tenant.objects.create(
        id=uuid.uuid4(),
        name="gh821-tenant",
        slug=f"gh821-{uuid.uuid4().hex[:8]}",
    )
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            id=uuid.uuid4(),
            tenant=tenant,
            name=f"gh821-ws-{uuid.uuid4().hex[:6]}",
            preset={"name": "extended"},
        )
        user = User.objects.create(
            id=uuid.uuid4(),
            tenant=tenant,
            username=f"gh821-{uuid.uuid4().hex[:8]}",
            email="gh821@example.com",
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


def _reported_findings(workspace, ctx):
    from application.audit_service import AuditService
    from traceability.audit import AuditScope

    findings = AuditService().blocking_findings(
        workspace.id, ctx, scopes=[AuditScope("project")]
    )
    assert findings, "expected the real auditor to report blockers"
    return findings


def _waiver_payload(findings, *, skip=0):
    return [
        {
            "rule_id": finding.rule_id,
            "artifact_ids": list(finding.artifact_ids),
            "reason": (
                f"Accepted deviation for {finding.rule_id} in the gh821 REST "
                "regression test."
            ),
        }
        for finding in findings[skip:]
    ]


@pytest.mark.django_db
def test_waived_findings_create_the_baseline_and_stay_visible() -> None:
    _, workspace, user = _broken_extended_workspace()
    ctx = _auth_context(user.id, workspace.tenant_id)
    findings = _reported_findings(workspace, ctx)

    response = _post(
        workspace,
        ctx,
        {
            "scope": "project",
            "name": "gh821-waived",
            "description": "Beta cut",
            "waived_findings": _waiver_payload(findings),
        },
    )

    assert response.status_code == 201, response.data
    assert "[SE-Auditor waiver]" in response.data["description"]
    # write_only: reasons are not echoed back as their own field.
    assert "waived_findings" not in response.data

    rows = BaselineGateWaiver.unscoped.filter(workspace_id=workspace.id)
    assert rows.count() == len(findings)
    assert {row.rule_id for row in rows} == {f.rule_id for f in findings}
    assert all(row.reason for row in rows)


@pytest.mark.django_db
def test_partial_waiver_still_blocks_and_names_the_remaining_findings() -> None:
    _, workspace, user = _broken_extended_workspace()
    ctx = _auth_context(user.id, workspace.tenant_id)
    findings = _reported_findings(workspace, ctx)
    if len(findings) < 2:
        pytest.skip("needs at least two findings to leave one unwaived")

    response = _post(
        workspace,
        ctx,
        {
            "scope": "project",
            "name": "gh821-partial",
            "waived_findings": _waiver_payload(findings, skip=1),
        },
    )

    assert response.status_code == 400
    assert response.data["error"]["code"] == "SE_AUDITOR_BLOCKED"
    message = response.data["error"]["message"]
    assert "waived_findings" in message and "override_reason" in message
    # The unwaived finding is named, the waived one is not.
    assert findings[0].rule_id in message
    assert findings[1].rule_id not in message


@pytest.mark.django_db
def test_waiver_without_a_reason_is_rejected_by_the_serializer() -> None:
    _, workspace, user = _broken_extended_workspace()
    ctx = _auth_context(user.id, workspace.tenant_id)
    findings = _reported_findings(workspace, ctx)

    response = _post(
        workspace,
        ctx,
        {
            "scope": "project",
            "name": "gh821-no-reason",
            "waived_findings": [
                {
                    "rule_id": findings[0].rule_id,
                    "artifact_ids": list(findings[0].artifact_ids),
                }
            ],
        },
    )

    assert response.status_code == 400
    assert response.data["error"]["code"] == "VALIDATION_ERROR"
    assert not BaselineGateWaiver.unscoped.filter(
        workspace_id=workspace.id
    ).exists()


@pytest.mark.django_db
def test_waiver_for_an_unreported_finding_is_a_validation_error() -> None:
    """Not a 500, and not silently stored: 400 with the field named."""
    _, workspace, user = _broken_extended_workspace()
    ctx = _auth_context(user.id, workspace.tenant_id)

    response = _post(
        workspace,
        ctx,
        {
            "scope": "project",
            "name": "gh821-unknown",
            "waived_findings": [
                {
                    "rule_id": "CONS-P11",
                    "artifact_ids": [str(uuid.uuid4())],
                    "reason": "Accepted deviation that does not exist anywhere.",
                }
            ],
        },
    )

    assert response.status_code == 400
    assert response.data["error"]["code"] == "VALIDATION_ERROR"
    assert "CONS-P11" in response.data["error"]["message"]
    assert not BaselineGateWaiver.unscoped.filter(
        workspace_id=workspace.id
    ).exists()


@pytest.mark.django_db
def test_editor_waiver_is_rejected_with_403() -> None:
    _, workspace, user = _broken_extended_workspace()
    ctx = _auth_context(user.id, workspace.tenant_id, roles=("editor",))
    findings = _reported_findings(workspace, ctx)

    response = _post(
        workspace,
        ctx,
        {
            "scope": "project",
            "name": "gh821-editor",
            "waived_findings": _waiver_payload(findings),
        },
    )

    assert response.status_code == 403
    assert response.data["error"]["code"] == "PERMISSION_DENIED"
    assert not BaselineGateWaiver.unscoped.filter(
        workspace_id=workspace.id
    ).exists()
