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
from baseline.models import BaselineSnapshot
from baseline.types import ChangedItem, DiffResult


class DiffEngine:
    """COMP-BL-002: O(n) set-based Baseline comparison.

    Algorithm (ADR-L3-BL002-01):
      1. Validate scope compatibility (fail-fast, ADR-L3-BL002-02).
      2. Load both delta indices from BaselineStore (IF-BL-INT-002) and both
         captured-state maps (REQ-L2-BL-012).
      3. Build dict-backed index sets: {item_id: version} and {item_id: state}.
      4. Single-pass set union iteration to classify added/removed/changed —
         membership decides added/removed, *captured field values* decide
         changed.

    Complexity: O(n) where n = |index_a ∪ index_b|.
    Memory: O(n) — both indices held in memory simultaneously.

    Why values and not a version counter (issue #398)
    -------------------------------------------------
    This engine used to classify an item as changed iff its delta-index
    ``version`` differed between the two baselines. That number is
    ``Artifact.version`` — the shadow/base-table counter, which does *not*
    increment when a subtype row (Requirement, ArchitectureElement, …) is
    edited. Editing a Requirement's title bumps ``Requirement.version`` and
    leaves ``Artifact.version`` at 1 in both snapshots, so the engine reported
    "nothing changed" for a genuinely changed artifact — configuration
    management's one core question answered with a silent lie.

    The fix is deliberately *not* "read the other version column". Any counter
    can be wrong for reasons beyond picking the wrong table: an out-of-band
    data fix, a migration backfill, or a future subtype that never wires
    version-bumping at all. The baseline already stores the full field state as
    JSONB, so the diff compares those values directly. That makes the whole
    "trusted the wrong/absent counter" bug class structurally impossible rather
    than fixing this one instance of it.

    Legacy entries (``state IS NULL``, created before REQ-L2-BL-012) have no
    values to compare and keep the old version-number classification.
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
        tenant_id: uuid.UUID,
    ) -> DiffResult:
        """Compute the diff between two Baselines.

        IF-BL-EXT-IN-001 (called from ApplicationService / service facade).

        Args:
            baseline_a_id: UUID of the reference baseline (older / from).
            baseline_b_id: UUID of the target baseline (newer / to).
            tenant_id: Active tenant UUID (row-level isolation) — either
                baseline belonging to a different tenant is treated as not
                found.

        Returns:
            DiffResult with added, removed, and changed lists.

        Raises:
            BaselineNotFoundError: If either baseline_id does not exist for
                this tenant.
            ScopeMismatchError: If the two baselines have different scopes.
        """
        # Step 1: Scope validation before index loading (ADR-L3-BL002-02)
        self._validate_scopes(baseline_a_id, baseline_b_id, tenant_id)

        # Step 2: Load delta indices via IF-BL-INT-002
        raw_a = self._store.load_delta_index(baseline_a_id, tenant_id)
        raw_b = self._store.load_delta_index(baseline_b_id, tenant_id)

        # Step 3: Build {item_id: version} dicts (O(n) construction)
        index_a: dict[str, int] = {row[0]: row[1] for row in raw_a}
        index_b: dict[str, int] = {row[0]: row[1] for row in raw_b}

        # Step 3b: Load the captured full states for BOTH baselines up front
        # (one batched query each). They are the authority for "changed"
        # (issue #398), so they must be available for every common item — not
        # only for items a version counter already flagged.
        states_a = self._load_states(baseline_a_id, tenant_id)
        states_b = self._load_states(baseline_b_id, tenant_id)

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
                continue
            if in_a and not in_b:
                removed.append(item_id)
                continue

            # Present in both — classify by captured values (REQ-L2-BL-012).
            state_a = states_a.get(item_id)
            state_b = states_b.get(item_id)
            field_changes = _field_diff(state_a, state_b)
            if field_changes is None:
                # Legacy entry without a snapshot on at least one side: the
                # only signal left is the recorded version number.
                if index_a[item_id] == index_b[item_id]:
                    continue
            elif not field_changes:
                # Both sides snapshotted and every comparable field is equal.
                continue

            changed.append(
                ChangedItem(
                    id=item_id,
                    old_version=_effective_version(state_a, index_a[item_id]),
                    new_version=_effective_version(state_b, index_b[item_id]),
                    field_changes=field_changes,
                )
            )

        # Sort for deterministic output
        added.sort()
        removed.sort()
        changed.sort(key=lambda c: c.id)

        return DiffResult(added=added, removed=removed, changed=changed)

    def _load_states(
        self, baseline_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> dict[str, Optional[dict]]:
        """Load all stored states of a baseline, tolerating older stores.

        Falls back to an empty mapping if the store predates ``load_states``
        (keeps mocked/stub stores in tests working) — every item then degrades
        to the legacy version-number classification.
        """
        loader = getattr(self._store, "load_states", None)
        if loader is None:
            return {}
        try:
            states = loader(baseline_id, tenant_id)
        except Exception:  # pragma: no cover - defensive
            return {}
        return states if isinstance(states, dict) else {}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _validate_scopes(
        self,
        baseline_a_id: uuid.UUID,
        baseline_b_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> None:
        """Assert both baselines exist (for this tenant) and share the same scope.

        Args:
            baseline_a_id: Reference baseline UUID.
            baseline_b_id: Target baseline UUID.
            tenant_id: Active tenant UUID (row-level isolation — security fix:
                this previously used ``.unscoped.get(id=...)`` with no tenant
                filter, letting any tenant probe/read another tenant's
                baseline scope by UUID and use it to pass the scope-match gate).

        Raises:
            BaselineNotFoundError: If either baseline does not exist for this tenant.
            ScopeMismatchError: If scopes differ.
        """
        # BaselineSnapshot is imported at module level to allow test mocking
        try:
            a = BaselineSnapshot.unscoped.only("scope").get(
                id=baseline_a_id, tenant_id=tenant_id
            )
        except BaselineSnapshot.DoesNotExist:
            raise BaselineNotFoundError()

        try:
            b = BaselineSnapshot.unscoped.only("scope").get(
                id=baseline_b_id, tenant_id=tenant_id
            )
        except BaselineSnapshot.DoesNotExist:
            raise BaselineNotFoundError()

        if a.scope != b.scope:
            raise ScopeMismatchError()


def _field_diff(
    state_a: Optional[dict],
    state_b: Optional[dict],
) -> Optional[dict]:
    """Return a per-field diff of two captured states (REQ-L2-BL-012).

    Only fields present in *both* snapshots are compared. The captured key set
    is decided by the capture schema in :mod:`baseline.state_capture`, never by
    the data — an entity always emits all of its keys, with ``None``/``""`` for
    empty values. A key that exists on one side only therefore means the
    capture schema was extended (or narrowed) between the two baseline dates,
    not that the entity changed. Comparing the union instead would make every
    pre-existing baseline report every artifact as "changed" the moment a new
    field is added to the capture, which is exactly the kind of false alarm
    that erodes trust in the drift signal (issue #398). A field that was never
    snapshotted simply cannot be diffed.

    Args:
        state_a: State snapshot from baseline A (older). None for legacy entries.
        state_b: State snapshot from baseline B (newer). None for legacy entries.

    Returns:
        ``{field: {"old": <a>, "new": <b>}}`` for every comparable field that
        differs (empty dict when all are equal), or ``None`` when either side
        lacks a snapshot — the caller then falls back to the version-number
        delta.
    """
    if not isinstance(state_a, dict) or not isinstance(state_b, dict):
        return None

    changes: dict[str, dict] = {}
    for key in state_a.keys() & state_b.keys():
        old_val = state_a[key]
        new_val = state_b[key]
        if old_val != new_val:
            changes[key] = {"old": old_val, "new": new_val}
    return changes


def _effective_version(state: Optional[dict], index_version: int) -> int:
    """Return the version to report for a snapshotted item.

    The delta index stores ``Artifact.version`` — the shadow/base-table counter
    that does not move when a subtype row is edited (issue #398). The captured
    state carries the *entity's own* version, which is the number a user
    recognises from the artifact page. Prefer it whenever it was snapshotted
    and is a plain integer; fall back to the index value otherwise.
    """
    if isinstance(state, dict):
        captured = state.get("version")
        # bool is an int subclass — exclude it explicitly.
        if isinstance(captured, int) and not isinstance(captured, bool):
            return captured
    return index_version


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
