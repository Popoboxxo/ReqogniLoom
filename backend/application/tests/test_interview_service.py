"""InterviewService core state machine — spec §4 (start/get_state/answer/list/get)."""
from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from application.base import NotFoundError, ValidationError
from application.interview_service import ABANDONED_TTL, InterviewService
from auth_tenancy.context import AuthContext, AuthMethod
from persistence.models import Tenant, Workspace
from persistence.tenancy import TenantContext


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="IS Tenant", slug="is-tenant")


@pytest.fixture
def workspace(tenant):
    TenantContext.set_tenant(tenant.id)
    try:
        return Workspace.objects.create(tenant=tenant, name="WS")
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def ctx(tenant):
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
    )


class TestStart:
    def test_start_creates_session_with_first_phase_missing_fields(self, ctx, workspace):
        session = InterviewService().start(ctx, "Requirement", workspace.id)

        assert session.status == "in_progress"
        assert session.artifact_type == "Requirement"
        assert session.workspace_id == workspace.id

    def test_start_rejects_out_of_scope_artifact_type(self, ctx, workspace):
        with pytest.raises(ValidationError):
            InterviewService().start(ctx, "MainGoal", workspace.id)


class TestGetState:
    def test_reports_missing_fields_for_fresh_session(self, ctx, workspace):
        session = InterviewService().start(ctx, "Requirement", workspace.id)

        state = InterviewService().get_state(ctx, session.id)

        assert state["phase"] == "elicitation"
        missing_names = [f["name"] for f in state["missing_fields"]]
        assert "title" in missing_names
        title_field = next(f for f in state["missing_fields"] if f["name"] == "title")
        assert title_field["type"] == "text"
        assert state["collected_fields"] == {}

    def test_unknown_session_raises_not_found(self, ctx):
        with pytest.raises(NotFoundError):
            InterviewService().get_state(ctx, uuid.uuid4())


class TestAnswer:
    def test_answer_moves_field_from_missing_to_collected(self, ctx, workspace):
        session = InterviewService().start(ctx, "Requirement", workspace.id)

        InterviewService().answer(ctx, session.id, "title", "Login must support SSO")
        state = InterviewService().get_state(ctx, session.id)

        assert state["collected_fields"]["title"] == "Login must support SSO"
        assert "title" not in [f["name"] for f in state["missing_fields"]]

    def test_answer_on_completed_session_raises_validation_error(self, ctx, workspace):
        from persistence.models import InterviewSession

        session = InterviewService().start(ctx, "Requirement", workspace.id)
        TenantContext.set_tenant(ctx.tenant_id)
        try:
            InterviewSession.objects.filter(id=session.id).update(
                status=InterviewSession.STATUS_COMPLETED
            )
        finally:
            TenantContext.clear_tenant()

        with pytest.raises(ValidationError):
            InterviewService().answer(ctx, session.id, "title", "x")


class TestListAndGet:
    def test_list_filters_by_status(self, ctx, workspace):
        svc = InterviewService()
        s1 = svc.start(ctx, "Requirement", workspace.id)
        s2 = svc.start(ctx, "Risk", workspace.id)

        results = list(svc.list_sessions(ctx, workspace.id, status="in_progress"))

        assert {r.id for r in results} == {s1.id, s2.id}

    def test_get_returns_the_session(self, ctx, workspace):
        session = InterviewService().start(ctx, "Requirement", workspace.id)
        fetched = InterviewService().get(ctx, session.id)
        assert fetched.id == session.id


class TestAbandonedTtl:
    """spec §9: a session untouched past ABANDONED_TTL lazily flips to
    abandoned on the next read -- no scheduled job."""

    def test_get_state_flips_stale_session_to_abandoned(self, ctx, workspace):
        from persistence.models import InterviewSession

        session = InterviewService().start(ctx, "Requirement", workspace.id)
        TenantContext.set_tenant(ctx.tenant_id)
        try:
            # Simulate a session nobody touched in a long time by
            # backdating modified_at past ABANDONED_TTL directly in the DB
            # (auto_now would otherwise overwrite any value set via .save()).
            InterviewSession.objects.filter(id=session.id).update(
                modified_at=timezone.now() - ABANDONED_TTL - timedelta(days=1)
            )
        finally:
            TenantContext.clear_tenant()

        state = InterviewService().get_state(ctx, session.id)

        assert state["status"] == "abandoned"

    def test_recent_session_is_not_flipped(self, ctx, workspace):
        session = InterviewService().start(ctx, "Requirement", workspace.id)

        state = InterviewService().get_state(ctx, session.id)

        assert state["status"] == "in_progress"

    def test_list_bulk_flips_stale_sessions(self, ctx, workspace):
        from persistence.models import InterviewSession

        session = InterviewService().start(ctx, "Requirement", workspace.id)
        TenantContext.set_tenant(ctx.tenant_id)
        try:
            InterviewSession.objects.filter(id=session.id).update(
                modified_at=timezone.now() - ABANDONED_TTL - timedelta(days=1)
            )
        finally:
            TenantContext.clear_tenant()

        in_progress = list(
            InterviewService().list_sessions(ctx, workspace.id, status="in_progress")
        )

        assert session.id not in {s.id for s in in_progress}


class TestGroundingStructural:
    """spec §6 step 1: structural (non-AI) grounding for Requirement interviews."""

    def test_grounding_finds_existing_requirement_by_title_overlap(self, ctx, workspace):
        from application.requirement_service import RequirementService

        RequirementService().create_requirement(
            workspace_id=workspace.id, title="SSO login support", ctx=ctx, description=""
        )
        session = InterviewService().start(ctx, "Requirement", workspace.id)
        InterviewService().answer(ctx, session.id, "title", "SSO login support")

        result = InterviewService().grounding_context(ctx, session.id)

        assert len(result["candidates"]) >= 1
        titles = [c["title"] for c in result["candidates"]]
        assert "SSO login support" in titles

    def test_grounding_with_no_answers_yet_returns_empty_candidates(self, ctx, workspace):
        session = InterviewService().start(ctx, "Requirement", workspace.id)
        result = InterviewService().grounding_context(ctx, session.id)
        assert result["candidates"] == []
