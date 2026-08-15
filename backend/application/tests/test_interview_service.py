"""InterviewService core state machine — spec §4 (start/get_state/answer/list/get)."""
from __future__ import annotations

import json
import uuid
from datetime import timedelta
from unittest.mock import MagicMock, patch

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

    def test_start_raises_not_found_for_unknown_workspace_id(self, ctx):
        """An unknown workspace_id must surface as a clean NotFoundError,
        not a bare IntegrityError from InterviewSession's FK constraint
        (same class as RequirementService.create_requirement's check)."""
        with pytest.raises(NotFoundError):
            InterviewService().start(ctx, "Requirement", uuid.uuid4())


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


class TestGroundingAiAssisted:
    """spec §6 step 2: AI-assisted ranking on top of the structural
    pre-filter -- fail-open per spec §6, this is the one hard correctness
    requirement (Task 6)."""

    def test_mock_provider_still_returns_structural_candidates(self, ctx, workspace):
        """No real provider configured (test env defaults to LLM_PROVIDER=mock)
        -> structural results only, never blocks (spec §6)."""
        from application.requirement_service import RequirementService

        RequirementService().create_requirement(
            workspace_id=workspace.id, title="SSO login support", ctx=ctx, description=""
        )
        session = InterviewService().start(ctx, "Requirement", workspace.id)
        InterviewService().answer(ctx, session.id, "title", "SSO login support")

        result = InterviewService().grounding_context(ctx, session.id)

        assert len(result["candidates"]) >= 1

    def test_provider_failure_does_not_raise(self, ctx, workspace):
        session = InterviewService().start(ctx, "Requirement", workspace.id)
        InterviewService().answer(ctx, session.id, "title", "anything")

        with patch(
            "application.interview_service.InterviewService._resolve_provider",
            side_effect=RuntimeError("boom"),
        ):
            # Must not raise -- fail-open per spec §6.
            result = InterviewService().grounding_context(ctx, session.id)

        assert "candidates" in result

    def test_provider_call_failure_falls_back_to_structural_candidates(self, ctx, workspace):
        """A real (non-mock) provider that raises mid-call must not lose the
        structural candidates already found -- fail-open at the call layer,
        not just the resolve layer."""
        from application.requirement_service import RequirementService

        RequirementService().create_requirement(
            workspace_id=workspace.id, title="SSO login support", ctx=ctx, description=""
        )
        session = InterviewService().start(ctx, "Requirement", workspace.id)
        InterviewService().answer(ctx, session.id, "title", "SSO login support")

        broken_provider = object()
        with patch(
            "application.interview_service.InterviewService._resolve_provider",
            return_value=(broken_provider, "anthropic", None),
        ):
            # broken_provider has no .complete(), so calling it raises
            # AttributeError -- exercises the real call-failure path, not
            # just a mocked side_effect.
            result = InterviewService().grounding_context(ctx, session.id)

        assert len(result["candidates"]) >= 1
        titles = [c["title"] for c in result["candidates"]]
        assert "SSO login support" in titles

    def test_real_provider_success_merges_scores_and_sorts(self, ctx, workspace):
        """A real provider that returns a well-formed ranking must actually
        get applied -- fail-open is not the only correctness bar here."""
        from application.requirement_service import RequirementService

        # Both titles must contain the answered "SSO login support" as a
        # substring -- that's what the Task 5 structural pre-filter matches
        # on (title.lower() in r.title.lower()).
        RequirementService().create_requirement(
            workspace_id=workspace.id, title="SSO login support", ctx=ctx, description=""
        )
        RequirementService().create_requirement(
            workspace_id=workspace.id,
            title="SSO login support (extended)",
            ctx=ctx,
            description="",
        )
        session = InterviewService().start(ctx, "Requirement", workspace.id)
        InterviewService().answer(ctx, session.id, "title", "SSO login support")

        state = InterviewService().grounding_context(ctx, session.id)
        by_title = {c["title"]: c["artifact_id"] for c in state["candidates"]}
        assert set(by_title) == {"SSO login support", "SSO login support (extended)"}

        fake_provider = MagicMock()
        fake_provider.complete.return_value = json.dumps(
            [
                {"artifact_id": by_title["SSO login support (extended)"], "score": 0.2},
                {"artifact_id": by_title["SSO login support"], "score": 0.95},
            ]
        )
        with patch(
            "application.interview_service.InterviewService._resolve_provider",
            return_value=(fake_provider, "anthropic", None),
        ):
            result = InterviewService().grounding_context(ctx, session.id)

        fake_provider.complete.assert_called_once()
        assert [c["title"] for c in result["candidates"]] == [
            "SSO login support",
            "SSO login support (extended)",
        ]
        assert result["candidates"][0]["score"] == 0.95
        assert result["candidates"][1]["score"] == 0.2

    def test_malformed_ai_response_falls_back_to_structural_candidates(self, ctx, workspace):
        """A real provider that returns non-JSON garbage must not lose the
        structural candidates or raise -- fail-open at the parse layer."""
        from application.requirement_service import RequirementService

        RequirementService().create_requirement(
            workspace_id=workspace.id, title="SSO login support", ctx=ctx, description=""
        )
        session = InterviewService().start(ctx, "Requirement", workspace.id)
        InterviewService().answer(ctx, session.id, "title", "SSO login support")

        fake_provider = MagicMock()
        fake_provider.complete.return_value = "not json at all {{{"
        with patch(
            "application.interview_service.InterviewService._resolve_provider",
            return_value=(fake_provider, "anthropic", None),
        ):
            result = InterviewService().grounding_context(ctx, session.id)

        assert len(result["candidates"]) >= 1
        titles = [c["title"] for c in result["candidates"]]
        assert "SSO login support" in titles


class TestFormalize:
    """spec §5 point 4 / §9: turn collected answers into a real Requirement,
    either creating a new one or updating the grounded target, then complete
    the session."""

    def test_formalize_with_no_target_creates_new_requirement(self, ctx, workspace):
        session = InterviewService().start(ctx, "Requirement", workspace.id)
        InterviewService().answer(ctx, session.id, "title", "SSO login support")
        InterviewService().answer(ctx, session.id, "rationale", "Reduce password fatigue")

        result = InterviewService().formalize(ctx, session.id)

        assert len(result["resulting_artifact_ids"]) == 1
        assert result["status"] == "completed"

        from persistence.models import InterviewSession

        TenantContext.set_tenant(ctx.tenant_id)
        try:
            refreshed = InterviewSession.objects.get(id=session.id)
        finally:
            TenantContext.clear_tenant()
        assert refreshed.status == InterviewSession.STATUS_COMPLETED
        assert refreshed.resulting_artifact_ids == result["resulting_artifact_ids"]

    def test_formalize_with_target_updates_existing_requirement(self, ctx, workspace):
        from application.requirement_service import RequirementService

        existing = RequirementService().create_requirement(
            workspace_id=workspace.id, title="Old title", ctx=ctx, description=""
        )
        session = InterviewService().start(ctx, "Requirement", workspace.id)
        InterviewService().answer(ctx, session.id, "title", "New title")
        InterviewService().answer(ctx, session.id, "rationale", "Because reasons")

        from persistence.models import InterviewSession

        TenantContext.set_tenant(ctx.tenant_id)
        try:
            InterviewSession.objects.filter(id=session.id).update(
                target_artifact_id=existing.artifact_id
            )
        finally:
            TenantContext.clear_tenant()

        result = InterviewService().formalize(ctx, session.id)

        updated = RequirementService().get_requirement(existing.id, ctx)
        assert updated.title == "New title"
        assert result["resulting_artifact_ids"] == [str(existing.artifact_id)]
        assert result["status"] == "completed"

    def test_formalize_reraises_if_target_artifact_deleted_mid_session(self, ctx, workspace):
        """spec §5 point 4 / §9: re-check existence at write time -- a stale
        grounded target must not silently fall back to creating a new
        artifact, nor let the update through against a gone row.

        Deletes only the ``Requirement`` sub-row, not its backing
        ``Artifact``: ``InterviewSession.target_artifact`` is
        ``on_delete=SET_NULL`` by deliberate, already-tested design
        (persistence/tests/test_interview_session_model.py::
        test_target_artifact_survives_artifact_deletion_as_null) -- hard-
        deleting the ``Artifact`` itself nulls ``target_artifact_id`` in
        the very same transaction, which by the time ``formalize()`` reads
        the session is indistinguishable from "no target was ever set" and
        would not exercise this re-check path at all. Deleting the
        ``Requirement`` while its ``Artifact`` survives reproduces exactly
        the state the re-check guards against: a ``target_artifact_id``
        that is still set, but no longer resolves to a ``Requirement``.
        """
        from application.requirement_service import RequirementService
        from persistence.models import InterviewSession, Requirement

        existing = RequirementService().create_requirement(
            workspace_id=workspace.id, title="Will be deleted", ctx=ctx, description=""
        )
        session = InterviewService().start(ctx, "Requirement", workspace.id)
        InterviewService().answer(ctx, session.id, "title", "New title")
        InterviewService().answer(ctx, session.id, "rationale", "Because reasons")

        TenantContext.set_tenant(ctx.tenant_id)
        try:
            InterviewSession.objects.filter(id=session.id).update(
                target_artifact_id=existing.artifact_id
            )
            Requirement.objects.filter(id=existing.id).delete()
        finally:
            TenantContext.clear_tenant()

        with pytest.raises(NotFoundError):
            InterviewService().formalize(ctx, session.id)

    def test_formalize_for_non_requirement_type_raises_validation_error(self, ctx, workspace):
        """Only Requirement is wired in this plan; the other 7 in-scope
        artifact types are an explicit, stated scope cut."""
        session = InterviewService().start(ctx, "Risk", workspace.id)

        with pytest.raises(ValidationError):
            InterviewService().formalize(ctx, session.id)

    def test_formalize_on_already_completed_session_raises_validation_error(self, ctx, workspace):
        session = InterviewService().start(ctx, "Requirement", workspace.id)
        InterviewService().answer(ctx, session.id, "title", "x")
        InterviewService().answer(ctx, session.id, "rationale", "y")
        InterviewService().formalize(ctx, session.id)

        with pytest.raises(ValidationError):
            InterviewService().formalize(ctx, session.id)

    def test_formalize_rejects_incomplete_session_with_missing_fields(self, ctx, workspace):
        session = InterviewService().start(ctx, "Requirement", workspace.id)
        # No answers given at all -- title/rationale still missing.

        with pytest.raises(ValidationError):
            InterviewService().formalize(ctx, session.id)

        # Must not have created anything or marked the session completed.
        from persistence.models import InterviewSession

        TenantContext.set_tenant(ctx.tenant_id)
        try:
            refreshed = InterviewSession.objects.get(id=session.id)
        finally:
            TenantContext.clear_tenant()
        assert refreshed.status == InterviewSession.STATUS_IN_PROGRESS
        assert refreshed.resulting_artifact_ids == []

    def test_formalize_rejects_empty_title_even_if_protocol_has_no_title_field(self, ctx, workspace):
        """The completeness guard only trusts the protocol: a workspace that
        overrides interview.protocol.Requirement to never ask for `title`
        would pass `missing_fields == []` trivially, but formalize() must
        still refuse to create a Requirement with an empty title
        independent of what the protocol declares as required."""
        from persistence.models import PromptTemplate

        TenantContext.set_tenant(ctx.tenant_id)
        try:
            PromptTemplate.objects.create(
                tenant_id=ctx.tenant_id,
                name="interview.protocol.Requirement",
                content="phases:\n  - name: only_phase\n    prompt_fragment: 'no title field'\n",
                version=1,
                is_active=True,
                workspace_id=workspace.id,
            )
        finally:
            TenantContext.clear_tenant()

        session = InterviewService().start(ctx, "Requirement", workspace.id)
        state = InterviewService().get_state(ctx, session.id)
        assert state["missing_fields"] == []

        with pytest.raises(ValidationError):
            InterviewService().formalize(ctx, session.id)
