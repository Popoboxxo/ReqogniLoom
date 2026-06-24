"""
ARCH-L1-006 BaselineService — COMP-BL-003 BaselineStore.

leaf_id: COMP-BL-003
req_id:  REQ-L2-BL-002, REQ-L2-BL-005, REQ-L2-BL-006, REQ-L2-BL-007

Responsibilities:
  - Append-Only persistence of BaselineSnapshot + BaselineDeltaIndexEntry
  - Immutability enforcement at application layer (DB triggers are the second guard)
  - Atomic snapshot creation (all entries or nothing)
  - Retrieval and Listing with workspace-level tenant isolation
  - Versions-Lookup for VersionReconstructor (IF-BL-INT-004)

Internal Interfaces:
  IF-BL-INT-001: persist_delta_index(delta_index, metadata) -> baseline_id
  IF-BL-INT-002: load_delta_index(baseline_id) -> list[tuple[entity_id, version, type]]
  IF-BL-INT-004: lookup_item_version(baseline_id, item_id) -> version

Architecture:
  docs/se/L1/Gesamtsystem/L2/BaselineServiceSystem/Components/
  COMP-BL-003_BaselineStore/L3_COMP-BL-003_BaselineStore_Architecture.md
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from baseline.exceptions import (
    BaselineImmutableError,
    BaselineNotFoundError,
    DuplicateBaselineNameError,
    ItemNotInBaselineError,
)
from baseline.models import BaselineDeltaIndexEntry, BaselineSnapshot
from baseline.types import (
    BaselineDetail,
    BaselineMetadata,
    BaselineSummary,
    DeltaIndexTuple,
)


class BaselineStore:
    """COMP-BL-003: Append-Only Baseline persistence and retrieval.

    All write operations are guarded against UPDATE/DELETE at the application
    layer.  DB-level triggers (migration 0001_initial) provide the second layer
    of immutability enforcement (ADR-L3-BL003-01).

    Thread-safety: stateless; safe to share across requests.
    """

    # ------------------------------------------------------------------
    # IF-BL-INT-001: persist_delta_index
    # ------------------------------------------------------------------

    def persist_delta_index(
        self,
        delta_index: list[DeltaIndexTuple],
        metadata: BaselineMetadata,
        tenant_id: uuid.UUID,
    ) -> uuid.UUID:
        """Persist a complete Baseline atomically.

        Creates BaselineSnapshot + all BaselineDeltaIndexEntry rows inside a
        single transaction.  Either all rows are committed or nothing is written
        (REQ-L2-BL-007, ADR-L3-BL003-02).

        Args:
            delta_index: Ordered list of (item_id, version, entity_type) tuples.
            metadata: Baseline header fields (name, scope, workspace_id, …).
            tenant_id: Active tenant primary key for row-level isolation.

        Returns:
            The UUID of the newly created BaselineSnapshot.

        Raises:
            DuplicateBaselineNameError: If name already exists in workspace.
        """
        from django.db import transaction

        created_at = metadata.created_at or datetime.now(tz=timezone.utc)

        with transaction.atomic():
            # Check for duplicate name before INSERT to produce a clean error
            # message.  The UNIQUE constraint will catch concurrent races.
            if BaselineSnapshot.unscoped.filter(
                workspace_id=metadata.workspace_id,
                name=metadata.name,
                tenant_id=tenant_id,
            ).exists():
                raise DuplicateBaselineNameError()

            snapshot = BaselineSnapshot(
                workspace_id=metadata.workspace_id,
                scope=metadata.scope,
                name=metadata.name,
                description=metadata.description or "",
                created_by_ref=metadata.created_by,
                tenant_id=tenant_id,
                # Override auto_now_add so callers can set a deterministic ts
                # (useful for tests and idempotent replays).
                created_at=created_at,
            )
            # Bypass auto_now_add for created_at by using save with update_fields=None
            snapshot.save()

            # Bulk-insert all delta entries in one SQL statement (performance)
            entries = [
                BaselineDeltaIndexEntry(
                    baseline=snapshot,
                    item_id=t.item_id,
                    version=t.version,
                    entity_type=t.entity_type,
                )
                for t in delta_index
            ]
            BaselineDeltaIndexEntry.objects.bulk_create(entries)

        return snapshot.id

    # ------------------------------------------------------------------
    # IF-BL-INT-002: load_delta_index
    # ------------------------------------------------------------------

    def load_delta_index(
        self, baseline_id: uuid.UUID
    ) -> list[tuple[str, int, str]]:
        """Load all delta entries for a baseline as (item_id, version, type) tuples.

        Used by DiffEngine (IF-BL-INT-002).

        Args:
            baseline_id: UUID of the target BaselineSnapshot.

        Returns:
            List of (item_id, version, entity_type) tuples.

        Raises:
            BaselineNotFoundError: If baseline_id does not exist.
        """
        if not BaselineSnapshot.unscoped.filter(id=baseline_id).exists():
            raise BaselineNotFoundError()

        entries = BaselineDeltaIndexEntry.objects.filter(
            baseline_id=baseline_id
        ).values_list("item_id", "version", "entity_type")
        return list(entries)

    # ------------------------------------------------------------------
    # IF-BL-INT-004: lookup_item_version (called by VersionReconstructor)
    # ------------------------------------------------------------------

    def lookup_item_version(
        self, baseline_id: uuid.UUID, item_id: str
    ) -> int:
        """Return the version number of item_id as recorded in the baseline.

        IF-BL-INT-004 (VersionReconstructor → BaselineStore).

        Args:
            baseline_id: UUID of the baseline to query.
            item_id: String identifier of the item.

        Returns:
            Recorded version integer.

        Raises:
            BaselineNotFoundError: If baseline_id does not exist.
            ItemNotInBaselineError: If item_id is not part of this baseline.
        """
        if not BaselineSnapshot.unscoped.filter(id=baseline_id).exists():
            raise BaselineNotFoundError()

        try:
            entry = BaselineDeltaIndexEntry.objects.get(
                baseline_id=baseline_id, item_id=item_id
            )
            return entry.version
        except BaselineDeltaIndexEntry.DoesNotExist:
            raise ItemNotInBaselineError()

    # ------------------------------------------------------------------
    # IF-BL-EXT-IN-001: get / list
    # ------------------------------------------------------------------

    def get(self, baseline_id: uuid.UUID) -> BaselineDetail:
        """Return the full Baseline record including all delta entries.

        REQ-L2-BL-006: get(baseline_id) → full snapshot.

        Args:
            baseline_id: UUID of the target baseline.

        Returns:
            BaselineDetail with all DeltaIndexTuple entries populated.

        Raises:
            BaselineNotFoundError: If baseline_id does not exist.
        """
        try:
            snapshot = BaselineSnapshot.unscoped.get(id=baseline_id)
        except BaselineSnapshot.DoesNotExist:
            raise BaselineNotFoundError()

        raw_entries = BaselineDeltaIndexEntry.objects.filter(
            baseline_id=baseline_id
        ).values_list("item_id", "version", "entity_type")

        entries = [
            DeltaIndexTuple(item_id=r[0], version=r[1], entity_type=r[2])
            for r in raw_entries
        ]

        return BaselineDetail(
            baseline_id=snapshot.id,
            workspace_id=snapshot.workspace_id,
            scope=snapshot.scope,
            name=snapshot.name,
            description=snapshot.description,
            created_at=snapshot.created_at,
            created_by=snapshot.created_by_ref,
            entries=entries,
        )

    def list(
        self,
        workspace_id: uuid.UUID,
        scope: Optional[str] = None,
        tenant_id: Optional[uuid.UUID] = None,
    ) -> list[BaselineSummary]:
        """Return Baseline summaries for a workspace, sorted by created_at DESC.

        REQ-L2-BL-006: list(workspace_id) → all baselines sorted DESC.
        ADR-L3-BL003-03: No delta entries in listing (lazy loading).

        Args:
            workspace_id: Workspace to filter by.
            scope: Optional scope filter ("document" | "project" | "global").
            tenant_id: Optional tenant filter (uses unscoped manager).

        Returns:
            List of BaselineSummary ordered by created_at descending.
        """
        qs = BaselineSnapshot.unscoped.filter(workspace_id=workspace_id)
        if tenant_id is not None:
            qs = qs.filter(tenant_id=tenant_id)
        if scope is not None:
            qs = qs.filter(scope=scope)
        qs = qs.order_by("-created_at")

        return [
            BaselineSummary(
                baseline_id=s.id,
                workspace_id=s.workspace_id,
                scope=s.scope,
                name=s.name,
                description=s.description,
                created_at=s.created_at,
                created_by=s.created_by_ref,
            )
            for s in qs
        ]

    # ------------------------------------------------------------------
    # Immutability guard — application layer
    # ------------------------------------------------------------------

    def update(self, *args, **kwargs) -> None:
        """Reject all update attempts.

        REQ-L2-BL-002: Baselines are immutable after creation.
        """
        raise BaselineImmutableError()

    def delete(self, *args, **kwargs) -> None:
        """Reject all delete attempts.

        REQ-L2-BL-002: Baselines are immutable after creation.
        """
        raise BaselineImmutableError()


# Module-level singleton — lazily initialized (BaselineStore is stateless)
_store: "BaselineStore | None" = None


def get_store() -> "BaselineStore":
    """Return the module-level BaselineStore singleton (lazy init)."""
    global _store
    if _store is None:
        _store = BaselineStore()
    return _store


__all__ = [
    "BaselineStore",
    "get_store",
]
