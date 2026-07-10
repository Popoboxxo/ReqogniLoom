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

    # ---------- Tree Query (REQ-L2-AS-002, ADR-L3-AS001-02) ----------

    def get_tree(
        self, root_id: UUID, workspace_id: UUID, ctx: AuthContext
    ) -> TreeNodeDTO:
        """Return the full subtree rooted at *root_id* using a Recursive CTE.

        REQ-L2-AS-002: < 200ms for 500 artifacts in 5 levels.
        ADR-L3-AS001-02: single SQL query, no N+1.
        """
        self._set_tenant_context(ctx)

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
