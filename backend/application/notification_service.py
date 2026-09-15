"""Notification production and read access (Menschen-im-System spec §5).

Layer 2 (ADR-01): every ORM access for notifications lives here. The four
triggers call ``create_notifications``; Layer 3 (REST) calls
``NotificationService``.

There is deliberately no MCP tool group and no real-time push: agents do not
read a notification center, and the frontend fetches this table once when the
NavigationShell mounts.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable, Optional
from uuid import UUID

from auth_tenancy.context import AuthContext
from persistence.errors import NotFoundError

from application.base import ServiceBase
from application.models import Notification
from application.notification_preference_service import NotificationPreferenceService
from application.trace_link_service import resolve_artifact_id_or_none

logger = logging.getLogger(__name__)

#: Hard ceiling on a single fan-out. The transition_pending role broadcast in a
#: workspace with a pathological member count would otherwise write unbounded
#: rows inside the transition transaction.
#: ponytail: fixed cap; make it a workspace setting only if a real workspace hits it.
MAX_FANOUT = 200


def create_notifications(
    *,
    user_ids: Iterable[Optional[UUID]],
    kind: str,
    message: str,
    artifact_id: Optional[UUID],
    tenant_id: UUID,
    exclude_user_id: Optional[UUID] = None,
) -> int:
    """Write one Notification per distinct non-null recipient; return the count.

    ``None`` entries are dropped (callers pass unset ``owner``/``assignee``
    straight through), duplicates are collapsed (owner == assignee is one
    notification), first-seen order is preserved, and ``exclude_user_id`` drops
    the acting user (spec §5.4: no self-notification on your own comment).

    This is the ONE place the recipient preference filter is applied (OD-1,
    Task 27): producers hand over a *candidate* list and never filter their own
    recipients, which is what makes the preference impossible to forget on one
    path and honour on another. The filter runs *before* the ``MAX_FANOUT``
    clamp so the clamp counts the users who will actually be notified.
    """
    recipients = list(dict.fromkeys(uid for uid in user_ids if uid is not None))
    if exclude_user_id is not None:
        recipients = [uid for uid in recipients if uid != exclude_user_id]
    if not recipients:
        return 0

    # The producer contract has no ``ctx`` parameter, and the preference table
    # is not tenant-scoped — only ``ctx.tenant_id`` is ever read here, so a
    # minimal system context is sufficient and keeps the signature identical
    # across all four producers (§10).
    recipients = NotificationPreferenceService().apply_preferences(
        AuthContext.system(tenant_id=tenant_id), recipients, kind
    )
    if not recipients:
        return 0

    if len(recipients) > MAX_FANOUT:
        logger.warning(
            "Notification fan-out for kind=%s capped at %d (was %d).",
            kind,
            MAX_FANOUT,
            len(recipients),
        )
        recipients = recipients[:MAX_FANOUT]

    rows = [
        Notification(
            tenant_id=tenant_id,
            user_id=user_id,
            kind=kind,
            artifact_id=artifact_id,
            message=message,
            read=False,
        )
        for user_id in recipients
    ]
    Notification.unscoped.bulk_create(rows)
    return len(rows)


def notify_assigned(
    *,
    ctx: AuthContext,
    artifact_id: Optional[UUID],
    owner: Any,
    previous_owner_id: Optional[UUID],
) -> int:
    """Notify the newly set artifact owner; return the number of rows written.

    Folded in from the superseded Task 11: the seam is the attribute gateway
    (§5), not an ``assignment.py``. Fires **only** when the owner ``Actor``
    actually changed (``owner.id != previous_owner_id``) and only for an
    internal actor (``kind == "user"`` with a non-null ``user_id``) — an
    ``external`` placeholder has no login and no notification feed.

    ``reporter`` is deliberately NOT notified: OD-1 resolved it as provenance,
    not an assignment (changeable later by extending this producer).

    Never raises: wrapped in ``try/except`` + ``logger.exception`` like the
    other producers, so a notification failure cannot roll back a legitimate
    attribute write.
    """
    try:
        current_owner_id = getattr(owner, "id", None)
        if current_owner_id is None or current_owner_id == previous_owner_id:
            return 0
        if getattr(owner, "kind", None) != "user":
            return 0
        user_id = getattr(owner, "user_id", None)
        if user_id is None:
            return 0

        return create_notifications(
            user_ids=[user_id],
            kind=Notification.KIND_ASSIGNED,
            message="You were assigned an artifact",
            artifact_id=artifact_id,
            tenant_id=ctx.tenant_id,
            exclude_user_id=ctx.user_id,
        )
    except Exception:
        logger.exception(
            "notify_assigned: failed for artifact_id=%s previous_owner_id=%s",
            artifact_id,
            previous_owner_id,
        )
        return 0


def _get_definition(workspace_id: UUID, item_type: str):
    """Return the active WorkflowDefinitionDTO. Isolated so tests can patch it."""
    from workflow.definition_store import WorkflowDefinitionStore

    return WorkflowDefinitionStore().get_definition(workspace_id, item_type)


def _user_ids_with_roles(*, workspace_id: UUID, roles: Iterable[str]) -> list[UUID]:
    """Return the ids of every non-suspended user holding one of *roles* here.

    Workspace-scoped by design: a role is granted per workspace
    (``auth_tenancy.UserRole``), so a global role lookup would notify people
    who cannot act on this item at all.
    """
    from auth_tenancy.models import UserRole

    return list(
        UserRole.objects.filter(
            workspace_id=workspace_id,
            role__in=list(roles),
            suspended_at__isnull=True,
        )
        .values_list("user_id", flat=True)
        .distinct()
    )


def notify_transition_pending(
    *,
    item_id: UUID,
    item_type: str,
    workspace_id: UUID,
    new_state: str,
    tenant_id: UUID,
    actor_user_id: UUID,
) -> int:
    """Notify everyone who may act on the item's *next* transition (spec §5.1).

    Role broadcast, not person-scoped routing — personalised assignment per
    transition is explicitly Q2.5 scope (spec §6). Covers the KI-Vorschlag
    ``proposed`` state with no special case: ``proposed -> draft`` and
    ``proposed -> rejected`` are ordinary role-gated transitions.

    Never raises: a notification must not break the transition it reacts to.
    """
    try:
        definition = _get_definition(workspace_id, item_type)
    except Exception:
        logger.warning(
            "notify_transition_pending: no workflow definition for workspace=%s type=%s",
            workspace_id,
            item_type,
            exc_info=True,
        )
        return 0

    roles: set[str] = set()
    for transition in definition.transitions:
        if transition.from_state == new_state:
            roles.update(transition.allowed_roles or ())

    if not roles:
        return 0

    try:
        user_ids = _user_ids_with_roles(workspace_id=workspace_id, roles=roles)
        return create_notifications(
            user_ids=user_ids,
            kind=Notification.KIND_TRANSITION_PENDING,
            message=f"{item_type} is in state '{new_state}' and awaits your action",
            artifact_id=resolve_artifact_id_or_none(item_id),
            tenant_id=tenant_id,
            exclude_user_id=actor_user_id,
        )
    except Exception:
        logger.exception("notify_transition_pending failed for item %s", item_id)
        return 0


def _load_artifact(artifact_id: UUID):
    """Fetch an Artifact with its owner-bearing relations. Isolated for patching."""
    from persistence.models import Artifact

    return (
        Artifact.objects.filter(pk=artifact_id)
        .select_related("owner", "reporter")
        .first()
    )


def _recipient_user_ids_for_artifact(artifact: Any) -> list[UUID]:
    """Return the user ids to notify for *artifact*. Isolated so tests can patch it.

    The rule itself — owner + reporter, internal actors only, external
    placeholders dropped (OD-4) — lives in
    ``application.comment_service.notify_user_ids_for_artifact``. The import is
    lazy on purpose: ``comment_service`` already imports this module, so a
    module-level import would be a cycle. Same patch-seam convention as
    ``_load_artifact`` / ``_get_definition``.
    """
    from application.comment_service import notify_user_ids_for_artifact

    return notify_user_ids_for_artifact(artifact)


def notify_suspect_flagged(
    *,
    artifact_id: UUID,
    tenant_id: UUID,
    actor_user_id: Optional[UUID] = None,
) -> int:
    """Notify an artifact's owner and reporter that it was flagged suspect.

    Called by the suspect propagation
    (``TraceLinkService.propagate_suspect_status``) right after it stamps the
    links that actually caused a flag (spec §5.2). Recipients come from
    ``notify_user_ids_for_artifact`` (Task 15) — owner + reporter, internal
    actors only, so an externally owned artifact produces no notification at all
    (OD-4). The per-user preference filter runs inside ``create_notifications``
    (OD-1); a producer-local check would be a second, divergence-prone filter.

    The generic ``Artifact`` carries no human title of its own (the title lives
    on the type-specific row), so the message falls back to the id rather than
    let an ``AttributeError`` silence the whole fan-out.

    Never raises: a notification must not break the propagation that triggered
    it.
    """
    try:
        artifact = _load_artifact(artifact_id)
        if artifact is None:
            return 0

        artifact_label = getattr(artifact, "title", None) or str(artifact.pk)
        return create_notifications(
            user_ids=_recipient_user_ids_for_artifact(artifact),
            kind=Notification.KIND_SUSPECT_FLAGGED,
            message=f"{artifact_label} was flagged suspect by an upstream change",
            artifact_id=artifact_id,
            tenant_id=tenant_id,
            exclude_user_id=actor_user_id,
        )
    except Exception:
        logger.exception("notify_suspect_flagged failed for artifact %s", artifact_id)
        return 0


class NotificationService(ServiceBase):
    """Read side of the notification center."""

    def list_for_user(
        self,
        ctx: AuthContext,
        *,
        unread_only: bool = False,
        limit: int = 50,
    ) -> list[Notification]:
        """Return the caller's own notifications, newest first."""
        self._set_tenant_context(ctx)
        qs = Notification.objects.filter(user_id=ctx.user_id)
        if unread_only:
            qs = qs.filter(read=False)
        return list(qs[: max(1, min(limit, 200))])

    def unread_count(self, ctx: AuthContext) -> int:
        """Return how many unread notifications the caller has."""
        self._set_tenant_context(ctx)
        return Notification.objects.filter(user_id=ctx.user_id, read=False).count()

    def mark_read(self, notification_id: UUID, ctx: AuthContext) -> Notification:
        """Mark one of the caller's own notifications as read.

        Raises NotFoundError for someone else's notification — deliberately the
        same error as "does not exist", so the endpoint cannot be used to probe
        which notification ids are real.
        """
        self._set_tenant_context(ctx)
        row = Notification.objects.filter(pk=notification_id, user_id=ctx.user_id).first()
        if row is None:
            raise NotFoundError(f"Notification {notification_id} not found")
        if not row.read:
            row.read = True
            row.save(update_fields=["read"])
        return row

    def mark_all_read(self, ctx: AuthContext) -> int:
        """Mark every unread notification of the caller as read; return the count."""
        self._set_tenant_context(ctx)
        return Notification.objects.filter(user_id=ctx.user_id, read=False).update(read=True)


__all__ = [
    "MAX_FANOUT",
    "NotificationService",
    "create_notifications",
    "notify_assigned",
    "notify_suspect_flagged",
    "notify_transition_pending",
]
