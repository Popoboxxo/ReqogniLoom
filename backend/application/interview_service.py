"""InterviewService — core session state machine (Interview-Management-Engine spec §4-5).

start/get_state/answer/list/get here; grounding is Task 5-6,
formalize is Task 7. Kept in this one file per the spec's "one MCP
toolgroup, one engine" framing -- split further only if it grows past
a single clear responsibility.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any, Optional
from uuid import UUID

from django.db.models import F
from django.utils import timezone

from application.base import NotFoundError, ServiceBase, ValidationError
from application.interview_protocol import IN_SCOPE_ARTIFACT_TYPES, get_protocol
from persistence.models import InterviewSession
from persistence.transactions import atomic_transaction

# spec §9 "verwaiste Sessions": a session untouched this long lazily flips
# to abandoned the next time anything reads it. No scheduled job (YAGNI).
ABANDONED_TTL = timedelta(days=30)


class InterviewService(ServiceBase):
    @atomic_transaction
    def start(
        self,
        ctx,
        artifact_type: str,
        workspace_id: UUID,
        seed_context: "Optional[dict]" = None,
    ) -> InterviewSession:
        if artifact_type not in IN_SCOPE_ARTIFACT_TYPES:
            raise ValidationError(
                f"Interviews are not available for artifact_type={artifact_type!r} "
                f"(MainGoal stays read-only; other unknown types are unsupported)."
            )
        self._set_tenant_context(ctx)
        # Fail fast if the protocol config is missing/broken rather than
        # creating a session that can never progress past get_state.
        get_protocol(ctx, artifact_type, workspace_id)
        return InterviewSession.objects.create(
            workspace_id=workspace_id,
            artifact_type=artifact_type,
            collected_fields=(seed_context or {}),
        )

    def _get_session(self, ctx, session_id: UUID) -> InterviewSession:
        self._set_tenant_context(ctx)
        session = InterviewSession.objects.filter(id=session_id).first()
        if session is None:
            raise NotFoundError(f"InterviewSession {session_id} not found")
        self._lazily_abandon_if_stale(session)
        return session

    @staticmethod
    def _lazily_abandon_if_stale(session: InterviewSession) -> None:
        """spec §9: flip a stale in_progress session to abandoned on read.

        Mutates and saves *session* in place when it fires, so callers that
        already hold the returned object see the up-to-date status without
        re-fetching.
        """
        if session.status != InterviewSession.STATUS_IN_PROGRESS:
            return
        if timezone.now() - session.modified_at < ABANDONED_TTL:
            return
        session.status = InterviewSession.STATUS_ABANDONED
        session.version = F("version") + 1
        session.save(update_fields=["status", "modified_at", "version"])
        session.refresh_from_db(fields=["version"])

    def _current_phase_and_missing(self, ctx, session: InterviewSession):
        protocol = get_protocol(ctx, session.artifact_type, session.workspace_id)
        for phase in protocol.phases:
            missing = [
                f for f in phase.required_fields
                if f.name not in session.collected_fields
            ]
            if missing:
                return phase, missing
        # Every field of every phase is answered.
        return protocol.phases[-1], []

    @staticmethod
    def _serialise_field(f) -> "dict[str, Any]":
        # Spec 2 (Hermes plugin, §3-4): InterviewFormView renders one input
        # per missing field and needs its type/choices to pick the right
        # control (text/textarea/enum/number) -- a bare field-name string
        # would lose exactly the information the protocol config's `type`
        # amendment was added for. Every host consumes this same shape;
        # skill-driven hosts (Claude Code/Opencode/Antigravity) just read
        # `.name` and ignore `.type`/`.choices`.
        return {"name": f.name, "type": f.type, "choices": f.choices}

    def get_state(self, ctx, session_id: UUID) -> "dict[str, Any]":
        session = self._get_session(ctx, session_id)
        phase, missing = self._current_phase_and_missing(ctx, session)
        return {
            "session_id": str(session.id),
            "status": session.status,
            "phase": phase.name,
            "collected_fields": session.collected_fields,
            "missing_fields": [self._serialise_field(f) for f in missing],
            "grounding_snapshot": session.grounding_snapshot,
        }

    @atomic_transaction
    def answer(self, ctx, session_id: UUID, field: str, value: Any) -> InterviewSession:
        session = self._get_session(ctx, session_id)
        if session.status != InterviewSession.STATUS_IN_PROGRESS:
            raise ValidationError(
                f"InterviewSession {session_id} is {session.status}, cannot answer."
            )
        session.collected_fields = {**session.collected_fields, field: value}
        session.version = F("version") + 1
        session.save(update_fields=["collected_fields", "modified_at", "version"])
        session.refresh_from_db(fields=["version"])
        return session

    def list_sessions(self, ctx, workspace_id: UUID, status: "Optional[str]" = None):
        self._set_tenant_context(ctx)
        # Bulk-flip stale rows before filtering, so a "status=in_progress"
        # list doesn't include sessions that are stale-but-not-yet-read
        # individually (list_sessions has no single row to lazily patch the
        # way _get_session does).
        InterviewSession.objects.filter(
            workspace_id=workspace_id,
            status=InterviewSession.STATUS_IN_PROGRESS,
            modified_at__lt=timezone.now() - ABANDONED_TTL,
        ).update(status=InterviewSession.STATUS_ABANDONED, version=F("version") + 1)

        qs = InterviewSession.objects.filter(workspace_id=workspace_id)
        if status:
            qs = qs.filter(status=status)
        return qs.order_by("-modified_at")

    def get(self, ctx, session_id: UUID) -> InterviewSession:
        return self._get_session(ctx, session_id)
