"""ReferenceResolverService — batch-resolve local ``uid`` references (issue #17).

Coding agents (Claude Code, Cursor) and CI gates work with the human-readable
identifiers that appear in commit messages, specs and prompts —
``REQ-L1-007``, ``NEED-003``, ``ARCH-001`` — not with UUIDs. This service is
the Layer-2 facade that turns such references into entities of a single
workspace: one call for the MCP tool ``workspace.resolve_references`` and any
future REST route, so the "query every artifact table" logic lives in the
application layer (ADR-01) instead of in an adapter.

Design notes
------------

* **Spec-driven, lazily imported.** :data:`_ENTITY_SPECS` mirrors the
  ``uid``-carrying models and their workspace access path (direct
  ``workspace_id`` vs. traversal through the backing ``artifact``), following
  the same dataclass-spec idiom as :mod:`application.workspace_lookup`. The
  model classes are imported lazily so importing this module never requires a
  ready app registry.
* **Bounded queries.** One ``uid__in`` query per entity type, exactly the
  "small, constant number of DB queries regardless of the input size"
  contract :meth:`application.import_service.ImportService._dedupe_rows`
  already established for the same natural key.
* **Workspace + tenant scoped.** Every query filters the entity's workspace
  path to the caller-supplied workspace; the tenant-filtered manager
  (``TenantScopedModel.objects``) then adds the tenant fence
  (ADR-03). A reference that exists only in another workspace or another
  tenant of the same deployment is therefore reported as unresolved — never
  leaked as data.
* **Fail-soft for data, fail-loud for context.** An unknown, malformed or
  foreign reference is reported back to the caller in ``not_found``; only a
  missing workspace/tenant mismatch raises ``NotFoundError``, matching how the
  other workspace-scoped MCP read tools answer.
* **Status through the workflow seam.** ``status`` on the wire is the
  workflow engine's ``current_state`` (Datenmodell-Konsolidierung D-1),
  resolved in one batched call per entity type via
  :func:`mcp_server.tools.base.resolve_status_map`'s seam
  ``workflow.state_reader.current_states``. ``TestRun`` is the one type
  whose lifecycle state is a plain model column rather than a workflow item,
  so its spec reads that column instead.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from uuid import UUID

from auth_tenancy.context import AuthContext

from application.base import NotFoundError, ServiceBase
from application.workspace_lookup import import_entity_model
from workflow import state_reader

logger = logging.getLogger(__name__)

__all__ = ["ReferenceResolverService"]


@dataclass(frozen=True)
class _ReferenceEntitySpec:
    """How to resolve one entity type's local ``uid`` within a workspace.

    Attributes:
        model_path: Dotted ``module.ClassName`` path, imported lazily.
        workspace_field: ORM path from the model to the workspace id — either
            a local column (``workspace_id``) or a traversal through the
            backing artifact (``artifact__workspace_id``) for artifact-backed
            entities.
        item_type: Workflow-engine item type used to resolve the wire
            ``status``; also the entity name reported as ``artifact_type``.
        title_field: Column carrying the display title (``name`` for
            TestRun, which has no title).
        description_field: Column carrying the description, or ``None`` for
            types that have none (TestRun).
        status_column: ``True`` for the one type whose lifecycle state is a
            plain model column (TestRun) rather than a workflow item.
    """

    model_path: str
    workspace_field: str
    item_type: str
    title_field: str = "title"
    description_field: Optional[str] = "description"
    status_column: bool = False


#: The entity types that carry a local readable ``uid`` (issue #932,
#: ``application.local_uid.UID_PREFIXES``). Workspace field verified against
#: the models: Requirement/ArchitectureElement/StakeholderNeed/TestCase are
#: artifact-backed (the workspace lives on ``pl_artifact``), the other four
#: hold their own ``workspace_id`` column.
_ENTITY_SPECS: Dict[str, _ReferenceEntitySpec] = {
    "StakeholderNeed": _ReferenceEntitySpec(
        model_path="persistence.models.StakeholderNeed",
        workspace_field="artifact__workspace_id",
        item_type="StakeholderNeed",
    ),
    "Requirement": _ReferenceEntitySpec(
        model_path="persistence.models.Requirement",
        workspace_field="artifact__workspace_id",
        item_type="Requirement",
    ),
    "ArchitectureElement": _ReferenceEntitySpec(
        model_path="persistence.models.ArchitectureElement",
        workspace_field="artifact__workspace_id",
        item_type="ArchitectureElement",
    ),
    "TestCase": _ReferenceEntitySpec(
        model_path="persistence.models.TestCase",
        workspace_field="artifact__workspace_id",
        item_type="TestCase",
    ),
    "TestRun": _ReferenceEntitySpec(
        model_path="persistence.models.TestRun",
        workspace_field="workspace_id",
        item_type="TestRun",
        title_field="name",
        description_field=None,
        status_column=True,
    ),
    "Adr": _ReferenceEntitySpec(
        model_path="persistence.models.Adr",
        workspace_field="workspace_id",
        item_type="Adr",
    ),
    "Risk": _ReferenceEntitySpec(
        model_path="persistence.models.Risk",
        workspace_field="workspace_id",
        item_type="Risk",
    ),
    "Issue": _ReferenceEntitySpec(
        model_path="persistence.models.Issue",
        workspace_field="workspace_id",
        item_type="Issue",
    ),
}


class ReferenceResolverService(ServiceBase):
    """Resolve local ``uid`` references against one workspace (issue #17)."""

    def resolve_references(
        self,
        *,
        workspace_id: UUID,
        references: List[str],
        ctx: AuthContext,
    ) -> Dict[str, Any]:
        """Resolve *references* (e.g. ``["REQ-L1-007", "NEED-003"]``).

        Args:
            workspace_id: The workspace to resolve in. Must belong to the
                caller's tenant — a foreign or unknown workspace raises
                ``NotFoundError``.
            references: Human-readable local uids. Already-validated by the
                caller (strings, bounded length); blank entries are reported
                as unresolved rather than rejected.
            ctx: Auth context — supplies the tenant fence.

        Returns:
            ``{"resolved": {reference: {"id", "artifact_type", "title",
            "description", "status"}}, "not_found": [reference, ...]}``.
            ``not_found`` preserves the input order (minus duplicates) and
            carries every reference that matched no entity in this
            workspace — unknown ids, malformed ids, cross-workspace and
            cross-tenant ids alike.

        Raises:
            NotFoundError: the workspace does not exist for this tenant.
        """
        from application.workspace_service import WorkspaceService

        self._set_tenant_context(ctx)

        # Existence + tenant membership in one call: the tenant-scoped
        # manager makes a foreign-tenant workspace invisible, so it is
        # answered exactly like an unknown one (no existence leak).
        WorkspaceService().get_workspace(workspace_id, ctx)

        # Deduplicate while preserving input order — the caller may send the
        # same reference twice (e.g. a commit message that repeats an id).
        # Blank/whitespace-only entries stay in the list: they are malformed
        # input, and the contract is that a malformed reference is reported
        # back in ``not_found`` rather than silently dropped.
        normalized: List[str] = []
        seen: set[str] = set()
        for raw in references:
            key = raw.strip()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(key)

        resolved: Dict[str, Dict[str, Any]] = {}
        for entity_key, spec in _ENTITY_SPECS.items():
            pending = [key for key in normalized if key not in resolved]
            if not pending:
                break
            hits = self._query_type(spec, workspace_id, pending)
            if not hits:
                continue
            status_map = self._status_map(spec, [str(hit["id"]) for hit in hits])
            for hit in hits:
                resolved[hit["uid"]] = {
                    "id": str(hit["id"]),
                    "artifact_type": spec.item_type,
                    "title": hit.get(spec.title_field) or "",
                    "description": (
                        (hit.get(spec.description_field) or "")
                        if spec.description_field
                        else ""
                    ),
                    "status": status_map.get(str(hit["id"]), ""),
                }

        not_found = [key for key in normalized if key not in resolved]
        return {"resolved": resolved, "not_found": not_found}

    # ---------- internals ----------

    def _query_type(
        self, spec: _ReferenceEntitySpec, workspace_id: UUID, uids: List[str]
    ) -> List[Dict[str, Any]]:
        """One bounded ``uid__in`` query for one entity type."""
        model = import_entity_model(spec.model_path)
        scope = {spec.workspace_field: workspace_id, "uid__in": uids}
        fields = ["id", "uid", spec.title_field]
        if spec.description_field:
            fields.append(spec.description_field)
        if spec.status_column:
            fields.append("status")
        return list(model.objects.filter(**scope).values(*fields))

    def _status_map(
        self, spec: _ReferenceEntitySpec, entity_ids: List[str]
    ) -> Dict[str, str]:
        """Wire-status lookup: the model column for TestRun, else the engine."""
        if spec.status_column:
            model = import_entity_model(spec.model_path)
            return {
                str(row_id): status
                for row_id, status in model.objects.filter(
                    id__in=entity_ids
                ).values_list("id", "status")
            }
        try:
            return state_reader.current_states(spec.item_type, entity_ids)
        except Exception:
            logger.debug(
                "resolve_references: status lookup failed for %s", spec.item_type
            )
            return {}
