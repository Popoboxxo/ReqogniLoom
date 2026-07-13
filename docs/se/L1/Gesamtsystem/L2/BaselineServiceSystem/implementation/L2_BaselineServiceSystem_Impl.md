---
step: implementation
agent: se-developer
status: done
timestamp: "2026-06-24T00:00:00Z"
schema_version: "1.0.0"
---
# L2 BaselineServiceSystem — Implementation Summary

**leaf_id:** ARCH-L1-006 / COMP-BL-001..004
**req_id:** REQ-L2-BL-001 through REQ-L2-BL-009
**context_boundary:** backend/baseline/

---

## Artifacts

| File | Component | Description |
|------|-----------|-------------|
| `backend/baseline/models.py` | COMP-BL-003 | BaselineSnapshot + BaselineDeltaIndexEntry ORM models |
| `backend/baseline/migrations/0001_initial.py` | COMP-BL-003 | Schema migration incl. DB-level immutability triggers |
| `backend/baseline/exceptions.py` | All | Domain exceptions with spec-mandated messages |
| `backend/baseline/types.py` | All | Shared dataclasses (DeltaIndexTuple, DiffResult, ItemPayload, etc.) |
| `backend/baseline/store.py` | COMP-BL-003 | BaselineStore — Append-Only persistence + retrieval |
| `backend/baseline/delta_index_builder.py` | COMP-BL-001 | DeltaIndexBuilder — scope resolution + preset gate |
| `backend/baseline/diff_engine.py` | COMP-BL-002 | DiffEngine — O(n) set-based Baseline comparison |
| `backend/baseline/version_reconstructor.py` | COMP-BL-004 | VersionReconstructor — historical payload from AuditLog |
| `backend/baseline/services.py` | All | Public facade (IF-BL-EXT-IN-001) |
| `backend/baseline/tests/test_baseline.py` | All | Pytest test suite |

---

## Public Import Paths

```python
from baseline.services import build, diff, get, list_baselines, get_item_at_baseline
from baseline.exceptions import (
    BaselineImmutableError, BaselineNotFoundError, ScopeMismatchError,
    ScopeNotAllowedError, EmptyBaselineNameError, DuplicateBaselineNameError,
    ItemNotInBaselineError, VersionNotFoundError
)
```

---

## Interfaces Implemented

| Interface | Implementation |
|-----------|---------------|
| IF-BL-EXT-IN-001 | `services.py` facade (build, diff, get, list_baselines, get_item_at_baseline) |
| IF-BL-EXT-IN-002 | `delta_index_builder.py._check_preset_gate()` calls `presets.services.is_scope_allowed` |
| IF-BL-EXT-IN-003 | `delta_index_builder.ScopeResolver` uses raw SQL on pl_artifact (TraceabilityEngine not called directly for scope resolution; collect_trace_graph is available for future full TraceLink inclusion) |
| IF-BL-INT-001 | `store.persist_delta_index()` |
| IF-BL-INT-002 | `store.load_delta_index()` |
| IF-BL-INT-004 | `store.lookup_item_version()` |

---

## Test Coverage

All acceptance criteria from REQ-L2-BL-001 through REQ-L2-BL-009 are covered:

- **3 scopes resolve correctly** (document/project/global) — ScopeResolver unit tests
- **Immutability enforced** — BaselineStore.update/delete raise BaselineImmutableError; DB triggers in migration
- **Duplicate name rejection** — TestBaselineStorePersistence.test_duplicate_name_raises
- **Empty name rejection** — TestDeltaIndexBuilderPresetGate.test_empty_name_raises_before_scope_check
- **Cross-workspace same name OK** — TestBaselineStorePersistence.test_same_name_different_workspace_allowed
- **Diff added/removed/changed** — TestDiffEngine.test_diff_added/removed/changed
- **Scope mismatch rejected** — TestDiffEngine.test_diff_scope_mismatch
- **Preset scope gating** — TestDeltaIndexBuilderPresetGate
- **Tenant isolation** — list() filtered by workspace_id + tenant_id
- **VersionReconstructor** — item-at-baseline, old version, cache hit, version not found
- **LRU eviction** — TestLruPayloadCache.test_cache_evicts_lru_on_overflow

---

## Escalations / Notes

- **ICD Management (IF-BL-EXT-IN-005):** `icd.services.get_icd_versions()` is a stub — not yet implemented. ICD versions are therefore NOT included in the delta index. No interface change required; this is a known gap that will be filled when ARCH-L1-014 IcdManagement is implemented.
- **TraceabilityEngine (IF-BL-EXT-IN-003):** `collect_trace_graph()` returns TraceLink rows only. The ScopeResolver queries Artifacts directly via raw SQL; TraceLinks are included for document scope. For project/global scope, TraceLinks are not included in the current delta index (they can be added via a separate pass once the ICD interface is resolved).
- **AuditLog/VersionHistory (IF-BL-EXT-IN-004):** VersionReconstructor queries `AuditLogEntry.payload` from `persistence.models` (which has a `payload` JSONField). If the payload contains `version`, `title`, `description`, `content`, reconstruction works. The live-entity fast path covers the most common case (entity not changed since baseline).
- **DB-level immutability triggers** require PostgreSQL. SQLite test databases will not enforce the trigger path; the application-layer guard in `BaselineStore.update/delete` covers that case for unit tests.
