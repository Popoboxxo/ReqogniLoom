"""Regression tests for the se-critic review findings B1/M1/M2
(multi-artifact-interview plan, post-implementation review round).

B1: get_state()/answer() on a multi-kind session must NOT fall through to
the per-artifact-type protocol resolver (artifact_type=None ->
ProtocolValidationError -> unhandled 500 at the REST facade). get_state()
returns the multi shape centrally in the service so every consumer (REST
state action, MCP interview.get_state, frontend getState refresh) is fixed
at once; answer() rejects multi sessions with a clean ValidationError.

M1: a confirmed-proposal item carrying a field name the target create_X()
signature does not accept must surface as ValidationError (HTTP 400), not
TypeError (unhandled 500).

M2: formalize() re-checks the session status under select_for_update() so
two concurrent formalize calls cannot both pass the in_progress guard.

Fixture pattern copied from test_interview_formalize_multi.py (local
fixtures -- no factories.py exists in this repo).
"""
from __future__ import annotations

import contextlib
from typing import Iterator

import pytest

from application.base import ValidationError
from application.interview_service import InterviewService
from auth_tenancy.context import AuthContext, AuthMethod
from persistence.models import InterviewSession, Tenant, User, Workspace
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db


@contextlib.contextmanager
def _active(tenant: Tenant) -> Iterator[None]:
    TenantContext.set_tenant(tenant.id)
    try:
        yield
    finally:
        TenantContext.clear_tenant()


@pytest.fixture(autouse=True)
def _clear_tenant() -> Iterator[None]:
    TenantContext.clear_tenant()
    yield
    TenantContext.clear_tenant()


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(name="IV-Review Tenant", slug="iv-review-tenant")


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    with _active(tenant):
        return Workspace.objects.create(tenant=tenant, name="IV-Review-WS")


@pytest.fixture
def editor_user(tenant: Tenant) -> User:
    return User.objects.create(
        username="iv-review-editor", email="review-editor@example.com", tenant=tenant
    )


@pytest.fixture
def editor_ctx(editor_user: User) -> AuthContext:
    return AuthContext(
        user_id=editor_user.id,
        tenant_id=editor_user.tenant.id,
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
    )


def _multi_session(tenant: Tenant, ws: Workspace) -> InterviewSession:
    with _active(tenant):
        return InterviewSession.objects.create(
            tenant=tenant,
            workspace=ws,
            artifact_type=None,
            session_kind=InterviewSession.SESSION_KIND_MULTI,
        )


def _multi_session_engine_tracked(
    tenant: Tenant, ws: Workspace, ctx: AuthContext
) -> InterviewSession:
    """A multi-session with a real WorkflowItemState (Task 12).

    ``test_completed_session_cannot_be_formalized_again`` needs its
    re-formalize guard to actually persist "completed" across two calls --
    the (now-dropped) `status` column used to do this unconditionally;
    without a real WorkflowEngineDefinition/WorkflowItemState there is
    nothing left to persist it to.
    """
    from workflow.services import create_default_workflow, initialize_workflow_states

    session = _multi_session(tenant, ws)
    with _active(tenant):
        create_default_workflow(
            workspace_id=ws.id,
            preset="interview_default",
            item_type="Interview",
            tenant_id=tenant.id,
        )
        initialize_workflow_states(
            item_ids=[session.id], item_type="Interview", workspace_id=ws.id, ctx=ctx
        )
    return session


class TestMultiSessionStateAndAnswer:
    def test_get_state_on_multi_session_returns_multi_shape(self, tenant, workspace, editor_ctx):
        session = _multi_session(tenant, workspace)

        state = InterviewService().get_state(editor_ctx, session.id)

        assert state["session_id"] == str(session.id)
        assert state["status"] == "in_progress"
        # Multi mode has no per-type protocol -> no phase/missing_fields.
        assert "phase" not in state
        assert "missing_fields" not in state

    def test_answer_on_multi_session_is_rejected_cleanly(self, tenant, workspace, editor_ctx):
        session = _multi_session(tenant, workspace)

        with pytest.raises(ValidationError):
            InterviewService().answer(editor_ctx, session.id, "title", "X")


class TestFormalizeMultiHardening:
    def test_unknown_field_in_proposal_surfaces_as_validation_error(
        self, tenant, workspace, editor_ctx
    ):
        # M1: create_X(**fields) with a field its signature does not accept
        # raises TypeError -- must be translated to ValidationError so the
        # REST facade answers 400 instead of 500.
        session = _multi_session(tenant, workspace)
        proposal = [
            {
                "type": "StakeholderNeed",
                "fields": {"title": "Need A", "nonsense_field": True},
                "links": [],
            }
        ]
        with pytest.raises(ValidationError):
            InterviewService().formalize(editor_ctx, session.id, confirmed_proposal=proposal)

    def test_completed_session_cannot_be_formalized_again(self, tenant, workspace, editor_ctx):
        # M2 behavioural anchor: the status guard must hold after completion
        # (the select_for_update lock making it race-free is structural).
        session = _multi_session_engine_tracked(tenant, workspace, editor_ctx)
        proposal = [{"type": "StakeholderNeed", "fields": {"title": "Need A"}, "links": []}]

        InterviewService().formalize(editor_ctx, session.id, confirmed_proposal=proposal)
        with pytest.raises(ValidationError):
            InterviewService().formalize(editor_ctx, session.id, confirmed_proposal=proposal)
