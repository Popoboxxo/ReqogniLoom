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

Registry coverage (ADR-019 Decision 3, extended by ADR-032)
---------------------------------------------------------
* ``trace_link`` — active; produced by
  ``TraceabilitySuggestService.suggest_links``.
* ``artifact_create`` — **active since ADR-032** (``suggestion.capture``):
  produce persists the receipt, accept calls the production ``create_X()``.
* ``artifact_update`` — **active since ADR-032**: "anpassen, erweitern,
  korrigieren" of an existing artifact through the type's update facade.
* ``requirement_level`` — active (#1289).
* ``interview_grounding``, ``context_edge`` — registered but **dormant** (raise
  :class:`SuggestionKindNotEnabledError`). They exist as registry entries so
  the lifecycle stays generic; their wiring is a later WP/O1.
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


class RequirementLevelSuggestionAdapter(SuggestionAdapter):
    """#1289: a suggested V-model cascade level for a Requirement.

    Produce: the level is already computed by
    :class:`application.requirement_level_service.RequirementLevelService` and
    handed in via ``payload`` — this adapter only persists the ADR-019 receipt,
    so no separate domain write happens at produce time (unlike ``trace_link``).
    Accept: sets the level through ``RequirementService.set_manual_level`` (which
    stamps ``level_source = manual``), guarded against an agent accepting its own
    proposal. Reject: no target artifact to destroy — the receipt alone changes.
    """

    kind = "requirement_level"

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
        level = payload.get("level")
        requirement_id = kwargs.get("requirement_id") or payload.get("requirement_id")
        if level is None or requirement_id is None:
            raise ValidationError(
                "A requirement_level suggestion requires a non-null 'level' and "
                "a 'requirement_id' (no source determined a level, or the "
                "requirement was not identified)."
            )
        if not 1 <= int(level) <= 4:
            raise ValidationError("A suggested level must be in 1..4.")
        return service.create(
            kind=self.kind,
            ctx=ctx,
            workspace_id=workspace_id,
            payload=payload,
            producer=producer,
            target_item_type=target_item_type or "Requirement",
            target_item_id=target_item_id or payload.get("requirement_id"),
        )

    def accept(
        self, service: SuggestionService, ctx: AuthContext, suggestion: Suggestion
    ) -> None:
        from application.requirement_service import RequirementService
        from application.trace_link_service import AgentSelfConfirmError

        # An agent may not accept its own proposal — the human-in-the-loop rule
        # of ADR-019, applied per adapter (Rule 0 does not cover this path).
        if ctx.actor_type == "agent" or ctx.api_key_id is not None:
            raise AgentSelfConfirmError(
                "An agent may not accept its own requirement_level suggestion."
            )

        requirement_id = suggestion.target_item_id or suggestion.payload.get(
            "requirement_id"
        )
        level = suggestion.payload.get("level")
        if requirement_id is None or level is None:
            raise ValidationError(
                "This requirement_level suggestion has no requirement/level to apply."
            )
        RequirementService().set_manual_level(
            requirement_id, ctx, int(level), change_reason="accepted level suggestion"
        )

    def reject(
        self,
        service: SuggestionService,
        ctx: AuthContext,
        suggestion: Suggestion,
        reason: str = "",
    ) -> None:
        """No-op: a level suggestion owns no target artifact (Zusage 7(e))."""
        return None


# Dormant kinds — registered so the lifecycle is generic; invoked => clear error.
class ArtifactCreateSuggestionAdapter(SuggestionAdapter):
    """M1 ``proposed`` path for a captured free-text proposal (ADR-032).

    Produce: **no domain write**. The capture flow has already discarded the raw
    message (decision D5), so the accepted artifact must be materialisable from
    the receipt alone: ``payload`` carries ``artifact_type`` and the validated
    ``fields``. This is the same split the ``requirement_level`` adapter uses —
    the receipt is the waiting place, produce only persists it.

    Accept: call ``ARTIFACT_CREATION_ADAPTERS[type]`` — the **production**
    ``create_X()`` the interview ``formalize`` path uses, never a shortcut insert
    — so workflow state initialization, local ``uid`` allocation, audit and the
    ``change_reason`` policy come for free. The suggestion row then records the
    created artifact as its target, which is what makes provenance
    (client/session/hash → suggestion → artifact) walkable.

    Reject: no-op. There is no target artifact to destroy (Zusage 7(e)); the
    receipt alone changes.
    """

    kind = "artifact_create"

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
        artifact_type = str(payload.get("artifact_type") or target_item_type or "")
        fields = payload.get("fields")
        if not artifact_type or not isinstance(fields, dict) or not fields:
            raise ValidationError(
                "An artifact_create suggestion requires 'artifact_type' and a "
                "non-empty 'fields' object."
            )
        from application.interview_artifact_adapters import ARTIFACT_CREATION_ADAPTERS

        if artifact_type not in ARTIFACT_CREATION_ADAPTERS:
            raise ValidationError(
                f"Cannot create a suggestion for artifact type {artifact_type!r}."
            )
        return service.create(
            kind=self.kind,
            ctx=ctx,
            workspace_id=workspace_id,
            payload=payload,
            producer=producer,
            target_item_type=artifact_type,
            target_item_id=target_item_id,
        )

    def accept(
        self, service: SuggestionService, ctx: AuthContext, suggestion: Suggestion
    ) -> None:
        from application.interview_artifact_adapters import ARTIFACT_CREATION_ADAPTERS

        # ADR-019 Decision 3: ``artifact_create`` must check the agent ban
        # itself — it inherits neither M1's Rule 0 nor M2's confirm guard.
        _assert_human_decision(ctx, self.kind)

        artifact_type = suggestion.target_item_type or str(
            suggestion.payload.get("artifact_type") or ""
        )
        adapter = ARTIFACT_CREATION_ADAPTERS.get(artifact_type)
        if adapter is None:
            raise ValidationError(
                f"This suggestion has no creatable artifact type ({artifact_type!r})."
            )
        fields = suggestion.payload.get("fields") or {}
        if not isinstance(fields, dict) or not fields:
            raise ValidationError(
                "This suggestion carries no fields to create an artifact from."
            )

        try:
            ref = adapter(dict(fields), ctx, suggestion.workspace_id)
        except (KeyError, TypeError) as exc:
            # Same conversion the interview path applies: a malformed proposal
            # must surface as a readable ValidationError, never a 500.
            raise ValidationError(
                f"invalid fields for {artifact_type!r}: {exc}"
            ) from exc

        # Record the created artifact on the receipt so provenance is walkable
        # from the artifact back to the capture (client/session/hash) and the
        # accept audit entry names what was created.
        # ``target_item_id`` stays the ENTITY id (one meaning for the column);
        # the backing Artifact id goes into the payload under an explicit name.
        suggestion.target_item_type = ref.artifact_type
        suggestion.target_item_id = ref.entity_id
        suggestion.payload = {
            **(suggestion.payload or {}),
            "accepted_artifact_id": str(ref.artifact_id),
        }
        suggestion.save(
            update_fields=["target_item_type", "target_item_id", "payload"]
        )

    def reject(
        self,
        service: SuggestionService,
        ctx: AuthContext,
        suggestion: Suggestion,
        reason: str = "",
    ) -> None:
        """No-op: a create suggestion owns no target artifact yet (Zusage 7(e))."""
        return None


class ArtifactUpdateSuggestionAdapter(SuggestionAdapter):
    """Update an existing artifact from a captured proposal (ADR-032, plan P3).

    Produce: persists the receipt only (``artifact_type``, ``target_artifact_id``,
    ``base_version`` and the validated ``fields`` live in the payload/columns).

    Accept: calls the target type's **production update facade** through
    ``ARTIFACT_UPDATE_ADAPTERS`` with the proposal's ``base_version`` as
    ``expected_version``. A stale base version therefore surfaces as a conflict
    (409 ``CONFLICT``) and the suggestion stays ``open`` — no overwrite, no
    silent loss. The facade also enforces the workflow state, the preset's
    ``change_reason`` policy and the field contract.

    Reject: no-op — rejecting a proposal never touches the target artifact.
    """

    kind = "artifact_update"

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
        artifact_type = str(payload.get("artifact_type") or target_item_type or "")
        fields = payload.get("fields")
        # ``target_entity_id`` is the capture payload's name (an ENTITY id). The
        # legacy ``target_artifact_id`` key is still accepted so a receipt
        # written before the rename keeps working.
        target_artifact_id = (
            payload.get("target_entity_id")
            or payload.get("target_artifact_id")
            or target_item_id
        )
        if not artifact_type or not isinstance(fields, dict) or not fields:
            raise ValidationError(
                "An artifact_update suggestion requires 'artifact_type' and a "
                "non-empty 'fields' object."
            )
        if target_artifact_id is None:
            raise ValidationError(
                "An artifact_update suggestion requires 'target_artifact_id'."
            )
        from application.capture_update import supports_update

        if not supports_update(artifact_type):
            raise ValidationError(
                f"Cannot update artifact type {artifact_type!r}."
            )
        return service.create(
            kind=self.kind,
            ctx=ctx,
            workspace_id=workspace_id,
            payload=payload,
            producer=producer,
            target_item_type=artifact_type,
            target_item_id=target_artifact_id,
        )

    def accept(
        self, service: SuggestionService, ctx: AuthContext, suggestion: Suggestion
    ) -> None:
        from application.capture_update import apply_update, supports_update

        _assert_human_decision(ctx, self.kind)

        artifact_type = suggestion.target_item_type or str(
            suggestion.payload.get("artifact_type") or ""
        )
        if not supports_update(artifact_type):
            raise ValidationError(
                f"This suggestion has no updatable artifact type ({artifact_type!r})."
            )
        target_id = suggestion.target_artifact_id or suggestion.target_item_id
        if target_id is None:
            raise ValidationError("This update suggestion has no target artifact.")

        fields = suggestion.payload.get("fields") or {}
        if not isinstance(fields, dict) or not fields:
            raise ValidationError(
                "This suggestion carries no fields to update the artifact with."
            )

        # Delegated domain path: the shared update seam enforces the allowlist,
        # the workflow/freeze gate, the item right, the optimistic lock and the
        # audit entry. ``base_version`` is the proposal's precondition, so a
        # stale proposal answers CONFLICT instead of overwriting (plan P3).
        result = apply_update(
            ctx,
            item_type=artifact_type,
            entity_id=target_id,
            fields=dict(fields),
            base_version=suggestion.base_version,
            change_reason=str(
                suggestion.payload.get("rationale") or "accepted capture suggestion"
            ),
        )

        suggestion.target_item_type = artifact_type
        suggestion.target_item_id = result.entity_id
        suggestion.payload = {
            **(suggestion.payload or {}),
            "accepted_artifact_id": str(result.artifact_id),
        }
        suggestion.save(
            update_fields=["target_item_type", "target_item_id", "payload"]
        )

    def reject(
        self,
        service: SuggestionService,
        ctx: AuthContext,
        suggestion: Suggestion,
        reason: str = "",
    ) -> None:
        """No-op: rejecting an update proposal never touches the target (7(e))."""
        return None


def _assert_human_decision(ctx: AuthContext, kind: str) -> None:
    """Refuse an agent decision on *kind* (ADR-019 Zusage 7(c)).

    The same blanket rule the ``requirement_level`` adapter applies: an agent
    principal (any ``reqlo_*`` API key) may never accept a proposal, its own or
    another agent's. ``SuggestionService.accept`` lets
    ``AgentSelfConfirmError`` propagate so REST/MCP answer 403.
    """
    from application.trace_link_service import AgentSelfConfirmError

    if ctx.actor_type == "agent" or ctx.api_key_id is not None:
        raise AgentSelfConfirmError(
            f"An agent may not accept its own {kind} suggestion."
        )
class InterviewGroundingSuggestionAdapter(SuggestionAdapter):
    """M3 ``grounding_snapshot`` path — registered, dormant."""

    kind = "interview_grounding"


class ContextEdgeSuggestionAdapter(SuggestionAdapter):
    """M4 ``ContextEdge.origin`` — registered, dormant (no existing accept path)."""

    kind = "context_edge"


def build_adapter_registry() -> dict[str, SuggestionAdapter]:
    """Return the ``kind`` -> adapter map covering every ADR-019 kind.

    ``artifact_create`` and ``artifact_update`` are active since ADR-032
    (``suggestion.capture``); ``interview_grounding`` and ``context_edge`` stay
    registered-but-dormant so the lifecycle remains generic.
    """
    adapters: list[SuggestionAdapter] = [
        TraceLinkSuggestionAdapter(),
        RequirementLevelSuggestionAdapter(),
        ArtifactCreateSuggestionAdapter(),
        ArtifactUpdateSuggestionAdapter(),
        InterviewGroundingSuggestionAdapter(),
        ContextEdgeSuggestionAdapter(),
    ]
    return {adapter.kind: adapter for adapter in adapters}


__all__ = [
    "ArtifactCreateSuggestionAdapter",
    "ArtifactUpdateSuggestionAdapter",
    "ContextEdgeSuggestionAdapter",
    "InterviewGroundingSuggestionAdapter",
    "RequirementLevelSuggestionAdapter",
    "SuggestionAdapter",
    "SuggestionKindNotEnabledError",
    "TraceLinkSuggestionAdapter",
    "build_adapter_registry",
]
