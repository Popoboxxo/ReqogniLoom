"""
COMP-AS-001 ArtifactService — Artifact hierarchy CRUD and cycle detection.

leaf_id : COMP-AS-001
req_id  : REQ-L2-AS-001 (Cycle Detection), REQ-L2-AS-002 (Tree Query)

Manages Artifact entities (the root of the polymorphic hierarchy).
Provides cycle detection (DFS, REQ-L3-AS001-001) and recursive tree queries
via PostgreSQL Recursive CTE (ADR-L3-AS001-02).

Interfaces consumed:
  IF-AS-INT-001     TraceLinkService.cascade_delete_trace_links (on delete)
  IF-AS-EXT-OUT-007 persistence.models.Artifact (Django ORM)

Architecture:
  docs/se/L1/Gesamtsystem/L2/ApplicationServiceSystem/
    Components/COMP-AS-001_ArtifactService/
      L3_COMP-AS-001_ArtifactService_Architecture.md

ADR-L3-AS001-01: DFS cycle detection before persist.
ADR-L3-AS001-02: Recursive CTE for tree query (no N+1).
ADR-L3-AS001-03: Cascade-delete via TraceLinkService.

TODO (hierarchy consolidation): Artifact.parent (persistence/models.py) is
deprecated in favor of 'derives-from' TraceLinks as the single source of
truth for hierarchy. RequirementService/StakeholderNeedService/AdrService/...
never populate it. This service's parent-based cycle detection / tree query
still work but operate on a parallel, generally-unpopulated mechanism —
callers should prefer TraceLinkService for hierarchy going forward.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from uuid import UUID

from django.db import connection, transaction

from auth_tenancy.context import AuthContext

# Backward-compat alias used by tests that patch 'application.artifact_service.TenantContext'
TenantContext = AuthContext

from persistence.models import Artifact, Tenant, Workspace
from persistence.transactions import atomic_transaction

from application.base import NotFoundError, ServiceBase, ValidationError
from application.event_bus import DomainEvent
from application.models import DomainEventOutbox

logger = logging.getLogger(__name__)

# Sentinel distinguishing "parameter omitted" from "clear custom_fields to {}".
_UNSET = object()

#: Universal soft-delete state written by ``workflow.services.outdate()``.
#: Mirrored into ``<Model>.status`` for the types registered in
#: ``workflow.lifecycle_manager._STATUS_MIRROR_MODELS``, and recorded only in
#: ``WorkflowItemState`` for the ones that are not (e.g. ArchitectureElement).
_OUTDATED_STATE = "outdated"


def _clean_custom_fields(value: object) -> dict:
    """Validate + normalize custom_fields at the service boundary (REQ-L2-AS-037).

    Defense in depth: the REST serializer validates first, but the service is
    the single write entry point (ADR-01) and may be called by MCP/import too.
    Raises :class:`application.base.ValidationError` on invalid input.
    """
    from django.core.exceptions import ValidationError as DjangoValidationError

    from persistence.custom_fields import validate_custom_fields

    try:
        return validate_custom_fields(value)
    except DjangoValidationError as exc:
        raise ValidationError(exc.messages[0] if exc.messages else str(exc))


def clean_free_text_field(value: Optional[str], field_name: str) -> Optional[str]:
    """Reject HTML markup / script URIs in a single free-text field (#269, #709).

    Defense in depth, same shape as :func:`_clean_custom_fields`: the REST
    serializer's ``SanitizedCharField`` plus ``FreeTextSanitizationMixin``
    already reject this at the REST boundary (GitHub #269), but that guard
    lives in ``rest_api`` and only fires for requests that go through a DRF
    ViewSet. The service is the single write entry point (ADR-01); MCP tools
    (e.g. ``requirement.create``) call it directly and never touch the DRF
    layer, so without this check a ``<script>`` payload sent over MCP was
    persisted verbatim (#709 regression).

    ``None`` passes through unchanged (mirrors the "field not provided" idiom
    used by ``update_*`` methods across this module — callers gate the
    assignment on ``is not None``, not this helper).

    Raises:
        application.base.ValidationError: if *value* contains HTML markup or
            a script-capable URI scheme.
    """
    if value is None:
        return None

    from persistence.free_text import find_free_text_violation

    violation = find_free_text_violation(value)
    if violation is not None:
        raise ValidationError(f"{field_name} {violation}")
    return value


# ---------------------------------------------------------------------------
# Version-bump gating (#269, finding 5)
# ---------------------------------------------------------------------------

#: Columns that must not take part in the "did anything actually change?"
#: comparison: ``version`` is the counter under test, and the timestamps are
#: bookkeeping that changes on every write by definition.
_VERSION_NEUTRAL_FIELDS = frozenset({"version", "created_at", "modified_at"})


def snapshot_versioned_fields(instance: Any) -> Dict[str, Any]:
    """Capture an entity's concrete column values before an update applies.

    Pair with :func:`has_field_changes` to decide whether an update is a real
    change or a no-op. Reads ``_meta.concrete_fields`` so a newly added column
    is covered automatically rather than needing a hand-maintained list.

    Returns an empty mapping for anything that cannot be introspected (a test
    double, most notably), which :func:`has_field_changes` reads as "unknown"
    and therefore treats as changed — see its docstring.

    Args:
        instance: A loaded Django model instance, before any field assignment.

    Returns:
        Mapping of column attname -> current value; empty if not introspectable.
    """
    try:
        concrete_fields = list(instance._meta.concrete_fields)
    except (AttributeError, TypeError):
        return {}
    return {
        field.attname: getattr(instance, field.attname)
        for field in concrete_fields
        if field.attname not in _VERSION_NEUTRAL_FIELDS
    }


def has_field_changes(instance: Any, snapshot: Dict[str, Any]) -> bool:
    """Return True if any snapshotted column now holds a different value.

    #269 finding 5: ``version`` used to be incremented for every ``update_*()``
    call regardless of whether a single column actually moved, so a PATCH that
    changed nothing still reported a bumped version. Since the baseline diff
    engine compares stored version numbers, those phantom bumps produced diffs
    between identical snapshots. Gating the increment on this predicate keeps
    ``version`` an honest change counter.

    An **empty snapshot means "cannot tell"**, not "nothing changed", and is
    reported as changed. Every real model has at least a primary key, so this
    only triggers for non-introspectable objects — in practice the ``MagicMock``
    ORM doubles in the service unit tests. Failing towards a bump keeps the
    conservative pre-existing behaviour whenever the comparison is blind: losing
    a legitimate version increment would corrupt the baseline history, whereas a
    surplus one is merely the old, tolerated inaccuracy.

    Args:
        instance: The same instance passed to :func:`snapshot_versioned_fields`,
            after the update assignments have been applied.
        snapshot: The mapping returned by :func:`snapshot_versioned_fields`.

    Returns:
        True if at least one column differs from its snapshotted value, or if
        the snapshot is empty.
    """
    if not snapshot:
        return True
    return any(
        getattr(instance, name) != value for name, value in snapshot.items()
    )


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------


@dataclass
class TreeNodeDTO:
    """Nested artifact tree node for API responses (REQ-L2-AS-002)."""

    id: UUID
    artifact_type: str
    children: List["TreeNodeDTO"] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "artifact_type": self.artifact_type,
            "children": [c.as_dict() for c in self.children],
        }


# ---------------------------------------------------------------------------
# ArtifactService
# ---------------------------------------------------------------------------


class ArtifactService(ServiceBase):
    """COMP-AS-001 — Artifact lifecycle management.

    Requires a TraceLinkService instance for cascade-delete (IF-AS-INT-001).
    """

    def __init__(self, trace_link_service=None) -> None:
        # Lazy import to avoid circular dependency at module load time.
        from application.trace_link_service import TraceLinkService

        self._trace_link_service = trace_link_service or TraceLinkService()

    # ---------- Cycle Detection (REQ-L2-AS-001, ADR-L3-AS001-01) ----------

    @staticmethod
    def _detect_cycle(new_parent_id: UUID, child_id: UUID) -> Optional[List[UUID]]:
        """Walk UP the ancestor chain from *new_parent_id* looking for *child_id*.

        Returns a list of UUIDs forming the cycle path if found, else None.
        O(depth) — acceptable for < 10-level hierarchies per ADR-L3-AS001-01.
        """
        visited: List[UUID] = []
        current_id: Optional[UUID] = new_parent_id

        while current_id is not None:
            if current_id == child_id:
                visited.append(current_id)
                return visited
            visited.append(current_id)
            try:
                artifact = Artifact.unscoped.filter(id=current_id).values("parent_id").first()
            except Exception:
                break
            if artifact is None:
                break
            current_id = artifact["parent_id"]

        return None

    def _validate_no_cycle(self, artifact_id: UUID, new_parent_id: Optional[UUID]) -> None:
        """Raise ValidationError if setting parent to *new_parent_id* creates a cycle.

        REQ-L2-AS-001 acceptance criteria:
          - self-reference → exception
          - chain A→B→C, try C.parent=A → exception with path
        """
        if new_parent_id is None:
            return
        if new_parent_id == artifact_id:
            raise ValidationError(
                f"Cycle detected: self-reference (id={artifact_id})"
            )
        cycle_path = self._detect_cycle(new_parent_id, artifact_id)
        if cycle_path:
            path_str = "→".join(str(p) for p in cycle_path)
            raise ValidationError(f"Cycle detected: {path_str}→{artifact_id}")

    # ---------- CRUD ----------

    @atomic_transaction
    def create_artifact(
        self,
        workspace_id: UUID,
        artifact_type: str,
        ctx: AuthContext,
        parent_id: Optional[UUID] = None,
        custom_fields: Optional[dict] = None,
    ) -> Artifact:
        """Create a new Artifact, validating parent cycle if supplied.

        REQ-L2-AS-001, REQ-L2-AS-018 (ACID).
        REQ-L2-AS-037: optional user-defined custom_fields (validated flat map).
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        # Workspace and Tenant are imported at module level to allow test mocking.
        workspace = Workspace.objects.filter(id=workspace_id).first()
        if workspace is None:
            raise NotFoundError(f"Workspace {workspace_id} not found")

        if parent_id is not None:
            parent = Artifact.objects.filter(id=parent_id).first()
            if parent is None:
                raise NotFoundError(f"Parent artifact {parent_id} not found")
            self._validate_no_cycle(artifact_id=UUID(str(parent_id)), new_parent_id=None)

        tenant = Tenant.objects.filter(id=ctx.tenant_id).first()
        if tenant is None:
            raise NotFoundError(f"Tenant {ctx.tenant_id} not found")

        artifact = Artifact.objects.create(
            tenant=tenant,
            workspace=workspace,
            artifact_type=artifact_type,
            parent_id=parent_id,
            custom_fields=_clean_custom_fields(custom_fields),
        )

        self._audit(
            ctx=ctx,
            operation="create",
            entity_type="Artifact",
            entity_id=artifact.id,
        )
        self._emit_event(
            self._make_event(
                event_type=DomainEventOutbox.EventType.REQUIREMENT_CREATED,
                entity_id=artifact.id,
                workspace_id=workspace_id,
            )
        )
        return artifact

    @atomic_transaction
    def update_artifact(
        self,
        artifact_id: UUID,
        ctx: AuthContext,
        parent_id: Optional[UUID] = None,
        artifact_type: Optional[str] = None,
        custom_fields: object = _UNSET,
    ) -> Artifact:
        """Update parent, type or custom_fields; validates cycle if parent changes.

        REQ-L2-AS-001.
        REQ-L2-AS-037: custom_fields replaces the stored map when provided
        (``_UNSET`` sentinel distinguishes "omitted" from "cleared to {}").
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        artifact = Artifact.objects.filter(id=artifact_id).first()
        if artifact is None:
            raise NotFoundError(f"Artifact {artifact_id} not found")

        if parent_id is not None:
            self._validate_no_cycle(artifact_id, parent_id)
            artifact.parent_id = parent_id

        if artifact_type is not None:
            artifact.artifact_type = artifact_type

        if custom_fields is not _UNSET:
            artifact.custom_fields = _clean_custom_fields(custom_fields)

        artifact.save()
        self._audit(ctx=ctx, operation="update", entity_type="Artifact", entity_id=artifact.id)
        return artifact

    @atomic_transaction
    def delete_artifact(self, artifact_id: UUID, ctx: AuthContext) -> None:
        """Delete artifact after cascading TraceLinks (ADR-L3-AS001-03).

        REQ-L2-AS-018: atomic — TraceLink cascade + Artifact delete in one TX.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        artifact = Artifact.objects.filter(id=artifact_id).first()
        if artifact is None:
            raise NotFoundError(f"Artifact {artifact_id} not found")

        # IF-AS-INT-001: cascade delete trace links first
        self._trace_link_service.cascade_delete_trace_links(artifact_id, ctx)

        workspace_id = artifact.workspace_id
        artifact.delete()

        self._audit(ctx=ctx, operation="delete", entity_type="Artifact", entity_id=artifact_id)
        self._emit_event(
            self._make_event(
                event_type=DomainEventOutbox.EventType.REQUIREMENT_DELETED,
                entity_id=artifact_id,
                workspace_id=workspace_id,
            )
        )

    def get_artifact(self, artifact_id: UUID, ctx: AuthContext) -> Artifact:
        """Fetch a single artifact (tenant-scoped)."""
        self._set_tenant_context(ctx)
        artifact = Artifact.objects.filter(id=artifact_id).first()
        if artifact is None:
            raise NotFoundError(f"Artifact {artifact_id} not found")
        return artifact

    # ---------- Read / label resolution (REQ-066 Phase 2) ----------

    def list_child_summaries(self, ctx: AuthContext, workspace_id: UUID):
        """Return a lazy QuerySet of artifact summary rows for a workspace.

        REQ-034: the caller hands the QuerySet straight to the paginator so it
        slices lazily (LIMIT/OFFSET) instead of materializing every row.
        REQ-066: keeps the ORM access inside the service layer.
        """
        self._set_tenant_context(ctx)
        return Artifact.unscoped.filter(workspace_id=workspace_id).values(
            "id", "parent_id", "artifact_type"
        )

    def resolve_artifact_titles(
        self, artifact_ids: List[Any]
    ) -> "Dict[str, Dict[str, Any]]":
        """Batch-resolve artifact IDs to ``{title, artifact_type, is_outdated}``.

        REQ-002: Provides human-readable labels for TraceLink endpoints without
        N+1 queries. Runs a small, constant number of DB queries regardless of
        the number of links: one Artifact query for types + one per domain
        entity table (+1 for the ArchitectureElement workflow-state lookup).
        REQ-066: ORM access lives in the service layer, not the REST view.

        ``is_outdated`` reports whether the backing entity has been soft-deleted
        via ``workflow.services.outdate()``. TraceLinks are deliberately
        *preserved* when their endpoint is soft-deleted (see
        ``AdrService.delete_adr``: "TraceLinks are preserved for audit trail
        purposes"), so the link keeps showing up in
        ``GET /api/v1/tracelinks/``. Without this flag every consumer rendered
        such a link as a perfectly live, named neighbour — indistinguishable
        from a link to an existing artifact. The title is still resolved on
        purpose: dropping it would only degrade the row to a raw UUID stub and
        hide *why* it looks odd. Marking lets the presentation layer grey the
        row out and keep it out of "live neighbour" counts.

        Soft-delete is recorded in two different places depending on the entity:

        * Types registered in ``workflow.lifecycle_manager._STATUS_MIRROR_MODELS``
          (Requirement, StakeholderNeed, TestCase, Adr) carry a mirrored
          ``status="outdated"`` column — the same value ``AdrService.list_adrs``
          and the SE-Auditor rule helpers filter on.
        * ``ArchitectureElement`` has **no** mirror: ``outdate()`` writes only
          ``WorkflowItemState`` and never touches the dead ``lifecycle_status``
          column, so its state must be read via
          ``workflow.services.outdated_item_ids`` (same idiom as
          ``ArchitectureService.list_architecture_elements``).

        Only the literal state ``"outdated"`` counts as soft-deleted. Business-
        terminal states (an ADR's ``Rejected``/``Superseded``, a Requirement's
        ``deprecated``) stay live on purpose — see the contract note on
        ``workflow.services.outdated_item_ids``.
        """
        from persistence.models import (
            ArchitectureElement,
            Requirement,
            StakeholderNeed,
            TestCase,
        )

        str_ids = [str(aid) for aid in artifact_ids if aid]
        if not str_ids:
            return {}

        result: Dict[str, Dict[str, Any]] = {}

        # Fetch artifact types first.
        for art in Artifact.objects.filter(id__in=str_ids).values(
            "id", "artifact_type"
        ):
            result[str(art["id"])] = {
                "title": "",
                "artifact_type": art["artifact_type"],
                "is_outdated": False,
            }

        # Each domain entity is OneToOne on Artifact — a single artifact_id__in
        # scan per table enriches all matching entries without N+1 queries.
        # These three mirror their workflow state into their own ``status``
        # column, so it comes along in the same values() projection for free.
        for model in (Requirement, StakeholderNeed, TestCase):
            for row in model.objects.filter(artifact_id__in=str_ids).values(
                "artifact_id", "title", "status"
            ):
                key = str(row["artifact_id"])
                if key in result:
                    result[key]["title"] = row["title"] or ""
                    result[key]["is_outdated"] = row["status"] == _OUTDATED_STATE

        # ArchitectureElement has no status mirror — consult WorkflowItemState.
        ae_rows = list(
            ArchitectureElement.objects.filter(artifact_id__in=str_ids).values(
                "id", "artifact_id", "title"
            )
        )
        if ae_rows:
            from workflow.services import outdated_item_ids

            # Narrow the state lookup to the elements actually referenced here
            # instead of materializing every outdated element of the tenant.
            outdated_ae_ids = set(
                outdated_item_ids("ArchitectureElement").filter(
                    item_id__in=[row["id"] for row in ae_rows]
                )
            )
            for row in ae_rows:
                key = str(row["artifact_id"])
                if key in result:
                    result[key]["title"] = row["title"] or ""
                    result[key]["is_outdated"] = row["id"] in outdated_ae_ids

        # ADR lives in the application layer (not persistence) — import locally
        # to avoid circular imports (adr_service imports TraceLinkService).
        try:
            from application.models import Adr

            for row in Adr.objects.filter(artifact_id__in=str_ids).values(
                "artifact_id", "title", "status"
            ):
                key = str(row["artifact_id"])
                if key in result:
                    result[key]["title"] = row["title"] or ""
                    result[key]["is_outdated"] = row["status"] == _OUTDATED_STATE
        except Exception:  # noqa: BLE001 — ADR model absent in some test configs
            pass

        return result

    def collect_artifact_names(
        self, item_ids: List[str], tenant_id: UUID
    ) -> Dict[str, str]:
        """Batch-resolve ``{item_id: title}`` for baseline-diff items (REQ-006).

        ``item_id`` is the Artifact UUID for ``entity_type == "item"`` entries
        (REQ-L2-BL-001). The concrete domain entity is discovered by
        batch-querying each candidate table on ``artifact_id__in``, mirroring
        ``baseline.state_capture._capture_items``. Non-UUID or unresolved ids
        (e.g. icd/trace_link/glossary_term entries) are simply omitted so
        callers can fall back to the raw id. REQ-066: ORM stays in the service.
        """
        from persistence.models import (
            ArchitectureElement,
            Requirement,
            StakeholderNeed,
            TestCase,
        )

        uuids: List[UUID] = []
        for raw in item_ids:
            try:
                uuids.append(UUID(str(raw)))
            except (ValueError, TypeError):
                continue
        if not uuids:
            return {}

        names: Dict[str, str] = {}
        for model in (Requirement, StakeholderNeed, ArchitectureElement, TestCase):
            for artifact_id, title in model.unscoped.filter(
                artifact_id__in=uuids, tenant_id=tenant_id
            ).values_list("artifact_id", "title"):
                names[str(artifact_id)] = title
        return names

    # ---------- Tree Query (REQ-L2-AS-002, ADR-L3-AS001-02) ----------

    def get_tree(
        self, root_id: UUID, workspace_id: UUID, ctx: AuthContext
    ) -> TreeNodeDTO:
        """Return the full subtree rooted at *root_id* using a Recursive CTE.

        REQ-L2-AS-002: < 200ms for 500 artifacts in 5 levels.
        ADR-L3-AS001-02: single SQL query, no N+1.

        #38: *root_id* is resolved the same way TraceLinkService resolves
        TraceLink endpoints — callers naturally pass the more user-facing
        Requirement/ArchitectureElement/Adr ID (as returned by
        requirement.create, etc.), which is a distinct UUID from its backing
        Artifact row. Without this resolution step the CTE's anchor query
        (``WHERE id = %s``) never matches and a real, existing artifact is
        reported as "not found".
        """
        self._set_tenant_context(ctx)

        from application.trace_link_service import TraceLinkService

        root_id = TraceLinkService()._resolve_artifact_id(root_id)

        # Recursive CTE: fetch all descendants in one query
        sql = """
            WITH RECURSIVE tree AS (
                SELECT id, parent_id, artifact_type, 0 AS depth
                FROM pl_artifact
                WHERE id = %s
                  AND workspace_id = %s

                UNION ALL

                SELECT a.id, a.parent_id, a.artifact_type, t.depth + 1
                FROM pl_artifact a
                INNER JOIN tree t ON a.parent_id = t.id
                WHERE t.depth < 20
            )
            SELECT id, parent_id, artifact_type FROM tree ORDER BY depth;
        """

        rows: Dict[UUID, Dict] = {}
        with connection.cursor() as cursor:
            cursor.execute(sql, [str(root_id), str(workspace_id)])
            for row_id, parent_id, artifact_type in cursor.fetchall():
                rows[row_id] = {
                    "parent_id": parent_id,
                    "artifact_type": artifact_type,
                    "children": [],
                }

        if not rows:
            raise NotFoundError(
                f"Artifact {root_id} not found in workspace {workspace_id}"
            )

        # Build nested structure
        nodes: Dict[UUID, TreeNodeDTO] = {
            uid: TreeNodeDTO(id=uid, artifact_type=data["artifact_type"])
            for uid, data in rows.items()
        }
        root_node: Optional[TreeNodeDTO] = None
        for uid, data in rows.items():
            parent_id = data["parent_id"]
            if parent_id and parent_id in nodes:
                nodes[parent_id].children.append(nodes[uid])
            else:
                root_node = nodes[uid]

        if root_node is None:
            root_node = nodes[root_id]

        return root_node


__all__ = [
    "ArtifactService",
    "TreeNodeDTO",
]
