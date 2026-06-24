"""
ARCH-L1-006 BaselineService — COMP-BL-002 DiffEngine.

leaf_id: COMP-BL-002
req_id:  REQ-L2-BL-003, REQ-L3-BL002-001, REQ-L3-BL002-002, REQ-L3-BL002-003

Responsibilities:
  - Compare two Baselines of the same scope (added / removed / changed)
  - Validate scope compatibility BEFORE loading indices (ADR-L3-BL002-02)
  - O(n) set-based comparison for ≤ 10k items per baseline (ADR-L3-BL002-01)

Internal Interfaces consumed:
  IF-BL-INT-002: BaselineStore.load_delta_index()

Architecture:
  docs/se/L1/Gesamtsystem/L2/BaselineServiceSystem/Components/
  COMP-BL-002_DiffEngine/L3_COMP-BL-002_DiffEngine_Architecture.md
"""
from __future__ import annotations

import uuid
from typing import Optional

from baseline.exceptions import BaselineNotFoundError, ScopeMismatchError
from baseline.types import ChangedItem, DiffResult


class DiffEngine:
    """COMP-BL-002: O(n) set-based Baseline comparison.

    Algorithm (ADR-L3-BL002-01):
      1. Validate scope compatibility (fail-fast, ADR-L3-BL002-02).
      2. Load both delta indices from BaselineStore (IF-BL-INT-002).
      3. Build dict-backed index sets: {item_id: version}.
      4. Single-pass set union iteration to classify added/removed/changed.

    Complexity: O(n) where n = |index_a ∪ index_b|.
    Memory: O(n) — both indices held in memory simultaneously.
    """

    def __init__(self, store=None) -> None:
        if store is None:
            from baseline.store import get_store
            store = get_store()
        self._store = store

    def diff(
        self,
        baseline_a_id: uuid.UUID,
        baseline_b_id: uuid.UUID,
    ) -> DiffResult:
        """Compute the diff between two Baselines.

        IF-BL-EXT-IN-001 (called from ApplicationService / service facade).

        Args:
            baseline_a_id: UUID of the reference baseline (older / from).
            baseline_b_id: UUID of the target baseline (newer / to).

        Returns:
            DiffResult with added, removed, and changed lists.

        Raises:
            BaselineNotFoundError: If either baseline_id does not exist.
            ScopeMismatchError: If the two baselines have different scopes.
        """
        # Step 1: Scope validation before index loading (ADR-L3-BL002-02)
        self._validate_scopes(baseline_a_id, baseline_b_id)

        # Step 2: Load delta indices via IF-BL-INT-002
        raw_a = self._store.load_delta_index(baseline_a_id)
        raw_b = self._store.load_delta_index(baseline_b_id)

        # Step 3: Build {item_id: version} dicts (O(n) construction)
        index_a: dict[str, int] = {row[0]: row[1] for row in raw_a}
        index_b: dict[str, int] = {row[0]: row[1] for row in raw_b}

        # Step 4: Set-union iteration (O(n))
        added: list[str] = []
        removed: list[str] = []
        changed: list[ChangedItem] = []

        all_ids = index_a.keys() | index_b.keys()
        for item_id in all_ids:
            in_a = item_id in index_a
            in_b = item_id in index_b
            if in_b and not in_a:
                added.append(item_id)
            elif in_a and not in_b:
                removed.append(item_id)
            elif in_a and in_b and index_a[item_id] != index_b[item_id]:
                changed.append(
                    ChangedItem(
                        id=item_id,
                        old_version=index_a[item_id],
                        new_version=index_b[item_id],
                    )
                )
            # Same item, same version → not in any category (unchanged)

        # Sort for deterministic output
        added.sort()
        removed.sort()
        changed.sort(key=lambda c: c.id)

        return DiffResult(added=added, removed=removed, changed=changed)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _validate_scopes(
        self,
        baseline_a_id: uuid.UUID,
        baseline_b_id: uuid.UUID,
    ) -> None:
        """Assert both baselines exist and share the same scope.

        Raises:
            BaselineNotFoundError: If either baseline does not exist.
            ScopeMismatchError: If scopes differ.
        """
        from baseline.models import BaselineSnapshot

        try:
            a = BaselineSnapshot.unscoped.only("scope").get(id=baseline_a_id)
        except BaselineSnapshot.DoesNotExist:
            raise BaselineNotFoundError()

        try:
            b = BaselineSnapshot.unscoped.only("scope").get(id=baseline_b_id)
        except BaselineSnapshot.DoesNotExist:
            raise BaselineNotFoundError()

        if a.scope != b.scope:
            raise ScopeMismatchError()


# Module-level singleton — lazily initialized
_engine: "DiffEngine | None" = None


def get_engine() -> "DiffEngine":
    """Return the module-level DiffEngine singleton (lazy init)."""
    global _engine
    if _engine is None:
        _engine = DiffEngine()
    return _engine


__all__ = [
    "DiffEngine",
    "get_engine",
]
