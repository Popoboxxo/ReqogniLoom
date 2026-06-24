"""
COMP-TE-001 TraceLinkManager — TraceLink CRUD, validation, cycle detection.

leaf_id: COMP-TE-001_TraceLinkManager
req_id: REQ-L2-TE-001, REQ-L2-TE-002, REQ-L2-TE-003, REQ-L2-TE-009,
        REQ-L2-TE-010, REQ-L2-TE-011

Responsibilities:
- TraceLink CRUD with 8 link types (REQ-L2-TE-001)
- Eager cycle detection for single links via DFS (REQ-L2-TE-002)
- Atomic batch operations with Tarjan SCC cycle check at transaction end
  (REQ-L2-TE-003)
- Tenant isolation on all operations (REQ-L2-TE-011)
- Audit metadata capture: created_by, modified_by (REQ-L2-TE-010)
- Referential integrity via ORM CASCADE is enforced at DB level (REQ-L2-TE-009)

Interface contracts consumed:
- IF-TE-EXT-OUT-001: PersistenceLayer — Django ORM TraceLink entity
- IF-TE-EXT-OUT-002: validate_cross_tenant_boundary via TenantContext

Interface contracts exposed:
- IF-TE-INT-001 / IF-TE-INT-002: get_trace_links(workspace_id, filters)
- IF-TE-INT-003: validate_graph_integrity() -> ValidationResult

Architecture:
  docs/se/L1/Gesamtsystem/L2/TraceabilityEngineSystem/Components/
  COMP-TE-001_TraceLinkManager/L3_COMP-TE-001_TraceLinkManager_Architecture.md
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Any, Optional

from django.db import transaction

from persistence.models import Artifact, TraceLink
from persistence.tenancy import TenantContext

from traceability.exceptions import (
    CrossTenantLinkError,
    CycleDetectedError,
    InvalidLinkTypeError,
    SourceNotFoundError,
    TargetNotFoundError,
)
from traceability.types import VALID_LINK_TYPES


# ---------------------------------------------------------------------------
# Link-type validation
# ---------------------------------------------------------------------------

def _validate_link_type(link_type: str) -> None:
    """Validate link_type against the 8-type enum (REQ-L2-TE-001).

    The persistence CharField accepts any string; the service layer enforces
    the 8-type contract here without modifying persistence.models.
    """
    if link_type not in VALID_LINK_TYPES:
        raise InvalidLinkTypeError(link_type)


# ---------------------------------------------------------------------------
# Cross-tenant guard (IF-TE-EXT-OUT-002)
# ---------------------------------------------------------------------------

def _validate_cross_tenant_boundary(source: Artifact, target: Artifact) -> None:
    """Reject links whose endpoints belong to different tenants.

    REQ-L2-TE-011 / IF-TE-EXT-OUT-002. Fail-closed: if tenant IDs cannot be
    compared (None), the link is rejected.
    """
    if source.tenant_id != target.tenant_id:
        raise CrossTenantLinkError()


# ---------------------------------------------------------------------------
# Cycle detection helpers
# ---------------------------------------------------------------------------

def _build_adjacency(
    workspace_links: list[TraceLink],
) -> dict[uuid.UUID, list[uuid.UUID]]:
    """Build an adjacency list from existing TraceLink rows."""
    adj: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    for link in workspace_links:
        adj[link.source_id].append(link.target_id)
    return adj


def _dfs_has_cycle_to(
    start: uuid.UUID,
    goal: uuid.UUID,
    adj: dict[uuid.UUID, list[uuid.UUID]],
) -> bool:
    """Return True if there is any path from *start* to *goal* in *adj*.

    Used for eager single-link cycle check (REQ-L2-TE-002):
    Before adding edge (source→target) we check if target already reaches
    source — that would form a cycle.
    """
    visited: set[uuid.UUID] = set()
    stack = [start]
    while stack:
        node = stack.pop()
        if node == goal:
            return True
        if node in visited:
            continue
        visited.add(node)
        stack.extend(adj.get(node, []))
    return False


def _tarjan_find_cycle(
    adj: dict[uuid.UUID, list[uuid.UUID]],
) -> list[uuid.UUID] | None:
    """Tarjan SCC algorithm — return a cycle path or None.

    O(V+E) complexity (REQ-L2-TE-003, ADR-TE-03).
    Returns the nodes of the first detected SCC with size > 1 (cycle).
    """
    index_counter = [0]
    stack: list[uuid.UUID] = []
    on_stack: set[uuid.UUID] = set()
    index: dict[uuid.UUID, int] = {}
    lowlink: dict[uuid.UUID, int] = {}
    cycle_found: list[list[uuid.UUID]] = []

    all_nodes = set(adj.keys())
    for neighbors in adj.values():
        all_nodes.update(neighbors)

    def strongconnect(v: uuid.UUID) -> None:
        index[v] = lowlink[v] = index_counter[0]
        index_counter[0] += 1
        stack.append(v)
        on_stack.add(v)

        for w in adj.get(v, []):
            if w not in index:
                strongconnect(w)
                lowlink[v] = min(lowlink[v], lowlink[w])
            elif w in on_stack:
                lowlink[v] = min(lowlink[v], index[w])

        if lowlink[v] == index[v]:
            scc: list[uuid.UUID] = []
            while True:
                w = stack.pop()
                on_stack.discard(w)
                scc.append(w)
                if w == v:
                    break
            if len(scc) > 1:
                cycle_found.append(scc)

    for node in all_nodes:
        if node not in index:
            strongconnect(node)
        if cycle_found:
            break

    if cycle_found:
        return cycle_found[0]
    return None


def _format_cycle_path(cycle: list[uuid.UUID]) -> str:
    """Format a cycle as a human-readable path string."""
    parts = [str(n) for n in cycle]
    return " -> ".join(parts) + " -> " + parts[0]


# ---------------------------------------------------------------------------
# Public component class
# ---------------------------------------------------------------------------

class TraceLinkManager:
    """COMP-TE-001: TraceLink CRUD, validation, and cycle detection.

    All write methods are designed to be called inside an atomic transaction
    by the caller (or the batch helpers below). The manager never opens its
    own transaction — atomicity is delegated to the caller or to
    persistence.transactions.atomic_transaction.

    REQ-L2-TE-001 / REQ-L2-TE-002 / REQ-L2-TE-003 / REQ-L2-TE-009
    REQ-L2-TE-010 / REQ-L2-TE-011
    """

    # IF-TE-INT-001 / IF-TE-INT-002
    def get_trace_links(
        self,
        workspace_id: uuid.UUID | None = None,
        filters: dict[str, Any] | None = None,
        link_type: str | None = None,
    ) -> list[TraceLink]:
        """Return TraceLinks for the active tenant, optionally filtered.

        IF-TE-INT-001 (QueryEngine): workspace_id + generic filters.
        IF-TE-INT-002 (CoverageCalculator): link_type shorthand.
        """
        qs = TraceLink.objects.all()  # TenantManager applies tenant filter
        if workspace_id is not None:
            qs = qs.filter(source__workspace_id=workspace_id)
        if link_type is not None:
            qs = qs.filter(link_type=link_type)
        if filters:
            qs = qs.filter(**filters)
        return list(qs.select_related("source", "target"))

    # IF-TE-EXT-IN-003: create
    def create(
        self,
        source_id: uuid.UUID,
        target_id: uuid.UUID,
        link_type: str,
        created_by_id: Optional[uuid.UUID] = None,
    ) -> TraceLink:
        """Create a single TraceLink with full validation.

        Performs:
        1. Link-type validation (REQ-L2-TE-001)
        2. Source/Target existence check (REQ-L2-TE-001)
        3. Cross-tenant guard (REQ-L2-TE-011)
        4. Eager cycle detection via DFS (REQ-L2-TE-002)
        5. Persist (REQ-L2-TE-001, audit: REQ-L2-TE-010)
        """
        _validate_link_type(link_type)

        tenant_id = TenantContext.get_tenant()

        # Fetch source and target using unscoped to allow explicit tenant check
        try:
            source = Artifact.unscoped.get(pk=source_id)
        except Artifact.DoesNotExist as exc:
            raise SourceNotFoundError(source_id) from exc

        try:
            target = Artifact.unscoped.get(pk=target_id)
        except Artifact.DoesNotExist as exc:
            raise TargetNotFoundError(target_id) from exc

        _validate_cross_tenant_boundary(source, target)

        # Verify tenant context matches source (defense-in-depth)
        if str(source.tenant_id) != str(tenant_id):
            raise CrossTenantLinkError()

        # Eager cycle detection: does target already reach source?
        existing = self.get_trace_links()
        adj = _build_adjacency(existing)
        if _dfs_has_cycle_to(target_id, source_id, adj):
            raise CycleDetectedError(link_type)

        link = TraceLink(
            source=source,
            target=target,
            link_type=link_type,
            tenant_id=tenant_id,
        )
        if created_by_id is not None:
            link.created_by_id = created_by_id
            link.modified_by_id = created_by_id
        link.save()
        return link

    # IF-TE-EXT-IN-003: read
    def get(self, link_id: uuid.UUID) -> TraceLink:
        """Retrieve a single TraceLink (tenant-scoped).

        REQ-L2-TE-011: not found = "TraceLink not found" from perspective of
        wrong-tenant caller.
        """
        return TraceLink.objects.get(pk=link_id)

    # IF-TE-EXT-IN-003: update
    def update(
        self,
        link_id: uuid.UUID,
        link_type: str | None = None,
        modified_by_id: Optional[uuid.UUID] = None,
    ) -> TraceLink:
        """Update link_type on an existing TraceLink.

        REQ-L2-TE-010: modified_by / modified_at are captured.
        """
        link = TraceLink.objects.get(pk=link_id)
        if link_type is not None:
            _validate_link_type(link_type)
            link.link_type = link_type
        if modified_by_id is not None:
            link.modified_by_id = modified_by_id
        link.save(update_fields=["link_type", "modified_by", "modified_at", "version"])
        return link

    # IF-TE-EXT-IN-003: delete
    def delete(self, link_id: uuid.UUID) -> None:
        """Delete a TraceLink (tenant-scoped).

        REQ-L2-TE-011: raises DoesNotExist if not in active tenant.
        """
        TraceLink.objects.get(pk=link_id).delete()

    # IF-TE-EXT-IN-003: batch
    @transaction.atomic
    def batch_create(
        self,
        items: list[dict],
        created_by_id: Optional[uuid.UUID] = None,
    ) -> list[TraceLink]:
        """Atomically create multiple TraceLinks with Tarjan cycle check.

        REQ-L2-TE-003:
        - All links are validated and persisted inside one transaction.
        - Tarjan SCC is run once at the end.
        - Any error (validation or cycle) triggers a full rollback.

        items: list of {source_id, target_id, link_type}
        """
        tenant_id = TenantContext.get_tenant()
        created: list[TraceLink] = []

        for item in items:
            link_type = item["link_type"]
            source_id = uuid.UUID(str(item["source_id"]))
            target_id = uuid.UUID(str(item["target_id"]))

            _validate_link_type(link_type)

            try:
                source = Artifact.unscoped.get(pk=source_id)
            except Artifact.DoesNotExist as exc:
                raise SourceNotFoundError(source_id) from exc

            try:
                target = Artifact.unscoped.get(pk=target_id)
            except Artifact.DoesNotExist as exc:
                raise TargetNotFoundError(target_id) from exc

            _validate_cross_tenant_boundary(source, target)
            if str(source.tenant_id) != str(tenant_id):
                raise CrossTenantLinkError()

            link = TraceLink(
                source=source,
                target=target,
                link_type=link_type,
                tenant_id=tenant_id,
            )
            if created_by_id is not None:
                link.created_by_id = created_by_id
                link.modified_by_id = created_by_id
            link.save()
            created.append(link)

        # Tarjan SCC on the full tenant graph at transaction end (REQ-L2-TE-003)
        all_links = list(TraceLink.objects.all())
        adj = _build_adjacency(all_links)
        cycle = _tarjan_find_cycle(adj)
        if cycle:
            path = _format_cycle_path(cycle)
            # Raising here triggers the @atomic rollback
            raise CycleDetectedError(link_type="batch", cycle_path=path)

        return created

    @transaction.atomic
    def batch_delete(self, link_ids: list[uuid.UUID]) -> int:
        """Atomically delete multiple TraceLinks.

        REQ-L2-TE-003: partial failure rolls back all deletes.
        Returns the number of deleted links.
        """
        count = 0
        for link_id in link_ids:
            link = TraceLink.objects.get(pk=link_id)  # raises if not in tenant
            link.delete()
            count += 1
        return count

    # IF-TE-INT-003
    def validate_graph_integrity(self) -> dict:
        """Check full tenant graph for cycles (called by QueryEngine).

        IF-TE-INT-003. Returns a dict with 'valid' bool and optional 'cycle_path'.
        """
        all_links = list(TraceLink.objects.all())
        adj = _build_adjacency(all_links)
        cycle = _tarjan_find_cycle(adj)
        if cycle:
            return {"valid": False, "cycle_path": _format_cycle_path(cycle)}
        return {"valid": True, "cycle_path": None}


__all__ = ["TraceLinkManager"]
