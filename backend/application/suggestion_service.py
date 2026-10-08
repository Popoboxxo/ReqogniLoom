"""
SuggestionService — Layer-2 facade for the generic proposal lifecycle (ADR-019).

leaf_id : ADR-019 WP2 (generic proposal lifecycle / suggestion loop)
req_id  : REQ-L1-009, REQ-L1-078 (workflow + audit trail), ADR-019

ADR-019 makes :class:`persistence.models.Suggestion` the durable
receipt/inbox/provenance row over the four existing proposal mechanisms M1–M4.
This service is the single Layer-2 entry point (ADR-01) for that row. It owns
**no** state-machine, link or workflow logic: ``accept``/``reject`` dispatch to
a per-``kind`` adapter (:mod:`application.suggestion_adapters`) which calls the
existing domain path, and only then stamps the receipt (ADR-019 Decision 2,
Zusage 7(b)/(e)).

Public API (these names are consumed by the MCP tool group/WP3, the REST
endpoints/WP4 and the ``suggest_links`` producer/WP5 — do not rename):

``list_open(workspace_id, ctx) -> list[dict]``
    Serialized ``open`` suggestions of a workspace, tenant-scoped, RBAC read.

``accept(suggestion_id, ctx) -> dict``
    Delegate to the adapter's accept path, then set ``status=accepted`` and the
    server-set ``decided_by``/``decided_at``. Idempotent for an already
    accepted suggestion. Surfaces ``AgentSelfConfirmError`` (agent accepting
    its own proposal) and ``ProducerContextRequiredError`` unchanged.

``reject(suggestion_id, ctx, reason="") -> dict``
    Delegate to the adapter's discard path, then set ``status=rejected`` and
    the server-set ``decided_*``. Never destroys the target artifact.

``create(*, kind, ctx, workspace_id, payload=None, producer="",
target_item_type="", target_item_id=None) -> Suggestion``
    Internal creation entry point used by adapters/producers. Persists the
    receipt with **server-set** provenance (``proposed_by``/``proposed_at``
    come from the authenticated principal, never from the payload/body). Fails
    closed outside an agent/API-key context (Zusage 7(f)).

``propose(kind, ctx, *, workspace_id, payload=None, producer="", ...) -> dict``
    Convenience dispatch: runs the adapter's ``produce`` and returns the new
    serialized receipt. This is what a producer (WP5) calls.

Trust boundaries (ADR-019 Decision 7 / Threat-Model 3)
------------------------------------------------------
* ``payload`` is **untrusted** (LLM output). It supplies candidate ids only;
  the delegated domain path validates every pair/link/workflow rule. It is
  never blind-materialized, never ``eval``'d.
* Provenance (``producer``, ``proposed_by``, ``proposed_at``, ``decided_by``,
  ``decided_at``) is server-set. ``proposed_by`` is ``ctx.api_key_id``;
  ``decided_by`` is ``ctx.user_id``; ``proposed_at``/``decided_at`` are
  ``timezone.now()``. None of these can be supplied by a caller.
* Production is limited to agent/API-key contexts (``actor_type == "agent"``
  and ``api_key_id`` set); a human bearer context raises
  :class:`~application.base.ProducerContextRequiredError` (→ HTTP 409).
* An agent may not accept its own proposal: the delegated
  ``TraceLinkService.confirm_proposed_link`` raises ``AgentSelfConfirmError``
  (→ HTTP 403), which this service lets propagate.

Atomicity (O11)
---------------
``propose`` wraps the whole production — adapter side effect **and** the
``Suggestion`` receipt insert — in a single ``atomic_transaction``. The
proposal link is created first, then the receipt (so a rollback leaves neither).
The accept/reject paths are atomic too, so a failed receipt update rolls the
delegated domain change back with it.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from django.utils import timezone

from application.base import (
    NotFoundError,
    PermissionDeniedError,
    ServiceBase,
    ValidationError,
    require_producer_context,
)
from application.suggestion_adapters import SuggestionAdapter, build_adapter_registry
from application.trace_link_service import TraceLinkService
from auth_tenancy.context import AuthContext
from persistence.models import Suggestion
from persistence.transactions import atomic_transaction


class SuggestionService(ServiceBase):
    """Layer-2 facade over the ADR-019 generic proposal lifecycle."""

    def __init__(self, trace_link_service: TraceLinkService | None = None) -> None:
        """Build the service.

        Args:
            trace_link_service: Optional injected ``TraceLinkService`` (tests);
                a fresh instance is created otherwise. Exposed as
                :attr:`trace_link_service` so the ``trace_link`` adapter can
                delegate to it.
        """
        self.trace_link_service = trace_link_service or TraceLinkService()
        self._adapters: dict[str, SuggestionAdapter] = build_adapter_registry()

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def list_open(
        self, workspace_id: str | UUID, ctx: AuthContext
    ) -> list[dict]:
        """Return the serialized ``open`` suggestions of *workspace_id*.

        Tenant-scoped through the inherited ``TenantManager`` (and RLS at the
        DB layer); a foreign tenant's workspace id therefore yields an empty
        list rather than a leak. Requires at least the ``viewer`` role
        (``Operation.READ``).

        Args:
            workspace_id: Workspace whose inbox is read.
            ctx: Authenticated, tenant-scoped context.

        Returns:
            A list of JSON-safe suggestion dicts (newest first).
        """
        self._set_tenant_context(ctx)
        self._assert_read_permission(ctx)
        queryset = (
            Suggestion.objects.filter(
                workspace_id=workspace_id,
                status=Suggestion.Status.OPEN,
            )
            .order_by("-proposed_at", "-created_at")
        )
        return [self._serialize(suggestion) for suggestion in queryset]

    # ------------------------------------------------------------------
    # Decide
    # ------------------------------------------------------------------

    @atomic_transaction
    def accept(self, suggestion_id: str | UUID, ctx: AuthContext) -> dict:
        """Accept a suggestion through its delegated domain path.

        Delegates to the per-kind adapter (which performs the real state/link
        transition) and only then stamps ``status=accepted`` plus the
        server-set ``decided_by``/``decided_at``. Idempotent: accepting an
        already accepted suggestion returns it unchanged.

        Raises:
            NotFoundError: no such suggestion in the active tenant.
            ValidationError: the suggestion is not ``open`` (already
                rejected/superseded).
            AgentSelfConfirmError: an agent tried to accept its own proposal.
            ProducerContextRequiredError: propagated from a delegated adapter.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        suggestion = self._get(suggestion_id)
        if suggestion.status == Suggestion.Status.ACCEPTED:
            return self._serialize(suggestion)
        if suggestion.status != Suggestion.Status.OPEN:
            raise ValidationError(
                f"Suggestion {suggestion.id} is '{suggestion.status}' and can no "
                "longer be accepted."
            )

        adapter = self._adapter_for(suggestion.kind)
        # Delegate FIRST: if the domain path fails (e.g. AgentSelfConfirmError,
        # a workflow/RBAC denial), the receipt must stay 'open'.
        adapter.accept(self, ctx, suggestion)
        self._decide(suggestion, ctx, Suggestion.Status.ACCEPTED)
        return self._serialize(suggestion)

    @atomic_transaction
    def reject(
        self,
        suggestion_id: str | UUID,
        ctx: AuthContext,
        reason: str = "",
    ) -> dict:
        """Reject a suggestion, destroying no target artifact (Zusage 7(e)).

        Delegates to the per-kind adapter's discard path (for ``trace_link``
        this deletes the *proposal link*, not the linked artifacts) and then
        stamps ``status=rejected`` plus the server-set ``decided_*``.
        Idempotent for an already rejected suggestion.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        suggestion = self._get(suggestion_id)
        if suggestion.status == Suggestion.Status.REJECTED:
            return self._serialize(suggestion)
        if suggestion.status != Suggestion.Status.OPEN:
            raise ValidationError(
                f"Suggestion {suggestion.id} is '{suggestion.status}' and can no "
                "longer be rejected."
            )

        adapter = self._adapter_for(suggestion.kind)
        adapter.reject(self, ctx, suggestion, reason)
        self._decide(suggestion, ctx, Suggestion.Status.REJECTED, reason=reason)
        return self._serialize(suggestion)

    # ------------------------------------------------------------------
    # Produce
    # ------------------------------------------------------------------

    @atomic_transaction
    def propose(
        self,
        kind: str,
        ctx: AuthContext,
        *,
        workspace_id: str | UUID,
        payload: dict | None = None,
        producer: str = "",
        target_item_type: str = "",
        target_item_id: UUID | None = None,
        **kwargs: Any,
    ) -> dict:
        """Produce a suggestion via the kind adapter and return its receipt.

        This is the entry point for a producer (WP5). Producer-context and kind
        are validated before any adapter side effect; the adapter's domain write
        and the ``Suggestion`` insert share the method's ``atomic_transaction``
        (O11).

        Raises:
            ProducerContextRequiredError: context is not agent/API-key.
            ValidationError: unknown kind, or an adapter's own validation.
            SuggestionKindNotEnabledError: the kind is registered but dormant.
        """
        self._set_tenant_context(ctx)
        require_producer_context(ctx)
        adapter = self._adapter_for(kind)
        suggestion = adapter.produce(
            self,
            ctx,
            workspace_id=workspace_id,
            payload=payload or {},
            producer=producer,
            target_item_type=target_item_type,
            target_item_id=target_item_id,
            **kwargs,
        )
        return self._serialize(suggestion)

    @atomic_transaction
    def create(
        self,
        *,
        kind: str,
        ctx: AuthContext,
        workspace_id: str | UUID,
        payload: dict | None = None,
        producer: str = "",
        target_item_type: str = "",
        target_item_id: UUID | None = None,
    ) -> Suggestion:
        """Persist a ``Suggestion`` receipt with server-set provenance.

        Internal creation entry point used by adapters/producers. Every
        provenance field is derived from *ctx* (or trusted producer code for the
        ``producer`` label) — never from ``payload``. Fails closed for a
        non-agent/non-API-key context (Zusage 7(f)).

        Returns the created :class:`persistence.models.Suggestion`.
        """
        self._set_tenant_context(ctx)
        require_producer_context(ctx)
        self._adapter_for(kind)  # reject an unknown kind early

        return Suggestion.objects.create(
            kind=kind,
            status=Suggestion.Status.OPEN,
            producer=producer or self._default_producer(ctx),
            proposed_by_id=ctx.api_key_id,
            proposed_at=timezone.now(),
            target_item_type=target_item_type,
            target_item_id=target_item_id,
            payload=payload or {},
            workspace_id=workspace_id,
            created_by_id=ctx.user_id,
            modified_by_id=ctx.user_id,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _default_producer(ctx: AuthContext) -> str:
        """Derive a default producer label from the authenticated principal."""
        return ctx.agent_label or "agent"

    def _adapter_for(self, kind: str) -> SuggestionAdapter:
        """Return the registered adapter for *kind* or raise ``ValidationError``."""
        adapter = self._adapters.get(str(kind))
        if adapter is None:
            raise ValidationError(
                f"Unknown suggestion kind '{kind}'. Registered kinds: "
                f"{', '.join(sorted(self._adapters))}."
            )
        return adapter

    def _get(self, suggestion_id: str | UUID) -> Suggestion:
        """Load a tenant-scoped suggestion or raise ``NotFoundError``."""
        suggestion = Suggestion.objects.filter(id=suggestion_id).first()
        if suggestion is None:
            raise NotFoundError(f"Suggestion {suggestion_id} not found")
        return suggestion

    def _decide(
        self,
        suggestion: Suggestion,
        ctx: AuthContext,
        status: str,
        reason: str = "",
    ) -> None:
        """Stamp the server-set decision fields + audit entry on *suggestion*."""
        suggestion.status = status
        suggestion.decided_by_id = ctx.user_id
        suggestion.decided_at = timezone.now()
        suggestion.modified_by_id = ctx.user_id
        suggestion.save(
            update_fields=[
                "status",
                "decided_by",
                "decided_at",
                "modified_by",
                "modified_at",
            ]
        )
        self._audit(
            ctx=ctx,
            operation="update",
            entity_type="Suggestion",
            entity_id=suggestion.id,
            change_reason=reason or None,
            details={
                "kind": suggestion.kind,
                "decision": status,
                "target_item_type": suggestion.target_item_type,
                "target_item_id": (
                    str(suggestion.target_item_id)
                    if suggestion.target_item_id
                    else None
                ),
            },
        )

    @staticmethod
    def _assert_read_permission(ctx: AuthContext) -> None:
        """Require a role that may read this tenant's suggestions.

        Uses the READ gate (``Operation.READ``); the lowest permitted role is
        ``viewer``. Mirrors ``BaselineFacade._assert_permission_read``.
        """
        from auth_tenancy.services.authorization import AuthorizationService, Operation

        decision = AuthorizationService().decide_access(ctx.active_roles, Operation.READ)
        if not decision.allow:
            raise PermissionDeniedError(
                "Permission denied: reading suggestions requires at least "
                f"'viewer' role, user has {ctx.active_roles}"
            )

    @staticmethod
    def _serialize(suggestion: Suggestion) -> dict:
        """Render a suggestion as a JSON-safe dict for REST/MCP transports."""
        return {
            "id": str(suggestion.id),
            "kind": suggestion.kind,
            "status": suggestion.status,
            "producer": suggestion.producer,
            "proposed_by": (
                str(suggestion.proposed_by_id) if suggestion.proposed_by_id else None
            ),
            "proposed_at": (
                suggestion.proposed_at.isoformat() if suggestion.proposed_at else None
            ),
            "decided_by": (
                str(suggestion.decided_by_id) if suggestion.decided_by_id else None
            ),
            "decided_at": (
                suggestion.decided_at.isoformat() if suggestion.decided_at else None
            ),
            "target_item_type": suggestion.target_item_type,
            "target_item_id": (
                str(suggestion.target_item_id)
                if suggestion.target_item_id
                else None
            ),
            "payload": suggestion.payload,
            "workspace_id": str(suggestion.workspace_id),
            "created_at": (
                suggestion.created_at.isoformat() if suggestion.created_at else None
            ),
        }


__all__ = ["SuggestionService"]
