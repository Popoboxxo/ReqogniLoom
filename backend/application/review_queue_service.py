"""Pending-review queue — the one implementation behind the MCP tool
``review.list_pending`` and the REST endpoints ``GET /api/v1/reviews/pending/``
and ``GET /api/v1/workspaces/{id}/reviews/pending/`` (issue #1089).

Why this module
===============

The review queue existed, but only as an MCP tool. ``GET /api/v1/reviews/pending/``
and ``GET /api/v1/workspaces/<id>/reviews/pending/`` both 404'd, so a human in
the UI had no way to ask "what is waiting for me?" — and an AI derivation that
landed in ``draft`` was invisible on every transport anyway.

Rather than teaching the REST layer a second copy of the queue logic, the
decision ("does this item sit in front of a real human approval gate?") lives
here in Layer 2, and both transports project it:

* :class:`ReviewQueueService` — the shared query (:meth:`list_pending`).
* ``mcp_server.tools.review.ReviewToolGroup._handle_list_pending`` — projects
  each row to the historical three-key MCP shape.
* ``rest_api.review_views`` — projects each row to the REST row shape and
  paginates it.

The gate itself is ``workflow.services.is_approval_gate`` — a transition whose
``allowed_roles`` excludes ``"editor"`` is a real sign-off, while one an
``editor`` may already take unsupervised is a self-service submission step.
That predicate is the *existing* mechanism and is not re-implemented here.

**AI proposals are surfaced by the same query.** An item in
:data:`workflow.definition_store.PROPOSED_STATE` is pending exactly when the
graph's proposal transitions are editor-gated (``PROPOSED_ROLES`` includes
``editor``, so ``is_approval_gate`` is *False* for them) — i.e. the generic
approval-gate rule deliberately does **not** catch proposals, because
confirming a proposal is a review chore rather than an approval decision. The
queue therefore unions two sets:

1. items in front of a genuine approval gate (``is_approval_gate``), and
2. items in the proposal state.

``states`` narrows that union to the states the caller asked about, which is
what lets the REST endpoint ask for "just the AI proposals" and what keeps the
per-item ``get_available_transitions`` walk proportional to the queue instead
of to the whole workspace.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional
from uuid import UUID

from auth_tenancy.context import AuthContext

from application.base import PermissionDeniedError, ServiceBase
from application.workspace_service import WorkspaceService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PendingReviewItem:
    """One item waiting for a human decision.

    Attributes:
        item_id: Primary key of the tracked item.
        item_type: Workflow ``item_type`` (``"Requirement"``, ``"Adr"``, ...).
        current_state: The item's workflow state.
        workspace_id: Workspace the item belongs to.
        is_proposal: Whether the item is an AI proposal (#904 /
            :data:`workflow.definition_store.PROPOSED_STATE`).
        proposed_by: Actor of the newest ``-> "proposed"`` history entry, or
            ``None`` — the "Vorschlag von {label}" provenance the artefact
            header shows.
        proposed_at: Timestamp of that history entry, or ``None``.
        approval_targets: States reachable from here through a genuine
            approval-gated transition, for a caller that wants to render the
            decision without a second request.
    """

    item_id: str
    item_type: str
    current_state: str
    workspace_id: str
    is_proposal: bool = False
    proposed_by: Optional[str] = None
    proposed_at: Optional[str] = None
    approval_targets: tuple[str, ...] = field(default=())

    def to_dict(self) -> dict[str, Any]:
        """Return the REST row shape (additive keys only)."""
        return {
            "item_id": self.item_id,
            "item_type": self.item_type,
            "current_state": self.current_state,
            "workspace_id": self.workspace_id,
            "is_proposal": self.is_proposal,
            "proposed_by": self.proposed_by or "",
            "proposed_at": (
                self.proposed_at.isoformat() if self.proposed_at else ""
            ),
            "approval_targets": list(self.approval_targets),
        }


def _proposal_history_by_item(
    item_ids: Iterable[str], item_type: str
) -> dict[str, tuple[str, Any]]:
    """Return ``{item_id: (transitioned_by, transitioned_at)}`` for proposals.

    One query for the whole page instead of one per row, and only for the rows
    that actually are proposals — the common case (an ordinary ``in_review``
    queue) costs no query at all.
    """
    ids = [str(i) for i in item_ids]
    if not ids:
        return {}
    from workflow.models import WorkflowHistoryEntry, WorkflowItemState

    out: dict[str, tuple[str, Any]] = {}
    states = WorkflowItemState.objects.filter(
        item_id__in=ids, item_type=item_type
    ).values_list("id", "item_id")
    state_by_item = {str(item_id): pk for pk, item_id in states}
    if not state_by_item:
        return out
    entries = (
        WorkflowHistoryEntry.objects.filter(
            item_state_id__in=list(state_by_item.values()), to_state="proposed"
        )
        .order_by("transitioned_at")
        .values("item_state_id", "transitioned_by", "transitioned_at")
    )
    # Newest wins: the rows arrive oldest-first, so a later assignment
    # overwrites an earlier one.
    pk_to_item = {pk: item for item, pk in state_by_item.items()}
    for entry in entries:
        out[pk_to_item[entry["item_state_id"]]] = (
            entry["transitioned_by"],
            entry["transitioned_at"],
        )
    return out


class ReviewQueueService(ServiceBase):
    """Layer-2 pending-review queue (ADR-01, REQ-L2-RV-001).

    Every read is tenant- and workspace-scoped. :meth:`list_pending` resolves
    the workspace through :class:`WorkspaceService` first, so a caller from
    another tenant gets the same 404 as a non-existent workspace and a caller
    with no role in it gets the same 403 — the queue can never widen the
    authorisation surface of the artefacts it lists.
    """

    def list_pending(
        self,
        ctx: AuthContext,
        *,
        workspace_id: UUID | str,
        item_type: str | None = None,
        states: Iterable[str] | None = None,
        required_roles: Iterable[str] | None = None,
    ) -> list[PendingReviewItem]:
        """Return the workspace's items awaiting a human decision.

        Args:
            ctx: Authenticated, tenant-scoped context.
            workspace_id: Workspace to scope the query to. Resolved through
                :meth:`WorkspaceService.get_workspace` first, which is what
                makes a foreign workspace a 404.
            item_type: Optional single-type filter. ``None`` scans every tracked
                type in the workspace.
            states: Optional whitelist of workflow states to consider. A state
                with neither a proposal nor an approval-gated outgoing
                transition yields nothing, so this narrows the scan in SQL
                rather than filtering a fully materialised result.
            required_roles: Optional workspace-scoped role gate, opt-in per
                transport. When ``None`` (the default, and what the MCP
                ``review.list_pending`` tool passes) this service adds **no**
                gate of its own, because that transport's dispatcher already
                resolved the caller's roles workspace-scoped and fenced the key
                to the target workspace before the handler runs
                (``mcp_server.tool_registry._resolve_roles`` /
                ``_check_workspace_fence``). REST passes
                ``workflow.definition_store.PROPOSED_ROLES`` because a REST
                request's ``active_roles`` are the tenant-wide union — the
                workspace arrives as a path/query parameter, not from the
                token — so the gate has to happen here. Any non-``None`` value
                requires the caller to be a member of the workspace AND to
                hold one of the named roles there; an empty iterable means
                "any active role in the workspace".

        Returns:
            The pending items, ordered by ``(item_type, current_state,
            item_id)`` so a paginated response is stable across calls.

        Raises:
            NotFoundError: The workspace does not exist for this tenant.
            PermissionDeniedError: The caller holds no role in the workspace,
                or none of *required_roles*.
        """
        from workflow.definition_store import PROPOSED_STATE
        from workflow.services import get_available_transitions, is_approval_gate

        workspace_uuid = UUID(str(workspace_id))
        self._set_tenant_context(ctx)
        # Authorisation first: every read below returns rows this call has
        # just proven the caller may see.
        WorkspaceService().get_workspace(workspace_uuid, ctx)
        if required_roles is not None:
            self._assert_workspace_role(ctx, workspace_uuid, required_roles)

        from workflow.services import list_item_states

        rows = list_item_states(
            workspace_uuid, tenant_id=ctx.tenant_id, item_type=item_type
        ).values_list("item_id", "item_type", "current_state")

        wanted = {str(s) for s in states} if states is not None else None

        # Group by (item_type, current_state): `get_available_transitions`
        # derives its answer from `dto.transitions` filtered on
        # `from_state == current_state` (workflow/services.py) and from nothing
        # item-specific, so one call per group is exactly equivalent to one
        # call per item — and the difference is what keeps a 100-item
        # workspace from costing 100 graph lookups.
        grouped: dict[tuple[str, str], list[Any]] = {}
        for item_id, row_type, current_state in rows:
            if wanted is not None and current_state not in wanted:
                continue
            grouped.setdefault((row_type, current_state), []).append(item_id)
        if not grouped:
            return []

        pending: list[PendingReviewItem] = []
        for (row_type, current_state), item_ids in grouped.items():
            is_proposal = current_state == PROPOSED_STATE
            if is_proposal:
                # A proposal's own moves are editor-gated by design (see the
                # module docstring), so the gate predicate is deliberately not
                # consulted for it — membership is the state name alone.
                targets: tuple[str, ...] = ()
            else:
                available = get_available_transitions(
                    item_ids[0], row_type, workspace_uuid
                )
                targets = tuple(
                    t.to_state for t in available.transitions if is_approval_gate(t)
                )
                if not targets:
                    continue
            for item_id in item_ids:
                pending.append(
                    PendingReviewItem(
                        item_id=str(item_id),
                        item_type=row_type,
                        current_state=current_state,
                        workspace_id=str(workspace_uuid),
                        is_proposal=is_proposal,
                        approval_targets=targets,
                    )
                )

        pending.sort(key=lambda i: (i.item_type, i.current_state, i.item_id))
        _attach_provenance(pending)
        return pending

    @staticmethod
    def _assert_workspace_role(
        ctx: AuthContext,
        workspace_id: UUID,
        required_roles: Iterable[str],
    ) -> None:
        """Assert the caller holds an active role in *workspace_id*.

        Membership is derived from :class:`~auth_tenancy.models.UserRole` — a
        user is a member iff they hold at least one non-suspended role in the
        workspace — the same rule
        :meth:`AuthorizationService.list_workspace_members` applies as its own
        access gate (REQ-014 AC#1). This is defense in depth on top of the
        tenant scoping every ORM read already gets: a member of one workspace
        must not be able to enumerate another's review queue.

        An API-key principal is additionally bound by its own
        ``api_key_workspace_ids`` (already enforced by the auth layer), so
        there is nothing to re-check for it.

        Raises:
            PermissionDeniedError: The caller is not a member of the workspace,
                or holds none of *required_roles* in it.
        """
        from auth_tenancy.models import UserRole

        roles = set(
            UserRole.objects.filter(
                user_id=ctx.user_id,
                workspace_id=workspace_id,
                suspended_at__isnull=True,
            ).values_list("role", flat=True)
        )
        if not roles:
            raise PermissionDeniedError(
                f"You hold no role in workspace {workspace_id}, so its review "
                "queue is not visible to you."
            )
        wanted = {str(r).lower() for r in required_roles}
        if wanted and not (roles & wanted):
            raise PermissionDeniedError(
                f"Viewing the review queue requires one of the roles "
                f"{sorted(wanted)} in this workspace; you hold {sorted(roles)}."
            )


def _attach_provenance(items: list[PendingReviewItem]) -> None:
    """Fill ``proposed_by``/``proposed_at`` on the proposal rows, in place.

    Batched per ``item_type``: one query for the whole page instead of one per
    row, and none at all when the queue holds no proposals (the common case
    for an ordinary ``in_review`` queue). The DTO stays frozen — the fields
    are assigned through ``object.__setattr__`` so no consumer can observe a
    half-filled row.
    """
    proposals = [i for i in items if i.is_proposal]
    if not proposals:
        return
    for item_type in {i.item_type for i in proposals}:
        group = [i for i in proposals if i.item_type == item_type]
        history = _proposal_history_by_item([i.item_id for i in group], item_type)
        for item in group:
            actor, at = history.get(item.item_id, (None, None))
            object.__setattr__(item, "proposed_by", actor)
            object.__setattr__(item, "proposed_at", at)


__all__ = ["PendingReviewItem", "ReviewQueueService"]
