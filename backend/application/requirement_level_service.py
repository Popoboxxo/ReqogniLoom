"""Requirement-level suggestion service — the V-model cascade (#1289).

ADR-005 made ``Requirement.level`` a *derived* field. #1289 adds a **suggestion**
path on top of it: this service proposes a cascade level for a Requirement from

(a) its **architecture allocation** — an ``allocated-to`` link to an
    ``ArchitectureElement`` at tree depth *n* maps through
    :data:`traceability.audit.hierarchy.ARCHITECTURE_DEPTH_TO_LEVEL`
    (the explicit depth -> level mapping),
(b) its **type** (``SyReq``/``UseCase``/``FeatureReq``) — the SE-mask default,
(c) the **trace-link direction** — the level of a ``derives-from`` parent
    (Requirement -> Requirement) is one below the requirement; where several
    sources disagree the suggestion is *not* made.

The suggestion is **never silently written** to ``level``. It is persisted as a
:class:`persistence.models.Suggestion` row of kind ``requirement_level`` via
:class:`application.suggestion_service.SuggestionService` (the ADR-019 generic
proposal lifecycle / suggestion inbox). A human accepts it, which routes through
``RequirementService.set_manual_level`` and stamps
``level_source = manual``; until then the derived field is untouched.

Priority (highest first): architecture allocation, then the trace-link parent,
then the type default — the same order the ticket names them. A source that is
itself not derivable (``None``) never masks a lower-priority one.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from application.base import NotFoundError, ServiceBase
from application.suggestion_service import SuggestionService
from auth_tenancy.context import AuthContext
from persistence.models import Artifact, Requirement, RequirementType
from traceability.audit.hierarchy import architecture_allocated_levels
from traceability.types import LinkType

#: Producer label recorded on the receipt (`Suggestion.producer`).
PRODUCER = "requirement.suggest_level"

#: SE-mask default level per Requirement type (signal (b)). Explicit, not
#: invented ad hoc: a System Requirement is L1, a Use Case (a scenario at the
#: system/subsystem boundary) is L2, a Feature Requirement is L3. A type that
#: yields no entry contributes no signal.
REQUIREMENT_TYPE_TO_LEVEL: dict[str, int] = {
    RequirementType.SYREQ.value: 1,
    RequirementType.USECASE.value: 2,
    RequirementType.FEATUREREQ.value: 3,
}


def suggest_level(
    *,
    requirement_type: str,
    architecture_level: int | None,
    parent_level: int | None,
) -> dict[str, Any]:
    """Return a pure level suggestion from the three signals (#1289).

    Pure and Django-free so it is unit-testable. Priority: architecture
    allocation > trace-link parent > type default. Returns
    ``{"level": int | None, "source": str | None, "signals": {...}}`` — a
    ``level`` of ``None`` means "no source determines a level", which the caller
    reports rather than guesses.
    """
    signals = {
        "architecture": architecture_level,
        "trace_link_parent": parent_level,
        "type": REQUIREMENT_TYPE_TO_LEVEL.get(requirement_type),
    }
    if architecture_level is not None:
        return {"level": architecture_level, "source": "architecture", "signals": signals}
    if parent_level is not None:
        level = parent_level + 1 if parent_level < 4 else None
        return {"level": level, "source": "trace_link_parent", "signals": signals}
    if signals["type"] is not None:
        return {"level": signals["type"], "source": "type", "signals": signals}
    return {"level": None, "source": None, "signals": signals}


class RequirementLevelService(ServiceBase):
    """Suggest (and propose) a V-model cascade level for a Requirement (#1289)."""

    def __init__(self, suggestion_service: SuggestionService | None = None) -> None:
        """Build the service; *suggestion_service* is injectable for tests."""
        self.suggestion_service = suggestion_service or SuggestionService()

    def _load(self, requirement_id: UUID, ctx: AuthContext) -> Requirement:
        self._set_tenant_context(ctx)
        requirement = (
            Requirement.objects.select_related("artifact")
            .filter(id=requirement_id)
            .first()
        )
        if requirement is None:
            raise NotFoundError(f"Requirement {requirement_id} not found")
        return requirement

    def _parent_level(self, requirement: Requirement) -> int | None:
        """Level of the requirement's hierarchy parent (FK tree or derives-from).

        Reads the ``Artifact.parent_id`` FK tree and the ``derives-from``
        (Requirement -> Requirement) direction. If the two disagree — or a
        parent's own level is NULL — the answer is ``None`` ("not derivable")
        rather than a guess, mirroring the derivation's disagreeing-parents rule.
        """
        parent_artifact_ids = set()
        if requirement.artifact.parent_id is not None:
            parent_artifact_ids.add(requirement.artifact.parent_id)
        from persistence.models import TraceLink

        for target_id in TraceLink.unscoped.filter(
            tenant_id=requirement.tenant_id,
            source_id=requirement.artifact_id,
            link_type=LinkType.DERIVES_FROM.value,
        ).values_list("target_id", flat=True):
            parent_artifact_ids.add(target_id)
        if not parent_artifact_ids:
            return None

        levels = set(
            Requirement.unscoped.filter(
                tenant_id=requirement.tenant_id,
                artifact_id__in=parent_artifact_ids,
            ).values_list("level", flat=True)
        )
        if len(levels) == 1:
            return next(iter(levels))
        return None

    def suggest_level(self, requirement_id: UUID, ctx: AuthContext) -> dict[str, Any]:
        """Return the suggestion dict for *requirement_id* (read-only, no write).

        ``{"requirement_id", "artifact_id", "level", "source", "signals"}``.
        Tenant-scoped; the caller needs at least read permission (enforced by the
        SuggestionService on the *propose* path, and by the requirement load here
        through the tenant-scoped manager + RLS).
        """
        requirement = self._load(requirement_id, ctx)
        architecture_level = architecture_allocated_levels(requirement.tenant_id).get(
            requirement.artifact_id
        )
        suggestion = suggest_level(
            requirement_type=requirement.type,
            architecture_level=architecture_level,
            parent_level=self._parent_level(requirement),
        )
        return {
            "requirement_id": str(requirement.id),
            "artifact_id": str(requirement.artifact_id),
            "level": suggestion["level"],
            "source": suggestion["source"],
            "signals": suggestion["signals"],
        }

    def propose_level(
        self, requirement_id: UUID, ctx: AuthContext
    ) -> dict[str, Any]:
        """Persist the level suggestion as a ``requirement_level`` Suggestion.

        Produces through the ADR-019 generic proposal lifecycle (agent/API-key
        context required — see ``require_producer_context``). The suggestion is
        durable and waits in the inbox; accepting it sets the manual override.
        """
        requirement = self._load(requirement_id, ctx)
        suggestion = self.suggest_level(requirement_id, ctx)
        return self.suggestion_service.propose(
            "requirement_level",
            ctx,
            workspace_id=requirement.artifact.workspace_id,
            payload={
                "requirement_id": str(requirement.id),
                "artifact_id": str(requirement.artifact_id),
                "level": suggestion["level"],
                "source": suggestion["source"],
                "signals": suggestion["signals"],
            },
            producer=PRODUCER,
            target_item_type="Requirement",
            target_item_id=requirement.id,
        )


__all__ = [
    "PRODUCER",
    "REQUIREMENT_TYPE_TO_LEVEL",
    "RequirementLevelService",
    "suggest_level",
]
