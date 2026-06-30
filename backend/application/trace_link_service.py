"""
COMP-AS-005 TraceLinkService — TraceLink CRUD and cascade-delete.

leaf_id : COMP-AS-005
req_id  : REQ-L2-AS-010 (TraceLink Orchestration)

Orchestrates TraceLink operations via the TraceabilityEngine (IF-AS-EXT-OUT-003).
Validates Source/Target existence and workspace membership before INSERT.
Cascade-delete runs inside the caller's transaction context (ADR-L3-AS005-02).

Interfaces served:
  IF-AS-INT-001  ArtifactService     → cascade_delete_trace_links(artifact_id)
  IF-AS-INT-002  RequirementService  → create_trace_link(source_id, target_id, type)
  IF-AS-INT-004  ArchitectureService → cascade_delete_trace_links(arch_el_id)
  IF-AS-INT-005  TestService         → cascade_delete_trace_links(test_case_id)

Interfaces consumed:
  IF-AS-EXT-OUT-003  TraceabilityEngine:
      create_trace_link, delete_trace_link, batch_delete_trace_links,
      query, VALID_LINK_TYPES

Architecture:
  docs/se/L1/Gesamtsystem/L2/ApplicationServiceSystem/
    Components/COMP-AS-005_TraceLinkService/
      L3_COMP-AS-005_TraceLinkService_Architecture.md

ADR-L3-AS005-01: cross-workspace prevention.
ADR-L3-AS005-02: cascade-delete in caller TX.
ADR-L3-AS005-03: polymorphic source_type/target_type.
"""
from __future__ import annotations

import logging
from typing import List, Optional
from uuid import UUID

from auth_tenancy.context import AuthContext

from application.base import NotFoundError, ServiceBase, ValidationError
from traceability.types import VALID_LINK_TYPES  # REQ-L1-030: single source of truth

logger = logging.getLogger(__name__)


class TraceLinkService(ServiceBase):
    """TraceLink CRUD and cascade-delete for COMP-AS-005.

    All write operations run inside the caller's transaction context —
    no internal transaction.atomic() wrapper is added here (ADR-L3-AS005-02).
    """

    # ---------- IF-AS-INT-002 ----------

    def _resolve_artifact_id(self, entity_id: UUID) -> UUID:
        """Resolve a Requirement/ArchitectureElement/Artifact ID to an Artifact ID.

        The TraceabilityEngine stores links between Artifact IDs.  Callers may
        pass the more user-facing Requirement or ArchitectureElement IDs; this
        helper transparently maps those to their backing Artifact.

        Resolution order:
          1. If *entity_id* is already an Artifact ID, return it unchanged.
          2. If it matches a Requirement, return Requirement.artifact_id.
          3. If it matches an ArchitectureElement, return its artifact_id.
          4. Otherwise raise NotFoundError.
        """
        from persistence.models import (
            ArchitectureElement,
            Artifact,
            Requirement,
        )

        # 1. Already an Artifact ID?
        if Artifact.objects.filter(id=entity_id).first() is not None:
            return entity_id

        # 2. Requirement -> Artifact
        req = Requirement.objects.filter(id=entity_id).first()
        if req is not None:
            return UUID(str(req.artifact_id))

        # 3. ArchitectureElement -> Artifact
        arch = ArchitectureElement.objects.filter(id=entity_id).first()
        if arch is not None:
            return UUID(str(arch.artifact_id))

        raise NotFoundError(f"Entity {entity_id} not found")

    def create_trace_link(
        self,
        source_id: UUID,
        target_id: UUID,
        link_type: str,
        ctx: AuthContext,
    ):
        """Create a single TraceLink after validation.

        REQ-L2-AS-010: validates existence, workspace membership, link type.
        Accepts Artifact, Requirement or ArchitectureElement IDs for
        *source_id* and *target_id* and resolves them to Artifact IDs before
        delegating to the TraceabilityEngine.

        Args:
            source_id: UUID of the source artifact or derived entity.
            target_id: UUID of the target artifact or derived entity.
            link_type: One of VALID_LINK_TYPES.
            ctx: Resolved AuthContext.

        Returns:
            Created TraceLink ORM instance.

        Raises:
            ValidationError: Invalid link_type or cross-workspace link.
            NotFoundError:   Source or target entity does not exist.
        """
        self._set_tenant_context(ctx)

        if link_type not in VALID_LINK_TYPES:
            raise ValidationError(
                f"Invalid link type '{link_type}'. "
                f"Valid types: {sorted(VALID_LINK_TYPES)}"
            )

        # Resolve Requirement/ArchitectureElement IDs to Artifact IDs
        resolved_source = self._resolve_artifact_id(source_id)
        resolved_target = self._resolve_artifact_id(target_id)

        from traceability.services import (
            SourceNotFoundError,
            TargetNotFoundError,
            create_trace_link as te_create,
        )

        try:
            result = te_create(
                source_id=resolved_source,
                target_id=resolved_target,
                link_type=link_type,
                created_by_id=ctx.user_id,
            )
        except SourceNotFoundError as exc:
            raise NotFoundError("Source entity not found") from exc
        except TargetNotFoundError as exc:
            raise NotFoundError("Target entity not found") from exc
        except Exception as exc:
            # Re-map cross-tenant errors as ValidationError
            msg = str(exc)
            if "cross" in msg.lower() or "tenant" in msg.lower():
                raise ValidationError(
                    "Cross-workspace TraceLinks are not permitted"
                ) from exc
            raise

        self._audit(
            ctx=ctx,
            operation="create",
            entity_type="TraceLink",
            entity_id=result.id if hasattr(result, "id") else source_id,
        )
        return result

    # ---------- IF-AS-INT-001 / 004 / 005 ----------

    def cascade_delete_trace_links(
        self, entity_id: UUID, ctx: AuthContext
    ) -> int:
        """Delete all TraceLinks where source OR target is *entity_id*.

        Runs in the caller's transaction context (ADR-L3-AS005-02).
        Idempotent: deleting a non-existent entity's links is a no-op.

        Returns:
            Number of deleted TraceLinks.
        """
        self._set_tenant_context(ctx)

        from traceability.services import batch_delete_trace_links, query
        from traceability.types import Direction

        # Gather all link IDs where this entity is source or target
        link_ids: List[UUID] = []
        for direction in ("upstream", "downstream"):
            try:
                results = query(
                    artifact_id=entity_id,
                    direction=direction,
                    transitive=False,
                )
                for item in results:
                    if hasattr(item, "link_id"):
                        link_ids.append(item.link_id)
            except Exception:
                logger.debug(
                    "TraceLinkService: no links found for entity %s direction=%s",
                    entity_id,
                    direction,
                )

        if not link_ids:
            return 0

        deleted = batch_delete_trace_links(link_ids)
        return deleted

    # ---------- Query ----------

    def query_trace_links(
        self,
        entity_id: UUID,
        direction: str,
        link_type: Optional[str] = None,
        ctx: Optional[AuthContext] = None,
    ) -> list:
        """Query TraceLinks for *entity_id* with optional direction/type filter.

        REQ-L2-AS-010.

        Args:
            entity_id: Starting artifact, Requirement or ArchitectureElement UUID.
            direction: "upstream" | "downstream".
            link_type: Optional filter; ignored if None.
            ctx: AuthContext (required for tenant scoping).
        """
        if ctx is not None:
            self._set_tenant_context(ctx)

        from traceability.services import query

        # Resolve Requirement/ArchitectureElement IDs to Artifact IDs so the
        # TraceabilityEngine can look them up (B-TR-002).
        resolved_id = self._resolve_artifact_id(entity_id)
        results = query(artifact_id=resolved_id, direction=direction)
        if link_type is not None:
            results = [
                r
                for r in results
                if getattr(r, "link_type", None) == link_type
            ]
        return results


__all__ = [
    "TraceLinkService",
    "VALID_LINK_TYPES",
]
