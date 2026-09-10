"""L2.1 regression: formalize() works for every in-scope artifact type.

One parametrized round trip per type -- start, answer the protocol's required
fields, formalize, then assert the artifact exists with the right
``artifact_type`` and an initialized workflow state. Requirement is included
(not only the 7 new types) so the parametrization is the single place the
per-type contract is stated.
"""
from __future__ import annotations

import uuid

import pytest

from application.interview_protocol import IN_SCOPE_ARTIFACT_TYPES
from application.interview_service import InterviewService
from auth_tenancy.context import AuthContext, AuthMethod
from persistence.models import Artifact, Tenant, User, Workspace
from persistence.tenancy import TenantContext
from workflow.services import create_default_workflow


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="IFA Tenant", slug="ifa-tenant")


@pytest.fixture
def workspace(tenant):
    TenantContext.set_tenant(tenant.id)
    try:
        ws = Workspace.objects.create(tenant=tenant, name="WS", goals_enabled=True)
        # A real WorkflowItemState only materializes if a workflow definition
        # exists for (workspace, item_type) -- initialize_workflow_states()
        # no-ops silently otherwise (graceful degradation for an
        # unconfigured type, not a bug). Provision the standard preset for
        # every in-scope type so the workflow-state assertion below is a
        # real integration check, not a false negative on a bare fixture.
        for artifact_type in IN_SCOPE_ARTIFACT_TYPES:
            create_default_workflow(
                workspace_id=ws.id,
                preset="standard",
                item_type=artifact_type,
                tenant_id=tenant.id,
            )
        return ws
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def ctx(tenant):
    # A real User row: StakeholderNeedService.create() (unlike several of the
    # sibling create_X() methods) sets created_by=ctx.user_id with a real FK
    # to pl_user -- a bare uuid4() 404s on the constraint, not on business logic.
    TenantContext.set_tenant(tenant.id)
    try:
        user = User.objects.create(
            username="ifa-user", email="ifa@t.test", tenant=tenant
        )
    finally:
        TenantContext.clear_tenant()
    return AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
    )


#: Values to answer per protocol field type. The factory-default protocol asks
#: title+rationale for every type; Risk additionally asks probability+impact
#: (enum low/medium/high, see interview_protocol._EXTRA_REQUIRED_FIELDS).
_ENUM_ANSWER = "high"


def _answer_all_required_fields(svc: InterviewService, ctx, session_id) -> None:
    """Answer whatever the resolved protocol declares as still missing."""
    state = svc.get_state(ctx, session_id)
    for field in state["missing_fields"]:
        if field["type"] == "enum":
            value = (field.get("choices") or [_ENUM_ANSWER])[0]
        elif field["type"] == "number":
            value = 1
        else:
            value = f"Interview answer for {field['name']}"
        svc.answer(ctx, session_id, field["name"], value)


@pytest.mark.parametrize("artifact_type", IN_SCOPE_ARTIFACT_TYPES)
def test_formalize_creates_the_artifact_for_every_in_scope_type(
    ctx, workspace, artifact_type
):
    svc = InterviewService()
    session = svc.start(ctx, artifact_type, workspace.id)
    _answer_all_required_fields(svc, ctx, session.id)

    result = svc.formalize(ctx, session.id)

    assert result["status"] == "completed"
    assert len(result["resulting_artifact_ids"]) == 1


@pytest.mark.parametrize("artifact_type", IN_SCOPE_ARTIFACT_TYPES)
def test_formalized_artifact_has_the_right_type_and_a_workflow_state(
    ctx, workspace, artifact_type
):
    """The adapters call the production create_X(), which initializes the
    workflow state -- that is the whole reason the registry exists (see
    interview_artifact_adapters module docstring)."""
    from workflow.models import WorkflowItemState

    svc = InterviewService()
    session = svc.start(ctx, artifact_type, workspace.id)
    _answer_all_required_fields(svc, ctx, session.id)
    svc.formalize(ctx, session.id)

    TenantContext.set_tenant(ctx.tenant_id)
    try:
        # TestCase is the one type whose Artifact.artifact_type is stored as
        # a compound "TestCase:<test_type>" value (TestService.create_test_case,
        # REQ-L2-AS-005 -- deliberate, tags the test type for differentiation).
        # Every other in-scope type stores the bare name. startswith handles
        # both without a type-specific branch.
        artifacts = list(
            Artifact.objects.filter(
                workspace_id=workspace.id, artifact_type__startswith=artifact_type
            )
        )
        assert len(artifacts) == 1, (
            f"expected exactly one {artifact_type} Artifact row, got {len(artifacts)}"
        )
        assert WorkflowItemState.objects.filter(
            item_type=artifact_type
        ).exists(), f"no WorkflowItemState initialized for {artifact_type}"
    finally:
        TenantContext.clear_tenant()
