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
from persistence.models import InterviewSession, Tenant, Workspace
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

    def test_start_rejects_unknown_session_kind(self, ctx, tenant, workspace):
        """Review-2 fix m2a: an unknown session_kind used to slip past every
        kind-specific gate and be silently created as a broken single-ish
        row (Django choices are not DB constraints) -- it must be rejected
        cleanly and create nothing."""
        with pytest.raises(ValidationError) as excinfo:
            InterviewService().start(ctx, "Requirement", workspace.id, session_kind="hybrid")
        assert "Unknown session_kind" in str(excinfo.value)
        # InterviewSession's manager is tenant-scoped -- set the context for
        # this assertion (same try/finally convention as the fixtures above).
        TenantContext.set_tenant(tenant.id)
        try:
            assert not InterviewSession.objects.filter(workspace_id=workspace.id).exists()
        finally:
            TenantContext.clear_tenant()


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
        assert state["transcript"] == []

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


def _install_number_and_enum_protocol(ctx, workspace) -> None:
    """Override interview.protocol.Requirement with a `priority` (number)
    and `element_type` (enum) field -- the default Requirement protocol
    (title/rationale, both text-family) has no number/enum field to
    exercise issue #542's type validation against."""
    from persistence.models import PromptTemplate

    TenantContext.set_tenant(ctx.tenant_id)
    try:
        PromptTemplate.objects.create(
            tenant_id=ctx.tenant_id,
            name="interview.protocol.Requirement",
            content=(
                "phases:\n"
                "  - name: elicitation\n"
                "    required_fields:\n"
                "      - name: title\n"
                "        type: text\n"
                "      - name: priority\n"
                "        type: number\n"
                "      - name: element_type\n"
                "        type: enum\n"
                "        choices: [a, b, c]\n"
                "    prompt_fragment: 'test protocol'\n"
            ),
            version=1,
            is_active=True,
            workspace_id=workspace.id,
        )
    finally:
        TenantContext.clear_tenant()


class TestAnswerFieldTypeValidation:
    """issue #542: answer() validates a submitted value against the
    protocol's declared field type before storing it."""

    def test_answer_rejects_non_numeric_value_for_number_field(self, ctx, workspace):
        _install_number_and_enum_protocol(ctx, workspace)
        session = InterviewService().start(ctx, "Requirement", workspace.id)

        with pytest.raises(ValidationError):
            InterviewService().answer(ctx, session.id, "priority", "not-a-number")

    def test_answer_rejects_value_not_in_enum_choices(self, ctx, workspace):
        _install_number_and_enum_protocol(ctx, workspace)
        session = InterviewService().start(ctx, "Requirement", workspace.id)

        with pytest.raises(ValidationError):
            InterviewService().answer(ctx, session.id, "element_type", "not-a-valid-choice")

    def test_answer_accepts_valid_typed_values(self, ctx, workspace):
        _install_number_and_enum_protocol(ctx, workspace)
        session = InterviewService().start(ctx, "Requirement", workspace.id)

        InterviewService().answer(ctx, session.id, "priority", 5)
        InterviewService().answer(ctx, session.id, "element_type", "b")
        state = InterviewService().get_state(ctx, session.id)

        assert state["collected_fields"]["priority"] == 5
        assert state["collected_fields"]["element_type"] == "b"

    def test_answer_does_not_validate_unknown_field_names(self, ctx, workspace):
        """A field name absent from the protocol entirely stays permissive
        (pre-existing behavior, must not regress) -- only fields that
        resolve to a real protocol field get type-checked."""
        session = InterviewService().start(ctx, "Requirement", workspace.id)

        InterviewService().answer(ctx, session.id, "not_a_real_field", 12345)
        state = InterviewService().get_state(ctx, session.id)

        assert state["collected_fields"]["not_a_real_field"] == 12345


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


class TestSetTarget:
    """issue #540: confirm a grounding_context() candidate (or any
    already-known artifact_id) as the session's formalize() update target."""

    def test_set_target_then_formalize_updates_existing_requirement(self, ctx, workspace):
        from application.requirement_service import RequirementService
        from persistence.models import InterviewSession

        existing = RequirementService().create_requirement(
            workspace_id=workspace.id, title="Old title", ctx=ctx, description=""
        )
        session = InterviewService().start(ctx, "Requirement", workspace.id)

        state = InterviewService().set_target(ctx, session.id, existing.artifact_id)

        TenantContext.set_tenant(ctx.tenant_id)
        try:
            refreshed = InterviewSession.objects.get(id=session.id)
        finally:
            TenantContext.clear_tenant()
        assert refreshed.target_artifact_id == existing.artifact_id
        # Reuses get_state()'s exact shape (this method's documented
        # judgment call) -- confirm the response is a state dict, not some
        # bespoke shape.
        assert state["session_id"] == str(session.id)
        assert state["status"] == "in_progress"

        InterviewService().answer(ctx, session.id, "title", "New title")
        InterviewService().answer(ctx, session.id, "rationale", "Because reasons")

        result = InterviewService().formalize(ctx, session.id)

        assert result["resulting_artifact_ids"] == [str(existing.artifact_id)]
        updated = RequirementService().get_requirement(existing.id, ctx)
        assert updated.title == "New title"
        # No second Requirement was created -- the update branch was taken,
        # not the create branch.
        assert (
            RequirementService()
            .list_requirements(workspace_id=workspace.id, ctx=ctx)
            .count()
            == 1
        )

    def test_set_target_rejects_unknown_artifact_id(self, ctx, workspace):
        session = InterviewService().start(ctx, "Requirement", workspace.id)

        with pytest.raises(NotFoundError):
            InterviewService().set_target(ctx, session.id, uuid.uuid4())

    def test_set_target_rejects_non_requirement_session(self, ctx, workspace):
        session = InterviewService().start(ctx, "Risk", workspace.id)

        with pytest.raises(ValidationError):
            InterviewService().set_target(ctx, session.id, uuid.uuid4())

    def test_set_target_rejects_completed_session(self, ctx, workspace):
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
            InterviewService().set_target(ctx, session.id, uuid.uuid4())


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

    def test_formalize_rejects_non_string_title_without_crashing(self, ctx, workspace):
        """issue #542 stopgap: a stray non-string, falsy `title` (old row,
        or a future caller bypassing answer()'s new validation) must
        degrade to a clean ValidationError, not AttributeError from
        `.strip()` on a non-string. Bypasses answer() on purpose via direct
        model manipulation, to exercise formalize()'s defense-in-depth
        independently of the front-door fix.

        Uses `0` rather than a truthy non-string like `42`: the fix is
        `str(value or "").strip()`, so a *truthy* non-string (e.g. `42`)
        coerces to a non-empty string ("42") and formalize() would proceed
        treating it as a real title -- no crash, nothing to assert via
        ValidationError. A *falsy* non-string is what actually exercises
        the "degrades to empty title, rejected cleanly" path the issue
        describes, while still proving `.strip()` never sees a raw int
        (which is the crash this guards against).
        """
        from persistence.models import InterviewSession

        session = InterviewService().start(ctx, "Requirement", workspace.id)
        TenantContext.set_tenant(ctx.tenant_id)
        try:
            InterviewSession.objects.filter(id=session.id).update(
                collected_fields={"title": 0, "rationale": "Because reasons"}
            )
        finally:
            TenantContext.clear_tenant()

        with pytest.raises(ValidationError):
            InterviewService().formalize(ctx, session.id)


class _ChatFakeProvider:
    """A provider double whose .complete() returns a fixed JSON-shaped
    extraction result, following the same non-vacuous-double principle as
    bundle_compression's _FakeProvider (issue #442 investigation): this
    must not be a hardcoded final-answer double, or a test asserting
    "field got extracted" would be meaningless. It returns exactly what a
    real provider following the chat_turn prompt's contract would."""

    PROVIDER_NAME = "anthropic"

    def __init__(self, response_json: str):
        self._response_json = response_json
        self.last_prompt = None

    def complete(self, prompt, *, purpose="", context=None, timeout=None):
        self.last_prompt = prompt
        return self._response_json


class TestGenerateChatTurn:
    """Web Widget spec §5: server-side conversational turn generation,
    NOT fail-open (unlike grounding)."""

    def test_extracts_field_and_records_transcript(self, ctx, workspace, monkeypatch):
        session = InterviewService().start(ctx, "Requirement", workspace.id)
        provider = _ChatFakeProvider(
            '{"extracted_fields": {"title": "SSO login support"}, "reply": "Got it -- what is the rationale?"}'
        )
        monkeypatch.setattr(InterviewService, "_resolve_provider", lambda self: (provider, "anthropic", None))

        result = InterviewService().generate_chat_turn(ctx, session.id, "We need SSO login support")

        assert result["reply"] == "Got it -- what is the rationale?"
        assert result["state"]["collected_fields"]["title"] == "SSO login support"

        transcript_texts = [t["text"] for t in InterviewService().get(ctx, session.id).transcript]
        assert "We need SSO login support" in transcript_texts
        assert "Got it -- what is the rationale?" in transcript_texts

    def test_no_provider_configured_raises_not_fail_open(self, ctx, workspace, monkeypatch):
        """spec §5: chat generation is NOT fail-open, unlike grounding."""
        session = InterviewService().start(ctx, "Requirement", workspace.id)
        monkeypatch.setattr(
            InterviewService,
            "_resolve_provider",
            lambda self: (None, "unknown", RuntimeError("no provider configured")),
        )

        with pytest.raises(ValidationError):
            InterviewService().generate_chat_turn(ctx, session.id, "anything")

    def test_ambiguous_extraction_asks_clarifying_question_without_recording_a_field(
        self, ctx, workspace, monkeypatch
    ):
        session = InterviewService().start(ctx, "Requirement", workspace.id)
        # No "extracted_fields" key at all -- the model chose to ask instead
        # of guess, exactly the spec §5 contract.
        provider = _ChatFakeProvider('{"extracted_fields": {}, "reply": "Could you clarify the title?"}')
        monkeypatch.setattr(InterviewService, "_resolve_provider", lambda self: (provider, "anthropic", None))

        result = InterviewService().generate_chat_turn(ctx, session.id, "something vague")

        assert result["state"]["collected_fields"] == {}
        assert result["reply"] == "Could you clarify the title?"

    def test_unknown_field_extraction_is_silently_skipped(self, ctx, workspace, monkeypatch):
        """The model must only extract fields from the "still needed" list
        (prompt contract) -- a field name outside the protocol must not
        blow up generate_chat_turn nor be stored, mirroring answer()'s own
        tolerance for names it doesn't resolve."""
        session = InterviewService().start(ctx, "Requirement", workspace.id)
        provider = _ChatFakeProvider(
            '{"extracted_fields": {"not_a_real_field": "x"}, "reply": "Noted."}'
        )
        monkeypatch.setattr(InterviewService, "_resolve_provider", lambda self: (provider, "anthropic", None))

        result = InterviewService().generate_chat_turn(ctx, session.id, "irrelevant")

        assert "not_a_real_field" not in result["state"]["collected_fields"]

    def test_completed_session_raises_validation_error(self, ctx, workspace, monkeypatch):
        session = InterviewService().start(ctx, "Requirement", workspace.id)
        InterviewService().answer(ctx, session.id, "title", "SSO login")
        InterviewService().answer(ctx, session.id, "rationale", "Reduce password fatigue")
        InterviewService().formalize(ctx, session.id)

        provider = _ChatFakeProvider('{"extracted_fields": {}, "reply": "n/a"}')
        monkeypatch.setattr(InterviewService, "_resolve_provider", lambda self: (provider, "anthropic", None))

        with pytest.raises(ValidationError):
            InterviewService().generate_chat_turn(ctx, session.id, "anything")

    def test_malformed_json_response_degrades_to_relaying_raw_text(self, ctx, workspace, monkeypatch):
        """The LLM call itself succeeded but didn't follow the JSON
        contract -- this is a response-shape leniency, distinct from the
        provider-availability contract, so it must not raise."""
        session = InterviewService().start(ctx, "Requirement", workspace.id)
        provider = _ChatFakeProvider("not json at all")
        monkeypatch.setattr(InterviewService, "_resolve_provider", lambda self: (provider, "anthropic", None))

        result = InterviewService().generate_chat_turn(ctx, session.id, "hi")

        assert result["reply"] == "not json at all"
        assert result["state"]["collected_fields"] == {}

    def test_prompt_includes_memory_context_when_memory_exists(self, ctx, tenant, workspace, monkeypatch):
        """Memory plan Task 6: build_memory_context() must actually reach the
        rendered prompt, not just be computed and discarded -- a template
        that lost its {memory_context} placeholder again would still "work"
        (render_template leaves unknown placeholders literally in place) but
        silently stop passing memory to the model."""
        from memory.backends import get_memory_backend
        from persistence.tests.factories import make_user

        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        # UserTenantMemory FKs to a real pl_user row -- the module `ctx`
        # fixture's user_id is a bare uuid4() with no backing User, so a
        # real user is created here rather than reusing ctx.user_id.
        user = make_user(tenant)
        ctx = AuthContext(
            user_id=user.id, tenant_id=ctx.tenant_id, active_roles=ctx.active_roles, auth_method=ctx.auth_method
        )
        backend = get_memory_backend()
        backend.upsert(ctx.tenant_id, "workspace", workspace.id, "Project uses hexagonal architecture.")
        backend.upsert(ctx.tenant_id, "user", ctx.user_id, "Prefers TypeScript over JavaScript.")

        session = InterviewService().start(ctx, "Requirement", workspace.id)
        provider = _ChatFakeProvider('{"extracted_fields": {}, "reply": "ok"}')
        monkeypatch.setattr(InterviewService, "_resolve_provider", lambda self: (provider, "anthropic", None))

        InterviewService().generate_chat_turn(ctx, session.id, "architecture question")

        assert "hexagonal architecture" in provider.last_prompt
        assert "TypeScript" in provider.last_prompt

    def test_prompt_renders_without_memory_context_placeholder_left_literal(
        self, ctx, workspace, monkeypatch
    ):
        """No memory exists yet -- build_memory_context() returns "", and the
        placeholder must be substituted with that empty string, not left as
        the literal ``{memory_context}`` text (REQ-046 only applies to
        placeholders nothing ever supplies a value for)."""
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        session = InterviewService().start(ctx, "Requirement", workspace.id)
        provider = _ChatFakeProvider('{"extracted_fields": {}, "reply": "ok"}')
        monkeypatch.setattr(InterviewService, "_resolve_provider", lambda self: (provider, "anthropic", None))

        InterviewService().generate_chat_turn(ctx, session.id, "anything")

        assert "{memory_context}" not in provider.last_prompt


# ---------------------------------------------------------------------------
# 2026-08-20 UI-visibility fix: workflow-engine integration
# (Interview-Session as a first-class WorkflowEntity)
# ---------------------------------------------------------------------------


@pytest.fixture
def workspace_with_interview_workflow(tenant, workspace):
    """Same `workspace` fixture, plus a provisioned 'interview_default'
    workflow -- the plain `workspace` fixture deliberately has none, so
    every pre-existing test in this file exercises the best-effort fallback
    path (no WorkflowItemState row), not the real integration. These tests
    need the real thing provisioned."""
    from workflow.services import create_default_workflow

    TenantContext.set_tenant(tenant.id)
    try:
        create_default_workflow(
            workspace_id=workspace.id,
            preset="interview_default",
            item_type="Interview",
            tenant_id=tenant.id,
        )
    finally:
        TenantContext.clear_tenant()
    return workspace


class TestWorkflowIntegration:
    def test_start_creates_backing_artifact(self, ctx, workspace):
        session = InterviewService().start(ctx, "Requirement", workspace.id)

        assert session.artifact_id is not None
        assert session.artifact.artifact_type == "Interview"
        assert session.artifact.workspace_id == workspace.id

    def test_start_registers_workflow_item_state_when_provisioned(
        self, ctx, workspace_with_interview_workflow
    ):
        from workflow.models import WorkflowItemState

        session = InterviewService().start(ctx, "Requirement", workspace_with_interview_workflow.id)

        item_state = WorkflowItemState.objects.get(item_id=session.id, item_type="Interview")
        assert item_state.current_state == "in_progress"

    def test_start_without_provisioned_workflow_still_succeeds(self, ctx, workspace):
        """The plain `workspace` fixture has no 'interview_default'
        definition -- initialize_workflow_states must fail closed
        (best-effort try/except) without blocking session creation."""
        session = InterviewService().start(ctx, "Requirement", workspace.id)
        assert session.status == "in_progress"

    def test_formalize_transitions_workflow_state_to_completed(
        self, ctx, workspace_with_interview_workflow
    ):
        from workflow.models import WorkflowItemState

        session = InterviewService().start(ctx, "Requirement", workspace_with_interview_workflow.id)
        InterviewService().answer(ctx, session.id, "title", "SSO login")
        InterviewService().answer(ctx, session.id, "rationale", "Reduce password fatigue")

        result = InterviewService().formalize(ctx, session.id)

        assert result["status"] == "completed"
        item_state = WorkflowItemState.objects.get(item_id=session.id, item_type="Interview")
        assert item_state.current_state == "completed"
        # status mirror (lifecycle_manager._STATUS_MIRROR_MODELS) kept in sync.
        session.refresh_from_db()
        assert session.status == "completed"

    def test_formalize_records_workflow_history_entry(self, ctx, workspace_with_interview_workflow):
        from workflow.models import WorkflowHistoryEntry, WorkflowItemState

        session = InterviewService().start(ctx, "Requirement", workspace_with_interview_workflow.id)
        InterviewService().answer(ctx, session.id, "title", "SSO login")
        InterviewService().answer(ctx, session.id, "rationale", "Reduce password fatigue")
        InterviewService().formalize(ctx, session.id)

        item_state = WorkflowItemState.objects.get(item_id=session.id, item_type="Interview")
        history = WorkflowHistoryEntry.objects.filter(item_state=item_state)
        assert history.filter(from_state="in_progress", to_state="completed").exists()

    def test_lazy_abandon_transitions_workflow_state(self, ctx, workspace_with_interview_workflow):
        from workflow.models import WorkflowItemState

        session = InterviewService().start(ctx, "Requirement", workspace_with_interview_workflow.id)
        stale_time = timezone.now() - ABANDONED_TTL - timedelta(days=1)
        from persistence.models import InterviewSession as ISModel

        ISModel.objects.filter(id=session.id).update(modified_at=stale_time)

        state = InterviewService().get_state(ctx, session.id)

        assert state["status"] == "abandoned"
        item_state = WorkflowItemState.objects.get(item_id=session.id, item_type="Interview")
        assert item_state.current_state == "abandoned"

    def test_lazy_abandon_without_provisioned_workflow_falls_back(self, ctx, workspace):
        """No WorkflowItemState row exists (workspace fixture has no
        provisioned workflow) -- force_transition raises DoesNotExist, and
        the direct-field-write fallback must still flip the status."""
        session = InterviewService().start(ctx, "Requirement", workspace.id)
        from persistence.models import InterviewSession as ISModel

        stale_time = timezone.now() - ABANDONED_TTL - timedelta(days=1)
        ISModel.objects.filter(id=session.id).update(modified_at=stale_time)

        InterviewService()._get_session(ctx, session.id)

        session.refresh_from_db()
        assert session.status == "abandoned"
