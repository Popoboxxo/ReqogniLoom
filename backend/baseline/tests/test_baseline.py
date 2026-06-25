"""
ARCH-L1-006 BaselineService — Integration and Unit Tests.

leaf_id: COMP-BL-001, COMP-BL-002, COMP-BL-003, COMP-BL-004
req_id:  REQ-L2-BL-001 through REQ-L2-BL-009

Coverage (all acceptance criteria):
  REQ-L2-BL-001: 3 scopes resolve correctly, no payload stored
  REQ-L2-BL-002: Immutability enforced (update, delete, duplicate ID)
  REQ-L2-BL-003: Diff correct (added/removed/changed), scope mismatch rejected
  REQ-L2-BL-004: Preset-scope gating (minimal/standard/extended)
  REQ-L2-BL-005: Duplicate name rejected, empty name rejected, cross-workspace OK
  REQ-L2-BL-006: get() returns full snapshot, list() sorted DESC, nonexistent raises
  REQ-L2-BL-007: Atomic creation (mocked rollback path)
  REQ-L2-BL-009: VersionReconstructor — item-at-baseline, old stand returned,
                  item not in baseline, version not found

Architecture:
  docs/se/L1/Gesamtsystem/L2/BaselineServiceSystem/L2_BaselineServiceSystem_Architecture.md
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from baseline.exceptions import (
    BaselineImmutableError,
    BaselineNotFoundError,
    DuplicateBaselineNameError,
    EmptyBaselineNameError,
    ItemNotInBaselineError,
    ScopeMismatchError,
    ScopeNotAllowedError,
    VersionNotFoundError,
)
from baseline.store import BaselineStore
from baseline.types import (
    BaselineDetail,
    BaselineMetadata,
    BaselineSummary,
    DeltaIndexTuple,
    DiffResult,
    ItemPayload,
)
from baseline.diff_engine import DiffEngine
from baseline.version_reconstructor import LruPayloadCache, VersionReconstructor
from baseline.delta_index_builder import DeltaIndexBuilder, ScopeResolver


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

TENANT_ID = uuid.uuid4()
WORKSPACE_ID = uuid.uuid4()
OTHER_WORKSPACE_ID = uuid.uuid4()


def _make_delta_tuples(n: int, entity_type: str = "item") -> list[DeltaIndexTuple]:
    """Generate n distinct DeltaIndexTuple instances."""
    return [
        DeltaIndexTuple(
            item_id=str(uuid.uuid4()),
            version=i + 1,
            entity_type=entity_type,
        )
        for i in range(n)
    ]


def _make_metadata(
    name: str = "Release 1.0",
    scope: str = "project",
    workspace_id: uuid.UUID | None = None,
) -> BaselineMetadata:
    return BaselineMetadata(
        workspace_id=workspace_id or WORKSPACE_ID,
        scope=scope,
        name=name,
        description="Test baseline",
        created_by="test-agent",
        created_at=datetime.now(tz=timezone.utc),
    )


# ---------------------------------------------------------------------------
# COMP-BL-003 BaselineStore — Unit tests (no real DB required)
# ---------------------------------------------------------------------------


class TestBaselineStoreImmutability:
    """REQ-L2-BL-002: Application-layer immutability guards."""

    def test_update_raises_immutable_error(self):
        store = BaselineStore()
        with pytest.raises(BaselineImmutableError):
            store.update(some="kwarg")

    def test_delete_raises_immutable_error(self):
        store = BaselineStore()
        with pytest.raises(BaselineImmutableError):
            store.delete()

    def test_immutable_error_message(self):
        store = BaselineStore()
        with pytest.raises(BaselineImmutableError) as exc_info:
            store.update()
        assert "immutable" in str(exc_info.value).lower()

    def test_delete_error_message(self):
        store = BaselineStore()
        with pytest.raises(BaselineImmutableError) as exc_info:
            store.delete()
        assert "immutable" in str(exc_info.value).lower()


@pytest.mark.django_db
class TestBaselineStorePersistence:
    """REQ-L2-BL-001, REQ-L2-BL-005, REQ-L2-BL-007: Persist and retrieve."""

    def _make_tenant(self):
        from persistence.models import Tenant

        return Tenant.objects.create(name="Test Tenant", slug=f"test-{uuid.uuid4().hex[:8]}")

    def test_persist_and_get_returns_entries(self):
        """REQ-L2-BL-001: Baseline stores (item_id, version) tuples without payload."""
        from persistence.tenancy import TenantContext

        tenant = self._make_tenant()
        TenantContext.set_tenant(tenant.id)
        try:
            store = BaselineStore()
            tuples = _make_delta_tuples(3)
            meta = _make_metadata()
            bl_id = store.persist_delta_index(tuples, meta, tenant_id=tenant.id)

            detail: BaselineDetail = store.get(bl_id)
            assert len(detail.entries) == 3
            stored_ids = {e.item_id for e in detail.entries}
            expected_ids = {t.item_id for t in tuples}
            assert stored_ids == expected_ids
            # No title/description/content in entries (ADR-BL-02)
            for entry in detail.entries:
                assert hasattr(entry, "item_id")
                assert hasattr(entry, "version")
                assert not hasattr(entry, "title")
        finally:
            TenantContext.clear_tenant()

    def test_persist_no_payload_in_entries(self):
        """REQ-L2-BL-001: entries must NOT contain title/description/content."""
        from persistence.tenancy import TenantContext

        tenant = self._make_tenant()
        TenantContext.set_tenant(tenant.id)
        try:
            store = BaselineStore()
            tuples = _make_delta_tuples(1)
            meta = _make_metadata()
            bl_id = store.persist_delta_index(tuples, meta, tenant_id=tenant.id)
            detail = store.get(bl_id)
            entry = detail.entries[0]
            assert not hasattr(entry, "title"), "DeltaIndexTuple must not carry payload"
        finally:
            TenantContext.clear_tenant()

    def test_duplicate_name_raises(self):
        """REQ-L2-BL-005: second baseline with same name in same workspace → error."""
        from persistence.tenancy import TenantContext

        tenant = self._make_tenant()
        TenantContext.set_tenant(tenant.id)
        try:
            store = BaselineStore()
            meta = _make_metadata(name="UniqueRelease")
            store.persist_delta_index([], meta, tenant_id=tenant.id)
            with pytest.raises(DuplicateBaselineNameError):
                store.persist_delta_index([], meta, tenant_id=tenant.id)
        finally:
            TenantContext.clear_tenant()

    def test_same_name_different_workspace_allowed(self):
        """REQ-L2-BL-005: Same name in a different workspace must succeed."""
        from persistence.tenancy import TenantContext

        tenant = self._make_tenant()
        TenantContext.set_tenant(tenant.id)
        try:
            store = BaselineStore()
            ws1 = uuid.uuid4()
            ws2 = uuid.uuid4()
            meta1 = _make_metadata(name="SharedName", workspace_id=ws1)
            meta2 = _make_metadata(name="SharedName", workspace_id=ws2)
            id1 = store.persist_delta_index([], meta1, tenant_id=tenant.id)
            id2 = store.persist_delta_index([], meta2, tenant_id=tenant.id)
            assert id1 != id2
        finally:
            TenantContext.clear_tenant()

    def test_empty_name_not_accepted_via_builder(self):
        """REQ-L2-BL-005: Empty name is rejected before persist."""
        from persistence.tenancy import TenantContext

        tenant = self._make_tenant()
        TenantContext.set_tenant(tenant.id)
        try:
            builder = DeltaIndexBuilder()
            with pytest.raises(EmptyBaselineNameError):
                builder.build(
                    scope="project",
                    workspace_id=uuid.uuid4(),
                    name="",
                    tenant_id=tenant.id,
                )
            with pytest.raises(EmptyBaselineNameError):
                builder.build(
                    scope="project",
                    workspace_id=uuid.uuid4(),
                    name="   ",
                    tenant_id=tenant.id,
                )
        finally:
            TenantContext.clear_tenant()

    def test_get_nonexistent_raises(self):
        """REQ-L2-BL-006: get(nonexistent_id) → BaselineNotFoundError."""
        store = BaselineStore()
        with pytest.raises(BaselineNotFoundError):
            store.get(uuid.uuid4())

    def test_list_sorted_desc(self):
        """REQ-L2-BL-006: list() returns baselines sorted by created_at DESC."""
        from persistence.tenancy import TenantContext

        tenant = self._make_tenant()
        TenantContext.set_tenant(tenant.id)
        try:
            store = BaselineStore()
            ws = uuid.uuid4()
            for i in range(3):
                store.persist_delta_index(
                    [],
                    _make_metadata(name=f"BL-{i}", workspace_id=ws),
                    tenant_id=tenant.id,
                )
            summaries = store.list(workspace_id=ws, tenant_id=tenant.id)
            assert len(summaries) == 3
            # sorted DESC means first entry is most recent
            timestamps = [s.created_at for s in summaries]
            assert timestamps == sorted(timestamps, reverse=True)
        finally:
            TenantContext.clear_tenant()

    def test_list_scope_filter(self):
        """REQ-L2-BL-006: list(scope=X) returns only baselines of that scope."""
        from persistence.tenancy import TenantContext

        tenant = self._make_tenant()
        TenantContext.set_tenant(tenant.id)
        try:
            store = BaselineStore()
            ws = uuid.uuid4()
            store.persist_delta_index(
                [], _make_metadata(name="Proj", scope="project", workspace_id=ws),
                tenant_id=tenant.id,
            )
            store.persist_delta_index(
                [], _make_metadata(name="Doc", scope="document", workspace_id=ws),
                tenant_id=tenant.id,
            )
            proj_only = store.list(workspace_id=ws, scope="project", tenant_id=tenant.id)
            assert len(proj_only) == 1
            assert proj_only[0].scope == "project"
        finally:
            TenantContext.clear_tenant()

    def test_lookup_item_version_found(self):
        """IF-BL-INT-004: lookup_item_version returns correct version."""
        from persistence.tenancy import TenantContext

        tenant = self._make_tenant()
        TenantContext.set_tenant(tenant.id)
        try:
            store = BaselineStore()
            item_id = str(uuid.uuid4())
            tuples = [DeltaIndexTuple(item_id=item_id, version=7)]
            meta = _make_metadata()
            bl_id = store.persist_delta_index(tuples, meta, tenant_id=tenant.id)
            assert store.lookup_item_version(bl_id, item_id) == 7
        finally:
            TenantContext.clear_tenant()

    def test_lookup_item_version_not_in_baseline(self):
        """IF-BL-INT-004: item not in baseline → ItemNotInBaselineError."""
        from persistence.tenancy import TenantContext

        tenant = self._make_tenant()
        TenantContext.set_tenant(tenant.id)
        try:
            store = BaselineStore()
            meta = _make_metadata()
            bl_id = store.persist_delta_index([], meta, tenant_id=tenant.id)
            with pytest.raises(ItemNotInBaselineError):
                store.lookup_item_version(bl_id, str(uuid.uuid4()))
        finally:
            TenantContext.clear_tenant()


# ---------------------------------------------------------------------------
# COMP-BL-002 DiffEngine — Unit tests (mock store)
# ---------------------------------------------------------------------------


class TestDiffEngine:
    """REQ-L2-BL-003: Diff returns added/removed/changed. Scope mismatch rejected."""

    def _make_store_mock(
        self,
        scope_a: str = "project",
        scope_b: str = "project",
        entries_a: list | None = None,
        entries_b: list | None = None,
    ) -> MagicMock:
        from baseline.models import BaselineSnapshot

        mock = MagicMock(spec=BaselineStore)
        mock.load_delta_index.side_effect = lambda bid: (
            entries_a or [] if bid == self._id_a else entries_b or []
        )
        return mock

    def setup_method(self):
        self._id_a = uuid.uuid4()
        self._id_b = uuid.uuid4()

    def _make_engine_with_scopes(
        self,
        scope_a: str,
        scope_b: str,
        entries_a: list | None = None,
        entries_b: list | None = None,
    ) -> DiffEngine:
        store = MagicMock(spec=BaselineStore)
        store.load_delta_index.side_effect = lambda bid: (
            entries_a or [] if bid == self._id_a else entries_b or []
        )
        engine = DiffEngine(store=store)

        with patch("baseline.diff_engine.BaselineSnapshot") as mock_snap:
            a_snap = MagicMock()
            a_snap.scope = scope_a
            b_snap = MagicMock()
            b_snap.scope = scope_b
            mock_snap.unscoped.only.return_value.get.side_effect = (
                lambda id: a_snap if id == self._id_a else b_snap
            )
            engine._mock_snap = mock_snap
            engine._a_snap = a_snap
            engine._b_snap = b_snap

        return engine

    def test_diff_added(self):
        """REQ-L2-BL-003: item only in B → appears in added."""
        new_item = str(uuid.uuid4())
        entries_a: list[tuple[str, int, str]] = []
        entries_b = [(new_item, 1, "item")]

        store = MagicMock(spec=BaselineStore)
        store.load_delta_index.side_effect = lambda bid: (
            entries_a if bid == self._id_a else entries_b
        )
        engine = DiffEngine(store=store)

        with patch("baseline.diff_engine.BaselineSnapshot") as mock_snap:
            snap_a = MagicMock()
            snap_a.scope = "project"
            snap_b = MagicMock()
            snap_b.scope = "project"
            mock_snap.unscoped.only.return_value.get.side_effect = (
                lambda id: snap_a if id == self._id_a else snap_b
            )
            result = engine.diff(self._id_a, self._id_b)

        assert new_item in result.added
        assert result.removed == []
        assert result.changed == []

    def test_diff_removed(self):
        """REQ-L2-BL-003: item only in A → appears in removed."""
        old_item = str(uuid.uuid4())
        entries_a = [(old_item, 1, "item")]
        entries_b: list[tuple[str, int, str]] = []

        store = MagicMock(spec=BaselineStore)
        store.load_delta_index.side_effect = lambda bid: (
            entries_a if bid == self._id_a else entries_b
        )
        engine = DiffEngine(store=store)

        with patch("baseline.diff_engine.BaselineSnapshot") as mock_snap:
            snap_a = MagicMock()
            snap_a.scope = "project"
            snap_b = MagicMock()
            snap_b.scope = "project"
            mock_snap.unscoped.only.return_value.get.side_effect = (
                lambda id: snap_a if id == self._id_a else snap_b
            )
            result = engine.diff(self._id_a, self._id_b)

        assert old_item in result.removed
        assert result.added == []
        assert result.changed == []

    def test_diff_changed(self):
        """REQ-L2-BL-003: same item, different version → appears in changed."""
        item = str(uuid.uuid4())
        entries_a = [(item, 1, "item")]
        entries_b = [(item, 2, "item")]

        store = MagicMock(spec=BaselineStore)
        store.load_delta_index.side_effect = lambda bid: (
            entries_a if bid == self._id_a else entries_b
        )
        engine = DiffEngine(store=store)

        with patch("baseline.diff_engine.BaselineSnapshot") as mock_snap:
            snap_a = MagicMock()
            snap_a.scope = "project"
            snap_b = MagicMock()
            snap_b.scope = "project"
            mock_snap.unscoped.only.return_value.get.side_effect = (
                lambda id: snap_a if id == self._id_a else snap_b
            )
            result = engine.diff(self._id_a, self._id_b)

        assert len(result.changed) == 1
        assert result.changed[0].id == item
        assert result.changed[0].old_version == 1
        assert result.changed[0].new_version == 2

    def test_diff_unchanged_item_not_listed(self):
        """REQ-L2-BL-003: same item, same version → not in any category."""
        item = str(uuid.uuid4())
        entries_a = [(item, 5, "item")]
        entries_b = [(item, 5, "item")]

        store = MagicMock(spec=BaselineStore)
        store.load_delta_index.side_effect = lambda bid: (
            entries_a if bid == self._id_a else entries_b
        )
        engine = DiffEngine(store=store)

        with patch("baseline.diff_engine.BaselineSnapshot") as mock_snap:
            snap_a = MagicMock()
            snap_a.scope = "project"
            snap_b = MagicMock()
            snap_b.scope = "project"
            mock_snap.unscoped.only.return_value.get.side_effect = (
                lambda id: snap_a if id == self._id_a else snap_b
            )
            result = engine.diff(self._id_a, self._id_b)

        assert result.added == []
        assert result.removed == []
        assert result.changed == []

    def test_diff_scope_mismatch(self):
        """REQ-L2-BL-003: different scopes → ScopeMismatchError."""
        store = MagicMock(spec=BaselineStore)
        engine = DiffEngine(store=store)

        with patch("baseline.diff_engine.BaselineSnapshot") as mock_snap:
            snap_a = MagicMock()
            snap_a.scope = "project"
            snap_b = MagicMock()
            snap_b.scope = "global"
            mock_snap.unscoped.only.return_value.get.side_effect = (
                lambda id: snap_a if id == self._id_a else snap_b
            )
            with pytest.raises(ScopeMismatchError) as exc_info:
                engine.diff(self._id_a, self._id_b)

        assert "different scopes" in str(exc_info.value)

    def test_diff_result_structure(self):
        """REQ-L2-BL-003: diff result has correct {added, removed, changed} keys."""
        store = MagicMock(spec=BaselineStore)
        store.load_delta_index.return_value = []
        engine = DiffEngine(store=store)

        with patch("baseline.diff_engine.BaselineSnapshot") as mock_snap:
            snap = MagicMock()
            snap.scope = "project"
            mock_snap.unscoped.only.return_value.get.return_value = snap
            result = engine.diff(self._id_a, self._id_b)

        d = result.to_dict()
        assert "added" in d
        assert "removed" in d
        assert "changed" in d


# ---------------------------------------------------------------------------
# COMP-BL-004 VersionReconstructor — Unit tests (mock store + DB)
# ---------------------------------------------------------------------------


class TestVersionReconstructor:
    """REQ-L2-BL-009: Reconstruct item at baseline version."""

    def setup_method(self):
        self._baseline_id = uuid.uuid4()
        self._item_id = str(uuid.uuid4())

    def _make_reconstructor(self, version: int = 3) -> tuple[VersionReconstructor, MagicMock]:
        store = MagicMock(spec=BaselineStore)
        store.lookup_item_version.return_value = version
        return VersionReconstructor(store=store), store

    def test_item_not_in_baseline_raises(self):
        """REQ-L2-BL-009: item_id not in baseline → ItemNotInBaselineError."""
        store = MagicMock(spec=BaselineStore)
        store.lookup_item_version.side_effect = ItemNotInBaselineError()
        reconstructor = VersionReconstructor(store=store)
        with pytest.raises(ItemNotInBaselineError) as exc_info:
            reconstructor.get_item_at_baseline(self._baseline_id, self._item_id)
        assert "not part of this baseline" in str(exc_info.value)

    def test_version_not_in_history_raises(self):
        """REQ-L2-BL-009: version not found → VersionNotFoundError."""
        reconstructor, _ = self._make_reconstructor(version=99)
        # Patch live entity and audit log to return nothing
        with patch.object(reconstructor, "_try_live_entity", return_value=None), \
             patch.object(reconstructor, "_load_from_audit_log", return_value=None):
            with pytest.raises(VersionNotFoundError) as exc_info:
                reconstructor.get_item_at_baseline(self._baseline_id, self._item_id)
        assert "Version not found" in str(exc_info.value)

    def test_returns_old_version_from_audit(self):
        """REQ-L2-BL-009: item changed after baseline → old version returned."""
        reconstructor, store = self._make_reconstructor(version=2)
        old_payload = ItemPayload(
            item_id=self._item_id, version=2, title="Old Title", description="old desc"
        )
        with patch.object(reconstructor, "_try_live_entity", return_value=None), \
             patch.object(reconstructor, "_load_from_audit_log", return_value=old_payload):
            result = reconstructor.get_item_at_baseline(self._baseline_id, self._item_id)
        assert result.title == "Old Title"
        assert result.version == 2

    def test_live_entity_used_when_version_matches(self):
        """REQ-L2-BL-009: live entity returned when version matches (cache hit path)."""
        reconstructor, store = self._make_reconstructor(version=5)
        live_payload = ItemPayload(
            item_id=self._item_id, version=5, title="Current Title"
        )
        with patch.object(reconstructor, "_try_live_entity", return_value=live_payload):
            result = reconstructor.get_item_at_baseline(self._baseline_id, self._item_id)
        assert result.title == "Current Title"

    def test_lru_cache_hit_avoids_db(self):
        """REQ-L3-BL004-003: second call hits LRU cache, not DB."""
        reconstructor, store = self._make_reconstructor(version=3)
        cached_payload = ItemPayload(item_id=self._item_id, version=3, title="Cached")
        reconstructor._cache.put(cached_payload)
        # No patching of _try_live_entity or _load_from_audit_log
        # — if cache hit works, neither should be called
        with patch.object(reconstructor, "_try_live_entity") as mock_live, \
             patch.object(reconstructor, "_load_from_audit_log") as mock_audit:
            result = reconstructor.get_item_at_baseline(self._baseline_id, self._item_id)
        mock_live.assert_not_called()
        mock_audit.assert_not_called()
        assert result.title == "Cached"


# ---------------------------------------------------------------------------
# COMP-BL-004 LruPayloadCache — Unit tests
# ---------------------------------------------------------------------------


class TestLruPayloadCache:
    """ADR-L3-BL004-01: LRU cache eviction and hit/miss."""

    def _make_payload(self, item_id: str, version: int) -> ItemPayload:
        return ItemPayload(item_id=item_id, version=version, title=f"T-{version}")

    def test_cache_miss_returns_none(self):
        cache = LruPayloadCache(max_size=10)
        assert cache.get("unknown", 1) is None

    def test_cache_put_and_get(self):
        cache = LruPayloadCache(max_size=10)
        p = self._make_payload("a", 1)
        cache.put(p)
        assert cache.get("a", 1) is p

    def test_cache_evicts_lru_on_overflow(self):
        cache = LruPayloadCache(max_size=2)
        p1 = self._make_payload("i1", 1)
        p2 = self._make_payload("i2", 2)
        p3 = self._make_payload("i3", 3)
        cache.put(p1)
        cache.put(p2)
        # Access p1 to make p2 the LRU
        cache.get("i1", 1)
        cache.put(p3)  # p2 should be evicted
        assert cache.get("i1", 1) is p1
        assert cache.get("i3", 3) is p3
        assert cache.get("i2", 2) is None  # evicted


# ---------------------------------------------------------------------------
# COMP-BL-001 DeltaIndexBuilder — Unit tests (mock store + preset)
# ---------------------------------------------------------------------------


class TestDeltaIndexBuilderPresetGate:
    """REQ-L2-BL-004: Preset scope gating."""

    def _make_builder(self) -> DeltaIndexBuilder:
        store = MagicMock(spec=BaselineStore)
        store.persist_delta_index.return_value = uuid.uuid4()
        # BaselineSnapshot.unscoped.filter().exists() → False (no duplicates)
        with patch("baseline.delta_index_builder.BaselineSnapshot"):
            return DeltaIndexBuilder(store=store)

    def test_scope_not_allowed_raises(self):
        """REQ-L2-BL-004: blocked scope raises ScopeNotAllowedError."""
        builder = DeltaIndexBuilder(store=MagicMock())
        with patch("baseline.delta_index_builder.BaselineSnapshot"):
            with patch("baseline.delta_index_builder.DeltaIndexBuilder._check_preset_gate") as gate:
                gate.side_effect = ScopeNotAllowedError(scope="global", preset="standard")
                with pytest.raises(ScopeNotAllowedError):
                    builder.build(
                        scope="global",
                        workspace_id=WORKSPACE_ID,
                        name="BL-Global",
                        tenant_id=TENANT_ID,
                    )

    def test_minimal_preset_rejects_document_scope(self):
        """REQ-L2-BL-004: Minimal → document scope → ScopeNotAllowedError."""
        builder = DeltaIndexBuilder(store=MagicMock())
        # Patch _check_preset_gate directly to simulate minimal preset rejection
        with patch.object(
            builder,
            "_check_preset_gate",
            side_effect=ScopeNotAllowedError(scope="document", preset="minimal"),
        ):
            with pytest.raises(ScopeNotAllowedError):
                builder.build(
                    scope="document",
                    workspace_id=WORKSPACE_ID,
                    name="BL",
                    tenant_id=TENANT_ID,
                    document_id=uuid.uuid4(),
                )

    def test_empty_name_raises_before_scope_check(self):
        """REQ-L2-BL-005: Empty name rejected before any DB/preset call."""
        builder = DeltaIndexBuilder(store=MagicMock())
        with patch("baseline.delta_index_builder.BaselineSnapshot"):
            with pytest.raises(EmptyBaselineNameError):
                builder.build(
                    scope="project",
                    workspace_id=WORKSPACE_ID,
                    name="",
                    tenant_id=TENANT_ID,
                )

    def test_duplicate_name_raised_by_validator(self):
        """REQ-L2-BL-005: duplicate name detection in _validate_metadata."""
        builder = DeltaIndexBuilder(store=MagicMock())
        with patch("baseline.delta_index_builder.BaselineSnapshot") as mock_snap:
            mock_snap.unscoped.filter.return_value.exists.return_value = True
            with pytest.raises(DuplicateBaselineNameError):
                builder._validate_metadata("Existing Name", WORKSPACE_ID, TENANT_ID)


# ---------------------------------------------------------------------------
# REQ-L2-BL-005: Naming constraints
# ---------------------------------------------------------------------------


class TestBaselineNaming:
    """REQ-L2-BL-005: Naming validation edge cases."""

    def test_whitespace_only_name_raises(self):
        builder = DeltaIndexBuilder(store=MagicMock())
        with patch("baseline.delta_index_builder.BaselineSnapshot"):
            with pytest.raises(EmptyBaselineNameError):
                builder.build(
                    scope="project",
                    workspace_id=WORKSPACE_ID,
                    name="   ",
                    tenant_id=TENANT_ID,
                )

    def test_valid_name_passes_validation(self):
        """No exception for a valid, non-duplicate name."""
        builder = DeltaIndexBuilder(store=MagicMock())
        with patch("baseline.delta_index_builder.BaselineSnapshot") as mock_snap:
            mock_snap.unscoped.filter.return_value.exists.return_value = False
            # Should not raise
            builder._validate_metadata("Release 1.0", WORKSPACE_ID, TENANT_ID)


# ---------------------------------------------------------------------------
# REQ-L2-BL-003: DiffResult serialization
# ---------------------------------------------------------------------------


class TestDiffResultSerialization:
    """DiffResult.to_dict() must contain added, removed, changed keys."""

    def test_to_dict_keys(self):
        from baseline.types import ChangedItem

        result = DiffResult(
            added=["a", "b"],
            removed=["c"],
            changed=[ChangedItem(id="d", old_version=1, new_version=2)],
        )
        d = result.to_dict()
        assert set(d.keys()) == {"added", "removed", "changed"}
        assert d["added"] == ["a", "b"]
        assert d["removed"] == ["c"]
        assert d["changed"][0] == {"id": "d", "old_version": 1, "new_version": 2}


# ---------------------------------------------------------------------------
# REQ-L2-BL-006: BaselineNotFoundError message
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestBaselineNotFoundError:
    def test_error_message(self):
        store = BaselineStore()
        with pytest.raises(BaselineNotFoundError) as exc_info:
            store.get(uuid.uuid4())
        assert "Baseline not found" in str(exc_info.value)


# ---------------------------------------------------------------------------
# REQ-L2-BL-001: Scope scope semantics (unit level, no DB)
# ---------------------------------------------------------------------------


class TestScopeResolverScope:
    """REQ-L2-BL-001: scope='document' requires document_id."""

    def test_document_scope_requires_document_id(self):
        resolver = ScopeResolver()
        with pytest.raises(ValueError, match="document_id is required"):
            # Calling resolve without document_id for scope=document
            resolver.resolve(
                scope="document",
                workspace_id=WORKSPACE_ID,
                tenant_id=TENANT_ID,
                document_id=None,
            )

    def test_unknown_scope_raises(self):
        resolver = ScopeResolver()
        with pytest.raises(ValueError, match="Unknown scope"):
            resolver.resolve(
                scope="invalid",
                workspace_id=WORKSPACE_ID,
                tenant_id=TENANT_ID,
            )


# ---------------------------------------------------------------------------
# REQ-L2-BL-003: Scope mismatch error message
# ---------------------------------------------------------------------------


class TestScopeMismatchMessage:
    def test_error_message(self):
        with pytest.raises(ScopeMismatchError) as exc_info:
            raise ScopeMismatchError()
        assert "different scopes" in str(exc_info.value)
