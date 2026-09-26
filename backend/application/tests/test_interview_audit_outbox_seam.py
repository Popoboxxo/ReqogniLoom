"""CR-07 — the audit/outbox seam for ``InterviewService`` writes.

Audit finding CR-07 (W2 slice): ``InterviewService`` wrote **zero**
``AuditEntry`` rows. Every other write in the application layer routes
through ``ServiceBase._audit`` (the sibling ``WorkflowFacade.transition``
covers the very same "item moved state" semantics for every non-interview
item type), so an interview — start, answer, formalize, abandon — was
invisible to the audit trail while mutating the same entities. ``abandon()``
was worse: it flipped a session to ``abandoned`` with neither an audit entry
nor an outbox event, so a user-cancelled session left no trace in either
seam.

This module pins the resulting contract:

* every completion/abandonment writes exactly one ``AuditEntry`` and exactly
  one outbox row, both inside the mutation's own transaction (so a rollback
  takes both with it and the two seams can never disagree);
* a failing write leaves **no** success audit entry and **no** success event;
* the deliberately-kept broad ``except Exception`` around the workflow-engine
  transition (it exists so legacy sessions without a ``WorkflowItemState``
  still complete) no longer swallows silently: the audit entry records
  ``workflow_transition_applied=False`` and the log line is a warning with a
  traceback, so the in-memory-only completion can never be mistaken for a
  real one.
"""
from __future__ import annotations

import uuid

import pytest

from application.base import ValidationError
from application.interview_service import InterviewService
from application.models import DomainEventOutbox
from audit.models import AuditEntry
from auth_tenancy.context import AuthContext, AuthMethod
from persistence.models import InterviewSession, Tenant, User, Workspace
from persistence.tenancy import TenantContext
from workflow.services import create_default_workflow

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant(db: None) -> Tenant:
    return Tenant.objects.create(name="CR07 Tenant", slug="cr07-tenant")


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    """A workspace with a provisioned ``Interview`` workflow definition.

    The real stack provisions definitions at workspace creation. Without one
    no ``WorkflowItemState`` row exists for the session, so the engine
    transition is swallowed by the legacy fallback and every audit entry here
    would carry ``workflow_transition_applied=False`` -- the flag this module
    asserts on would stop distinguishing anything.
    """
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name="WS")
        create_default_workflow(
            workspace_id=workspace.id,
            preset="interview_default",
            item_type="Interview",
            tenant_id=tenant.id,
        )
        return workspace
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def user(tenant: Tenant) -> User:
    """A real User row: ``Artifact.created_by`` is a real FK, not a free uuid.

    Required for the multi-kind path, whose StakeholderNeed adapter sets
    ``created_by`` from ``ctx.user_id``.
    """
    return User.objects.create(
        username="cr07-user",
        email="cr07-user@example.test",
        tenant=tenant,
        is_active=True,
    )


@pytest.fixture
def ctx(tenant: Tenant, user: User) -> AuthContext:
    return AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
    )


def _complete_single_session(ctx: AuthContext, workspace: Workspace):
    service = InterviewService()
    session = service.start(ctx, "Requirement", workspace.id)
    service.answer(ctx, session.id, "title", "Audit seam probe")
    service.answer(ctx, session.id, "rationale", "so formalize() is allowed")
    return session


def _audit_rows(entity_id: uuid.UUID, op: str = "transition") -> list[AuditEntry]:
    return list(
        AuditEntry.objects.filter(
            entity_type="Interview", entity_id=entity_id, op=op
        )
    )


def _outbox_rows(entity_id: uuid.UUID, event_type: str) -> list[DomainEventOutbox]:
    return list(
        DomainEventOutbox.objects.filter(event_type=event_type, entity_id=entity_id)
    )


class TestSingleFormalizeSeam:
    def test_formalize_writes_one_audit_entry_and_one_outbox_event(
        self, ctx, workspace
    ):
        session = _complete_single_session(ctx, workspace)

        result = InterviewService().formalize(ctx, session.id)

        assert result["status"] == "completed", result
        rows = _audit_rows(session.id)
        assert len(rows) == 1, [(r.op, r.entity_type) for r in rows]
        assert rows[0].op == "transition"
        assert rows[0].change_reason == "Interview formalized into a real artifact"
        assert rows[0].details["session_kind"] == "single"
        assert rows[0].details["resulting_artifact_ids"] == result[
            "resulting_artifact_ids"
        ]
        assert rows[0].details["workflow_transition_applied"] is True

        events = _outbox_rows(session.id, DomainEventOutbox.EventType.INTERVIEW_FORMALIZED)
        assert len(events) == 1, [e.event_type for e in events]
        # Audit and outbox must describe the SAME outcome, not just both exist.
        assert events[0].payload["resulting_artifact_ids"] == result[
            "resulting_artifact_ids"
        ]

    def test_single_formalize_payload_carries_session_kind(self, ctx, workspace):
        """m4: the event alone must say which shape it describes.

        ``INTERVIEW_FORMALIZED`` had two incompatible payload shapes —
        single ``{artifact_type, resulting_artifact_ids}`` and multi
        ``{artifact_type, created}`` — and the only discriminator,
        ``session_kind``, was carried by the *abandon* event alone. A consumer
        reading formalized events had to infer the shape from which key happened
        to be present.
        """
        session = _complete_single_session(ctx, workspace)

        InterviewService().formalize(ctx, session.id)

        events = _outbox_rows(session.id, DomainEventOutbox.EventType.INTERVIEW_FORMALIZED)
        assert len(events) == 1
        payload = events[0].payload
        assert payload["session_kind"] == InterviewSession.SESSION_KIND_SINGLE
        assert "resulting_artifact_ids" in payload
        assert "created" not in payload

    def test_surviving_workflow_transition_failure_is_flagged_not_swallowed(
        self, ctx, workspace, monkeypatch
    ):
        """The broad ``except Exception`` stays, but is no longer invisible.

        Simulates the exact case it exists for: a session with no engine state
        to transition. The call must still succeed (that fallback is a
        documented, reviewed contract), yet the audit entry must not claim a
        clean engine transition.
        """
        def _boom(*args, **kwargs):
            raise RuntimeError("no WorkflowItemState for this session")

        monkeypatch.setattr("workflow.services.transition", _boom)

        session = _complete_single_session(ctx, workspace)
        result = InterviewService().formalize(ctx, session.id)

        assert result["status"] == "completed", result
        rows = _audit_rows(session.id)
        assert len(rows) == 1, [(r.op, r.entity_type) for r in rows]
        assert rows[0].details["workflow_transition_applied"] is False, (
            "a completion that never reached the engine must be distinguishable "
            "from a real one in the audit trail"
        )
        assert len(_outbox_rows(session.id, DomainEventOutbox.EventType.INTERVIEW_FORMALIZED)) == 1

    def test_failed_formalize_writes_neither_audit_nor_outbox(self, ctx, workspace):
        """A refused completion must leave no success trace in either seam."""
        service = InterviewService()
        session = service.start(ctx, "Requirement", workspace.id)
        # No answers -> the completeness guard refuses to create an artifact.
        with pytest.raises(ValidationError):
            service.formalize(ctx, session.id)

        assert _audit_rows(session.id) == []
        assert _outbox_rows(session.id, DomainEventOutbox.EventType.INTERVIEW_FORMALIZED) == []


class TestMultiFormalizeSeam:
    def test_multi_formalize_writes_one_audit_entry_and_one_outbox_event(
        self, ctx, workspace
    ):
        service = InterviewService()
        session = service.start(
            ctx,
            None,
            workspace.id,
            session_kind=InterviewSession.SESSION_KIND_MULTI,
        )
        proposal = [
            {"type": "StakeholderNeed", "fields": {"title": "Need A"}, "links": []}
        ]

        result = service.formalize(ctx, session.id, proposal)

        assert result["status"] == "completed", result
        rows = _audit_rows(session.id)
        assert len(rows) == 1, [(r.op, r.entity_type) for r in rows]
        assert rows[0].details["session_kind"] == "multi"
        assert rows[0].details["workflow_transition_applied"] is True
        assert len(_outbox_rows(session.id, DomainEventOutbox.EventType.INTERVIEW_FORMALIZED)) == 1

    def test_multi_formalize_payload_carries_session_kind(self, ctx, workspace):
        """m4: the multi half of the pair — see the single-path twin."""
        service = InterviewService()
        session = service.start(
            ctx, None, workspace.id, session_kind=InterviewSession.SESSION_KIND_MULTI
        )
        proposal = [
            {"type": "StakeholderNeed", "fields": {"title": "Need A"}, "links": []}
        ]

        service.formalize(ctx, session.id, proposal)

        events = _outbox_rows(session.id, DomainEventOutbox.EventType.INTERVIEW_FORMALIZED)
        assert len(events) == 1
        payload = events[0].payload
        assert payload["session_kind"] == InterviewSession.SESSION_KIND_MULTI
        assert "created" in payload
        assert "resulting_artifact_ids" not in payload

    def test_multi_batch_failure_rolls_back_the_seam_too(self, ctx, workspace):
        """A batch that aborts half-way must leave no success audit/event."""
        service = InterviewService()
        session = service.start(
            ctx,
            None,
            workspace.id,
            session_kind=InterviewSession.SESSION_KIND_MULTI,
        )
        # The second item is structurally valid but semantically impossible:
        # Risk without probability/impact raises KeyError inside the adapter,
        # i.e. after the first item was already created.
        proposal = [
            {"type": "StakeholderNeed", "fields": {"title": "Need A"}, "links": []},
            {"type": "Risk", "fields": {"title": "Risk B"}, "links": []},
        ]

        with pytest.raises(ValidationError):
            service.formalize(ctx, session.id, proposal)

        assert _audit_rows(session.id) == []
        assert _outbox_rows(session.id, DomainEventOutbox.EventType.INTERVIEW_FORMALIZED) == []


class TestAbandonSeam:
    def test_abandon_writes_one_audit_entry_and_one_outbox_event(self, ctx, workspace):
        service = InterviewService()
        session = service.start(ctx, "Requirement", workspace.id)

        result = service.abandon(ctx, session.id)

        assert result["status"] == "abandoned", result
        rows = _audit_rows(session.id)
        assert len(rows) == 1, [(r.op, r.entity_type) for r in rows]
        assert rows[0].op == "transition"
        assert rows[0].change_reason == "Cancelled by user"
        assert rows[0].details["new_state"] == "abandoned"
        assert rows[0].details["workflow_transition_applied"] is True

        events = _outbox_rows(session.id, DomainEventOutbox.EventType.INTERVIEW_ABANDONED)
        assert len(events) == 1, [e.event_type for e in events]
        assert events[0].payload["session_kind"] == "single"

    def test_abandon_audit_entry_carries_resulting_artifact_ids(self, ctx, workspace):
        """m5: the key is present on every formalize/abandon audit entry.

        Both formalize paths recorded ``resulting_artifact_ids`` and abandon did
        not, so a consumer had to branch on the change_reason text to know
        whether the key was meaningful. It is always empty on abandon — an
        abandoned session creates nothing — but its ABSENCE is what made the
        entry unqueryable.
        """
        service = InterviewService()
        session = service.start(ctx, "Requirement", workspace.id)

        service.abandon(ctx, session.id)

        rows = _audit_rows(session.id)
        assert len(rows) == 1
        assert rows[0].details["resulting_artifact_ids"] == []
        # The neighbouring keys are untouched — this is additive.
        assert rows[0].details["session_kind"] == "single"
        assert rows[0].details["artifact_type"] == "Requirement"

    def test_abandon_of_a_non_in_progress_session_writes_nothing(self, ctx, workspace):
        service = InterviewService()
        session = _complete_single_session(ctx, workspace)
        service.formalize(ctx, session.id)

        with pytest.raises(ValidationError):
            service.abandon(ctx, session.id)

        # Only the formalize entry/event must exist -- abandon added nothing.
        assert len(_audit_rows(session.id)) == 1
        assert _outbox_rows(session.id, DomainEventOutbox.EventType.INTERVIEW_ABANDONED) == []

    def test_surviving_workflow_transition_failure_is_flagged_in_audit(
        self, ctx, workspace, monkeypatch
    ):
        def _boom(*args, **kwargs):
            raise RuntimeError("no WorkflowItemState for this session")

        monkeypatch.setattr("workflow.services.transition", _boom)

        service = InterviewService()
        session = service.start(ctx, "Requirement", workspace.id)
        result = service.abandon(ctx, session.id)

        assert result["status"] == "abandoned", result
        rows = _audit_rows(session.id)
        assert len(rows) == 1
        assert rows[0].details["workflow_transition_applied"] is False
