"""
ARCH-L1-006 BaselineService — COMP-BL-004 VersionReconstructor.

leaf_id: COMP-BL-004
req_id:  REQ-L2-BL-009, REQ-L3-BL004-001, REQ-L3-BL004-002, REQ-L3-BL004-003

Responsibilities:
  - Reconstruct the historical payload (title, description, content) of an item
    at the version recorded in a given Baseline.
  - Uses AuditLogEntry.payload from persistence.models as the version history source.
  - Optionally caches reconstructed payloads via LRU to avoid repeated DB queries.

Internal Interfaces consumed:
  IF-BL-INT-004: BaselineStore.lookup_item_version(baseline_id, item_id) -> version

External Interfaces consumed:
  IF-BL-EXT-IN-004: AuditLogEntry (Django ORM) — payload at specific version

Architecture:
  docs/se/L1/Gesamtsystem/L2/BaselineServiceSystem/Components/
  COMP-BL-004_VersionReconstructor/L3_COMP-BL-004_VersionReconstructor_Architecture.md

Version history note:
  The persistence layer stores AuditLogEntry rows with a ``payload`` JSONField
  that contains entity data at the time of write. VersionReconstructor queries
  AuditLogEntry WHERE object_id = <item_id> AND payload->>version = <version>,
  returning title/description/content from the payload dict.

  If the live Requirement/Artifact matches the requested version (no changes
  since baseline), the live record is returned directly as an optimization.
"""
from __future__ import annotations

import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Optional

from baseline.exceptions import ItemNotInBaselineError, VersionNotFoundError
from baseline.types import ItemPayload

# LRU cache default size (ADR-L3-BL004-01)
LRU_CACHE_MAX_SIZE = 1000


class LruPayloadCache:
    """Simple LRU cache keyed on (item_id, version).

    Evicts the least-recently-used entry when max_size is exceeded.
    Thread-safety: not required — Django runs single-threaded per request
    in WSGI mode (one cache instance per singleton VersionReconstructor).

    REQ-L3-BL004-003.
    """

    def __init__(self, max_size: int = LRU_CACHE_MAX_SIZE) -> None:
        self._max_size = max_size
        # OrderedDict maintains insertion order; we move accessed items to end.
        self._cache: OrderedDict[tuple[str, int], ItemPayload] = OrderedDict()

    def get(self, item_id: str, version: int) -> Optional[ItemPayload]:
        """Return cached payload or None on miss."""
        key = (item_id, version)
        if key not in self._cache:
            return None
        # Move to most-recently-used end
        self._cache.move_to_end(key)
        return self._cache[key]

    def put(self, payload: ItemPayload) -> None:
        """Insert payload into cache, evicting LRU entry if needed."""
        key = (payload.item_id, payload.version)
        if key in self._cache:
            self._cache.move_to_end(key)
            return
        self._cache[key] = payload
        if len(self._cache) > self._max_size:
            # Evict LRU (first item)
            self._cache.popitem(last=False)


class VersionReconstructor:
    """COMP-BL-004: Reconstruct historical item payloads from audit history.

    Sequence for get_item_at_baseline(baseline_id, item_id):
      1. Lookup version from BaselineStore (IF-BL-INT-004).
      2. Check LRU cache.
      3. Try live entity (Requirement/ArchitectureElement) if versions match.
      4. Fall back to AuditLogEntry payload query.
      5. Cache and return ItemPayload.

    REQ-L2-BL-009, ADR-L3-BL004-01, ADR-L3-BL004-02.
    """

    def __init__(
        self,
        store=None,
        cache: Optional[LruPayloadCache] = None,
    ) -> None:
        if store is None:
            from baseline.store import get_store
            store = get_store()
        self._store = store
        self._cache = cache if cache is not None else LruPayloadCache()

    def get_item_at_baseline(
        self, baseline_id: uuid.UUID, item_id: str
    ) -> ItemPayload:
        """Return the item payload as it was at baseline creation time.

        IF-BL-EXT-IN-001 (called from ApplicationService / services facade).

        Args:
            baseline_id: UUID of the target baseline.
            item_id: String UUID of the item (Artifact/Requirement).

        Returns:
            ItemPayload with title, description, content at the recorded version.

        Raises:
            BaselineNotFoundError: (from BaselineStore) baseline does not exist.
            ItemNotInBaselineError: item_id is not part of this baseline.
            VersionNotFoundError: version not found in the audit history.
        """
        # Step 1: Get recorded version from BaselineStore (IF-BL-INT-004)
        # Propagates ItemNotInBaselineError / BaselineNotFoundError directly.
        version = self._store.lookup_item_version(baseline_id, item_id)

        # Step 2: LRU cache check (REQ-L3-BL004-003)
        cached = self._cache.get(item_id, version)
        if cached is not None:
            return cached

        # Step 3: Try live entity first (cheap; avoids audit log query if unchanged)
        payload = self._try_live_entity(item_id, version)

        # Step 4: Fall back to AuditLogEntry if live entity version has moved on
        if payload is None:
            payload = self._load_from_audit_log(item_id, version)

        if payload is None:
            raise VersionNotFoundError()

        # Step 5: Cache and return
        self._cache.put(payload)
        return payload

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _try_live_entity(
        self, item_id: str, version: int
    ) -> Optional[ItemPayload]:
        """Return live entity payload if its current version matches.

        Avoids an audit log lookup for recently-created baselines where the
        entity has not been modified since the baseline was taken.

        Returns None if the live entity is not found or its version differs.
        """
        try:
            item_uuid = uuid.UUID(item_id)
        except (ValueError, AttributeError):
            return None

        # Try Requirement first (most common entity type)
        try:
            from persistence.models import Requirement

            req = Requirement.unscoped.filter(
                artifact_id=item_uuid
            ).select_related("artifact").first()
            if req is not None and req.artifact.version == version:
                return ItemPayload(
                    item_id=item_id,
                    version=version,
                    title=req.title,
                    description=req.description or None,
                    content=None,
                    reconstructed_at=datetime.now(tz=timezone.utc),
                )
        except Exception:
            pass

        # Try ArchitectureElement
        try:
            from persistence.models import ArchitectureElement

            ae = ArchitectureElement.unscoped.filter(
                artifact_id=item_uuid
            ).select_related("artifact").first()
            if ae is not None and ae.artifact.version == version:
                return ItemPayload(
                    item_id=item_id,
                    version=version,
                    title=ae.title,
                    description=ae.description or None,
                    content=None,
                    reconstructed_at=datetime.now(tz=timezone.utc),
                )
        except Exception:
            pass

        # Try bare Artifact
        try:
            from persistence.models import Artifact

            art = Artifact.unscoped.filter(id=item_uuid).first()
            if art is not None and art.version == version:
                return ItemPayload(
                    item_id=item_id,
                    version=version,
                    title=str(art),
                    description=None,
                    content=None,
                    reconstructed_at=datetime.now(tz=timezone.utc),
                )
        except Exception:
            pass

        return None

    def _load_from_audit_log(
        self, item_id: str, version: int
    ) -> Optional[ItemPayload]:
        """Query AuditLogEntry for the entity payload at the specified version.

        The AuditLogEntry.payload JSONField is expected to contain the entity
        snapshot at the time of the write operation.  A matching entry is one
        where object_id = item_id AND payload['version'] == version.

        Returns None if no matching entry is found (caller raises VersionNotFoundError).

        IF-BL-EXT-IN-004 (AuditLog/VersionHistory access).
        """
        try:
            item_uuid = uuid.UUID(item_id)
        except (ValueError, AttributeError):
            return None

        try:
            from persistence.models import AuditLogEntry

            # Query audit log entries for this entity, ordered by id DESC
            # (most recent first) to find the entry whose payload.version matches.
            entries = AuditLogEntry.unscoped.filter(
                object_id=item_uuid
            ).order_by("-id")

            for entry in entries:
                payload_data = entry.payload or {}
                entry_version = payload_data.get("version")

                if entry_version == version:
                    title = (
                        payload_data.get("title")
                        or payload_data.get("name")
                        or f"item:{item_id}"
                    )
                    return ItemPayload(
                        item_id=item_id,
                        version=version,
                        title=str(title),
                        description=payload_data.get("description"),
                        content=payload_data.get("content"),
                        reconstructed_at=datetime.now(tz=timezone.utc),
                    )
        except Exception:
            pass

        return None


# Module-level singleton — lazily initialized to avoid Django import at module load
_reconstructor: "VersionReconstructor | None" = None


def get_reconstructor() -> "VersionReconstructor":
    """Return the module-level VersionReconstructor singleton (lazy init)."""
    global _reconstructor
    if _reconstructor is None:
        _reconstructor = VersionReconstructor()
    return _reconstructor


__all__ = [
    "LruPayloadCache",
    "VersionReconstructor",
    "get_reconstructor",
]
