"""
Per-``kind`` suggestion adapters + registry (ADR-019 WP2).

ADR-019 (generic proposal lifecycle) keeps the state authority with the four
existing mechanisms M1–M4 and makes :class:`persistence.models.Suggestion` the
durable receipt/inbox row above them. This module holds the **kind → adapter**
registry that :class:`application.suggestion_service.SuggestionService`
dispatches to. An adapter is the only place that may touch a domain accept path;
the service itself never reimplements state-machine, link or workflow logic
(ADR-019 Decision 2, Zusage 7(b)).

Adapter contract
----------------
Every adapter implements three methods, all receiving the owning
:class:`~application.suggestion_service.SuggestionService` as first argument so
it can persist the receipt via ``service.create(...)``:

``produce(service, ctx, *, workspace_id, payload, producer, target_item_type,
target_item_id, **kwargs) -> Suggestion``
    Side-effect the domain (e.g. create the M2 proposal TraceLink) and return
    the new ``Suggestion`` receipt. Runs inside the service's single
    ``atomic_transaction`` (O11).

``accept(service, ctx, suggestion) -> None``
    Call the existing accept path for the target (e.g.
    ``TraceLinkService.confirm_proposed_link``). Must raise on failure so the
    service does not stamp ``accepted``.

``reject(service, ctx, suggestion, reason="") -> None``
    Call the existing reject/discard path. Must not destroy the *target
    artifact* (Zusage 7(e)) — for ``trace_link`` this deletes the proposal
    *link*, which is the M2 discard semantics, not the linked artifacts.

Registry coverage (ADR-019 Decision 3)
--------------------------------------
* ``trace_link`` — **active** in the MVP (this is the only producer in scope,
  ``TraceabilitySuggestService.suggest_links``).
* ``artifact_create``, ``interview_grounding``, ``context_edge`` — registered
  but **dormant** (raise :class:`SuggestionKindNotEnabledError`). They exist as
  registry entries so the lifecycle is generic; their wiring is a later WP/O1.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from application.base import ValidationError
from application.trace_link_service import TraceLinkService

if TYPE_CHECKING:  # pragma: no cover — avoids a runtime import cycle
    from application.suggestion_service import SuggestionService
    from auth_tenancy.context import AuthContext
    from persistence.models import Suggestion


class SuggestionKindNotEnabledError(ValidationError):
    """A registered but dormant suggestion kind was invoked.

    The kind exists in the registry (ADR-019 requires all four to be present)
    but its producer/accept path is not enabled in the MVP. Mapped like any
    ``ValidationError`` (400) — the caller asked for something the current MVP
    deliberately does not support yet.
    """

    error_code = "SUGGESTION_KIND_NOT_ENABLED"


#: Maps a ``TraceabilitySuggestService`` ``rule_id`` to the trace-link type the
#: proposal link must carry. ADR-019 Decision 3: TRACE-P1/P1b → ``derives-from``,
#: TRACE-P2 → ``allocated-to``. The ``suggest_links`` DTO itself carries no
#: ``link_type``.
_RULE_ID_TO_LINK_TYPE: dict[str, str] = {
    "TRACE-P1": "derives-from",
    "TRACE-P1b": "derives-from",
    "TRACE-P2": "allocated-to",
}


class SuggestionAdapter:
    """Base adapter + the "not enabled" behaviour for dormant kinds.

    Subclasses set :attr:`kind` and override the methods they support. The
    default implementations fail loudly instead of silently no-op'ing, so a
    dormant kind can never masquerade as a successful decision.
    """

    kind: ClassVar[str] = ""

    def produce(
        self,
        service: SuggestionService,
        ctx: AuthContext,
        *,
        workspace_id: Any,
        payload: dict,
        producer: str = "",
        target_item_type: str = "",
        target_item_id: Any = None,
        **kwargs: Any,
    ) -> Suggestion:
        raise SuggestionKindNotEnabledError(
            f"The '{self.kind}' suggestion kind is registered but not enabled "
            "in this MVP."
        )

    def accept(
        self, service: SuggestionService, ctx: AuthContext, suggestion: Suggestion
    ) -> None:
        raise SuggestionKindNotEnabledError(
            f"The '{self.kind}' suggestion kind is registered but not enabled "
            "in this MVP."
        )

    def reject(
        self,
        service: SuggestionService,
        ctx: AuthContext,
        suggestion: Suggestion,
        reason: str = "",
    ) -> None:
        raise SuggestionKindNotEnabledError(
            f"The '{self.kind}' suggestion kind is registered but not enabled "
            "in this MVP."
        )


class TraceLinkSuggestionAdapter(SuggestionAdapter):
    """MVP adapter: M2 proposal TraceLink -> confirm / discard.

    Produce = ``TraceLinkService.create_trace_link`` (which stamps
    ``proposed_by``/``proposed_at`` for an agent context, ``trace_link_service.py``
    :601-617). Accept = ``confirm_proposed_link`` (agent-blocked via
    ``AgentSelfConfirmError``). Reject = ``discard_proposed_link`` (deletes the
    proposal link; the linked artifacts survive).
    """

    kind = "trace_link"

    def produce(
        self,
        service: SuggestionService,
        ctx: AuthContext,
        *,
        workspace_id: Any,
        payload: dict,
        producer: str = "",
        target_item_type: str = "",
        target_item_id: Any = None,
        **kwargs: Any,
    ) -> Suggestion:
        source_id = (
            kwargs.get("source_id")
            or payload.get("source_artifact_id")
            or payload.get("source_id")
        )
        target_id = (
            kwargs.get("target_id")
            or payload.get("target_id")
            or self._top_candidate_id(payload)
        )
        if source_id is None or target_id is None:
            raise ValidationError(
                "A trace_link suggestion requires a source and a target "
                "(pass source_id/target_id or a payload with "
                "source_artifact_id + ranked_candidates)."
            )
        link_type = kwargs.get("link_type") or self._link_type_from_rule(
            payload.get("rule_id")
        )
        rationale = kwargs.get("rationale") or payload.get("rationale") or ""

        link_service = service.trace_link_service

        # O7 (001-10) edge dedup: a repeated producer run must not hard-fail on
        # uq_tracelink_edge. If an *open* proposal already exists on the same
        # (source, target, link_type) edge, attach the new receipt to it
        # instead of creating a duplicate.
        existing = self._find_open_proposal(
            link_service, source_id, target_id, link_type, ctx
        )
        if existing is not None:
            link_id = existing.id
        else:
            link = link_service.create_trace_link(
                source_id, target_id, link_type, ctx, rationale=rationale
            )
            link_id = link.id

        # B-02 (001-10/O7): a repeated producer run must not only reuse the
        # proposal *link* above but also the open *receipt*. Unconditionally
        # inserting a second ``open`` Suggestion would leave the inbox with two
        # rows pointing at one link — the later one un-rejectable (the M2
        # discard removes the link the first row owns) and a silent no-op on
        # accept. Reuse the existing open receipt for the edge instead.
        receipt = self._find_open_receipt(workspace_id, link_id)
        if receipt is not None:
            return receipt

        return service.create(
            kind=self.kind,
            ctx=ctx,
            workspace_id=workspace_id,
            payload=payload,
            producer=producer,
            target_item_type=target_item_type or "TraceLink",
            target_item_id=link_id,
        )

    def accept(
        self, service: SuggestionService, ctx: AuthContext, suggestion: Suggestion
    ) -> None:
        link_id = suggestion.target_item_id
        if link_id is None:
            raise ValidationError(
                "This trace_link suggestion has no target proposal link to confirm."
            )
        # Delegated domain path: honours the catalog, workflow policy, RBAC,
        # audit and the agent guard (AgentSelfConfirmError propagates).
        service.trace_link_service.confirm_proposed_link(link_id, ctx)

    def reject(
        self,
        service: SuggestionService,
        ctx: AuthContext,
        suggestion: Suggestion,
        reason: str = "",
    ) -> None:
        link_id = suggestion.target_item_id
        if link_id is None:
            raise ValidationError(
                "This trace_link suggestion has no target proposal link to discard."
            )
        # M2 discard deletes the *proposal link*; the linked artifacts are not
        # touched (Zusage 7(e)).
        service.trace_link_service.discard_proposed_link(link_id, ctx)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _top_candidate_id(payload: dict) -> Any:
        """Return the top-ranked candidate's artifact id, if present."""
        candidates = payload.get("ranked_candidates") or payload.get("candidates") or []
        if candidates and isinstance(candidates, list):
            first = candidates[0]
            if isinstance(first, dict):
                return first.get("artifact_id") or first.get("id")
        return None

    @staticmethod
    def _link_type_from_rule(rule_id: Any) -> str:
        """Map an audit ``rule_id`` to a trace-link type (ADR-019 Decision 3)."""
        key = str(rule_id or "").strip()
        link_type = _RULE_ID_TO_LINK_TYPE.get(key)
        if link_type is None:
            raise ValidationError(
                f"Cannot derive a trace-link type from rule_id '{key}'. "
                f"Known: {', '.join(sorted(_RULE_ID_TO_LINK_TYPE))}."
            )
        return link_type

    @staticmethod
    def _find_open_proposal(
        link_service: TraceLinkService,
        source_id: Any,
        target_id: Any,
        link_type: str,
        ctx: AuthContext,
    ) -> Any:
        """Return an existing unconfirmed proposal on the edge, else ``None``.

        ``TraceLink.proposed_at`` is the M2 proposal marker (a confirmed link
        has both fields NULL). Tenant context must already be armed by the
        caller (the service does this before dispatch).
        """
        from persistence.models import TraceLink

        return (
            TraceLink.objects.filter(
                source_id=source_id,
                target_id=target_id,
                link_type=link_type,
                proposed_at__isnull=False,
            )
            .order_by("created_at")
            .first()
        )

    def _find_open_receipt(self, workspace_id: Any, link_id: Any) -> Any:
        """Return the existing ``open`` receipt for *link_id*, else ``None``.

        B-02/O7 dedup: the durable inbox row for a given edge is reused on a
        repeated producer run so the inbox never accumulates duplicate ``open``
        rows. Tenant context must already be armed by the caller (the service
        does this before dispatch); ``objects`` is the tenant-scoped manager.
        """
        from persistence.models import Suggestion

        return (
            Suggestion.objects.filter(
                workspace_id=workspace_id,
                kind=self.kind,
                target_item_id=link_id,
                status=Suggestion.Status.OPEN,
            )
            .order_by("proposed_at", "created_at")
            .first()
        )


# Dormant kinds — registered so the lifecycle is generic; invoked => clear error.
class ArtifactCreateSuggestionAdapter(SuggestionAdapter):
    """M1 ``proposed`` path — registered, dormant (ADR-019 Decision 3/4)."""

    kind = "artifact_create"


class InterviewGroundingSuggestionAdapter(SuggestionAdapter):
    """M3 ``grounding_snapshot`` path — registered, dormant."""

    kind = "interview_grounding"


class ContextEdgeSuggestionAdapter(SuggestionAdapter):
    """M4 ``ContextEdge.origin`` — registered, dormant (no existing accept path)."""

    kind = "context_edge"


def build_adapter_registry() -> dict[str, SuggestionAdapter]:
    """Return the ``kind`` -> adapter map covering all four ADR-019 kinds."""
    adapters: list[SuggestionAdapter] = [
        TraceLinkSuggestionAdapter(),
        ArtifactCreateSuggestionAdapter(),
        InterviewGroundingSuggestionAdapter(),
        ContextEdgeSuggestionAdapter(),
    ]
    return {adapter.kind: adapter for adapter in adapters}


__all__ = [
    "ArtifactCreateSuggestionAdapter",
    "ContextEdgeSuggestionAdapter",
    "InterviewGroundingSuggestionAdapter",
    "SuggestionAdapter",
    "SuggestionKindNotEnabledError",
    "TraceLinkSuggestionAdapter",
    "build_adapter_registry",
]
