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

For ordinary items the gate is :func:`resolve_approval_target` — the one
predicate shared with ``review.approve``/``reject``/``request_changes``. It
prefers the definition's ``auto_approve_target``, otherwise takes a transition
whose ``allowed_roles`` excludes ``"editor"`` (``is_approval_gate`` -- a real
sign-off rather than an editor's self-service submission step), and always
excludes self-transitions and ``is_outdated_equivalent`` rejection endpoints
(issues #2015/#2017/#2018). One decision, every transport.

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
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from uuid import UUID

from application.base import PermissionDeniedError, ServiceBase
from application.workspace_service import WorkspaceService
from auth_tenancy.context import AuthContext

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids Django startup cost
    from workflow.definition_store import TransitionDefinitionDTO

logger = logging.getLogger(__name__)


def resolve_approval_target(
    *,
    current_state: str | None,
    transitions: Iterable[TransitionDefinitionDTO],
    workflow_json: dict[str, Any],
) -> str | None:
    """Return the state an approval decision would move to, or ``None``.

    One predicate answering "is this item awaiting a human review decision?"
    for every transport (issues #2015/#2016/#2017/#2018). It is the exact rule
    ``review.approve`` has always applied, lifted out of the MCP layer so the
    pending queue, ``approve``, ``reject`` and ``request_changes`` can no
    longer disagree about which items are reviewable:

    1. prefer the definition's explicit ``auto_approve_target`` among the
       transitions available from the item's current state;
    2. otherwise take the first approval-gated transition (``allowed_roles``
       excludes ``editor`` -- :func:`workflow.services.is_approval_gate`);
    3. ignore self-transitions and states flagged ``is_outdated_equivalent``
       (a rejection endpoint is not an approval endpoint, GH-370).

    ``None`` means the item is **not** awaiting review: either the current
    state could not be resolved, or it has no genuine approval-shaped move.
    "proposed" is deliberately not special-cased here -- callers that surface
    AI proposals keep their own state-name branch (see ``list_pending``).

    Args:
        current_state: The item's workflow state. ``None`` means unresolved;
            the predicate then has no genuine transition to return.
        transitions: The moves available from *current_state* (the
            ``AvailableTransitions.transitions`` tuple).
        workflow_json: Raw workflow document supplying ``state_meta``; an
            empty dict is handled as "no per-state metadata".

    Returns:
        The approval target state name, or ``None`` when the item is not
        awaiting a human approval decision.
    """
    from workflow.definition_store import get_state_meta
    from workflow.services import is_approval_gate

    if current_state is None:
        return None

    genuine = [t for t in transitions if t.from_state != t.to_state]
    meta = {t.to_state: get_state_meta(workflow_json, t.to_state) for t in genuine}
    target = next(
        (
            t.to_state
            for t in genuine
            if meta[t.to_state].get("auto_approve_target", False)
            and not meta[t.to_state].get("is_outdated_equivalent", False)
        ),
        None,
    )
    if target is None:
        gate = next(
            (
                t
                for t in genuine
                if is_approval_gate(t)
                and not meta[t.to_state].get("is_outdated_equivalent", False)
            ),
            None,
        )
        target = gate.to_state if gate is not None else None
    return target


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
    proposed_by: str | None = None
    proposed_at: str | None = None
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
                ``_check_workspace_fence``). REST passes the RBAC READ role
                list from ``auth_tenancy.services.roles_with_capability``
                because a REST request's ``active_roles`` are the tenant-wide
                union — the workspace arrives as a path/query parameter, not
                from the token — so the gate has to happen here. Any
                non-``None`` value requires the caller to be a member of the
                workspace AND to hold one of the named roles there; an empty
                iterable means "any active role in the workspace". The queue is
                a pure read, so every role passes the role test and membership
                is the effective gate (#1594).

        Returns:
            The pending items, ordered by ``(item_type, current_state,
            item_id)`` so a paginated response is stable across calls.

        Raises:
            NotFoundError: The workspace does not exist for this tenant.
            PermissionDeniedError: The caller holds no role in the workspace,
                or none of *required_roles*.
        """
        from workflow.definition_store import PROPOSED_STATE
        from workflow.services import get_available_transitions, get_workflow_json

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
                # #2015: use the SAME predicate as review.approve so the queue
                # never lists an item approve() would refuse (e.g. an Issue in
                # ``open`` whose sole gate target ``wontfix`` is
                # ``is_outdated_equivalent``). The filtered target is also what
                # ``to_dict()`` surfaces to REST as ``approval_targets``.
                target = resolve_approval_target(
                    current_state=available.current_state,
                    transitions=available.transitions,
                    workflow_json=get_workflow_json(workspace_uuid, row_type),
                )
                if target is None:
                    continue
                targets = (target,)
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


__all__ = ["PendingReviewItem", "ReviewQueueService", "resolve_approval_target"]
