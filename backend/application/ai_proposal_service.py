"""AI-proposal authoring context — the single seam for "this artefact is a
proposal a human still has to accept" (issue #1089).

Why this module exists
======================

Issue #904 ("KI-Vorschlag-als-Zustand") already established the *proposal
state*: :data:`workflow.definition_store.PROPOSED_STATE` is injected into every
default workflow graph except ``minimal`` and ``interview_default``, and
:func:`workflow.services.initial_state_for` seeds a newly created item there
whenever the acting principal is an **agent**.

That switch keys on ``ctx.actor_type == "agent"``, which is decided at the auth
layer and is therefore correct for MCP/API-key traffic — and *wrong* for the
dominant AI-derivation path: a human pressing "KI-Ableitung" in the UI. There
the credential is a Bearer token, ``actor_type`` is ``"user"``, and every
AI-authored Requirement landed in ``draft``. The derivation reported success,
the rows existed, and no human was ever shown them for approval — the exact
SE-correctness gap #1089 reports.

What this module does
=====================

It separates *"who pressed the button"* (an audit fact, owned by the auth layer
and carried by :class:`~auth_tenancy.context.AuthContext`) from *"who wrote the
content"* (a domain fact, owned here). :func:`resolve_proposal_authoring`
answers the second question and returns a context the creation path hands to
the service that persists the artefact:

* when the workspace's graph for *item_type* actually contains
  ``"proposed"`` → ``create_context`` is the caller's context with
  ``actor_type="agent"`` and ``agent_label`` naming the derivation, so
  :func:`workflow.services.initial_state_for` seeds the row in the proposal
  state and :class:`~workflow.lifecycle_manager.StateLifecycleManager` writes the
  ``from_state="" -> "proposed"`` history entry that
  :func:`rest_api.mixins.workflow_transitions.resolve_proposed_by` reads back as
  ``proposed_by``;
* when it does not (a ``minimal``-preset workspace, or an admin who removed the
  state from their customised graph) → ``supported`` is ``False`` and
  ``reason`` names the state the artefact will actually get. **The caller is
  required to surface that**, never to quietly accept the downgrade:
  :func:`require_proposal_support` raises instead, for the callers whose whole
  contract is "create a reviewable proposal".

Why no ``draft -> proposed`` transition
=======================================

``workflow.definition_store.inject_proposed_state`` gives ``proposed`` exactly
two *outgoing* moves (confirm to the graph's initial state, discard to the
reject state). There is deliberately no ``draft -> proposed`` edge, so an
artefact cannot be promoted after the fact through the engine — it has to be
*born* a proposal. That is why the seeding happens through
``initialize_workflow_states(initial_state=...)`` at creation time and why
:func:`verify_proposal_state` re-reads the row instead of trusting the intent.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from typing import Optional
from uuid import UUID

from auth_tenancy.context import AuthContext

from application.base import ServiceBase, ValidationError

logger = logging.getLogger(__name__)

#: ``proposed_by`` / ``agent_label`` for a derivation started from a human
#: session. The API-key path keeps its own label (``ctx.agent_label``) — this
#: only fills the gap where no agent principal exists to name one.
AI_DERIVATION_LABEL = "ai-derivation"


@dataclass(frozen=True)
class ProposalAuthoring:
    """Outcome of resolving "should this artefact be born a proposal?".

    Attributes:
        create_context: The :class:`AuthContext` to hand to the creation
            service. Carries the caller's identity, tenant, roles and
            workspace **unchanged**; only ``actor_type`` and ``agent_label``
            are rewritten when the graph supports proposals, and ``actor_type``
            is additionally forced back to ``"user"`` when it does not, so the
            unsupported case is also the *honest* audit case.
        supported: Whether the workspace's resolved graph for ``item_type``
            contains :data:`workflow.definition_store.PROPOSED_STATE`.
        state: The state the artefact will actually be created in —
            ``"proposed"`` when supported, otherwise the graph's initial state.
        reason: Human-readable explanation of why the proposal state is
            unavailable, or ``""`` when it is.
        label: The ``proposed_by`` value recorded in the proposal history entry.
    """

    create_context: AuthContext
    supported: bool
    state: str
    reason: str
    label: str


def _definition_for(workspace_id: UUID, item_type: str):
    """Return the resolved ``WorkflowDefinitionDTO`` for a workspace/type.

    ``None`` when the workspace has no workflow configured for that type — the
    same "not configured" answer :meth:`WorkflowFacade.get_definition` gives,
    so a definition-less workspace degrades to the documented initial state
    instead of raising through the creation path.
    """
    from workflow.definition_store import WorkflowDefinitionError
    from workflow.services import get_definition

    try:
        return get_definition(workspace_id, item_type)
    except WorkflowDefinitionError:
        return None
    except Exception:  # noqa: BLE001 — never break a creation over a probe
        logger.warning(
            "ProposalAuthoring: no workflow definition for workspace=%s type=%s",
            workspace_id,
            item_type,
            exc_info=True,
        )
        return None


def resolve_proposal_authoring(
    ctx: AuthContext,
    *,
    item_type: str,
    workspace_id: UUID | str,
    label: str = "",
) -> ProposalAuthoring:
    """Resolve the authoring context for one AI-derived artefact.

    Never raises: a graph that cannot express a proposal is a *reportable
    outcome*, not an error at this level. Use :func:`require_proposal_support`
    for the callers that cannot accept the downgrade.

    Args:
        ctx: The caller's context. Its identity, tenant, roles and workspace
            are preserved verbatim; only the authorship markers change.
        item_type: Workflow ``item_type`` of the artefact about to be created
            (e.g. ``"Requirement"``).
        workspace_id: Workspace the artefact belongs to.
        label: Overrides the proposal label. Defaults to the caller's
            ``agent_label`` for an API-key caller, else
            :data:`AI_DERIVATION_LABEL`.

    Returns:
        The :class:`ProposalAuthoring` to drive the creation.
    """
    from workflow.definition_store import PROPOSED_STATE

    # The definition read below goes through the tenant-scoped ORM manager, so
    # the thread-local must be armed here rather than at the call site. Every
    # caller of this function either already did (``ServiceBase._set_tenant_context``
    # in the AiDerivationService / AiProposalService facades, or the
    # ``_write_*`` helpers) or is a direct unit-test caller; without this the
    # read raised ``TenantContextNotSetError``, was swallowed by the
    # "never break a creation over a probe" guard below, and every call
    # silently reported "no workflow configured" — a fail-open into a wrong
    # answer, which is the exact class of bug #1089 is about.
    from persistence.tenancy import TenantContext

    TenantContext.set_tenant(ctx.tenant_id)

    resolved_label = label or ctx.agent_label or AI_DERIVATION_LABEL
    dto = _definition_for(UUID(str(workspace_id)), item_type)

    if dto is None:
        return ProposalAuthoring(
            create_context=_as_user(ctx),
            supported=False,
            state="draft",
            reason=(
                f"No workflow is configured for {item_type} in this workspace, "
                f"so '{PROPOSED_STATE}' cannot be assigned. The artefact is "
                "created in its default state and is NOT a reviewable proposal."
            ),
            label=resolved_label,
        )

    if PROPOSED_STATE in dto.states:
        return ProposalAuthoring(
            create_context=replace(
                ctx, actor_type="agent", agent_label=resolved_label
            ),
            supported=True,
            state=PROPOSED_STATE,
            reason="",
            label=resolved_label,
        )

    return ProposalAuthoring(
        create_context=_as_user(ctx),
        supported=False,
        state=dto.initial_state,
        reason=(
            f"The workflow configured for {item_type} in this workspace has no "
            f"'{PROPOSED_STATE}' state (its initial state is "
            f"'{dto.initial_state}'), so the artefact is created in "
            f"'{dto.initial_state}' and is NOT a reviewable proposal."
        ),
        label=resolved_label,
    )


def require_proposal_support(
    authoring: ProposalAuthoring, *, item_type: str
) -> ProposalAuthoring:
    """Return *authoring* unchanged, or raise when it cannot produce a proposal.

    For the callers whose contract *is* the proposal (the REST persist path a
    human triggers from the UI). A ``minimal``-preset workspace, or one whose
    admin removed ``"proposed"`` from the graph, is a real 4xx for them —
    answering 201 with an unreviewable draft is exactly the silent downgrade
    #1089 forbids.

    Raises:
        ValidationError: The graph cannot express a proposal for *item_type*.
            The message is the human-readable ``authoring.reason``.
    """
    if authoring.supported:
        return authoring
    raise ValidationError(
        f"This workspace cannot create reviewable AI proposals: {authoring.reason}"
    )


def verify_proposal_state(
    item_id: UUID | str, item_type: str
) -> tuple[Optional[str], Optional[str]]:
    """Re-read an artefact's real workflow state and proposal provenance.

    The verification half of #1089: the creation path is only allowed to claim
    "created as a proposal" when the row actually says so. Returns
    ``(current_state, proposed_by)`` — ``(None, None)`` when the state cannot
    be read (a definition-less workspace writes no ``WorkflowItemState`` at
    all), which the caller reports rather than treats as success.

    Reads through ``workflow.state_reader`` with no tenant context argument on
    purpose: the caller has already set the thread-local tenant via
    ``ServiceBase._set_tenant_context``, and the state row was just written by
    the same transaction.
    """
    from workflow import state_reader

    current = state_reader.current_state(item_type, UUID(str(item_id)))
    if current != "proposed":
        return current, None
    return current, _latest_proposal_actor(
        UUID(str(item_id)), item_type, None
    )


def proposal_report(
    *,
    state: Optional[str],
    proposed_by: Optional[str],
    supported: bool,
    reason: str,
    label: str,
) -> dict:
    """Build the machine-readable ``proposal`` block of a write response.

    The block is **always** present on an AI write so a client can never
    mistake a plain draft for a proposal. ``state`` is the state that was
    actually written; ``supported`` says whether the graph could express a
    proposal at all; ``reason`` explains the gap when it could not.
    """
    return {
        "state": state or "",
        "is_proposal": state == "proposed",
        "supported": supported,
        "proposed_by": proposed_by or "",
        "label": label,
        "reason": reason,
    }


def _as_user(ctx: AuthContext) -> AuthContext:
    """Return *ctx* with ``actor_type`` forced to ``"user"``.

    Used on the unsupported branch so the audit log keeps recording the
    principal that actually acted. The alternative — leaving ``"agent"`` in
    place — would file a human-triggered derivation under
    ``actor_type="agent"`` in a workspace whose graph has no proposal state,
    which is both untrue and lossy for the audit trail.
    """
    if ctx.actor_type == "user":
        return ctx
    return replace(ctx, actor_type="user", agent_label="")


def _latest_proposal_actor(
    item_id: UUID, item_type: str, workspace_id: Optional[UUID]
) -> Optional[str]:
    """Return the actor of the newest ``-> "proposed"`` history entry.

    Same read ``rest_api.mixins.workflow_transitions._latest_proposal_actor``
    performs; duplicated here rather than imported because that module is
    Layer 3 and this is Layer 2 (ADR-01: Layer 2 must not import Layer 3).
    """
    from workflow.models import WorkflowHistoryEntry, WorkflowItemState

    filters: dict = {"item_id": item_id, "item_type": item_type}
    if workspace_id is not None:
        filters["workspace_id"] = workspace_id
    state = WorkflowItemState.objects.filter(**filters).first()
    if state is None:
        return None
    entry = (
        WorkflowHistoryEntry.objects.filter(item_state=state, to_state="proposed")
        .order_by("-transitioned_at")
        .first()
    )
    return entry.transitioned_by if entry is not None else None


class AiProposalService(ServiceBase):
    """Layer-2 facade over the proposal-authoring seam (ADR-01).

    Thin on purpose: every method is a pass-through so the MCP tool group and
    the REST layer reach the same logic through the same service class instead
    of importing the module functions directly (which is what let the proposal
    state be bypassed in the first place).
    """

    def resolve(
        self,
        ctx: AuthContext,
        *,
        item_type: str,
        workspace_id: UUID | str,
        label: str = "",
    ) -> ProposalAuthoring:
        """See :func:`resolve_proposal_authoring`."""
        self._set_tenant_context(ctx)
        return resolve_proposal_authoring(
            ctx, item_type=item_type, workspace_id=workspace_id, label=label
        )

    def require(
        self, authoring: ProposalAuthoring, *, item_type: str
    ) -> ProposalAuthoring:
        """See :func:`require_proposal_support`."""
        return require_proposal_support(authoring, item_type=item_type)

    @staticmethod
    def verify(item_id: UUID | str, item_type: str) -> tuple[Optional[str], Optional[str]]:
        """See :func:`verify_proposal_state`."""
        return verify_proposal_state(item_id, item_type)

    @staticmethod
    def report(
        *,
        state: Optional[str],
        proposed_by: Optional[str],
        supported: bool,
        reason: str,
        label: str,
    ) -> dict:
        """See :func:`proposal_report`."""
        return proposal_report(
            state=state,
            proposed_by=proposed_by,
            supported=supported,
            reason=reason,
            label=label,
        )


__all__ = [
    "AI_DERIVATION_LABEL",
    "AiProposalService",
    "ProposalAuthoring",
    "proposal_report",
    "require_proposal_support",
    "resolve_proposal_authoring",
    "verify_proposal_state",
]
