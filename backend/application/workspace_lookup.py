"""Resolve the workspace that owns a domain entity, given its id.

Systemaudit 2026-08-29 (§6.5) closed a cross-workspace read/write hole in the
MCP dispatcher: RBAC has to be decided against the workspace a call *targets*,
and most tools name their target by id rather than by ``workspace_id``. Turning
such an id into its owning workspace is a domain query over ten-plus models, so
by ADR-01 it belongs here — the adapter layers (``mcp_server``, and any future
one) only supply the id and consume the answer.

Design notes
------------

* **Fail-soft by contract.** Every failure mode — unknown key, no such row, a
  model refactor, a missing tenant context — returns ``None``. Callers use this
  to *tighten* an authorisation decision, so "cannot tell" must degrade to
  their previous behaviour rather than deny a legitimate request. The deny
  decision itself belongs to the caller and only ever fires on a positive hit.
* **Lazy model import.** Specs carry dotted paths, resolved on first use, so
  importing this module never requires a ready app registry.
* **Cross-tenant ids can resolve.** ``objects`` is tenant-scoped for the
  ``persistence`` models but a plain manager for the ``application`` ones. That
  asymmetry is harmless for the authorisation use case: a workspace belonging
  to another tenant can only produce an *empty* role set for the caller, i.e. a
  deny. It cannot manufacture an allow.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple
from uuid import UUID

logger = logging.getLogger(__name__)

__all__ = [
    "ARTIFACT_BACKED_ENTITY_KEYS",
    "ENTITY_SPECS",
    "EntityWorkspaceSpec",
    "import_entity_model",
    "resolve_owning_workspace_id",
]


@dataclass(frozen=True)
class EntityWorkspaceSpec:
    """How to resolve one entity type's owning workspace from an id.

    Attributes:
        model_path: Dotted ``module.ClassName`` path, imported lazily.
        workspace_field: ORM path from the model to the workspace id — either a
            local column (``workspace_id``) or a traversal through the backing
            artifact (``artifact__workspace_id``) for entities whose workspace
            lives on ``pl_artifact``.
        lookup_field: Column the supplied id is matched against. ``id`` for
            every entity except ``goal_lineage``, where the caller names a
            lineage rather than a single version row.
    """

    model_path: str
    workspace_field: str = "workspace_id"
    lookup_field: str = "id"


#: Verified against the models on 2026-08-29. ``Requirement`` carries both a
#: local ``workspace`` FK and an ``artifact`` OneToOne; the local column is used
#: because it needs no join. ``ArchitectureElement``/``TestCase``/
#: ``StakeholderNeed`` carry only the artifact link.
ENTITY_SPECS: Dict[str, EntityWorkspaceSpec] = {
    "requirement": EntityWorkspaceSpec("persistence.models.Requirement"),
    "architecture": EntityWorkspaceSpec(
        "persistence.models.ArchitectureElement",
        workspace_field="artifact__workspace_id",
    ),
    "testcase": EntityWorkspaceSpec(
        "persistence.models.TestCase", workspace_field="artifact__workspace_id"
    ),
    "need": EntityWorkspaceSpec(
        "persistence.models.StakeholderNeed",
        workspace_field="artifact__workspace_id",
    ),
    "artifact": EntityWorkspaceSpec("persistence.models.Artifact"),
    "glossary": EntityWorkspaceSpec("persistence.models.GlossaryTerm"),
    "custom_field": EntityWorkspaceSpec("persistence.models.CustomFieldDefinition"),
    "test_run": EntityWorkspaceSpec("persistence.models.TestRun"),
    "interview": EntityWorkspaceSpec("persistence.models.InterviewSession"),
    "adr": EntityWorkspaceSpec("persistence.models.Adr"),
    "risk": EntityWorkspaceSpec("persistence.models.Risk"),
    "issue": EntityWorkspaceSpec("persistence.models.Issue"),
    "change_request": EntityWorkspaceSpec("persistence.models.ChangeRequest"),
    "goal": EntityWorkspaceSpec("persistence.models.Goal"),
    # Every version of a lineage lives in the same workspace, so any row answers
    # a lineage-scoped question.
    "goal_lineage": EntityWorkspaceSpec(
        "persistence.models.Goal", lookup_field="lineage_id"
    ),
    "main_goal": EntityWorkspaceSpec("persistence.models.MainGoal"),
    "diagram": EntityWorkspaceSpec("diagram.models.Diagram"),
    # A Global-scope BaselineSnapshot has workspace_id NULL; that resolves to
    # None and correctly falls through to the caller's unscoped path.
    "baseline": EntityWorkspaceSpec("baseline.models.BaselineSnapshot"),
}


#: Probe order for the domain entities that carry a backing ``Artifact``.
#: Mirrors ``traceability.service._domain_model_registry`` /
#: ``TraceLinkService._resolve_artifact_id``: since fix #264 the tools that take
#: an ``artifact_id`` accept a *domain* id (e.g. a Requirement id) just as
#: readily as a generic ``pl_artifact`` id, so probing only ``Artifact`` would
#: leave the common case unresolved.
ARTIFACT_BACKED_ENTITY_KEYS: Tuple[str, ...] = (
    "requirement",
    "architecture",
    "need",
    "testcase",
    "adr",
    "risk",
    "issue",
    "goal",
    "main_goal",
)


def import_entity_model(model_path: str) -> Any:
    """Import ``module.ClassName`` lazily.

    Public so the architecture/schema guards can walk :data:`ENTITY_SPECS`
    without re-implementing the import.
    """
    module_path, _, class_name = model_path.rpartition(".")
    module = __import__(module_path, fromlist=[class_name])
    return getattr(module, class_name)


def resolve_owning_workspace_id(
    entity_key: str, entity_id: UUID
) -> Optional[UUID]:
    """Return the workspace owning ``entity_id``, or ``None`` if unresolvable.

    Args:
        entity_key: A key of :data:`ENTITY_SPECS`.
        entity_id: The entity's primary key (or lineage id for
            ``goal_lineage``).

    Returns:
        The owning workspace id, or ``None`` when the key is unknown, no row
        matches, the row's workspace is NULL, or the query fails. See the
        module docstring for why every one of those is ``None`` rather than an
        exception.
    """
    spec = ENTITY_SPECS.get(entity_key)
    if spec is None:  # pragma: no cover - guarded by the registry test
        return None
    try:
        model = import_entity_model(spec.model_path)
        return (
            model.objects.filter(**{spec.lookup_field: entity_id})
            .values_list(spec.workspace_field, flat=True)
            .first()
        )
    except Exception:
        logger.debug(
            "Workspace resolution failed for entity=%s id=%s", entity_key, entity_id
        )
        return None
