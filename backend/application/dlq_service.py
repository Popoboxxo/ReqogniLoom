"""
ARCH-L1-004 ApplicationService — DLQ service (COMP-AS-016 companion).

Provides admin-only inspection and replay of the Domain-Event Dead-Letter
Queue (REQ-L3-DEB-007). Backed by ``application.models.DomainEventDLQ``
and the ``DomainEventBus`` outbox.

Public API (used by the MCP AuditToolGroup, see ``mcp_server/tools/audit.py``):

  DlqService.list_dlq(ctx, event_type=None, limit=100)
      -> List[DomainEventDLQ]
  DlqService.replay_dlq_event(ctx, event_id)
      -> DomainEventDLQ  (the row that was just re-queued)

Both methods enforce the admin role via :class:`ServiceBase`.

Replay semantics
----------------
A replayed event is **re-inserted into the Outbox** with a fresh
``retry_count=0`` and ``published=False``. The DLQ row is removed in the
same atomic block. The event then re-enters the normal
``poll_and_dispatch`` cycle; subscribers will be invoked again on the next
worker tick. This matches the standard "dead-letter replay" pattern: the
event gets a fresh retry budget and is observable in the outbox
monitoring the same way as a never-dispatched event.

Architecture:
  docs/se/se/L1/Gesamtsystem/L2/ApplicationServiceSystem/
    Components/COMP-AS-016_DomainEventBus/
      L3_COMP-AS-016_DomainEventBus_Architecture.md
"""
from __future__ import annotations

import logging
from typing import List, Optional
from uuid import UUID

from django.db import transaction

from auth_tenancy.context import AuthContext

from application.base import (
    NotFoundError,
    PermissionDeniedError,
    ServiceBase,
)
from application.models import DomainEventDLQ, DomainEventOutbox

logger = logging.getLogger(__name__)


# Hard cap to match BackupService / AuditLogQuery (defensive against accidental
# large pulls from MCP clients).
LIST_LIMIT_CAP: int = 1000
DEFAULT_LIMIT: int = 100


class DlqService:
    """Admin-only operations on the Domain-Event Dead-Letter Queue.

    Public surface (see ``backend/admin_ops/services/INTERFACES.md`` §2.1
    for the parallel BackupService contract):

    * :meth:`list_dlq`      — admin overview listing of DLQ entries.
    * :meth:`replay_dlq_event` — re-insert a single event into the Outbox.

    Stateless. All callers must have the ``admin`` role.
    """

    # ------------------------------------------------------------------
    # Read: list
    # ------------------------------------------------------------------

    def list_dlq(
        self,
        ctx: AuthContext,
        *,
        event_type: Optional[str] = None,
        limit: int = DEFAULT_LIMIT,
    ) -> List[DomainEventDLQ]:
        """Return DLQ entries ordered by ``-moved_at`` (admin-only).

        Args:
            ctx: Caller AuthContext (must have the ``admin`` role).
            event_type: Optional filter on ``DomainEventDLQ.event_type``.
            limit: Maximum number of rows to return (1..LIST_LIMIT_CAP,
                default DEFAULT_LIMIT=100). Negative or non-integer
                inputs are coerced to safe defaults.

        Returns:
            List of :class:`DomainEventDLQ` rows. The QuerySet is
            evaluated into a list before the function returns so the
            caller may iterate it outside a DB transaction.
        """
        ServiceBase._assert_permission(ctx, "admin")
        ServiceBase._set_tenant_context(ctx)

        safe_limit = max(1, min(int(limit or DEFAULT_LIMIT), LIST_LIMIT_CAP))

        qs = DomainEventDLQ.objects.all().order_by("-moved_at")
        if event_type:
            qs = qs.filter(event_type=event_type)
        return list(qs[:safe_limit])

    # ------------------------------------------------------------------
    # Write: replay
    # ------------------------------------------------------------------

    def replay_dlq_event(
        self, ctx: AuthContext, event_id: UUID
    ) -> DomainEventDLQ:
        """Re-insert a DLQ event into the Outbox and remove the DLQ row.

        Admin-only. The replay is atomic: either both the new outbox row
        and the DLQ deletion happen, or neither does. The original DLQ
        row is returned to the caller so it can be reported back in the
        MCP response (with the original error_message, retry_count, etc.)
        — the actual replayed event is the new outbox row.

        Args:
            ctx: Caller AuthContext (must have the ``admin`` role).
            event_id: UUID of the original :class:`DomainEventDLQ.event_id`.

        Returns:
            The DLQ row that was removed (snapshot fields before delete).

        Raises:
            PermissionDeniedError: If the caller is not an admin.
            NotFoundError: If no DLQ row with the given ``event_id`` exists.
        """
        ServiceBase._assert_permission(ctx, "admin")
        ServiceBase._set_tenant_context(ctx)

        with transaction.atomic():
            dlq_row = (
                DomainEventDLQ.objects.filter(event_id=event_id).first()
            )
            if dlq_row is None:
                raise NotFoundError(
                    f"DomainEventDLQ entry with event_id={event_id} not found."
                )

            # Snapshot fields before we delete the DLQ row.
            snapshot_event_id = dlq_row.event_id
            snapshot_event_type = dlq_row.event_type
            snapshot_workspace_id = dlq_row.workspace_id
            snapshot_entity_id = dlq_row.entity_id
            snapshot_payload = dict(dlq_row.payload or {})
            snapshot_error_message = dlq_row.error_message
            snapshot_retry_count = dlq_row.retry_count

            # Re-insert into the outbox with a fresh retry budget.
            DomainEventOutbox.objects.create(
                event_id=snapshot_event_id,
                event_type=snapshot_event_type,
                workspace_id=snapshot_workspace_id,
                entity_id=snapshot_entity_id,
                payload=snapshot_payload,
                published=False,
                retry_count=0,
            )

            dlq_row.delete()

            ServiceBase._audit(
                ctx,
                operation="replay",
                entity_type="DomainEventDLQ",
                entity_id=snapshot_event_id,
                change_reason=(
                    f"events.dlq_replay event_type={snapshot_event_type} "
                    f"previous_retry_count={snapshot_retry_count}"
                ),
                details={
                    "operation_kind": "events.dlq_replay",
                    "event_type": snapshot_event_type,
                    "workspace_id": str(snapshot_workspace_id),
                    "entity_id": str(snapshot_entity_id),
                    "previous_retry_count": snapshot_retry_count,
                    "previous_error_message": snapshot_error_message,
                },
            )

            logger.info(
                "DlqService: replayed DLQ event_id=%s type=%s workspace=%s",
                snapshot_event_id,
                snapshot_event_type,
                snapshot_workspace_id,
            )

            # Return the snapshot for the caller (the actual DB row is
            # already deleted, so we cannot return the ORM instance
            # directly).
            return _frozen_snapshot(
                event_id=snapshot_event_id,
                event_type=snapshot_event_type,
                workspace_id=snapshot_workspace_id,
                entity_id=snapshot_entity_id,
                payload=snapshot_payload,
                error_message=snapshot_error_message,
                retry_count=snapshot_retry_count,
            )


# ---------------------------------------------------------------------------
# Internal helper: in-memory snapshot returned by replay_dlq_event
# ---------------------------------------------------------------------------


class _DlqSnapshot:
    """Read-only snapshot of a DLQ row that has just been replayed.

    Used as the return value of :meth:`DlqService.replay_dlq_event` so the
    caller (e.g. the MCP handler) can report original fields to the user
    after the underlying row has been deleted.
    """

    __slots__ = (
        "event_id",
        "event_type",
        "workspace_id",
        "entity_id",
        "payload",
        "error_message",
        "retry_count",
    )

    def __init__(
        self,
        *,
        event_id: UUID,
        event_type: str,
        workspace_id: UUID,
        entity_id: UUID,
        payload: dict,
        error_message: str,
        retry_count: int,
    ) -> None:
        self.event_id = event_id
        self.event_type = event_type
        self.workspace_id = workspace_id
        self.entity_id = entity_id
        self.payload = payload
        self.error_message = error_message
        self.retry_count = retry_count


def _frozen_snapshot(
    *,
    event_id: UUID,
    event_type: str,
    workspace_id: UUID,
    entity_id: UUID,
    payload: dict,
    error_message: str,
    retry_count: int,
) -> _DlqSnapshot:
    return _DlqSnapshot(
        event_id=event_id,
        event_type=event_type,
        workspace_id=workspace_id,
        entity_id=entity_id,
        payload=payload,
        error_message=error_message,
        retry_count=retry_count,
    )


__all__ = ["DlqService", "LIST_LIMIT_CAP", "DEFAULT_LIMIT", "_DlqSnapshot"]
