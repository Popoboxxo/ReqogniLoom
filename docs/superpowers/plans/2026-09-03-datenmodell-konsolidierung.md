# Datenmodell-Konsolidierung Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate ReqogniLoom's artifact data model onto one status axis (`WorkflowItemState.current_state`), one persistence layer (`persistence/models.py` + `TenantScopedModel`), one `Artifact` backing per artifact type, and one versioning mechanism.

**Architecture:** A read seam (`workflow.state_reader`) is introduced first so every consumer of the denormalized `status` mirror reads the workflow engine instead; only then are the mirror columns dropped. The six Layer-2 plain models move to Layer 0 via `SeparateDatabaseAndState` (tables never move, only the Django app label and the base class), the four Artifact-less types get their backing row through one shared `ensure_artifact()` helper, and content history is unified into a single `ArtifactVersion` snapshot table that the three legacy version tables are migrated into.

**Tech Stack:** Django 5.2+ / Python 3.x, PostgreSQL 16 (Row-Level-Security policies per table), Django REST Framework 3.15+, pytest + pytest-django, React 18 + TypeScript 5.5 (read-only consumer — no frontend change required, see Decision D-1).

**Spec:** docs/superpowers/specs/2026-09-03-datenmodell-konsolidierung-design.md

## Global Constraints

- Every DRF view MUST call `set_tenant(request.user.tenant)` — no view may bypass `TenantContext`.
- No DRF view may query `persistence.models` directly; all reads/writes go through `application/` services (ADR-01, Single Entry Point).
- Every table added to or removed from a mirror map MUST have its RLS policy changed in the same commit (SA-22 rule, documented in `StateLifecycleManager._sync_status_mirror`).
- `WorkflowItemState.current_state` is the single source of truth for lifecycle status (ADR `docs/architecture/ADR-status-single-source.md`, ACCEPTED 2026-07-15). Nothing may reintroduce a writable status column.
- The public REST/MCP wire key `status` MUST keep its name and its value vocabulary. Only its *source* changes (column → workflow engine). See Decision D-1.
- `AuditableModel.version` is an optimistic-lock counter, never a revision number (issue #213). New revision numbering MUST NOT reuse it.
- Migrations that write data run as the DB owner, not the app role — the app role is silently no-op'd by RLS.
- Branch policy: `feat/*`, `fix/*`, `refactor/*` — never commit on `main`.
- Commits: Conventional Commits, English, imperative, max 72 chars in the subject line.
- Python: PEP 8, type hints, docstrings on public API. No wildcard imports. Import order: stdlib → third-party → local.
- Backend test invocation (paths scoped to the changed modules, never the full tree):
  `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test pytest <paths> -v`
- Full Playwright E2E runs are NOT part of this plan's Definition of Done (CI covers them). Targeted `--grep` checks are allowed.

---

## Spec-Verifikation gegen den Code-Stand (2026-09-03)

The spec was written before this plan; six of its factual claims do not match the code. Each is resolved below and the resolution is what the tasks implement.

| # | Spec claim | Verified reality | Resolution |
|---|---|---|---|
| V-1 | "alle sechs haben bereits eine `artifact`-OneToOne-FK" (§3.3) | `ChangeRequest` (`application/models.py:670-758`) has **no** `artifact` FK. Adr/Risk/Goal/MainGoal/Issue do. | ChangeRequest is added to the Phase 3 backfill set (Task 18), not treated as already-backed. |
| V-2 | "`Diagram` und `Icd` … haben **kein** Artifact-Backing" (§1) | `Diagram.artifact` **already exists** (`diagram/models.py:108-114`, nullable OneToOne, `SET_NULL`), created lazily by `diagram/traceability_connector.py:60 _resolve_artifact_id`. Only pre-existing rows are unbacked. `Icd` genuinely has none. | For Diagram: no new field — only backfill + eager creation (Task 17). For Icd/GlossaryTerm/ChangeRequest: new field + backfill. |
| V-3 | "`lifecycle_status` … wandert von `Requirement` (heute der einzige Typ, der es hat)" (§5) | Four models carry it: `StakeholderNeed:905`, `Requirement:1005`, `ArchitectureElement:1144`, `GlossaryTerm:1844`. | All four columns are dropped in Phase 4, replaced by one column on `Artifact`. |
| V-4 | "`lifecycle_status` ist ein … orthogonales Soft-Delete-Flag" (§2/§5) | Today it is a *projection* of the workflow state, written by `StateLifecycleManager._sync_lifecycle_mirror` via `_LIFECYCLE_MIRROR_MODELS` (`workflow/lifecycle_manager.py:168-171`), and soft-delete itself is the workflow state `"outdated"` written by `workflow.services.outdate()`. | See Decision D-3: `Artifact.lifecycle_status` becomes the authoritative orthogonal flag and `outdate()` stops hijacking `current_state`. |
| V-5 | "Audit-Log-basierte Versionierung (`backend/audit/`, `AuditEntry` + `VersionReconstructor`) … ist bereits der Mechanismus für 8 von 10 Typen" (§6) | `VersionReconstructor` lives in `baseline/version_reconstructor.py`, not `audit/`, and reconstructs items *at a baseline*, not a content revision. `AuditEntry` (`audit/models.py:89`) has **no payload column** (actor, op, entity_type, entity_id, entity_version, change_reason, timestamp, source, client_name, api_key_hash). The 8 types use ADR-AS-019's *single-row* model: `ArtifactDiffService` can only resolve the current lock version, every other version reports `content_available: false`. | See OFFENE FRAGE F-1 and Decision D-4: a new `persistence.ArtifactVersion` snapshot table becomes the single mechanism; the audit log stays an operation trail. |
| V-6 | "`Goal.status` … deutscher String-Default `"Entwurf"` … Bug B1 damit als Nebeneffekt behoben" (§5) | `Entwurf`/`Freigegeben`/`Archiviert` are the *declared workflow states* of the `goal_default` preset (`application/goal_service.py:46-48`), consumed by `list_effective`/`MainGoalService`. They are correct, not a bug. Only the hardcoded model-level default is wrong. | Dropping the column removes the hardcoded default; the German state names stay. `list_effective` is rewritten against the workflow engine (Task 8), not "fixed". |

## Offene Fragen

**F-1 (blocking for Phase 5 only — Phases 0–4 are unaffected): Which store holds content history?**
Spec §6 instructs to retire `DiagramVersion`/`IcdVersion`/`GlossaryTermVersion` into "the existing audit-log-based versioning". That mechanism does not exist as described (V-5): `AuditEntry` stores no payload and is an append-only, trigger-protected operation trail. Executing §6 literally would delete the only three real content-history tables in the system and replace them with a store that cannot answer "what did v3 look like".
This plan resolves it as **Decision D-4** (new generic `persistence.ArtifactVersion` snapshot table, the three legacy tables migrated into it) because that satisfies every stated goal of §6 — one mechanism, all 10 types, `ArtifactDiff` sees one world, the B6 gaps close — without a history regression.
**Confirm before starting Phase 5.** If the intent was instead to add a payload column to `AuditEntry`, only Tasks 22–26 change; Phases 0–4 stand either way.

## Entscheidungen

**D-1 — The wire contract keeps the key `status`.** `status` stops being a column but stays a serializer/DTO field, now computed from `WorkflowItemState`. Consequence: zero frontend changes, zero MCP schema changes, zero CSV-export changes in Phases 0–2. Rejected alternative: renaming the field to `current_state` — a breaking API change with no benefit, since the value vocabulary is identical (the column was a faithful same-transaction mirror).

**D-2 — Phase order deviates from spec §7 in one place.** Spec order is Status → Layer → Backfill → Versioning. The `lifecycle_status` relocation named in §5 is moved out of Phase 1 into its own Phase 4, *after* the Artifact backfill, because `Artifact.lifecycle_status` cannot be authoritative for a type that has no `Artifact` row yet (Diagram/Icd/GlossaryTerm/ChangeRequest, Phase 3). The spec's own §7 dependency ("jeder Typ braucht ein stabiles Artifact-Fundament") forces this. The Attribut-Definition dependency (§5, §7.1) is satisfied by **Milestone M1** — it requires only that the legacy *status* columns are gone.

**D-3 — `Artifact.lifecycle_status` becomes truly orthogonal (spec §5 taken literally).** Today `outdate()` overwrites `current_state` with `"outdated"` and `reactivate()` restores the previous state by walking `WorkflowHistoryEntry` — soft-delete is a state hijack, so an approved artifact loses its approval on soft-delete. Phase 4 makes `outdate()` set `Artifact.lifecycle_status = "outdated"` and leave `current_state` untouched; `reactivate()` sets it back to `"active"` and no longer needs the history walk. Rejected alternative: keep it a projection of the workflow state — that keeps the two axes fused, which is exactly what the spec eliminates.

**D-4 — One `persistence.ArtifactVersion` table instead of audit-log payloads.** See F-1. Rejected alternatives: (a) payload column on `AuditEntry` — turns an append-only compliance trail into a blob store and inflates every audit query; (b) keep three per-type version tables — leaves `ArtifactDiffService` with two dispatch worlds, which §6.4 explicitly closes.

**D-5 — `workspace_id` stays a `UUIDField` on the moved models.** Spec §3.2 says the manual `tenant_id`/`workspace_id` fields "entfallen zugunsten der gemeinsamen RLS-Basisklasse". `TenantScopedModel` supplies only `tenant`; it has no `workspace` field. `tenant_id` is genuinely replaced (the FK's DB column is also `tenant_id`, so it is a constraint addition, not a data move). `workspace_id` is kept as-is — converting it to a FK is an unrelated, riskier change with no RLS benefit.

---

## File Structure

### New files

| Path | Responsibility |
|---|---|
| `backend/workflow/state_reader.py` | Read-only seam over `WorkflowItemState`: `current_state`, `current_states`, `item_ids_in_state`. The single place any consumer resolves an artifact's status. |
| `backend/workflow/tests/test_state_reader.py` | Tests for the seam. |
| `backend/rest_api/mixins/workflow_state.py` | `WorkflowStateSerializerMixin` — one batched `status` `SerializerMethodField` for all nine artifact serializers. |
| `backend/rest_api/tests/test_workflow_state_mixin.py` | Tests for the mixin (single + list, N+1 guard). |
| `backend/persistence/artifact_backing.py` | `ensure_artifact()` — the one shared helper that creates/returns the backing `Artifact` row for any entity. Replaces the Diagram-only lazy resolver. |
| `backend/persistence/tests/test_artifact_backing.py` | Tests for `ensure_artifact`. |
| `backend/application/artifact_version_service.py` | `ArtifactVersionService` — record/list/get content revisions against `persistence.ArtifactVersion`. |
| `backend/application/tests/test_artifact_version_service.py` | Tests for the version service. |
| `backend/persistence/migrations/0070_drop_status_mirror_columns.py` | Drops `Requirement.status`, `StakeholderNeed.status`, `TestCase.status` and their status indexes. |
| `backend/persistence/migrations/0071_glossary_changerequest_artifact_fk.py` | Adds `GlossaryTerm.artifact`; state-only move of the six Layer-2 models into `persistence`. |
| `backend/persistence/migrations/0072_backfill_artifact_backing.py` | Data migration: `Artifact` rows for existing Diagram/Icd/GlossaryTerm/ChangeRequest rows + integrity check. |
| `backend/persistence/migrations/0073_artifact_lifecycle_status.py` | Adds `Artifact.lifecycle_status`, backfills from workflow state, drops the four per-model columns. |
| `backend/persistence/migrations/0074_artifact_version.py` | Creates `persistence.ArtifactVersion` + its RLS policy. |
| `backend/persistence/migrations/0075_migrate_legacy_version_tables.py` | Copies `DiagramVersion`/`IcdVersion`/`GlossaryTermVersion` rows into `ArtifactVersion`. |
| `backend/application/migrations/0020_drop_status_columns.py` | Drops `status` on Adr/Risk/Issue/ChangeRequest/Goal/MainGoal and their status indexes. |
| `backend/application/migrations/0021_move_models_to_persistence.py` | State-only `DeleteModel` counterpart to persistence/0071. |
| `backend/icd/migrations/0009_icd_artifact_fk.py` | Adds `Icd.artifact`. |

### Modified files

| Path | Change |
|---|---|
| `backend/workflow/services.py` | Re-export the seam; `outdate`/`reactivate` rewritten onto `Artifact.lifecycle_status` (Phase 4). |
| `backend/workflow/lifecycle_manager.py` | `_sync_status_mirror` + `_STATUS_MIRROR_MODELS` deleted (Phase 1); `_sync_lifecycle_mirror` + `_LIFECYCLE_MIRROR_MODELS` deleted (Phase 4). |
| `backend/rest_api/serializers.py` | Nine artifact serializers switch their `status` field to the mixin. |
| `backend/baseline/state_capture.py` | `status` values read through the seam instead of `entity.status`. |
| `backend/application/{adr,risk,issue,goal,main_goal,change_request,requirement,stakeholder_need,test}_service.py` | `status=` filters/writes replaced by the seam; `status` DTO values resolved from the engine. |
| `backend/application/artifact_diff_service.py` | Version resolution routed to `ArtifactVersionService` (Phase 5). |
| `backend/application/models.py` | Six model classes removed (moved to `persistence/models.py`). |
| `backend/persistence/models.py` | Receives the six models; `Artifact` gains `lifecycle_status`; `ArtifactVersion` added; four `lifecycle_status` columns removed; `GlossaryTerm` gains `artifact`. |
| `backend/diagram/models.py`, `backend/diagram/manager.py`, `backend/diagram/traceability_connector.py` | Eager Artifact creation via `ensure_artifact`; `_resolve_artifact_id` delegates. |
| `backend/icd/models.py`, `backend/icd/icd_manager.py` | `Icd.artifact` + eager creation. |
| `backend/application/glossary_service.py` | Eager Artifact creation on term create. |
| `backend/mcp_server/tool_registry.py` and the per-type tool groups | `status` in tool payloads resolved from the seam. |

---

## Milestones

| ID | After task | Meaning |
|---|---|---|
| **M0** | Task 3 | Read seam exists and every REST reader uses it. Columns still present — fully reversible. |
| **M1** | Task 13 | **All legacy status columns are dropped.** This is the gate the Attribut-Definition plan (`docs/superpowers/specs/2026-09-03-attribute-definition-design.md` §3.2/§4) depends on. Its bootstrap migration MUST NOT run before M1 is green on `main`. |
| **M2** | Task 16 | The six Layer-2 models live in `persistence/` on `TenantScopedModel`. |
| **M3** | Task 21 | All 10 artifact types have a backing `Artifact` row. |
| **M4** | Task 24 | `Artifact.lifecycle_status` is the single soft-delete flag. |
| **M5** | Task 29 | One versioning mechanism for all 10 types. |

---

# Phase 0 — Read seam (spec §5 preparation)

Goal: every consumer of `status` reads the workflow engine. No schema change, no behaviour change, fully reversible.

### Task 1: Workflow state read seam

**Files:**
- Create: `backend/workflow/state_reader.py`
- Modify: `backend/workflow/services.py:1068-1093` (extend `__all__` and re-export)
- Test: `backend/workflow/tests/test_state_reader.py`

**Interfaces:**
- Consumes: `workflow.models.WorkflowItemState` (fields `item_id`, `item_type`, `workspace_id`, `current_state`), `persistence.tenancy` TenantContext (via the `objects` manager).
- Produces:
  - `current_state(item_type: str, item_id: UUID | str) -> str | None`
  - `current_states(item_type: str, item_ids: Iterable[UUID | str]) -> dict[str, str]` — keys are `str(item_id)`
  - `item_ids_in_state(item_type: str, state: str, *, tenant_id: UUID | str | None = None) -> QuerySet[UUID]`

- [ ] **Step 1: Write the failing test**

Create `backend/workflow/tests/test_state_reader.py`:

```python
"""Tests for the workflow state read seam (Datenmodell-Konsolidierung Phase 0)."""
import uuid

import pytest

from persistence.tenancy import set_tenant
from workflow import state_reader


@pytest.mark.django_db
class TestCurrentStates:
    def test_returns_state_keyed_by_string_id(self, seeded_states):
        tenant, workspace, ids = seeded_states
        set_tenant(str(tenant.id))

        result = state_reader.current_states("Requirement", ids)

        assert result == {str(ids[0]): "draft", str(ids[1]): "approved"}

    def test_unknown_id_is_absent_not_none(self, seeded_states):
        tenant, workspace, ids = seeded_states
        set_tenant(str(tenant.id))
        missing = uuid.uuid4()

        result = state_reader.current_states("Requirement", [missing])

        assert result == {}

    def test_empty_input_does_not_hit_the_db(self, django_assert_num_queries):
        with django_assert_num_queries(0):
            assert state_reader.current_states("Requirement", []) == {}

    def test_one_query_for_many_ids(self, seeded_states, django_assert_num_queries):
        tenant, workspace, ids = seeded_states
        set_tenant(str(tenant.id))

        with django_assert_num_queries(1):
            state_reader.current_states("Requirement", ids)

    def test_item_type_scopes_the_lookup(self, seeded_states):
        tenant, workspace, ids = seeded_states
        set_tenant(str(tenant.id))

        assert state_reader.current_states("Adr", ids) == {}


@pytest.mark.django_db
class TestCurrentState:
    def test_single_lookup(self, seeded_states):
        tenant, workspace, ids = seeded_states
        set_tenant(str(tenant.id))

        assert state_reader.current_state("Requirement", ids[1]) == "approved"

    def test_missing_returns_none(self, seeded_states):
        tenant, workspace, ids = seeded_states
        set_tenant(str(tenant.id))

        assert state_reader.current_state("Requirement", uuid.uuid4()) is None


@pytest.mark.django_db
class TestItemIdsInState:
    def test_filters_by_state(self, seeded_states):
        tenant, workspace, ids = seeded_states
        set_tenant(str(tenant.id))

        assert list(state_reader.item_ids_in_state("Requirement", "approved")) == [ids[1]]

    def test_explicit_tenant_id_overrides_context(self, seeded_states):
        tenant, workspace, ids = seeded_states
        set_tenant(str(tenant.id))

        result = list(
            state_reader.item_ids_in_state("Requirement", "draft", tenant_id=tenant.id)
        )

        assert result == [ids[0]]
```

Add the fixture at the top of the same file:

```python
@pytest.fixture
def seeded_states(db):
    """Two Requirement item states: ids[0] -> draft, ids[1] -> approved."""
    from persistence.models import Tenant, Workspace
    from workflow.models import WorkflowEngineDefinition, WorkflowItemState

    tenant = Tenant.objects.create(name="t-state-reader")
    set_tenant(str(tenant.id))
    workspace = Workspace.objects.create(tenant=tenant, name="ws-state-reader")
    definition = WorkflowEngineDefinition.objects.create(
        tenant=tenant,
        workspace_id=workspace.id,
        item_type="Requirement",
        definition_json={"states": ["draft", "approved"], "transitions": []},
    )
    ids = [uuid.uuid4(), uuid.uuid4()]
    for item_id, state in zip(ids, ["draft", "approved"]):
        WorkflowItemState.objects.create(
            tenant=tenant,
            item_id=item_id,
            item_type="Requirement",
            workspace_id=workspace.id,
            definition=definition,
            current_state=state,
        )
    return tenant, workspace, ids
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test pytest workflow/tests/test_state_reader.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'workflow.state_reader'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/workflow/state_reader.py`:

```python
"""Read-only seam over ``WorkflowItemState`` (Datenmodell-Konsolidierung Phase 0).

Every consumer that previously read a denormalized ``status`` column reads
through this module instead. Keeping the resolution in one place is what makes
dropping those columns (Phase 1) a mechanical change rather than an audit of
every reader.

Tenant isolation: all queries go through ``WorkflowItemState.objects``, the
tenant-scoped manager, so an active ``TenantContext`` is required — exactly like
every other Layer-1 read. ``item_ids_in_state`` additionally accepts an explicit
``tenant_id`` for callers that already hold one (mirrors
``workflow.services.outdated_item_ids``).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Iterable
from uuid import UUID

from workflow.models import WorkflowItemState

if TYPE_CHECKING:  # pragma: no cover - typing only
    from django.db.models import QuerySet


def current_states(
    item_type: str, item_ids: Iterable[UUID | str]
) -> dict[str, str]:
    """Resolve the current workflow state of many items in one query.

    Args:
        item_type: Entity type string, e.g. ``"Requirement"``.
        item_ids:  Item UUIDs (or their string form).

    Returns:
        Mapping ``str(item_id) -> current_state``. Items without a
        ``WorkflowItemState`` row are **absent** from the mapping (not mapped to
        ``None``), so callers decide their own fallback.
    """
    ids = [str(item_id) for item_id in item_ids]
    if not ids:
        return {}
    rows = WorkflowItemState.objects.filter(
        item_type=item_type, item_id__in=ids
    ).values_list("item_id", "current_state")
    return {str(item_id): state for item_id, state in rows}


def current_state(item_type: str, item_id: UUID | str) -> str | None:
    """Resolve the current workflow state of a single item.

    Returns:
        The state name, or ``None`` if the item has no ``WorkflowItemState``.
    """
    return current_states(item_type, [item_id]).get(str(item_id))


def item_ids_in_state(
    item_type: str, state: str, *, tenant_id: UUID | str | None = None
) -> "QuerySet[UUID]":
    """Return the ``item_id`` values of *item_type* currently in *state*.

    Matches the state name literally — no ``state_meta`` interpretation (same
    contract as ``workflow.services.outdated_item_ids``).

    Args:
        item_type: Entity type string.
        state:     Exact state name to match.
        tenant_id: Optional explicit tenant filter applied on top of the
                   tenant-scoped manager. Keyword-only so it cannot be passed
                   positionally into a cross-tenant read.

    Returns:
        Lazy ``QuerySet`` of ``item_id`` UUIDs, usable as an ``__in`` subquery.
    """
    qs = WorkflowItemState.objects.filter(item_type=item_type, current_state=state)
    if tenant_id is not None:
        qs = qs.filter(tenant_id=tenant_id)
    return qs.values_list("item_id", flat=True)


__all__ = ["current_state", "current_states", "item_ids_in_state"]
```

- [ ] **Step 4: Re-export from the service facade**

In `backend/workflow/services.py`, add below the existing imports:

```python
from workflow.state_reader import current_state, current_states, item_ids_in_state
```

and extend `__all__` (currently ending at line 1093) with:

```python
    "current_state",
    "current_states",
    "item_ids_in_state",
```

- [ ] **Step 5: Run test to verify it passes**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test pytest workflow/tests/test_state_reader.py -v`
Expected: PASS (9 tests)

- [ ] **Step 6: Verify the facade re-export**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test python -c "from workflow import services; print(services.current_states, services.item_ids_in_state)"`
Expected: prints two function objects, no ImportError.

- [ ] **Step 7: Commit**

```bash
git add backend/workflow/state_reader.py backend/workflow/tests/test_state_reader.py backend/workflow/services.py
git commit -m "feat: add workflow state read seam"
```

---

### Task 2: Batched status serializer mixin

**Files:**
- Create: `backend/rest_api/mixins/workflow_state.py`
- Test: `backend/rest_api/tests/test_workflow_state_mixin.py`

**Interfaces:**
- Consumes: `workflow.state_reader.current_states(item_type: str, item_ids) -> dict[str, str]` (Task 1).
- Produces: `WorkflowStateSerializerMixin` with class attribute `workflow_item_type: str` and field `status = serializers.SerializerMethodField()`; method `get_status(self, obj) -> str`.

- [ ] **Step 1: Write the failing test**

Create `backend/rest_api/tests/test_workflow_state_mixin.py`:

```python
"""Tests for WorkflowStateSerializerMixin (Datenmodell-Konsolidierung Phase 0)."""
import uuid
from unittest.mock import patch

from rest_framework import serializers

from rest_api.mixins.workflow_state import WorkflowStateSerializerMixin


class _Row:
    def __init__(self, pk: uuid.UUID, title: str) -> None:
        self.pk = pk
        self.id = pk
        self.title = title


class _RowSerializer(WorkflowStateSerializerMixin, serializers.Serializer):
    workflow_item_type = "Requirement"
    title = serializers.CharField()


class TestWorkflowStateSerializerMixin:
    def test_single_object_resolves_status(self):
        row = _Row(uuid.uuid4(), "R1")
        with patch(
            "rest_api.mixins.workflow_state.state_reader.current_states",
            return_value={str(row.pk): "approved"},
        ):
            assert _RowSerializer(row).data["status"] == "approved"

    def test_missing_state_is_empty_string(self):
        row = _Row(uuid.uuid4(), "R1")
        with patch(
            "rest_api.mixins.workflow_state.state_reader.current_states",
            return_value={},
        ):
            assert _RowSerializer(row).data["status"] == ""

    def test_list_resolves_all_in_one_lookup(self):
        rows = [_Row(uuid.uuid4(), "R1"), _Row(uuid.uuid4(), "R2")]
        mapping = {str(rows[0].pk): "draft", str(rows[1].pk): "approved"}
        with patch(
            "rest_api.mixins.workflow_state.state_reader.current_states",
            return_value=mapping,
        ) as spy:
            data = _RowSerializer(rows, many=True).data

        assert [entry["status"] for entry in data] == ["draft", "approved"]
        assert spy.call_count == 1

    def test_item_type_is_passed_through(self):
        row = _Row(uuid.uuid4(), "R1")
        with patch(
            "rest_api.mixins.workflow_state.state_reader.current_states",
            return_value={},
        ) as spy:
            _RowSerializer(row).data

        assert spy.call_args[0][0] == "Requirement"

    def test_missing_item_type_raises(self):
        class _Broken(WorkflowStateSerializerMixin, serializers.Serializer):
            title = serializers.CharField()

        row = _Row(uuid.uuid4(), "R1")
        try:
            _Broken(row).data
        except AssertionError as exc:
            assert "workflow_item_type" in str(exc)
        else:  # pragma: no cover - guard
            raise AssertionError("expected AssertionError")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test pytest rest_api/tests/test_workflow_state_mixin.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rest_api.mixins.workflow_state'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/rest_api/mixins/workflow_state.py`:

```python
"""Batched ``status`` field backed by the workflow engine.

Datenmodell-Konsolidierung Phase 0. Replaces the denormalized ``status`` model
column as the serializer's data source while keeping the wire key and its value
vocabulary identical (Decision D-1) — the column was a same-transaction mirror,
so no response value changes.

The resolution is batched deliberately. DRF builds a *single* child serializer
for ``many=True`` and calls ``get_status`` once per row; resolving per row would
turn every list endpoint into an N+1. The child caches the whole mapping on
first access, so a list of any size costs one query.
"""
from __future__ import annotations

from typing import Any, ClassVar

from rest_framework import serializers

from workflow import state_reader


class WorkflowStateSerializerMixin:
    """Adds a read-only, engine-resolved ``status`` field.

    Subclasses must set :attr:`workflow_item_type` to the entity type string
    used in ``WorkflowItemState.item_type`` (e.g. ``"Requirement"``).
    """

    #: ``WorkflowItemState.item_type`` value for this serializer's model.
    workflow_item_type: ClassVar[str] = ""

    status = serializers.SerializerMethodField()

    def get_status(self, obj: Any) -> str:
        """Return the item's current workflow state, or ``""`` if untracked."""
        return self._workflow_state_map().get(str(obj.pk), "")

    def _workflow_state_map(self) -> dict[str, str]:
        cached = getattr(self, "_workflow_state_cache", None)
        if cached is not None:
            return cached

        assert self.workflow_item_type, (
            f"{type(self).__name__} uses WorkflowStateSerializerMixin but does "
            "not set workflow_item_type"
        )

        # For many=True the ListSerializer parent holds the full instance set;
        # for a single object `self` does.
        root = self.parent if isinstance(self.parent, serializers.ListSerializer) else self
        instance = root.instance

        if instance is None:
            ids: list[Any] = []
        elif hasattr(instance, "__iter__") and not isinstance(instance, (str, bytes)):
            # A QuerySet is already fully evaluated at this point: DRF's
            # ListSerializer.to_representation iterates it before the first
            # child call, which populates _result_cache.
            ids = [row.pk for row in instance]
        else:
            ids = [instance.pk]

        cached = state_reader.current_states(self.workflow_item_type, ids)
        self._workflow_state_cache = cached
        return cached


__all__ = ["WorkflowStateSerializerMixin"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test pytest rest_api/tests/test_workflow_state_mixin.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/rest_api/mixins/workflow_state.py backend/rest_api/tests/test_workflow_state_mixin.py
git commit -m "feat: add batched workflow-state serializer mixin"
```

---

### Task 3: Wire the nine artifact serializers to the mixin — **Milestone M0**

**Files:**
- Modify: `backend/rest_api/serializers.py` (the `status` declarations at lines 707, 824, 960, 1359, 1416, 1511, 1571, 1610 and the TestCase serializer)
- Test: `backend/rest_api/tests/test_status_from_engine.py` (create)

**Interfaces:**
- Consumes: `WorkflowStateSerializerMixin` with `workflow_item_type: str` and field `status` (Task 2).
- Produces: nine serializers whose `status` is engine-resolved. Wire key and vocabulary unchanged (D-1).

The nine `(serializer, workflow_item_type)` pairs:
`RequirementSerializer`/`"Requirement"`, `StakeholderNeedSerializer`/`"StakeholderNeed"`, `TestCaseSerializer`/`"TestCase"`, `AdrSerializer`/`"Adr"`, `RiskSerializer`/`"Risk"`, `IssueSerializer`/`"Issue"`, `ChangeRequestSerializer`/`"ChangeRequest"`, `GoalSerializer`/`"Goal"`, `MainGoalSerializer`/`"MainGoal"`.

- [ ] **Step 1: Write the failing test**

Create `backend/rest_api/tests/test_status_from_engine.py`:

```python
"""Every artifact serializer resolves `status` from the workflow engine.

Datenmodell-Konsolidierung Phase 0 / Milestone M0.
"""
import pytest
from rest_framework import serializers

from rest_api import serializers as api_serializers
from rest_api.mixins.workflow_state import WorkflowStateSerializerMixin

EXPECTED_ITEM_TYPES = {
    "RequirementSerializer": "Requirement",
    "StakeholderNeedSerializer": "StakeholderNeed",
    "TestCaseSerializer": "TestCase",
    "AdrSerializer": "Adr",
    "RiskSerializer": "Risk",
    "IssueSerializer": "Issue",
    "ChangeRequestSerializer": "ChangeRequest",
    "GoalSerializer": "Goal",
    "MainGoalSerializer": "MainGoal",
}


@pytest.mark.parametrize("name,item_type", sorted(EXPECTED_ITEM_TYPES.items()))
def test_serializer_uses_the_engine_seam(name, item_type):
    cls = getattr(api_serializers, name)
    assert issubclass(cls, WorkflowStateSerializerMixin), f"{name} must use the mixin"
    assert cls.workflow_item_type == item_type


@pytest.mark.parametrize("name", sorted(EXPECTED_ITEM_TYPES))
def test_status_is_read_only(name):
    cls = getattr(api_serializers, name)
    field = cls().fields["status"]
    assert isinstance(field, serializers.SerializerMethodField)
    assert field.read_only is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test pytest rest_api/tests/test_status_from_engine.py -v`
Expected: FAIL — `AssertionError: RequirementSerializer must use the mixin`

- [ ] **Step 3: Write minimal implementation**

In `backend/rest_api/serializers.py`, add to the imports:

```python
from rest_api.mixins.workflow_state import WorkflowStateSerializerMixin
```

Then, for each of the nine serializers: add the mixin as the *first* base class, set `workflow_item_type`, and delete the local `status = serializers.CharField(...)` / `serializers.ChoiceField(...)` / `NormalizedChoiceField(...)` declaration. Example for `RequirementSerializer` (the `status` declaration currently at line 707):

```python
class RequirementSerializer(WorkflowStateSerializerMixin, serializers.ModelSerializer):
    workflow_item_type = "Requirement"
    # REQ-143 / Datenmodell-Konsolidierung: `status` is no longer a model
    # column. It is resolved from WorkflowItemState by the mixin, which keeps
    # the wire key and its vocabulary identical (Decision D-1).
    ...
```

Apply the identical two-line change (mixin base + `workflow_item_type`) and the same deletion to `StakeholderNeedSerializer` (`"StakeholderNeed"`, line 824), `TestCaseSerializer` (`"TestCase"`), `AdrSerializer` (`"Adr"`, line 1359), `RiskSerializer` (`"Risk"`, line 1416), `IssueSerializer` (`"Issue"`, line 1571), `ChangeRequestSerializer` (`"ChangeRequest"`, line 1610), `GoalSerializer` (`"Goal"`), `MainGoalSerializer` (`"MainGoal"`, line 1511).

For every one of the nine, also remove `"status"` from `Meta.fields` **only if** the serializer is a `ModelSerializer` and `status` is listed there — a `SerializerMethodField` may stay in `Meta.fields`, but must not appear in `Meta.read_only_fields` (DRF raises `AssertionError: Cannot both declare the field 'status' and include it in read_only_fields`).

- [ ] **Step 4: Run test to verify it passes**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test pytest rest_api/tests/test_status_from_engine.py -v`
Expected: PASS (18 tests)

- [ ] **Step 5: Run the REST regression suite**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test pytest rest_api/ -q`
Expected: PASS — no new failures versus the pre-change baseline. Record the baseline first with `git stash && pytest rest_api/ -q && git stash pop` if any failure is ambiguous (`rest_api/` has a known red baseline in some environments).

- [ ] **Step 6: Verify a live response actually carries the engine value**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test pytest rest_api/tests/ -k "status" -v`
Expected: PASS. Every assertion on a `status` value in an API response still holds — proving the mirror and the engine agreed, which is the precondition for dropping the column in Phase 1.

- [ ] **Step 7: Commit — Milestone M0**

```bash
git add backend/rest_api/serializers.py backend/rest_api/tests/test_status_from_engine.py
git commit -m "refactor: resolve serializer status from the workflow engine"
```

---

# Phase 1 — Status-Konsolidierung (spec §5)

Goal: drop every legacy `status` column. Ends at **Milestone M1**, the gate the Attribut-Definition plan depends on.

### Task 4: ADR, Risk and Issue services read the engine

**Files:**
- Modify: `backend/application/adr_service.py:405-440` (`list_adrs`, `list_adrs_by_status`) and its DTO builder (`:69`, `:83`)
- Modify: `backend/application/risk_service.py` (`list_risks`, `list_risks_by_status`, DTO builder)
- Modify: `backend/application/issue_service.py` (`list_issues`, `list_issues_by_status`, DTO builder)
- Test: `backend/application/tests/test_status_seam_services.py`

**Interfaces:**
- Consumes: `workflow.state_reader.item_ids_in_state(item_type: str, state: str, *, tenant_id) -> QuerySet[UUID]` and `workflow.state_reader.current_state(item_type: str, item_id) -> str | None` (Task 1).
- Produces: `AdrService.list_adrs`, `AdrService.list_adrs_by_status`, `RiskService.list_risks`, `RiskService.list_risks_by_status`, `IssueService.list_issues`, `IssueService.list_issues_by_status` — identical signatures, no longer touching a `status` column.

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_status_seam_services.py`:

```python
"""ADR/Risk/Issue list paths filter through the workflow engine, not a column.

Datenmodell-Konsolidierung Phase 1.
"""
import inspect
import uuid

import pytest

from application import adr_service, issue_service, risk_service

MODULES = [adr_service, risk_service, issue_service]


@pytest.fixture
def adr_fixture(db):
    from auth_tenancy.context import AuthContext
    from persistence.models import Artifact, Tenant, Workspace
    from persistence.tenancy import set_tenant
    from workflow.models import WorkflowEngineDefinition, WorkflowItemState

    from application.models import Adr

    tenant = Tenant.objects.create(name="t-status-seam")
    set_tenant(str(tenant.id))
    workspace = Workspace.objects.create(tenant=tenant, name="ws-status-seam")
    definition = WorkflowEngineDefinition.objects.create(
        tenant=tenant,
        workspace_id=workspace.id,
        item_type="Adr",
        definition_json={"states": ["Draft", "outdated"], "transitions": []},
    )
    created = []
    for state in ("Draft", "outdated"):
        artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="Adr"
        )
        adr = Adr.objects.create(
            artifact=artifact,
            workspace_id=workspace.id,
            tenant_id=tenant.id,
            title=f"ADR {state}",
            description="d",
        )
        WorkflowItemState.objects.create(
            tenant=tenant,
            item_id=adr.id,
            item_type="Adr",
            workspace_id=workspace.id,
            definition=definition,
            current_state=state,
        )
        created.append(adr.id)
    ctx = AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        roles=["admin"],
        workspace_id=workspace.id,
    )
    return ctx, workspace.id, created[0], created[1]


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_no_status_column_filter_remains(module):
    source = inspect.getsource(module)
    assert 'exclude(status="outdated")' not in source
    assert "status=status," not in source


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_module_imports_the_seam(module):
    assert "from workflow import state_reader" in inspect.getsource(module)


@pytest.mark.django_db
class TestAdrListing:
    def test_outdated_adr_is_excluded_by_default(self, adr_fixture):
        from application.adr_service import AdrService

        ctx, workspace_id, live_id, outdated_id = adr_fixture
        ids = {a.id for a in AdrService().list_adrs(workspace_id, ctx)}

        assert live_id in ids
        assert outdated_id not in ids

    def test_include_deleted_returns_both(self, adr_fixture):
        from application.adr_service import AdrService

        ctx, workspace_id, live_id, outdated_id = adr_fixture
        ids = {
            a.id
            for a in AdrService().list_adrs(workspace_id, ctx, include_deleted=True)
        }

        assert {live_id, outdated_id} <= ids

    def test_list_by_status_matches_engine_state(self, adr_fixture):
        from application.adr_service import AdrService

        ctx, workspace_id, live_id, outdated_id = adr_fixture
        result = AdrService().list_adrs_by_status(workspace_id, "outdated", ctx)

        assert [a.id for a in result] == [outdated_id]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test pytest application/tests/test_status_seam_services.py -v`
Expected: FAIL — `assert 'exclude(status="outdated")' not in source` fails for `application.adr_service`.

- [ ] **Step 3: Implement `adr_service.py`**

Add to the imports of `backend/application/adr_service.py`:

```python
from workflow import state_reader
```

Replace the filter block in `list_adrs` (lines 409-418):

```python
        self._set_tenant_context(ctx)
        qs = Adr.objects.filter(workspace_id=workspace_id, tenant_id=ctx.tenant_id)
        if not include_deleted:
            # Datenmodell-Konsolidierung Phase 1: soft-delete routes through
            # workflow.services.outdate(); the state is read from
            # WorkflowItemState now that the Adr.status column is gone.
            qs = qs.exclude(
                id__in=state_reader.item_ids_in_state(
                    "Adr", "outdated", tenant_id=ctx.tenant_id
                )
            )
        return qs.order_by("created_at")
```

Replace the body of `list_adrs_by_status` (lines 433-440):

```python
        self._set_tenant_context(ctx)
        return list(
            Adr.objects.filter(
                workspace_id=workspace_id,
                tenant_id=ctx.tenant_id,
                id__in=state_reader.item_ids_in_state(
                    "Adr", status, tenant_id=ctx.tenant_id
                ),
            ).order_by("created_at")
        )
```

Change the DTO builder that currently reads `status=adr.status,` (line 83) so the value is injected instead of read from the row:

```python
    @classmethod
    def from_orm(cls, adr: "Adr", *, status: str = "") -> "AdrDTO":
        """Build a DTO. ``status`` comes from the workflow engine (Phase 1)."""
        return cls(
            id=adr.id,
            title=adr.title,
            description=adr.description,
            context=adr.context,
            decision=adr.decision,
            consequences=adr.consequences,
            uid=adr.uid,
            status=status,
            version=adr.version,
            created_at=adr.created_at,
            updated_at=adr.updated_at,
            workspace_id=adr.workspace_id,
            artifact_id=adr.artifact_id,
        )
```

At every `from_orm` call site inside `adr_service.py`, pass the resolved value:

```python
        return AdrDTO.from_orm(
            adr, status=state_reader.current_state("Adr", adr.id) or ""
        )
```

- [ ] **Step 4: Implement `risk_service.py`**

Add `from workflow import state_reader` to the imports. In `list_risks`, replace the soft-delete exclusion:

```python
            qs = qs.exclude(
                id__in=state_reader.item_ids_in_state(
                    "Risk", "outdated", tenant_id=ctx.tenant_id
                )
            )
```

In `list_risks_by_status`, replace the `status=status,` filter keyword:

```python
                id__in=state_reader.item_ids_in_state(
                    "Risk", status, tenant_id=ctx.tenant_id
                ),
```

In the Risk DTO builder, replace `status=risk.status,` with a keyword-only `status: str = ""` parameter (same shape as `AdrDTO.from_orm` above) and pass `state_reader.current_state("Risk", risk.id) or ""` at every call site.

- [ ] **Step 5: Implement `issue_service.py`**

Add `from workflow import state_reader` to the imports. In `list_issues`:

```python
            qs = qs.exclude(
                id__in=state_reader.item_ids_in_state(
                    "Issue", "outdated", tenant_id=ctx.tenant_id
                )
            )
```

In `list_issues_by_status`:

```python
                id__in=state_reader.item_ids_in_state(
                    "Issue", status, tenant_id=ctx.tenant_id
                ),
```

In the Issue DTO builder, replace `status=issue.status,` with a keyword-only `status: str = ""` parameter and pass `state_reader.current_state("Issue", issue.id) or ""` at every call site.

- [ ] **Step 6: Run test to verify it passes**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test pytest application/tests/test_status_seam_services.py -v`
Expected: PASS (9 tests)

- [ ] **Step 7: Run the three services' own suites**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test pytest application/tests/test_adr_service.py application/tests/test_risk_service.py application/tests/test_issue_service.py -q`
Expected: PASS. Tests that patch `Adr.objects` with a `MagicMock` and assert `filter(status=...)` kwargs must be updated to assert `id__in` — that is the intended contract change, not a regression.

- [ ] **Step 8: Commit**

```bash
git add backend/application/adr_service.py backend/application/risk_service.py backend/application/issue_service.py backend/application/tests/test_status_seam_services.py
git commit -m "refactor: read adr/risk/issue status from the workflow engine"
```

---

### Task 5: Goal and MainGoal services read the engine

**Files:**
- Modify: `backend/application/goal_service.py:158` (create), `:268-296` (`list_current`), `:299-335` (`list_effective`) and its dict builder
- Modify: `backend/application/main_goal_service.py:151`, `:213-221`, `:365`, `:410` and its dict builder
- Test: `backend/application/tests/test_goal_status_seam.py`

**Interfaces:**
- Consumes: `workflow.state_reader.item_ids_in_state(item_type, state, *, tenant_id)`, `workflow.state_reader.current_state(item_type, item_id)` (Task 1).
- Produces: `GoalService.list_current`, `GoalService.list_effective`, `MainGoalService.get_current` — unchanged signatures.

`Entwurf` / `Freigegeben` / `Archiviert` are the declared states of the `goal_default` preset (verified finding V-6), not a bug. They stay exactly as they are; only the column read is replaced. The hardcoded model default `"Entwurf"` disappears with the column in Task 12.

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_goal_status_seam.py`:

```python
"""Goal/MainGoal effective-version selection runs off the workflow engine.

Datenmodell-Konsolidierung Phase 1. The German state names (Entwurf /
Freigegeben / Archiviert) are the goal_default preset's declared states and are
deliberately unchanged.
"""
import inspect
import uuid

import pytest

from application import goal_service, main_goal_service


@pytest.fixture
def goal_env(db):
    from auth_tenancy.context import AuthContext
    from persistence.models import Tenant, Workspace
    from persistence.tenancy import set_tenant
    from workflow.models import WorkflowEngineDefinition

    tenant = Tenant.objects.create(name="t-goal-seam")
    set_tenant(str(tenant.id))
    workspace = Workspace.objects.create(tenant=tenant, name="ws-goal-seam")
    definition = WorkflowEngineDefinition.objects.create(
        tenant=tenant,
        workspace_id=workspace.id,
        item_type="Goal",
        definition_json={
            "states": ["Entwurf", "Freigegeben", "Archiviert"],
            "transitions": [],
        },
    )
    ctx = AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        roles=["admin"],
        workspace_id=workspace.id,
    )
    return tenant, workspace, definition, ctx


def make_goal(env, lineage_id, sequence_number, state):
    from persistence.models import Artifact
    from workflow.models import WorkflowItemState

    from application.models import Goal

    tenant, workspace, definition, _ctx = env
    artifact = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="Goal"
    )
    goal = Goal.objects.create(
        artifact=artifact,
        tenant_id=tenant.id,
        workspace_id=workspace.id,
        title=f"G{sequence_number}",
        description="d",
        lineage_id=lineage_id,
        sequence_number=sequence_number,
    )
    WorkflowItemState.objects.create(
        tenant=tenant,
        item_id=goal.id,
        item_type="Goal",
        workspace_id=workspace.id,
        definition=definition,
        current_state=state,
    )
    return goal.id


def test_goal_service_has_no_status_column_filter():
    source = inspect.getsource(goal_service)
    assert "status=APPROVED_STATE" not in source
    assert "status=ARCHIVED_STATE" not in source
    assert "from workflow import state_reader" in source


def test_main_goal_service_has_no_status_column_filter():
    source = inspect.getsource(main_goal_service)
    assert 'status="Entwurf"' not in source
    assert 'status="Freigegeben"' not in source
    assert "from workflow import state_reader" in source


@pytest.mark.django_db
class TestListEffective:
    def test_only_approved_lineage_head_is_effective(self, goal_env):
        from application.goal_service import GoalService

        _tenant, workspace, _definition, ctx = goal_env
        lineage = uuid.uuid4()
        approved_id = make_goal(goal_env, lineage, 1, "Freigegeben")
        make_goal(goal_env, lineage, 2, "Entwurf")

        result = GoalService().list_effective(workspace.id, ctx)

        assert [g.id for g in result] == [approved_id]

    def test_never_approved_lineage_contributes_nothing(self, goal_env):
        from application.goal_service import GoalService

        _tenant, workspace, _definition, ctx = goal_env
        make_goal(goal_env, uuid.uuid4(), 1, "Entwurf")

        assert GoalService().list_effective(workspace.id, ctx) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test pytest application/tests/test_goal_status_seam.py -v`
Expected: FAIL — `assert "status=APPROVED_STATE" not in source`

- [ ] **Step 3: Implement `goal_service.py`**

Add `from workflow import state_reader` to the imports. Replace the `approved_ids` query in `list_effective` (lines 326-335):

```python
        self._set_tenant_context(ctx)
        approved_ids = (
            Goal.objects.filter(
                workspace_id=workspace_id,
                tenant_id=ctx.tenant_id,
                id__in=state_reader.item_ids_in_state(
                    "Goal", APPROVED_STATE, tenant_id=ctx.tenant_id
                ),
            )
            .order_by("lineage_id", "-sequence_number")
            .distinct("lineage_id")
            .values_list("id", flat=True)
        )
        return list(Goal.objects.filter(id__in=list(approved_ids)))
```

In `list_current`, replace the `Archiviert` exclusion:

```python
            qs = qs.exclude(
                id__in=state_reader.item_ids_in_state(
                    "Goal", ARCHIVED_STATE, tenant_id=ctx.tenant_id
                )
            )
```

At line 158, delete the `status=DRAFT_STATE,` keyword from `Goal.objects.create(...)` — the initial state now comes solely from the workflow definition's `initial_state`, which `initialize_workflow_states` already writes.

In the Goal dict builder, replace `"status": goal.status,` with:

```python
            "status": state_reader.current_state("Goal", goal.id) or "",
```

- [ ] **Step 4: Implement `main_goal_service.py`**

Add `from workflow import state_reader` to the imports. In `get_current` (line 151) and in the aggregation guard (lines 213-221), replace the `status=` filters:

```python
        approved = (
            MainGoal.objects.filter(
                workspace_id=workspace_id,
                tenant_id=ctx.tenant_id,
                id__in=state_reader.item_ids_in_state(
                    "MainGoal", "Freigegeben", tenant_id=ctx.tenant_id
                ),
            )
            .order_by("-sequence_number")
            .first()
        )
```

At lines 365 and 410, delete the `status="Entwurf",` keyword from the `MainGoal.objects.create(...)` calls.

In the MainGoal dict builder, replace `"status": mg.status,` with:

```python
            "status": state_reader.current_state("MainGoal", mg.id) or "",
```

- [ ] **Step 5: Run test to verify it passes**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test pytest application/tests/test_goal_status_seam.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Run the Goal/MainGoal suites**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test pytest application/tests/test_goal_service.py application/tests/test_main_goal_service.py mcp_server/tests/test_goal_lifecycle_issue346.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/application/goal_service.py backend/application/main_goal_service.py backend/application/tests/test_goal_status_seam.py
git commit -m "refactor: read goal status from the workflow engine"
```

---

### Task 6: Requirement, StakeholderNeed and TestCase services read the engine

**Files:**
- Modify: `backend/application/requirement_service.py:624` and its DTO builder
- Modify: `backend/application/stakeholder_need_service.py:172` and its DTO builder
- Modify: `backend/application/test_service.py` (TestCase list + DTO builder)
- Test: `backend/application/tests/test_requirement_status_seam.py`

**Interfaces:**
- Consumes: `workflow.state_reader.item_ids_in_state(item_type, state, *, tenant_id)`, `workflow.state_reader.current_state(item_type, item_id)` (Task 1).
- Produces: `RequirementService.list_requirements`, `StakeholderNeedService.list_needs`, `TestService.list_test_cases` — unchanged signatures.

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_requirement_status_seam.py`:

```python
"""Requirement/Need/TestCase listing filters via the workflow engine.

Datenmodell-Konsolidierung Phase 1.
"""
import inspect
import uuid

import pytest

from application import requirement_service, stakeholder_need_service, test_service

MODULES = [requirement_service, stakeholder_need_service, test_service]


@pytest.fixture
def requirement_fixture(db):
    from auth_tenancy.context import AuthContext
    from persistence.models import Artifact, Requirement, Tenant, Workspace
    from persistence.tenancy import set_tenant
    from workflow.models import WorkflowEngineDefinition, WorkflowItemState

    tenant = Tenant.objects.create(name="t-req-seam")
    set_tenant(str(tenant.id))
    workspace = Workspace.objects.create(tenant=tenant, name="ws-req-seam")
    definition = WorkflowEngineDefinition.objects.create(
        tenant=tenant,
        workspace_id=workspace.id,
        item_type="Requirement",
        definition_json={"states": ["draft", "outdated"], "transitions": []},
    )
    created = []
    for state in ("draft", "outdated"):
        artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="Requirement"
        )
        req = Requirement.objects.create(
            tenant=tenant,
            artifact=artifact,
            workspace=workspace,
            title=f"REQ {state}",
            description="d",
        )
        WorkflowItemState.objects.create(
            tenant=tenant,
            item_id=req.id,
            item_type="Requirement",
            workspace_id=workspace.id,
            definition=definition,
            current_state=state,
        )
        created.append(req.id)
    ctx = AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        roles=["admin"],
        workspace_id=workspace.id,
    )
    return ctx, workspace.id, created[0], created[1]


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_no_status_column_read_remains(module):
    source = inspect.getsource(module)
    assert 'exclude(status="outdated")' not in source
    assert "status=status," not in source
    assert "from workflow import state_reader" in source


@pytest.mark.django_db
def test_outdated_requirement_is_excluded(requirement_fixture):
    from application.requirement_service import RequirementService

    ctx, workspace_id, live_id, outdated_id = requirement_fixture
    ids = {r.id for r in RequirementService().list_requirements(workspace_id, ctx)}

    assert live_id in ids
    assert outdated_id not in ids


@pytest.mark.django_db
def test_include_deleted_returns_outdated(requirement_fixture):
    from application.requirement_service import RequirementService

    ctx, workspace_id, live_id, outdated_id = requirement_fixture
    ids = {
        r.id
        for r in RequirementService().list_requirements(
            workspace_id, ctx, include_deleted=True
        )
    }

    assert {live_id, outdated_id} <= ids
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test pytest application/tests/test_requirement_status_seam.py -v`
Expected: FAIL — `assert "from workflow import state_reader" in source`

- [ ] **Step 3: Implement `requirement_service.py`**

Add `from workflow import state_reader` to the imports. Replace the soft-delete exclusion around line 624:

```python
        if not include_deleted:
            # Datenmodell-Konsolidierung Phase 1: the Requirement.status column
            # is gone; "outdated" lives only in WorkflowItemState.
            qs = qs.exclude(
                id__in=state_reader.item_ids_in_state(
                    "Requirement", "outdated", tenant_id=ctx.tenant_id
                )
            )
```

In the Requirement DTO builder, replace `status=req.status,` with:

```python
            status=state_reader.current_state("Requirement", req.id) or "",
```

- [ ] **Step 4: Implement `stakeholder_need_service.py`**

Add `from workflow import state_reader` to the imports. Replace the exclusion around line 172:

```python
            qs = qs.exclude(
                id__in=state_reader.item_ids_in_state(
                    "StakeholderNeed", "outdated", tenant_id=ctx.tenant_id
                )
            )
```

In the Need DTO builder, replace `status=need.status,` with:

```python
            status=state_reader.current_state("StakeholderNeed", need.id) or "",
```

- [ ] **Step 5: Implement `test_service.py`**

Add `from workflow import state_reader` to the imports. Replace the TestCase soft-delete exclusion:

```python
            qs = qs.exclude(
                id__in=state_reader.item_ids_in_state(
                    "TestCase", "outdated", tenant_id=ctx.tenant_id
                )
            )
```

In the TestCase DTO builder, replace `status=tc.status,` with:

```python
            status=state_reader.current_state("TestCase", tc.id) or "",
```

- [ ] **Step 6: Run test to verify it passes**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test pytest application/tests/test_requirement_status_seam.py -v`
Expected: PASS (5 tests)

- [ ] **Step 7: Run the three services' suites**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test pytest application/tests/test_requirement_service.py application/tests/test_stakeholder_need_service.py application/tests/test_test_service.py -q`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add backend/application/requirement_service.py backend/application/stakeholder_need_service.py backend/application/test_service.py backend/application/tests/test_requirement_status_seam.py
git commit -m "refactor: read requirement/need/testcase status from the engine"
```

---

### Task 7: ChangeRequest service reads the engine

**Files:**
- Modify: `backend/application/change_request_service.py:445-470` (`list_change_requests`), `:558-572` (`transition`)
- Test: `backend/application/tests/test_change_request_status_seam.py`

**Interfaces:**
- Consumes: `workflow.state_reader.item_ids_in_state(item_type, state, *, tenant_id)`, `workflow.state_reader.current_state(item_type, item_id)` (Task 1).
- Produces: `ChangeRequestService.list_change_requests(workspace_id, ctx, *, status_filter=None, include_deleted=False)` — unchanged signature.

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_change_request_status_seam.py`:

```python
"""ChangeRequest listing/transition run off the workflow engine.

Datenmodell-Konsolidierung Phase 1.
"""
import inspect
import uuid

import pytest

from application import change_request_service


@pytest.fixture
def cr_fixture(db):
    from auth_tenancy.context import AuthContext
    from persistence.models import Tenant, Workspace
    from persistence.tenancy import set_tenant
    from workflow.models import WorkflowEngineDefinition, WorkflowItemState

    from application.models import ChangeRequest

    tenant = Tenant.objects.create(name="t-cr-seam")
    set_tenant(str(tenant.id))
    workspace = Workspace.objects.create(tenant=tenant, name="ws-cr-seam")
    definition = WorkflowEngineDefinition.objects.create(
        tenant=tenant,
        workspace_id=workspace.id,
        item_type="ChangeRequest",
        definition_json={
            "states": ["draft", "under_review", "outdated"],
            "transitions": [],
        },
    )
    created = {}
    for state in ("draft", "under_review", "outdated"):
        cr = ChangeRequest.objects.create(
            workspace_id=workspace.id,
            tenant_id=tenant.id,
            title=f"CR {state}",
        )
        WorkflowItemState.objects.create(
            tenant=tenant,
            item_id=cr.id,
            item_type="ChangeRequest",
            workspace_id=workspace.id,
            definition=definition,
            current_state=state,
        )
        created[state] = cr.id
    ctx = AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        roles=["admin"],
        workspace_id=workspace.id,
    )
    return ctx, workspace.id, created


def test_no_status_column_read_remains():
    source = inspect.getsource(change_request_service)
    assert "status=status_filter" not in source
    assert 'exclude(status="outdated")' not in source
    assert 'refresh_from_db(fields=["version", "status", "change_reason"])' not in source
    assert "from workflow import state_reader" in source


@pytest.mark.django_db
def test_outdated_is_excluded_by_default(cr_fixture):
    from application.change_request_service import ChangeRequestService

    ctx, workspace_id, created = cr_fixture
    ids = {
        cr.id
        for cr in ChangeRequestService().list_change_requests(workspace_id, ctx)
    }

    assert created["draft"] in ids
    assert created["outdated"] not in ids


@pytest.mark.django_db
def test_status_filter_matches_engine_state(cr_fixture):
    from application.change_request_service import ChangeRequestService

    ctx, workspace_id, created = cr_fixture
    result = ChangeRequestService().list_change_requests(
        workspace_id, ctx, status_filter="under_review"
    )

    assert [cr.id for cr in result] == [created["under_review"]]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test pytest application/tests/test_change_request_status_seam.py -v`
Expected: FAIL — `assert "from workflow import state_reader" in source`

- [ ] **Step 3: Implement `list_change_requests`**

Add `from workflow import state_reader` to the imports. Replace the filter block:

```python
        self._set_tenant_context(ctx)
        qs = ChangeRequest.objects.filter(
            workspace_id=workspace_id, tenant_id=ctx.tenant_id
        )
        if status_filter:
            qs = qs.filter(
                id__in=state_reader.item_ids_in_state(
                    "ChangeRequest", status_filter, tenant_id=ctx.tenant_id
                )
            )
        if not include_deleted:
            qs = qs.exclude(
                id__in=state_reader.item_ids_in_state(
                    "ChangeRequest", "outdated", tenant_id=ctx.tenant_id
                )
            )
        return qs.order_by("created_at")
```

Update the `include_deleted` docstring paragraph (lines 448-451) to drop the `_STATUS_MIRROR_MODELS` reference:

```python
            include_deleted: If True, include outdated ChangeRequests.
                delete_change_request() routes through
                workflow.services.outdate(); the "outdated" state is read from
                WorkflowItemState (Datenmodell-Konsolidierung Phase 1).
                Excluded by default.
```

- [ ] **Step 4: Implement the `transition` refresh fix**

Replace the mirror comment and the `refresh_from_db` call (lines 562-570):

```python
        # Datenmodell-Konsolidierung Phase 1: the ChangeRequest.status column is
        # gone. WorkflowItemState alone holds the state, so nothing has to be
        # refreshed back onto the row after a transition.
        update_fields: Dict[str, Any] = {"version": F("version") + 1}
        if change_reason is not None:
            update_fields["change_reason"] = change_reason
        ChangeRequest.objects.filter(id=cr.id).update(**update_fields)
        cr.refresh_from_db(fields=["version", "change_reason"])
```

In the ChangeRequest DTO/dict builder, replace `"status": cr.status,` with:

```python
            "status": state_reader.current_state("ChangeRequest", cr.id) or "",
```

- [ ] **Step 5: Run test to verify it passes**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test pytest application/tests/test_change_request_status_seam.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Run the ChangeRequest and CCB suites**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test pytest application/tests/ -k "change_request or ccb" -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/application/change_request_service.py backend/application/tests/test_change_request_status_seam.py
git commit -m "refactor: read change request status from the workflow engine"
```

---

### Task 8: Baseline state capture reads the engine

**Files:**
- Modify: `backend/baseline/state_capture.py:142` (Requirement), `:180` (StakeholderNeed), `:198` (TestCase), `:277` (Adr), `:296` (Risk), `:311` (Issue), `:322` (Goal), `:333` (MainGoal)
- Test: `backend/baseline/tests/test_state_capture_status_seam.py`

**Interfaces:**
- Consumes: `workflow.state_reader.current_states(item_type: str, item_ids) -> dict[str, str]` (Task 1).
- Produces: module-level helper `_engine_status(item_type: str, entity_ids: list) -> dict[str, str]` in `state_capture.py`; the captured `states[...]["status"]` values keep their existing key and vocabulary.

`state_capture` keys its output by `artifact_id` but the workflow engine keys by *entity* id, so the lookup runs on entity ids and the result is applied per row. `TestRun.status` (`:465`) and `TestRunResult.status` (`:500`) are **not** artifact lifecycle status — they stay untouched.

- [ ] **Step 1: Write the failing test**

Create `backend/baseline/tests/test_state_capture_status_seam.py`:

```python
"""Baseline snapshots capture the engine state, not a mirror column.

Datenmodell-Konsolidierung Phase 1. A missed reader here silently freezes a
stale status into an immutable baseline, so this is asserted structurally as
well as behaviourally.
"""
import inspect
import uuid

import pytest

from baseline import state_capture


def test_no_entity_status_attribute_read_remains():
    source = inspect.getsource(state_capture)
    for expr in (
        '"status": req.status',
        '"status": sn.status',
        '"status": tc.status',
        '"status": adr.status',
        '"status": risk.status',
        '"status": issue.status',
        '"status": goal.status',
        '"status": mg.status',
    ):
        assert expr not in source, f"{expr} still reads the dropped column"


def test_test_run_status_is_untouched():
    source = inspect.getsource(state_capture)
    assert '"status": tr.status' in source
    assert '"status": trr.status' in source


@pytest.mark.django_db
def test_requirement_snapshot_carries_the_engine_state(capture_fixture):
    tenant_id, artifact_id, req_id = capture_fixture

    states = state_capture.capture_states([artifact_id], tenant_id=tenant_id)

    assert states[str(artifact_id)]["status"] == "approved"
```

Add the fixture:

```python
@pytest.fixture
def capture_fixture(db):
    from persistence.models import Artifact, Requirement, Tenant, Workspace
    from persistence.tenancy import set_tenant
    from workflow.models import WorkflowEngineDefinition, WorkflowItemState

    tenant = Tenant.objects.create(name="t-capture-seam")
    set_tenant(str(tenant.id))
    workspace = Workspace.objects.create(tenant=tenant, name="ws-capture-seam")
    artifact = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="Requirement"
    )
    req = Requirement.objects.create(
        tenant=tenant,
        artifact=artifact,
        workspace=workspace,
        title="REQ",
        description="d",
    )
    definition = WorkflowEngineDefinition.objects.create(
        tenant=tenant,
        workspace_id=workspace.id,
        item_type="Requirement",
        definition_json={"states": ["draft", "approved"], "transitions": []},
    )
    WorkflowItemState.objects.create(
        tenant=tenant,
        item_id=req.id,
        item_type="Requirement",
        workspace_id=workspace.id,
        definition=definition,
        current_state="approved",
    )
    return tenant.id, artifact.id, req.id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test pytest baseline/tests/test_state_capture_status_seam.py -v`
Expected: FAIL — `'"status": req.status' still reads the dropped column`

- [ ] **Step 3: Add the helper**

Add to the imports of `backend/baseline/state_capture.py`:

```python
from workflow import state_reader
```

and define, just below the module's other private helpers:

```python
def _engine_status(item_type: str, entity_ids: list) -> dict[str, str]:
    """Resolve the workflow state of *entity_ids* keyed by ``str(entity_id)``.

    Datenmodell-Konsolidierung Phase 1: baselines used to snapshot the
    denormalized ``status`` column. That column is gone; the engine is the
    single source of truth. One query per entity type keeps capture O(types),
    not O(rows).
    """
    return state_reader.current_states(item_type, entity_ids)
```

- [ ] **Step 4: Rewrite the eight capture blocks**

Each block currently iterates a queryset and reads `entity.status`. Materialise the rows first, resolve once, then read from the mapping. Requirement (lines 132-150) becomes:

```python
    # Requirement
    requirements = list(
        Requirement.unscoped.filter(artifact_id__in=uuids, tenant_id=tenant_id)
    )
    req_states = _engine_status("Requirement", [r.id for r in requirements])
    for req in requirements:
        states[str(req.artifact_id)] = {
            "artifact_type": "requirement",
            "uid": req.uid,
            "title": req.title,
            "description": req.description,
            "acceptance_criteria": req.acceptance_criteria,
            "category": req.category,
            "status": req_states.get(str(req.id), ""),
            "type": req.type,
            "level": req.level,
            "complexity_fibonacci": req.complexity_fibonacci,
            "verification_method": req.verification_method,
            "suspect": req.suspect,
            "lifecycle_status": req.lifecycle_status,
            "version": req.version,
        }
```

Apply the identical three-line pattern (materialise → `_engine_status(<ItemType>, ids)` → `.get(str(entity.id), "")`) to the seven remaining blocks, using these item types: `StakeholderNeed` (`sn`, line 180), `TestCase` (`tc`, line 198), `Adr` (`adr`, line 277), `Risk` (`risk`, line 296), `Issue` (`issue`, line 311), `Goal` (`goal`, line 322), `MainGoal` (`mg`, line 333). Leave the `TestRun` (line 465) and `TestRunResult` (line 500) blocks unchanged — those are execution statuses, not artifact lifecycle.

- [ ] **Step 5: Run test to verify it passes**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test pytest baseline/tests/test_state_capture_status_seam.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Run the baseline suite**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test pytest baseline/ -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/baseline/state_capture.py backend/baseline/tests/test_state_capture_status_seam.py
git commit -m "refactor: capture baseline status from the workflow engine"
```

---

### Task 9: MCP tool groups read the engine

**Files:**
- Modify: `backend/mcp_server/tool_registry.py` and the per-type tool groups that build `status` into a payload
- Test: `backend/mcp_server/tests/test_status_seam_tools.py`

**Interfaces:**
- Consumes: `workflow.state_reader.current_state(item_type: str, item_id) -> str | None` (Task 1). Item types used: `"Requirement"`, `"StakeholderNeed"`, `"TestCase"`, `"Adr"`, `"Risk"`, `"Issue"`, `"ChangeRequest"`, `"Goal"`, `"MainGoal"`.
- Produces: unchanged tool payload shape — `status` stays a top-level string key with the same vocabulary (Decision D-1).

Reminder from prior incidents: an MCP tool payload must never use the key `content`, must have the same shape on hit and on miss, and every value must be stdlib-`json.dumps`-serialisable (no `UUID`/`datetime` objects).

- [ ] **Step 1: Locate every payload site**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test grep -rn '"status": ' --include=*.py mcp_server/ | grep -v tests`
Expected: a list of `_*_to_dict` helpers. Record it — every line in that list is edited in Step 3.

- [ ] **Step 2: Write the failing test**

Create `backend/mcp_server/tests/test_status_seam_tools.py`:

```python
"""MCP payloads carry the engine state, not a dropped mirror column.

Datenmodell-Konsolidierung Phase 1.
"""
import json
import pathlib

import pytest

MCP_ROOT = pathlib.Path(__file__).resolve().parent.parent

FORBIDDEN = (
    ".status,",
    ".status}",
    ".status)",
)


def _production_sources():
    for path in MCP_ROOT.rglob("*.py"):
        if "tests" in path.parts:
            continue
        yield path


@pytest.mark.parametrize("path", sorted(_production_sources()), ids=lambda p: p.name)
def test_no_entity_status_attribute_access(path):
    text = path.read_text(encoding="utf-8")
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        for token in FORBIDDEN:
            assert f"entity{token}" not in stripped


@pytest.mark.django_db
def test_requirement_payload_is_json_serialisable_and_has_status(requirement_tool_env):
    from mcp_server.tool_registry import ToolRegistry

    ctx, requirement_id = requirement_tool_env
    result = ToolRegistry().dispatch(
        "requirement.get", {"requirement_id": str(requirement_id)}, ctx
    )

    payload = result.payload
    assert "content" not in payload
    assert payload["status"] == "approved"
    json.dumps(payload)
```

Add the fixture:

```python
@pytest.fixture
def requirement_tool_env(db):
    import uuid

    from auth_tenancy.context import AuthContext
    from persistence.models import Artifact, Requirement, Tenant, Workspace
    from persistence.tenancy import set_tenant
    from workflow.models import WorkflowEngineDefinition, WorkflowItemState

    tenant = Tenant.objects.create(name="t-mcp-seam")
    set_tenant(str(tenant.id))
    workspace = Workspace.objects.create(tenant=tenant, name="ws-mcp-seam")
    artifact = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="Requirement"
    )
    req = Requirement.objects.create(
        tenant=tenant,
        artifact=artifact,
        workspace=workspace,
        title="REQ",
        description="d",
    )
    definition = WorkflowEngineDefinition.objects.create(
        tenant=tenant,
        workspace_id=workspace.id,
        item_type="Requirement",
        definition_json={"states": ["draft", "approved"], "transitions": []},
    )
    WorkflowItemState.objects.create(
        tenant=tenant,
        item_id=req.id,
        item_type="Requirement",
        workspace_id=workspace.id,
        definition=definition,
        current_state="approved",
    )
    ctx = AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        roles=["admin"],
        workspace_id=workspace.id,
    )
    return ctx, req.id
```

- [ ] **Step 3: Run test to verify it fails**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test pytest mcp_server/tests/test_status_seam_tools.py -v`
Expected: FAIL — at least one `_*_to_dict` still reads `entity.status`.

- [ ] **Step 4: Write the implementation**

Every MCP payload builder already receives a DTO from the service layer (Tasks 4-7), which now carries the engine-resolved value. Where a builder reads the ORM row directly instead of the DTO, add to that module's imports:

```python
from workflow import state_reader
```

and replace the read, e.g. in the ADR payload builder:

```python
        "status": state_reader.current_state("Adr", adr.id) or "",
```

Repeat for every line recorded in Step 1, using the entity's own item type from the list in **Interfaces** above.

- [ ] **Step 5: Run test to verify it passes**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test pytest mcp_server/tests/test_status_seam_tools.py -v`
Expected: PASS

- [ ] **Step 6: Run the MCP suite**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test pytest mcp_server/ -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/mcp_server/ 
git commit -m "refactor: read mcp payload status from the workflow engine"
```

---

### Task 10: Retire the create-time initial-status parameters

**Files:**
- Modify: `backend/application/adr_service.py:106-118` (`AdrValidator.validate_create`), `:144-210` (`create_adr`)
- Modify: `backend/application/risk_service.py` (`create_risk`), `backend/application/issue_service.py` (`create_issue`)
- Modify: `backend/rest_api/views.py` (`IssueViewSet.create` — it currently forwards a client-supplied initial status)
- Test: `backend/application/tests/test_no_initial_status.py`

**Interfaces:**
- Consumes: `workflow.services.initialize_workflow_states(item_ids: list[UUID], item_type: str, workspace_id: UUID) -> list[WorkflowItemState]` (existing, `workflow/services.py:428`).
- Produces: `AdrService.create_adr(workspace_id, title, description, ctx, context="", decision="", consequences="", uid=None)`, `RiskService.create_risk(...)`, `IssueService.create_issue(...)` — the `status` parameter is **removed** from all three (breaking change, see below).

**Breaking change, named explicitly:** `AdrService.create_adr(..., status=...)`, `RiskService.create_risk(..., status=...)` and `IssueService.create_issue(..., status=...)` lose their `status` keyword. `POST /api/v1/issues/` stops honouring a client-supplied `status`; the item is always created at the workflow definition's `initial_state`. This is the last write path into the removed columns and is required by ADR-status-single-source ("Statusänderungen erfolgen nur noch über die Transition-Endpoints").

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_no_initial_status.py`:

```python
"""No create path accepts or writes an initial status.

Datenmodell-Konsolidierung Phase 1. The workflow definition's initial_state is
the only source of a new item's state (ADR-status-single-source).
"""
import inspect

import pytest

from application.adr_service import AdrService
from application.issue_service import IssueService
from application.risk_service import RiskService

CREATE_METHODS = [
    (AdrService, "create_adr"),
    (RiskService, "create_risk"),
    (IssueService, "create_issue"),
]


@pytest.mark.parametrize(
    "service,method", CREATE_METHODS, ids=lambda v: getattr(v, "__name__", str(v))
)
def test_create_has_no_status_parameter(service, method):
    signature = inspect.signature(getattr(service, method))
    assert "status" not in signature.parameters


def test_adr_validator_has_no_status_check():
    source = inspect.getsource(AdrService)
    assert "VALID_STATUSES" not in source


@pytest.mark.django_db
def test_issue_create_ignores_a_client_supplied_status(api_client_env):
    client, workspace_id = api_client_env

    response = client.post(
        "/api/v1/issues/",
        {
            "workspace_id": str(workspace_id),
            "title": "I1",
            "description": "d",
            "status": "closed",
        },
        format="json",
    )

    assert response.status_code == 201
    assert response.data["status"] != "closed"
```

Reuse the project's existing authenticated-client fixture for `api_client_env`; if the module has none, add:

```python
@pytest.fixture
def api_client_env(db):
    import uuid

    from rest_framework.test import APIClient

    from persistence.models import Tenant, User, Workspace
    from persistence.tenancy import set_tenant

    tenant = Tenant.objects.create(name="t-no-init-status")
    set_tenant(str(tenant.id))
    workspace = Workspace.objects.create(tenant=tenant, name="ws-no-init-status")
    user = User.objects.create(
        tenant=tenant, email=f"u{uuid.uuid4().hex[:8]}@example.com", is_active=True
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return client, workspace.id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test pytest application/tests/test_no_initial_status.py -v`
Expected: FAIL — `assert "status" not in signature.parameters`

- [ ] **Step 3: Implement `adr_service.py`**

Delete the `VALID_STATUSES` class attribute and the status branch from `AdrValidator.validate_create`, which becomes:

```python
    @classmethod
    def validate_create(cls, title: str, description: str) -> None:
        """Validate ADR create input. Status is not an input (Phase 1)."""
        cls._validate_title(title)
        cls._validate_description(description)
```

In `create_adr`, drop the `status: str = "Draft"` parameter, its docstring line, the `status=status` argument to `validate_create`, and the `status=status,` keyword in `Adr.objects.create(...)`:

```python
    def create_adr(
        self,
        workspace_id: UUID,
        title: str,
        description: str,
        ctx: AuthContext,
        context: str = "",
        decision: str = "",
        consequences: str = "",
        uid: Optional[str] = None,
    ) -> Adr:
        ...
        AdrValidator.validate_create(title=title, description=description)
```

Delete the now-unreferenced `class Status(models.TextChoices)` from `Adr` in `application/models.py` (it only enumerated values for the removed column; the workflow definition owns the vocabulary now).

- [ ] **Step 4: Implement `risk_service.py` and `issue_service.py`**

In `RiskService.create_risk`, remove the `status` parameter, its docstring line, and the `status=status,` keyword in `Risk.objects.create(...)`. Delete `Risk`'s `RiskStatus` choices class from `application/models.py`.

In `IssueService.create_issue`, remove the `status` parameter, its docstring line, and the `status=status,` keyword in `Issue.objects.create(...)`. Delete `Issue`'s status choices class from `application/models.py`. Delete `ChangeRequest.Status` from `application/models.py` as well — the `ccb_approval` workflow definition owns those state names.

- [ ] **Step 5: Implement the `IssueViewSet.create` change**

In `backend/rest_api/views.py`, find `IssueViewSet.create` and delete the line that forwards `status` into `create_issue(...)`. Replace the comment block that justified accepting an initial status (serializers.py lines 1564-1571 reference it) with:

```python
        # Datenmodell-Konsolidierung Phase 1: a new Issue always starts at the
        # workflow definition's initial_state. A client-supplied `status` is
        # ignored, not rejected, consistent with ADR-status-single-source.
```

- [ ] **Step 6: Run test to verify it passes**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test pytest application/tests/test_no_initial_status.py -v`
Expected: PASS (5 tests)

- [ ] **Step 7: Run the affected suites**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test pytest application/tests/test_adr_service.py application/tests/test_risk_service.py application/tests/test_issue_service.py rest_api/ -q`
Expected: PASS. Callers passing `status=` now raise `TypeError` — every such call site must be updated in this task, not deferred.

- [ ] **Step 8: Commit**

```bash
git add backend/application/ backend/rest_api/views.py
git commit -m "refactor: drop create-time initial status parameters"
```

---

### Task 11: Delete the status mirror

**Files:**
- Modify: `backend/workflow/lifecycle_manager.py:89-135` (`_STATUS_MIRROR_MODELS`, `_LAYER2_MODEL_MODULES`, `_resolve_mirror_model`), `:540-591` (`_sync_status_mirror`) and its call site inside `perform_transition`/`force_transition`
- Modify: `backend/persistence/models.py:2436-2445` (`InterviewSession.status` help text) — see note
- Delete: `backend/workflow/tests/test_status_mirror_rls_sa22.py`
- Test: `backend/workflow/tests/test_no_status_mirror.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `StateLifecycleManager` without `_sync_status_mirror`. `_sync_lifecycle_mirror` and `_LIFECYCLE_MIRROR_MODELS` stay for now — they are removed in Phase 4 (Task 24).

`InterviewSession` is the eleventh entry in the mirror map. Its `status` is explicitly documented as a mirror of the same engine, is already tracked under `item_type="Interview"`, and is therefore dropped together with the other ten — which lets the map be deleted rather than kept alive for one entry.

- [ ] **Step 1: Write the failing test**

Create `backend/workflow/tests/test_no_status_mirror.py`:

```python
"""The status mirror is gone (Datenmodell-Konsolidierung Phase 1)."""
import inspect

import pytest

from workflow import lifecycle_manager
from workflow.lifecycle_manager import StateLifecycleManager


def test_mirror_map_is_removed():
    assert not hasattr(lifecycle_manager, "_STATUS_MIRROR_MODELS")
    assert not hasattr(lifecycle_manager, "_LAYER2_MODEL_MODULES")
    assert not hasattr(lifecycle_manager, "_resolve_mirror_model")


def test_sync_method_is_removed():
    assert not hasattr(StateLifecycleManager, "_sync_status_mirror")


def test_lifecycle_mirror_still_exists_until_phase_4():
    assert hasattr(lifecycle_manager, "_LIFECYCLE_MIRROR_MODELS")
    assert hasattr(StateLifecycleManager, "_sync_lifecycle_mirror")


def test_no_module_references_the_map():
    source = inspect.getsource(lifecycle_manager)
    assert "_STATUS_MIRROR_MODELS" not in source
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test pytest workflow/tests/test_no_status_mirror.py -v`
Expected: FAIL — `assert not hasattr(lifecycle_manager, "_STATUS_MIRROR_MODELS")`

- [ ] **Step 3: Delete the mirror**

In `backend/workflow/lifecycle_manager.py`, delete:
- the `_STATUS_MIRROR_MODELS` dict (lines 89-104),
- the `_LAYER2_MODEL_MODULES` frozenset (lines 106-108),
- the `_resolve_mirror_model` function (lines 111-135),
- the `_sync_status_mirror` static method (lines 539-591),
- every call to `self._sync_status_mirror(...)` / `StateLifecycleManager._sync_status_mirror(...)` inside the transition methods.

`_sync_lifecycle_mirror` still calls no removed helper (it resolves its two models by direct import), so it keeps working unchanged.

- [ ] **Step 4: Remove the map's remaining references**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test grep -rn "_STATUS_MIRROR_MODELS\|_sync_status_mirror" --include=*.py .`
Expected after edits: only comment text remains. Rewrite each remaining comment so it no longer describes a live mechanism, e.g. in `application/artifact_service.py:59`:

```python
#: Datenmodell-Konsolidierung Phase 1: status is no longer denormalized onto
#: the entity row. WorkflowItemState is the only store; read it through
#: ``workflow.state_reader``.
```

Delete `backend/workflow/tests/test_status_mirror_rls_sa22.py` — it is the regression suite for the removed method. The SA-22 RLS concern remains covered for `_sync_lifecycle_mirror` by `backend/workflow/tests/test_lifecycle_manager.py`; add there, if absent:

```python
    def test_lifecycle_mirror_uses_pk_filter_under_rls(self):
        source = inspect.getsource(StateLifecycleManager._sync_lifecycle_mirror)
        assert "unscoped.filter(pk=" in source
```

In `application/models.py`, delete the `objects = models.Manager()` / `unscoped = models.Manager()` pair and its `REQ-165/REQ-166` comment from `Adr`, `Risk`, `Goal`, `MainGoal`, `Issue` and `ChangeRequest` — those aliases existed only for the mirror. (`application/apps.py`'s `register_models` call stays: `domain_model_registry` is still used by other Layer-1 consumers; it is revisited in Task 15.)

In `persistence/models.py`, replace `InterviewSession.status`'s help text (lines 2437-2444) — the field itself is dropped in Task 12, so this step only removes the stale reference:

```python
        help_text=(
            "Datenmodell-Konsolidierung Phase 1: superseded by "
            "WorkflowItemState(item_type='Interview'). Dropped in "
            "persistence/0070."
        ),
```

- [ ] **Step 5: Run test to verify it passes**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test pytest workflow/tests/test_no_status_mirror.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Run the workflow suite**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test pytest workflow/ -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/workflow/ backend/application/models.py backend/application/artifact_service.py backend/persistence/models.py
git commit -m "refactor: remove the denormalized status mirror"
```

---

### Task 12: Drop the status columns

**Files:**
- Modify: `backend/persistence/models.py:887` (`StakeholderNeed.status`), `:916` (index `idx_sn_tnt_status`), `:964` (`Requirement.status`), `:1037` (index `idx_req_tnt_status`), `:1470` (`TestCase.status`), `:1481` (index `idx_testcase_status`), `:2436` (`InterviewSession.status`), `:2466` (index `idx_iview_ws_status`)
- Modify: `backend/application/models.py:273` (`Adr.status`), `:293` (index `idx_adr_ws_status`), `:410` (`Risk.status`), `:486` (`Goal.status`), `:531` (`MainGoal.status`), `:639` (`Issue.status`), `:704` (`ChangeRequest.status`), `:752` (index `idx_cr_ws_status`) and the sibling `*_ws_status` indexes on Risk/Issue/Goal/MainGoal
- Create: `backend/persistence/migrations/0070_drop_status_mirror_columns.py`
- Create: `backend/application/migrations/0020_drop_status_columns.py`
- Test: `backend/persistence/tests/test_no_status_columns.py`

**Interfaces:**
- Consumes: nothing — this is the schema half of Tasks 4-11.
- Produces: eleven models without a `status` field. `TestRun.status`, `TestRunResult.status` and `WebhookDeliveryLog.status_code` are untouched (not artifact lifecycle).

`RunPython` is not needed: no data is preserved. The values already live in `WorkflowItemState`, which `workflow/0003_reconcile_status_mirror` guaranteed for every row and `_sync_status_mirror` kept true until Task 11.

- [ ] **Step 1: Write the failing test**

Create `backend/persistence/tests/test_no_status_columns.py`:

```python
"""No artifact model carries a status column any more.

Datenmodell-Konsolidierung Phase 1 / Milestone M1. The Attribut-Definition
bootstrap (spec 2026-09-03-attribute-definition-design.md section 3.2)
introspects these models and must not find a status field.
"""
import pytest
from django.apps import apps

ARTIFACT_MODELS = [
    ("persistence", "Requirement"),
    ("persistence", "StakeholderNeed"),
    ("persistence", "TestCase"),
    ("persistence", "InterviewSession"),
    ("application", "Adr"),
    ("application", "Risk"),
    ("application", "Issue"),
    ("application", "ChangeRequest"),
    ("application", "Goal"),
    ("application", "MainGoal"),
]

KEPT_STATUS_MODELS = [
    ("persistence", "TestRun"),
    ("persistence", "TestRunResult"),
]


@pytest.mark.parametrize("app_label,model_name", ARTIFACT_MODELS)
def test_status_field_is_gone(app_label, model_name):
    model = apps.get_model(app_label, model_name)
    names = {field.name for field in model._meta.get_fields()}
    assert "status" not in names


@pytest.mark.parametrize("app_label,model_name", ARTIFACT_MODELS)
def test_status_index_is_gone(app_label, model_name):
    model = apps.get_model(app_label, model_name)
    for index in model._meta.indexes:
        assert "status" not in index.fields, f"{index.name} still indexes status"


@pytest.mark.parametrize("app_label,model_name", KEPT_STATUS_MODELS)
def test_execution_status_is_kept(app_label, model_name):
    model = apps.get_model(app_label, model_name)
    names = {field.name for field in model._meta.get_fields()}
    assert "status" in names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test pytest persistence/tests/test_no_status_columns.py -v`
Expected: FAIL — `assert "status" not in names` for `persistence.Requirement`

- [ ] **Step 3: Remove the model fields and indexes**

In `backend/persistence/models.py`, delete these lines and nothing else:
- line 887 `status = models.CharField(max_length=64, default="draft")` (StakeholderNeed)
- line 916 `models.Index(fields=["tenant", "status"], name="idx_sn_tnt_status"),`
- line 964 `status = models.CharField(max_length=64, default="draft")` (Requirement)
- line 1037 `models.Index(fields=["tenant", "status"], name="idx_req_tnt_status"),`
- lines 1470-1479 the `TestCase.status` field and the comment block at 1466-1469 explaining its single-column index
- line 1481 `models.Index(fields=["status"], name="idx_testcase_status"),`
- lines 2436-2445 the `InterviewSession.status` field
- line 2466 `models.Index(fields=["workspace", "status"], name="idx_iview_ws_status"),`

In `backend/application/models.py`, delete the `status = models.CharField(...)` declaration from `Adr` (273), `Risk` (410), `Goal` (486), `MainGoal` (531), `Issue` (639) and `ChangeRequest` (704), plus every `models.Index` in those models whose `fields` contains `"status"` (`idx_adr_ws_status` at 293, `idx_cr_ws_status` at 752, and the equivalent entries in Risk/Issue/Goal/MainGoal).

- [ ] **Step 4: Generate the migrations**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test python manage.py makemigrations persistence application --name drop_status_columns`
Expected: creates `persistence/migrations/0070_drop_status_columns.py` and `application/migrations/0020_drop_status_columns.py` containing only `RemoveIndex` + `RemoveField` operations.

Rename the persistence file to `0070_drop_status_mirror_columns.py` (and its `name` in any later `dependencies`) so it reads as what it is. Verify the generated content is exactly `RemoveIndex` then `RemoveField` — a `RunPython` or `AlterField` in the diff means a model edit was missed.

- [ ] **Step 5: Run the migrations**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test python manage.py migrate`
Expected: `Applying persistence.0070_drop_status_mirror_columns... OK` and `Applying application.0020_drop_status_columns... OK`

- [ ] **Step 6: Run test to verify it passes**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test pytest persistence/tests/test_no_status_columns.py -v`
Expected: PASS (22 tests)

- [ ] **Step 7: Commit**

```bash
git add backend/persistence/ backend/application/models.py backend/application/migrations/
git commit -m "feat: drop the legacy status columns"
```

---

### Task 13: Milestone M1 gate

**Files:**
- Create: `backend/persistence/tests/test_milestone_m1_gate.py`

**Interfaces:**
- Consumes: `workflow.state_reader.current_state`, `workflow.state_reader.current_states`, `workflow.state_reader.item_ids_in_state` (Task 1); the schema state after Task 12.
- Produces: an executable, permanent assertion that M1 holds. The Attribut-Definition plan references this test file by path as its precondition.

- [ ] **Step 1: Write the gate test**

Create `backend/persistence/tests/test_milestone_m1_gate.py`:

```python
"""Milestone M1 gate — legacy status columns are gone, end to end.

Datenmodell-Konsolidierung Phase 1. The Attribut-Definition plan
(docs/superpowers/specs/2026-09-03-attribute-definition-design.md, section 3.2)
runs a bootstrap that introspects the artifact models. Its migration MUST NOT
run before this test is green on main: a status column present at bootstrap
time is frozen into the generated core-attribute list.
"""
import pytest
from django.apps import apps
from django.db import connection

TABLES = {
    "pl_requirement",
    "pl_stakeholder_need",
    "pl_testcase",
    "pl_interview_session",
    "as_adr",
    "as_risk",
    "as_issue",
    "as_change_request",
    "as_goal",
    "as_main_goal",
}


@pytest.mark.django_db
def test_no_artifact_table_has_a_status_column():
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT table_name
            FROM information_schema.columns
            WHERE column_name = 'status' AND table_name = ANY(%s)
            """,
            [sorted(TABLES)],
        )
        offenders = [row[0] for row in cursor.fetchall()]

    assert offenders == []


@pytest.mark.django_db
def test_the_read_seam_is_the_only_status_source():
    from workflow import state_reader

    assert callable(state_reader.current_state)
    assert callable(state_reader.current_states)
    assert callable(state_reader.item_ids_in_state)


@pytest.mark.django_db
def test_bootstrap_introspection_sees_no_status_field():
    """Exactly the introspection the Attribut-Definition bootstrap performs."""
    for app_label, model_name in [
        ("persistence", "Requirement"),
        ("persistence", "StakeholderNeed"),
        ("persistence", "TestCase"),
        ("application", "Adr"),
        ("application", "Risk"),
        ("application", "Issue"),
        ("application", "Goal"),
    ]:
        model = apps.get_model(app_label, model_name)
        concrete = {f.name for f in model._meta.fields}
        assert "status" not in concrete, f"{app_label}.{model_name}"
```

- [ ] **Step 2: Run the gate**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test pytest persistence/tests/test_milestone_m1_gate.py -v`
Expected: PASS (3 tests)

- [ ] **Step 3: Run the full Phase 1 regression set**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test pytest workflow/ baseline/ application/ rest_api/ mcp_server/ -q`
Expected: PASS

- [ ] **Step 4: Verify in a running stack, not only in tests**

Run: `make up`, then `docker-compose -f deploy/docker-compose.yml --project-directory . exec backend python manage.py seed_demo`, then open `http://localhost:5173`, open a Requirement and a Goal, and confirm the status badge shows the same value it showed before Phase 1 and that a workflow transition still updates it. Green tests alone do not close this task.

- [ ] **Step 5: Commit — Milestone M1**

```bash
git add backend/persistence/tests/test_milestone_m1_gate.py
git commit -m "test: add milestone M1 gate for status consolidation"
```

> **MILESTONE M1 reached.** The Attribut-Definition plan's bootstrap migration
> (spec `2026-09-03-attribute-definition-design.md` §3.2/§4) may now run.
> Its precondition check is `backend/persistence/tests/test_milestone_m1_gate.py`.

---

# Phase 2 — Layer-Bereinigung (spec §3)

Goal: `Adr`, `Risk`, `Goal`, `MainGoal`, `Issue`, `ChangeRequest` (+ `ChangeRequestAffectedItem`) live in `persistence/models.py` on `TenantScopedModel`. Their tables never move — only the Django app label and the base class change.

Three collisions block a naive base-class swap, and all six models have the identical shape (verified: `id`, `version`, `created_by` CharField, `created_at`, `updated_at` at `application/models.py` lines 241/276-279, 344/413-416, 474/487-490, 516/532-535, 601/642-645, 691/719/740-742):

| Local field | Base-class field | Column | Conflict |
|---|---|---|---|
| `id = UUIDField(primary_key=True)` | `AuditableModel.id` | `id` | identical — local must go, no schema change |
| `version = IntegerField(default=1)` | `AuditableModel.version` | `version` | identical — local must go, no schema change |
| `created_at = DateTimeField(auto_now_add=True)` | `AuditableModel.created_at` | `created_at` | identical — local must go, no schema change |
| `created_by = CharField(255)` | `AuditableModel.created_by = FK(User)` | `created_by` vs `created_by_id` | **Python attribute clash** → `FieldError` at import |
| `tenant_id = UUIDField(db_index=True)` | `TenantScopedModel.tenant = FK(Tenant)` | `tenant_id` (both) | same column, gains a FK constraint |
| — | `AuditableModel.modified_at`, `modified_by` | new columns | must be added and backfilled |

`workspace_id` stays a `UUIDField` (Decision D-5) — `TenantScopedModel` provides no `workspace` field.

### Task 14: Reconcile the audit fields in place

**Files:**
- Modify: `backend/application/models.py` — `Adr:277`, `Risk:414`, `Goal:488`, `MainGoal:533`, `Issue:643`, `ChangeRequest:740`
- Create: `backend/application/migrations/0021_reconcile_audit_fields.py`
- Test: `backend/application/tests/test_audit_field_reconciliation.py`

**Interfaces:**
- Consumes: nothing.
- Produces: on all six models — `created_by_name: CharField` (same DB column `created_by`), plus new nullable columns `modified_at: DateTimeField`, `created_by_id: UUID`, `modified_by_id: UUID`. `created_by` as a Python attribute is free for the base-class FK in Task 15.

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_audit_field_reconciliation.py`:

```python
"""Audit-field collisions are cleared before the base-class swap.

Datenmodell-Konsolidierung Phase 2 Task 14.
"""
import pytest
from django.apps import apps

MODELS = ["Adr", "Risk", "Goal", "MainGoal", "Issue", "ChangeRequest"]


@pytest.mark.parametrize("model_name", MODELS)
def test_created_by_char_field_is_renamed(model_name):
    model = apps.get_model("application", model_name)
    field = model._meta.get_field("created_by_name")

    assert field.get_attname_column()[1] == "created_by"
    assert field.max_length == 255


@pytest.mark.parametrize("model_name", MODELS)
def test_created_by_attribute_is_free(model_name):
    model = apps.get_model("application", model_name)
    names = {f.name for f in model._meta.fields}

    assert "created_by" not in names


@pytest.mark.parametrize("model_name", MODELS)
def test_modified_at_exists_and_is_nullable(model_name):
    model = apps.get_model("application", model_name)
    field = model._meta.get_field("modified_at")

    assert field.null is True


@pytest.mark.django_db
def test_modified_at_is_backfilled_from_updated_at():
    from application.models import Adr

    row = Adr.objects.create(
        workspace_id="00000000-0000-0000-0000-000000000001",
        tenant_id="00000000-0000-0000-0000-000000000002",
        title="A",
        description="d",
    )
    row.refresh_from_db()

    assert row.modified_at is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test pytest application/tests/test_audit_field_reconciliation.py -v`
Expected: FAIL — `FieldDoesNotExist: Adr has no field named 'created_by_name'`

- [ ] **Step 3: Edit the six models**

In `backend/application/models.py`, in each of `Adr` (277), `Risk` (414), `Goal` (488), `MainGoal` (533), `Issue` (643), `ChangeRequest` (740), replace

```python
    created_by = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
```

with

```python
    # Datenmodell-Konsolidierung Phase 2: renamed so the attribute name is free
    # for AuditableModel.created_by (a User FK). db_column keeps the existing
    # column, so this is a state-only rename with no data movement.
    created_by_name = models.CharField(
        max_length=255, blank=True, db_column="created_by"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # Added ahead of the TenantScopedModel swap (Task 15) so the base class
    # finds the columns already present and backfilled. Nullable because
    # existing rows have no value until the data migration runs.
    modified_at = models.DateTimeField(null=True, blank=True)
    created_by_id = models.UUIDField(null=True, blank=True)
    modified_by_id = models.UUIDField(null=True, blank=True)
```

- [ ] **Step 4: Update the `created_by` write sites**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test grep -rn "created_by=" --include=*.py application/ rest_api/ mcp_server/ | grep -v tests`
Expected: a list of `Adr.objects.create(..., created_by=...)`-style calls. Change every one that targets one of the six models to `created_by_name=`.

- [ ] **Step 5: Generate the migration**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test python manage.py makemigrations application --name reconcile_audit_fields`
Expected: creates `application/migrations/0021_reconcile_audit_fields.py`. Django will offer `RenameField` for `created_by` → `created_by_name`; accept it, then verify the generated file uses `RenameField` (not `RemoveField` + `AddField`, which would drop the data).

Append a backfill to the generated file, before the closing bracket of `operations`:

```python
def _backfill_modified_at(apps_registry, schema_editor):
    """Seed modified_at from updated_at so no row starts NULL."""
    for model_name in ("Adr", "Risk", "Goal", "MainGoal", "Issue", "ChangeRequest"):
        model = apps_registry.get_model("application", model_name)
        model.objects.filter(modified_at__isnull=True).update(
            modified_at=models.F("updated_at")
        )
```

and register it as the last operation:

```python
        migrations.RunPython(_backfill_modified_at, migrations.RunPython.noop),
```

adding `from django.db import models` to the migration's imports.

- [ ] **Step 6: Run the migration**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test python manage.py migrate application`
Expected: `Applying application.0021_reconcile_audit_fields... OK`

- [ ] **Step 7: Run test to verify it passes**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test pytest application/tests/test_audit_field_reconciliation.py -v`
Expected: PASS (19 tests)

- [ ] **Step 8: Commit**

```bash
git add backend/application/
git commit -m "refactor: reconcile audit fields ahead of the layer move"
```

---

### Task 15: Switch the six models to TenantScopedModel

**Files:**
- Modify: `backend/application/models.py` — the six class statements and their now-duplicated `id`/`version`/`created_at`/`tenant_id` declarations
- Create: `backend/application/migrations/0022_tenant_scoped_base.py`
- Test: `backend/application/tests/test_tenant_scoped_base.py`

**Interfaces:**
- Consumes: `persistence.models.TenantScopedModel` (abstract, supplies `tenant: FK(Tenant, PROTECT)`, `objects: TenantManager`, `unscoped: UnscopedManager`, `base_manager_name = "unscoped"`) and `persistence.models.AuditableModel` (`id`, `created_at`, `created_by`, `modified_at`, `modified_by`, `version`, `lock_version`).
- Produces: `Adr`, `Risk`, `Goal`, `MainGoal`, `Issue`, `ChangeRequest`, `ChangeRequestAffectedItem` as `TenantScopedModel` subclasses. `Model.objects` is now **tenant-filtered**.

**Breaking change, named explicitly:** `Adr.objects` (and the five siblings) stop returning cross-tenant rows. Every query through `objects` now requires an active `TenantContext` and returns nothing without one. Call sites that deliberately read across tenants must switch to `.unscoped`. This is the RLS-consistency win the spec asks for and simultaneously the largest behavioural risk in Phase 2 — Step 4 enumerates the call sites rather than trusting the test suite to catch them.

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_tenant_scoped_base.py`:

```python
"""The six Layer-2 models are tenant-scoped (Datenmodell-Konsolidierung Phase 2)."""
import uuid

import pytest
from django.apps import apps

from persistence.models import TenantScopedModel

MODELS = ["Adr", "Risk", "Goal", "MainGoal", "Issue", "ChangeRequest"]


@pytest.fixture
def two_tenants(db):
    from persistence.models import Tenant, Workspace
    from persistence.tenancy import set_tenant

    from application.models import Adr

    made = {}
    for label in ("a", "b"):
        tenant = Tenant.objects.create(name=f"t-scoped-{label}")
        set_tenant(str(tenant.id))
        workspace = Workspace.objects.create(tenant=tenant, name=f"ws-{label}")
        adr = Adr.objects.create(
            tenant=tenant,
            workspace_id=workspace.id,
            title=f"ADR {label}",
            description="d",
        )
        made[label] = (tenant, adr.id)
    return made


@pytest.mark.parametrize("model_name", MODELS)
def test_model_inherits_the_tenant_scoped_base(model_name):
    model = apps.get_model("application", model_name)
    assert issubclass(model, TenantScopedModel)


@pytest.mark.parametrize("model_name", MODELS)
def test_tenant_is_a_foreign_key(model_name):
    model = apps.get_model("application", model_name)
    field = model._meta.get_field("tenant")

    assert field.many_to_one is True
    assert field.get_attname_column()[1] == "tenant_id"
    assert field.remote_field.model._meta.model_name == "tenant"


@pytest.mark.parametrize("model_name", MODELS)
def test_local_duplicates_are_gone(model_name):
    model = apps.get_model("application", model_name)
    local = {f.name for f in model._meta.local_fields}

    assert "tenant_id" not in local
    assert "id" not in local
    assert "version" not in local


@pytest.mark.django_db
def test_objects_is_tenant_filtered(two_tenants):
    from persistence.tenancy import set_tenant

    from application.models import Adr

    tenant_a, adr_a = two_tenants["a"]
    _tenant_b, adr_b = two_tenants["b"]
    set_tenant(str(tenant_a.id))

    visible = set(Adr.objects.values_list("id", flat=True))

    assert adr_a in visible
    assert adr_b not in visible


@pytest.mark.django_db
def test_unscoped_still_crosses_tenants(two_tenants):
    from persistence.tenancy import set_tenant

    from application.models import Adr

    tenant_a, adr_a = two_tenants["a"]
    _tenant_b, adr_b = two_tenants["b"]
    set_tenant(str(tenant_a.id))

    visible = set(Adr.unscoped.values_list("id", flat=True))

    assert {adr_a, adr_b} <= visible
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test pytest application/tests/test_tenant_scoped_base.py -v`
Expected: FAIL — `assert issubclass(Adr, TenantScopedModel)`

- [ ] **Step 3: Edit the seven classes**

Add to the imports of `backend/application/models.py`:

```python
from persistence.models import TenantScopedModel
```

For each of `Adr` (223), `Risk` (302), `Goal` (466), `MainGoal` (509), `Issue` (572), `ChangeRequest` (670) and `ChangeRequestAffectedItem` (761):
- change the class statement to `class Adr(TenantScopedModel):` (etc.),
- delete the local `id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)`,
- delete the local `tenant_id = models.UUIDField(db_index=True)`,
- delete the local `version = models.IntegerField(default=1)`,
- delete the local `created_at = models.DateTimeField(auto_now_add=True)`,
- delete the `modified_at`, `created_by_id`, `modified_by_id` shims added in Task 14 (the base class now declares `modified_at` and the two FKs; the columns already exist and are backfilled),
- keep `workspace_id`, `updated_at`, `created_by_name` and every domain field,
- keep `Meta.db_table` and every non-status index unchanged.

- [ ] **Step 4: Enumerate and fix the cross-tenant call sites**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test grep -rn "Adr\.objects\|Risk\.objects\|Goal\.objects\|MainGoal\.objects\|Issue\.objects\|ChangeRequest\.objects" --include=*.py . | grep -v tests`
Expected: a list of call sites. For each one, decide and record:
- inside a service method that already calls `self._set_tenant_context(ctx)` → leave on `objects` (now correctly scoped),
- inside a management command, Celery task, migration or admin action that runs without a tenant context → switch to `.unscoped` and add a one-line comment naming why,
- inside `baseline/state_capture.py` → it already filters `tenant_id=tenant_id` explicitly and must keep working without a context; switch those three (`Adr`, `Risk`, `Issue`, `Goal`, `MainGoal`) to `.unscoped`, matching the `Requirement.unscoped` usage already present at line 132.

- [ ] **Step 5: Generate the migration**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test python manage.py makemigrations application --name tenant_scoped_base`
Expected: creates `application/migrations/0022_tenant_scoped_base.py` with `AlterField` on `tenant` (UUIDField → ForeignKey) and `AlterModelManagers`. Verify there is **no** `RemoveField`/`AddField` pair on `tenant_id` — that would drop the tenant of every row.

Prepend an orphan check as the first operation, so the FK constraint cannot fail mid-migration on production data:

```python
def _assert_no_orphan_tenants(apps_registry, schema_editor):
    """Fail loudly before the FK constraint is added, not during it."""
    Tenant = apps_registry.get_model("persistence", "Tenant")
    known = set(Tenant.objects.values_list("id", flat=True))
    for model_name in (
        "Adr", "Risk", "Goal", "MainGoal", "Issue",
        "ChangeRequest", "ChangeRequestAffectedItem",
    ):
        model = apps_registry.get_model("application", model_name)
        orphans = sorted(
            set(model.objects.values_list("tenant_id", flat=True)) - known
        )
        if orphans:
            raise RuntimeError(
                f"{model_name} references unknown tenant ids {orphans}; "
                "clean these rows before adding the tenant FK."
            )
```

```python
        migrations.RunPython(_assert_no_orphan_tenants, migrations.RunPython.noop),
```

- [ ] **Step 6: Run the migration**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test python manage.py migrate application`
Expected: `Applying application.0022_tenant_scoped_base... OK`

- [ ] **Step 7: Run test to verify it passes**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test pytest application/tests/test_tenant_scoped_base.py -v`
Expected: PASS (20 tests)

- [ ] **Step 8: Run the full application and baseline suites**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test pytest application/ baseline/ rest_api/ mcp_server/ -q`
Expected: PASS. A test that now returns an empty queryset is a missing `set_tenant`, not a flake — fix the call site, never the assertion.

- [ ] **Step 9: Commit**

```bash
git add backend/application/ backend/baseline/state_capture.py
git commit -m "refactor: base adr/risk/goal/issue models on TenantScopedModel"
```

---

### Task 16: Move the six models into persistence — **Milestone M2**

**Files:**
- Modify: `backend/persistence/models.py` (append the seven classes), `backend/application/models.py` (remove them, keep a compatibility re-export)
- Create: `backend/persistence/migrations/0071_adopt_layer2_models.py`
- Create: `backend/application/migrations/0023_release_layer2_models.py`
- Test: `backend/application/tests/test_layer_boundary.py`

**Interfaces:**
- Consumes: the `TenantScopedModel` subclasses from Task 15.
- Produces: `persistence.models.Adr`, `.Risk`, `.Goal`, `.MainGoal`, `.Issue`, `.ChangeRequest`, `.ChangeRequestAffectedItem`. `application.models` keeps `from persistence.models import Adr, ChangeRequest, ChangeRequestAffectedItem, Goal, Issue, MainGoal, Risk` so the ~40 existing `from application.models import Adr` imports keep working — the spec's §3.4 goal ("`application/` behält nur noch die Services") is about ownership, and a one-line re-export avoids a 40-file churn commit with no behavioural content.

The tables do not move. `SeparateDatabaseAndState` changes only Django's model registry.

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_layer_boundary.py`:

```python
"""The six domain models are owned by Layer 0 (persistence).

Datenmodell-Konsolidierung Phase 2 / Milestone M2, spec section 3.
"""
import pytest
from django.apps import apps
from django.db import connection

MODELS = [
    "Adr",
    "Risk",
    "Goal",
    "MainGoal",
    "Issue",
    "ChangeRequest",
    "ChangeRequestAffectedItem",
]

TABLES = {
    "Adr": "as_adr",
    "Risk": "as_risk",
    "Goal": "as_goal",
    "MainGoal": "as_main_goal",
    "Issue": "as_issue",
    "ChangeRequest": "as_change_request",
    "ChangeRequestAffectedItem": "as_change_request_affected_item",
}


@pytest.mark.parametrize("model_name", MODELS)
def test_model_is_registered_under_persistence(model_name):
    model = apps.get_model("persistence", model_name)
    assert model._meta.app_label == "persistence"


@pytest.mark.parametrize("model_name", MODELS)
def test_application_re_export_is_the_same_class(model_name):
    from application import models as application_models

    assert getattr(application_models, model_name) is apps.get_model(
        "persistence", model_name
    )


@pytest.mark.parametrize("model_name", MODELS)
def test_table_name_is_unchanged(model_name):
    model = apps.get_model("persistence", model_name)
    assert model._meta.db_table == TABLES[model_name]


@pytest.mark.django_db
@pytest.mark.parametrize("model_name", MODELS)
def test_table_still_exists_with_its_data_shape(model_name):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
            [TABLES[model_name]],
        )
        columns = {row[0] for row in cursor.fetchall()}

    assert "tenant_id" in columns
    assert "id" in columns


def test_application_models_declares_no_domain_model():
    import inspect

    from application import models as application_models

    source = inspect.getsource(application_models)
    for model_name in MODELS:
        assert f"class {model_name}(" not in source
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test pytest application/tests/test_layer_boundary.py -v`
Expected: FAIL — `LookupError: App 'persistence' doesn't have a 'Adr' model.`

- [ ] **Step 3: Move the class bodies**

Cut the seven class definitions (`Adr`, `Risk`, `Goal`, `MainGoal`, `Issue`, `ChangeRequest`, `ChangeRequestAffectedItem`) verbatim out of `backend/application/models.py` and paste them into `backend/persistence/models.py`, after `TestCase` and before `WorkflowDefinition`. Adjust their base class references from `TenantScopedModel` (imported) to the locally defined `TenantScopedModel`, and change the `artifact` FK strings from `"persistence.Artifact"` to `Artifact` (now a local name). `ChangeRequest.baseline`'s `"baseline.BaselineSnapshot"` string stays a string — `persistence` must not import `baseline` (Layer 0 depends on nothing).

At the top of `backend/application/models.py`, replace the removed classes with:

```python
# Datenmodell-Konsolidierung Phase 2 (spec section 3): these seven domain models
# moved to Layer 0 (persistence/models.py) so they inherit TenantScopedModel's
# RLS-consistent base instead of duplicating tenant_id by hand. Re-exported here
# because `from application.models import Adr` is the established import path
# across ~40 modules and the move is about ownership, not call-site churn.
from persistence.models import (  # noqa: F401
    Adr,
    ChangeRequest,
    ChangeRequestAffectedItem,
    Goal,
    Issue,
    MainGoal,
    Risk,
)
```

Also drop the now-unnecessary `application/apps.py` `register_models` entries for these seven — Layer 1 can import `persistence.models` directly. Leave `register_models` itself in place if it still registers other classes; if it becomes empty, delete the call and the `ready()` body's registry import.

- [ ] **Step 4: Write the state-only migrations**

Create `backend/application/migrations/0023_release_layer2_models.py`:

```python
"""Release the seven domain models from the application app (state only).

Datenmodell-Konsolidierung Phase 2 / Milestone M2. Paired with
persistence/0071_adopt_layer2_models, which re-creates them in Layer 0. No SQL
runs: the tables (as_adr, as_risk, as_goal, as_main_goal, as_issue,
as_change_request, as_change_request_affected_item) are untouched.
"""
from django.db import migrations

MOVED = [
    "Adr",
    "Risk",
    "Goal",
    "MainGoal",
    "Issue",
    "ChangeRequest",
    "ChangeRequestAffectedItem",
]


class Migration(migrations.Migration):

    dependencies = [
        ("application", "0022_tenant_scoped_base"),
        ("persistence", "0071_adopt_layer2_models"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.DeleteModel(name=name) for name in MOVED
            ],
        ),
    ]
```

Create `backend/persistence/migrations/0071_adopt_layer2_models.py` by generating it and then wrapping the result:

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test python manage.py makemigrations persistence --name adopt_layer2_models`
Expected: a file whose `operations` is a list of seven `migrations.CreateModel(...)` calls. Wrap that list — do not edit the `CreateModel` bodies:

```python
    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                # the seven generated CreateModel(...) calls, verbatim
            ],
        ),
    ]
```

and set `dependencies = [("persistence", "0070_drop_status_mirror_columns"), ("application", "0022_tenant_scoped_base"), ("baseline", "0006_baseline_snapshot_rls")]`.

- [ ] **Step 5: Verify the migration plan is a no-op at the SQL level**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test python manage.py sqlmigrate persistence 0071_adopt_layer2_models`
Expected: empty output (or only `BEGIN;`/`COMMIT;`). Any `CREATE TABLE` means the `SeparateDatabaseAndState` wrapper is wrong — stop and fix it before migrating.

- [ ] **Step 6: Run the migrations and confirm no drift**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test sh -c "python manage.py migrate && python manage.py makemigrations --check --dry-run"`
Expected: migrations apply, then `No changes detected`.

- [ ] **Step 7: Run test to verify it passes**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test pytest application/tests/test_layer_boundary.py -v`
Expected: PASS (29 tests)

- [ ] **Step 8: Run the full backend regression set**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test pytest persistence/ application/ workflow/ baseline/ rest_api/ mcp_server/ -q`
Expected: PASS

- [ ] **Step 9: Verify in a running stack**

Run: `make up`, then `docker-compose -f deploy/docker-compose.yml --project-directory . exec backend python manage.py seed_demo`. In the SPA, create an ADR, a Risk and a Change Request, transition each once, and reload. All three must persist and show their new state.

- [ ] **Step 10: Commit — Milestone M2**

```bash
git add backend/persistence/ backend/application/
git commit -m "refactor: move layer-2 domain models into persistence"
```

---

# Phase 3 — Artifact-Backing nachrüsten (spec §4)

Goal: every artifact type owns exactly one `persistence.Artifact` row.

Corrected scope versus the spec (findings V-1 and V-2): `Diagram.artifact` **already exists** and is created lazily by `diagram/traceability_connector._resolve_artifact_id`; only the backfill and eager creation are missing. `Icd`, `GlossaryTerm` and `ChangeRequest` need the field itself.

Two types can hold rows that cannot be backed at all: `Diagram.workspace_id` is `null=True` (`diagram/models.py:83`) and `GlossaryTerm.workspace` is `null=True` (`persistence/models.py:1836`). `Artifact.workspace` is non-nullable, so those rows are reported and skipped, never silently mis-assigned.

### Task 17: One shared `ensure_artifact` helper

**Files:**
- Create: `backend/persistence/artifact_backing.py`
- Modify: `backend/diagram/traceability_connector.py:60-131` (`_resolve_artifact_id` delegates)
- Test: `backend/persistence/tests/test_artifact_backing.py`

**Interfaces:**
- Consumes: `persistence.models.Artifact` (fields `tenant`, `workspace`, `artifact_type`).
- Produces:
  - `ensure_artifact(entity, *, artifact_type: str, workspace_id: UUID | None, field_name: str = "artifact") -> UUID`
  - `class ArtifactBackingError(RuntimeError)`

  `ensure_artifact` is idempotent, race-safe (`select_for_update` on the entity row), must be called inside an open transaction, and raises `ArtifactBackingError` when `workspace_id` is `None`.

This generalises the Diagram-only resolver rather than copying it a fourth time — `_resolve_artifact_id` has been the recurring source of "artifact not found" bugs for every newly Artifact-backed type.

- [ ] **Step 1: Write the failing test**

Create `backend/persistence/tests/test_artifact_backing.py`:

```python
"""Shared Artifact-backing helper (Datenmodell-Konsolidierung Phase 3)."""
import uuid

import pytest
from django.db import transaction

from persistence.artifact_backing import ArtifactBackingError, ensure_artifact


@pytest.fixture
def diagram_env(db):
    from persistence.models import Tenant, Workspace
    from persistence.tenancy import set_tenant

    from diagram.models import Diagram

    tenant = Tenant.objects.create(name="t-backing")
    set_tenant(str(tenant.id))
    workspace = Workspace.objects.create(tenant=tenant, name="ws-backing")
    diagram = Diagram.objects.create(
        tenant=tenant,
        name="D1",
        diagram_type="block",
        workspace_id=workspace.id,
    )
    orphan = Diagram.objects.create(
        tenant=tenant, name="D2", diagram_type="block", workspace_id=None
    )
    return tenant, workspace, diagram, orphan


@pytest.mark.django_db
def test_creates_the_artifact_row(diagram_env):
    from persistence.models import Artifact

    _tenant, _workspace, diagram, _orphan = diagram_env

    with transaction.atomic():
        artifact_id = ensure_artifact(
            diagram, artifact_type="Diagram", workspace_id=diagram.workspace_id
        )

    artifact = Artifact.objects.get(pk=artifact_id)
    assert artifact.artifact_type == "Diagram"
    diagram.refresh_from_db()
    assert diagram.artifact_id == artifact_id


@pytest.mark.django_db
def test_is_idempotent(diagram_env):
    from persistence.models import Artifact

    _tenant, _workspace, diagram, _orphan = diagram_env

    with transaction.atomic():
        first = ensure_artifact(
            diagram, artifact_type="Diagram", workspace_id=diagram.workspace_id
        )
    with transaction.atomic():
        second = ensure_artifact(
            diagram, artifact_type="Diagram", workspace_id=diagram.workspace_id
        )

    assert first == second
    assert Artifact.objects.filter(artifact_type="Diagram").count() == 1


@pytest.mark.django_db
def test_missing_workspace_raises(diagram_env):
    _tenant, _workspace, _diagram, orphan = diagram_env

    with pytest.raises(ArtifactBackingError) as excinfo:
        with transaction.atomic():
            ensure_artifact(orphan, artifact_type="Diagram", workspace_id=None)

    assert "workspace" in str(excinfo.value)


@pytest.mark.django_db
def test_requires_an_open_transaction(diagram_env):
    from django.db.transaction import TransactionManagementError

    _tenant, _workspace, diagram, _orphan = diagram_env

    with pytest.raises((TransactionManagementError, ArtifactBackingError)):
        ensure_artifact(
            diagram, artifact_type="Diagram", workspace_id=diagram.workspace_id
        )


@pytest.mark.django_db
def test_custom_field_name_is_honoured(diagram_env):
    _tenant, _workspace, diagram, _orphan = diagram_env

    with transaction.atomic():
        artifact_id = ensure_artifact(
            diagram,
            artifact_type="Diagram",
            workspace_id=diagram.workspace_id,
            field_name="artifact",
        )

    assert isinstance(artifact_id, uuid.UUID)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test pytest persistence/tests/test_artifact_backing.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'persistence.artifact_backing'`

- [ ] **Step 3: Write the implementation**

Create `backend/persistence/artifact_backing.py`:

```python
"""Shared Artifact-backing helper (Datenmodell-Konsolidierung Phase 3, spec §4).

Every specialised artifact table owns exactly one ``persistence.Artifact`` row,
which is what makes it a valid TraceLink endpoint, a baseline-diff subject and
an interview target. Four types acquired that backing at different times with
four slightly different code paths; this module is the one implementation all of
them use.

Lives in Layer 0 on purpose: ``diagram``, ``icd`` and ``persistence`` itself all
need it, and Layer 0 is the only layer all three may import.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from django.db import models, transaction

from persistence.models import Artifact


class ArtifactBackingError(RuntimeError):
    """An entity cannot be given a backing Artifact row."""


def ensure_artifact(
    entity: models.Model,
    *,
    artifact_type: str,
    workspace_id: UUID | None,
    field_name: str = "artifact",
) -> UUID:
    """Return *entity*'s backing Artifact id, creating the row if absent.

    Idempotent and race-safe: the entity row is re-read under
    ``select_for_update`` whenever the backing is ambiguous, so two concurrent
    callers cannot both insert an Artifact and orphan one of them.

    Must be called inside an open transaction — ``select_for_update`` requires
    one, and the Artifact insert must roll back with the caller's operation.

    Args:
        entity:        The specialised row (Diagram, Icd, GlossaryTerm, ...).
        artifact_type: Value for ``Artifact.artifact_type``, e.g. ``"Icd"``.
        workspace_id:  Owning workspace. ``Artifact.workspace`` is not
                       nullable, so ``None`` is a hard error.
        field_name:    Name of the OneToOne field on *entity*.

    Returns:
        The UUID of the (possibly newly created) Artifact.

    Raises:
        ArtifactBackingError: *workspace_id* is ``None``.
    """
    existing = getattr(entity, f"{field_name}_id", None)
    if existing is not None:
        return existing

    if workspace_id is None:
        raise ArtifactBackingError(
            f"{type(entity).__name__} {entity.pk} has no workspace; an Artifact "
            "row requires a non-null workspace and cannot be created."
        )

    if not transaction.get_connection().in_atomic_block:
        raise ArtifactBackingError(
            "ensure_artifact must run inside an atomic block so the Artifact "
            "row rolls back with the caller's operation."
        )

    locked = type(entity).objects.select_for_update().get(pk=entity.pk)
    locked_id = getattr(locked, f"{field_name}_id", None)
    if locked_id is not None:
        setattr(entity, f"{field_name}_id", locked_id)
        return locked_id

    artifact = Artifact.objects.create(
        artifact_type=artifact_type,
        tenant=locked.tenant,
        workspace_id=workspace_id,
    )
    setattr(locked, field_name, artifact)
    locked.save(update_fields=[field_name, "modified_at"])
    setattr(entity, field_name, artifact)
    return artifact.id


def artifact_id_of(entity: Any, field_name: str = "artifact") -> UUID | None:
    """Return *entity*'s backing Artifact id without creating one."""
    return getattr(entity, f"{field_name}_id", None)


__all__ = ["ArtifactBackingError", "artifact_id_of", "ensure_artifact"]
```

- [ ] **Step 4: Delegate the Diagram resolver**

In `backend/diagram/traceability_connector.py`, replace the body of `_resolve_artifact_id` (lines 104-131) — keep the docstring, change only the implementation:

```python
    from persistence.artifact_backing import ArtifactBackingError, ensure_artifact

    try:
        return ensure_artifact(
            diagram, artifact_type="Diagram", workspace_id=diagram.workspace_id
        )
    except ArtifactBackingError as exc:
        # Preserve the historical exception type for this call path.
        raise TraceLinkError(str(exc)) from exc
```

- [ ] **Step 5: Run test to verify it passes**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test pytest persistence/tests/test_artifact_backing.py -v`
Expected: PASS (5 tests)

- [ ] **Step 6: Run the diagram suite**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test pytest diagram/ -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/persistence/artifact_backing.py backend/persistence/tests/test_artifact_backing.py backend/diagram/traceability_connector.py
git commit -m "feat: add shared ensure_artifact backing helper"
```

---

### Task 18: Add the missing `artifact` fields

**Files:**
- Modify: `backend/icd/models.py:93-140` (`Icd`), `backend/persistence/models.py:1833-1856` (`GlossaryTerm`) and the `ChangeRequest` class moved in Task 16
- Create: `backend/icd/migrations/0009_icd_artifact_fk.py`
- Create: `backend/persistence/migrations/0072_glossary_changerequest_artifact_fk.py`
- Test: `backend/persistence/tests/test_artifact_fk_present.py`

**Interfaces:**
- Consumes: `persistence.models.Artifact`.
- Produces: `Icd.artifact`, `GlossaryTerm.artifact`, `ChangeRequest.artifact` — all `OneToOneField("persistence.Artifact", null=True, blank=True)`, matching `Adr.artifact`'s shape (`on_delete=CASCADE`, `related_name` = lowercase model name) except `Icd`, which uses `SET_NULL` to match its sibling `Diagram.artifact` (an ICD must survive the removal of its shadow Artifact).

- [ ] **Step 1: Write the failing test**

Create `backend/persistence/tests/test_artifact_fk_present.py`:

```python
"""Every artifact type declares a backing Artifact FK.

Datenmodell-Konsolidierung Phase 3, spec section 4.
"""
import pytest
from django.apps import apps
from django.db import models

BACKED = [
    ("persistence", "Requirement"),
    ("persistence", "StakeholderNeed"),
    ("persistence", "ArchitectureElement"),
    ("persistence", "TestCase"),
    ("persistence", "GlossaryTerm"),
    ("persistence", "Adr"),
    ("persistence", "Risk"),
    ("persistence", "Issue"),
    ("persistence", "Goal"),
    ("persistence", "MainGoal"),
    ("persistence", "ChangeRequest"),
    ("diagram", "Diagram"),
    ("icd", "Icd"),
]


@pytest.mark.parametrize("app_label,model_name", BACKED)
def test_artifact_field_exists_and_is_one_to_one(app_label, model_name):
    model = apps.get_model(app_label, model_name)
    field = model._meta.get_field("artifact")

    assert isinstance(field, models.OneToOneField)
    assert field.remote_field.model is apps.get_model("persistence", "Artifact")


@pytest.mark.parametrize("app_label,model_name", BACKED)
def test_artifact_field_is_nullable(app_label, model_name):
    """Nullable so the schema migration stays additive; the backfill fills it."""
    model = apps.get_model(app_label, model_name)
    assert model._meta.get_field("artifact").null is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test pytest persistence/tests/test_artifact_fk_present.py -v`
Expected: FAIL — `FieldDoesNotExist: Icd has no field named 'artifact'`

- [ ] **Step 3: Add the field to `Icd`**

In `backend/icd/models.py`, inside `class Icd(TenantScopedModel)` after `workspace_id` (line 105):

```python
    # Datenmodell-Konsolidierung Phase 3 (spec §4): backing Artifact row so an
    # ICD is a valid TraceLink endpoint and a Document-scope baseline subject.
    # SET_NULL rather than CASCADE, matching Diagram.artifact: removing the
    # shadow Artifact (e.g. a TraceLink cleanup cascade) must never delete the
    # ICD itself.
    artifact = models.OneToOneField(
        "persistence.Artifact",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="icd",
    )
```

- [ ] **Step 4: Add the field to `GlossaryTerm` and `ChangeRequest`**

In `backend/persistence/models.py`, inside `class GlossaryTerm(TenantScopedModel)` after `workspace` (line 1838):

```python
    # Datenmodell-Konsolidierung Phase 3 (spec §4): closes the gap that made
    # interview_artifact_adapters._glossary_term reject every creation with
    # "GlossaryTerm is not Artifact-backed yet".
    artifact = models.OneToOneField(
        "persistence.Artifact",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="glossary_term",
    )
```

In the `ChangeRequest` class (moved into `persistence/models.py` by Task 16), after `workspace_id`:

```python
    # Datenmodell-Konsolidierung Phase 3 (spec §4, correction V-1): unlike the
    # five sibling models, ChangeRequest never had a backing Artifact.
    artifact = models.OneToOneField(
        Artifact,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="change_request",
    )
```

- [ ] **Step 5: Generate the migrations**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test python manage.py makemigrations icd persistence --name artifact_fk`
Expected: `icd/migrations/0009_artifact_fk.py` (one `AddField`) and `persistence/migrations/0072_artifact_fk.py` (two `AddField`s). Rename the persistence file to `0072_glossary_changerequest_artifact_fk.py`.

- [ ] **Step 6: Run the migrations and the test**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test sh -c "python manage.py migrate && pytest persistence/tests/test_artifact_fk_present.py -v"`
Expected: migrations apply, then PASS (26 tests)

- [ ] **Step 7: Commit**

```bash
git add backend/icd/ backend/persistence/
git commit -m "feat: add artifact backing fields to icd, glossary and cr"
```

---

### Task 19: Create the Artifact row eagerly on write

**Files:**
- Modify: `backend/diagram/manager.py:163-235` (`create_diagram`)
- Modify: `backend/icd/icd_manager.py:200` (`create_icd`)
- Modify: `backend/application/glossary_service.py:103` (`create`)
- Modify: `backend/application/change_request_service.py` (`create_change_request`)
- Test: `backend/persistence/tests/test_eager_artifact_creation.py`

**Interfaces:**
- Consumes: `persistence.artifact_backing.ensure_artifact(entity, *, artifact_type, workspace_id, field_name="artifact") -> UUID` (Task 17).
- Produces: `DiagramManager.create_diagram`, `IcdManager.create_icd`, `GlossaryService.create`, `ChangeRequestService.create_change_request` — unchanged signatures; every newly created row leaves the method with `artifact_id is not None`.

- [ ] **Step 1: Write the failing test**

Create `backend/persistence/tests/test_eager_artifact_creation.py`:

```python
"""New rows of every artifact type are Artifact-backed on creation.

Datenmodell-Konsolidierung Phase 3, spec section 4.3.
"""
import uuid

import pytest


@pytest.fixture
def env(db):
    from auth_tenancy.context import AuthContext
    from persistence.models import Tenant, Workspace
    from persistence.tenancy import set_tenant

    tenant = Tenant.objects.create(name="t-eager")
    set_tenant(str(tenant.id))
    workspace = Workspace.objects.create(tenant=tenant, name="ws-eager")
    ctx = AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        roles=["admin"],
        workspace_id=workspace.id,
    )
    return tenant, workspace, ctx


@pytest.mark.django_db
def test_new_diagram_is_backed(env):
    from diagram.manager import DiagramManager

    tenant, workspace, _ctx = env
    diagram = DiagramManager().create_diagram(
        name="D",
        diagram_type="block",
        payload_format="mermaid",
        content="graph TD;A-->B;",
        tenant=tenant,
        workspace_id=workspace.id,
    )

    assert diagram.artifact_id is not None
    assert diagram.artifact.artifact_type == "Diagram"


@pytest.mark.django_db
def test_new_glossary_term_is_backed(env):
    from application.glossary_service import GlossaryService
    from persistence.models import GlossaryTerm

    _tenant, workspace, ctx = env
    dto = GlossaryService().create(
        ctx=ctx, workspace_id=workspace.id, term="Widget", definition="a thing"
    )
    row = GlossaryTerm.objects.get(pk=dto.id)

    assert row.artifact_id is not None
    assert row.artifact.artifact_type == "GlossaryTerm"


@pytest.mark.django_db
def test_new_change_request_is_backed(env):
    from application.change_request_service import ChangeRequestService
    from persistence.models import ChangeRequest

    _tenant, workspace, ctx = env
    created = ChangeRequestService().create_change_request(
        workspace_id=workspace.id, title="CR", description="d", ctx=ctx
    )
    row = ChangeRequest.objects.get(pk=created.id)

    assert row.artifact_id is not None
    assert row.artifact.artifact_type == "ChangeRequest"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test pytest persistence/tests/test_eager_artifact_creation.py -v`
Expected: FAIL — `assert diagram.artifact_id is not None`

- [ ] **Step 3: Implement `create_diagram`**

In `backend/diagram/manager.py`, after the `Diagram.objects.create(...)` call and before the `DiagramVersion.objects.create(...)` call, insert:

```python
        # Datenmodell-Konsolidierung Phase 3 (spec §4.3): create the backing
        # Artifact up front instead of lazily on first TraceLink use, so a
        # Diagram is a valid link endpoint and baseline subject from birth.
        # Skipped for the workspace-less legacy shape (workspace_id is
        # nullable, REQ-173) — those rows keep the pre-existing behaviour of
        # raising only when a link is actually attempted.
        if workspace_id is not None:
            ensure_artifact(
                diagram, artifact_type="Diagram", workspace_id=workspace_id
            )
```

and add to the module's imports:

```python
from persistence.artifact_backing import ensure_artifact
```

`create_diagram` already runs under `@atomic_transaction`, which satisfies `ensure_artifact`'s transaction requirement.

- [ ] **Step 4: Implement `create_icd`**

In `backend/icd/icd_manager.py`, inside `create_icd` after the `Icd.objects.create(...)` call:

```python
        ensure_artifact(icd, artifact_type="Icd", workspace_id=icd.workspace_id)
```

with `from persistence.artifact_backing import ensure_artifact` in the imports. If `create_icd` is not already wrapped in an atomic block, wrap its body with `with transaction.atomic():` (import `from django.db import transaction`) — the Icd row, its first `IcdVersion` and the Artifact must commit together.

- [ ] **Step 5: Implement `GlossaryService.create` and `ChangeRequestService.create_change_request`**

In `backend/application/glossary_service.py`, after the `GlossaryTerm.objects.create(...)` call:

```python
        ensure_artifact(
            term, artifact_type="GlossaryTerm", workspace_id=workspace_id
        )
```

In `backend/application/change_request_service.py`, after the `ChangeRequest.objects.create(...)` call:

```python
        ensure_artifact(
            cr, artifact_type="ChangeRequest", workspace_id=workspace_id
        )
```

Add `from persistence.artifact_backing import ensure_artifact` to both modules. Both create methods already carry `@atomic_transaction`; if either does not, add it.

- [ ] **Step 6: Run test to verify it passes**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test pytest persistence/tests/test_eager_artifact_creation.py -v`
Expected: PASS (3 tests)

- [ ] **Step 7: Run the affected suites**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test pytest diagram/ icd/ application/ -q`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add backend/diagram/manager.py backend/icd/icd_manager.py backend/application/glossary_service.py backend/application/change_request_service.py backend/persistence/tests/test_eager_artifact_creation.py
git commit -m "feat: create backing artifact rows eagerly on write"
```

---

### Task 20: Backfill the existing rows

**Files:**
- Create: `backend/persistence/migrations/0073_backfill_artifact_backing.py`
- Create: `backend/persistence/management/commands/check_artifact_backing.py`
- Test: `backend/persistence/tests/test_artifact_backfill.py`

**Interfaces:**
- Consumes: the `artifact` fields from Task 18.
- Produces:
  - migration `persistence.0073_backfill_artifact_backing` — creates one `Artifact` row per unbacked Diagram/Icd/GlossaryTerm/ChangeRequest row and links it.
  - management command `check_artifact_backing` printing a per-type report and exiting non-zero on any integrity violation (`python manage.py check_artifact_backing`).

The migration runs raw ORM against the historical model registry, so it must not import `ensure_artifact` (which binds the live models). Rows without a workspace are counted and reported, not backed.

- [ ] **Step 1: Write the failing test**

Create `backend/persistence/tests/test_artifact_backfill.py`:

```python
"""Backfill integrity: one Artifact per legacy row, no orphans, no duplicates.

Datenmodell-Konsolidierung Phase 3, spec section 4.2.
"""
import io

import pytest
from django.core.management import call_command


@pytest.fixture
def legacy_rows(db):
    """Rows that predate their type's artifact FK, plus one workspace-less row."""
    from persistence.models import GlossaryTerm, Tenant, Workspace
    from persistence.tenancy import set_tenant

    from diagram.models import Diagram

    tenant = Tenant.objects.create(name="t-backfill")
    set_tenant(str(tenant.id))
    workspace = Workspace.objects.create(tenant=tenant, name="ws-backfill")
    backed = Diagram.objects.create(
        tenant=tenant, name="D", diagram_type="block", workspace_id=workspace.id
    )
    orphan = Diagram.objects.create(
        tenant=tenant, name="D-no-ws", diagram_type="block", workspace_id=None
    )
    term = GlossaryTerm.objects.create(
        tenant=tenant, workspace=workspace, term="T", definition="d"
    )
    # Simulate the pre-migration state.
    Diagram.objects.filter(pk__in=[backed.pk, orphan.pk]).update(artifact=None)
    GlossaryTerm.objects.filter(pk=term.pk).update(artifact=None)
    return tenant, workspace, backed.pk, orphan.pk, term.pk


@pytest.mark.django_db
def test_check_command_reports_unbacked_rows(legacy_rows):
    out = io.StringIO()

    with pytest.raises(SystemExit) as excinfo:
        call_command("check_artifact_backing", stdout=out)

    assert excinfo.value.code != 0
    assert "Diagram" in out.getvalue()


@pytest.mark.django_db
def test_no_duplicate_artifact_per_entity(legacy_rows):
    """One Artifact per row is the invariant the migration must preserve."""
    from django.db.models import Count

    from persistence.models import Artifact

    duplicates = (
        Artifact.objects.values("id")
        .annotate(n=Count("diagram"))
        .filter(n__gt=1)
    )

    assert list(duplicates) == []


@pytest.mark.django_db
def test_workspace_less_rows_are_skipped_not_guessed(legacy_rows):
    from diagram.models import Diagram

    _tenant, _workspace, _backed, orphan_pk, _term = legacy_rows

    assert Diagram.objects.get(pk=orphan_pk).artifact_id is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test pytest persistence/tests/test_artifact_backfill.py -v`
Expected: FAIL — `CommandError: Unknown command: 'check_artifact_backing'`

- [ ] **Step 3: Write the check command**

Create `backend/persistence/management/commands/check_artifact_backing.py`:

```python
"""Referential-integrity report for Artifact backing (spec §4.2).

Exits non-zero if any artifact-typed row lacks a backing Artifact, points at a
missing Artifact, or shares one with another row.

    python manage.py check_artifact_backing
"""
from __future__ import annotations

import sys
from typing import Any

from django.core.management.base import BaseCommand
from django.db.models import Count

#: (app_label, model_name, artifact_type, workspace_attr)
BACKED_TYPES = [
    ("persistence", "Requirement", "Requirement", "workspace_id"),
    ("persistence", "StakeholderNeed", "StakeholderNeed", "workspace_id"),
    ("persistence", "ArchitectureElement", "ArchitectureElement", "workspace_id"),
    ("persistence", "TestCase", "TestCase", "workspace_id"),
    ("persistence", "GlossaryTerm", "GlossaryTerm", "workspace_id"),
    ("persistence", "Adr", "Adr", "workspace_id"),
    ("persistence", "Risk", "Risk", "workspace_id"),
    ("persistence", "Issue", "Issue", "workspace_id"),
    ("persistence", "Goal", "Goal", "workspace_id"),
    ("persistence", "MainGoal", "MainGoal", "workspace_id"),
    ("persistence", "ChangeRequest", "ChangeRequest", "workspace_id"),
    ("diagram", "Diagram", "Diagram", "workspace_id"),
    ("icd", "Icd", "Icd", "workspace_id"),
]


class Command(BaseCommand):
    help = "Report artifact-backing integrity for every artifact type."

    def handle(self, *args: Any, **options: Any) -> None:
        from django.apps import apps

        failures = 0
        for app_label, model_name, _artifact_type, workspace_attr in BACKED_TYPES:
            model = apps.get_model(app_label, model_name)
            total = model.unscoped.count()
            unbacked = model.unscoped.filter(artifact__isnull=True)
            unbacked_total = unbacked.count()
            backable = unbacked.exclude(**{f"{workspace_attr}__isnull": True}).count()
            skipped = unbacked_total - backable

            duplicates = (
                model.unscoped.exclude(artifact__isnull=True)
                .values("artifact_id")
                .annotate(n=Count("id"))
                .filter(n__gt=1)
                .count()
            )

            if backable or duplicates:
                failures += 1
                self.stdout.write(
                    f"FAIL {model_name}: {total} rows, {backable} backable but "
                    f"unbacked, {duplicates} shared Artifact rows, "
                    f"{skipped} skipped (no workspace)"
                )
            else:
                self.stdout.write(
                    f"OK   {model_name}: {total} rows, {skipped} skipped (no workspace)"
                )

        if failures:
            self.stdout.write(f"{failures} type(s) failed the integrity check.")
            sys.exit(1)
        self.stdout.write("All artifact types are consistently backed.")
```

- [ ] **Step 4: Write the backfill migration**

Create `backend/persistence/migrations/0073_backfill_artifact_backing.py`:

```python
"""Create one Artifact row per unbacked Diagram/Icd/GlossaryTerm/ChangeRequest.

Datenmodell-Konsolidierung Phase 3, spec section 4.2. Rows whose workspace is
NULL cannot be backed (Artifact.workspace is non-nullable) and are left as-is;
`manage.py check_artifact_backing` reports them as skipped, never as failures.

Runs against the historical model registry, so it deliberately does not import
persistence.artifact_backing.
"""
from django.db import migrations

TARGETS = [
    ("diagram", "Diagram", "Diagram"),
    ("icd", "Icd", "Icd"),
    ("persistence", "GlossaryTerm", "GlossaryTerm"),
    ("persistence", "ChangeRequest", "ChangeRequest"),
]


def _workspace_id_of(row, model_name):
    if model_name == "GlossaryTerm":
        return row.workspace_id
    return row.workspace_id


def backfill(apps_registry, schema_editor):
    Artifact = apps_registry.get_model("persistence", "Artifact")
    for app_label, model_name, artifact_type in TARGETS:
        model = apps_registry.get_model(app_label, model_name)
        for row in model.objects.filter(artifact__isnull=True).iterator():
            workspace_id = _workspace_id_of(row, model_name)
            if workspace_id is None:
                continue
            artifact = Artifact.objects.create(
                artifact_type=artifact_type,
                tenant_id=row.tenant_id,
                workspace_id=workspace_id,
            )
            model.objects.filter(pk=row.pk).update(artifact=artifact)


def verify(apps_registry, schema_editor):
    """Fail the migration if the result violates the one-Artifact invariant."""
    from django.db.models import Count

    for app_label, model_name, _artifact_type in TARGETS:
        model = apps_registry.get_model(app_label, model_name)
        leftover = (
            model.objects.filter(artifact__isnull=True)
            .exclude(workspace_id__isnull=True)
            .count()
        )
        if leftover:
            raise RuntimeError(
                f"{model_name}: {leftover} backable rows are still unbacked."
            )
        shared = (
            model.objects.exclude(artifact__isnull=True)
            .values("artifact_id")
            .annotate(n=Count("id"))
            .filter(n__gt=1)
            .count()
        )
        if shared:
            raise RuntimeError(
                f"{model_name}: {shared} Artifact rows are shared by two rows."
            )


class Migration(migrations.Migration):

    dependencies = [
        ("persistence", "0072_glossary_changerequest_artifact_fk"),
        ("icd", "0009_artifact_fk"),
        ("diagram", "0008_diagram_rls_policies"),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
        migrations.RunPython(verify, migrations.RunPython.noop),
    ]
```

- [ ] **Step 5: Run the migration**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test python manage.py migrate persistence`
Expected: `Applying persistence.0073_backfill_artifact_backing... OK`. A `RuntimeError` from `verify` means the backfill missed rows — investigate before retrying, do not weaken `verify`.

- [ ] **Step 6: Run test to verify it passes**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test pytest persistence/tests/test_artifact_backfill.py -v`
Expected: PASS (3 tests)

- [ ] **Step 7: Run the check against seeded demo data**

Run: `make up`, then `docker-compose -f deploy/docker-compose.yml --project-directory . exec backend sh -c "python manage.py seed_demo && python manage.py check_artifact_backing"`
Expected: `All artifact types are consistently backed.` and exit code 0.

- [ ] **Step 8: Commit**

```bash
git add backend/persistence/
git commit -m "feat: backfill artifact backing for legacy rows"
```

---

### Task 21: Milestone M3 gate — the GlossaryTerm interview adapter

**Files:**
- Modify: `backend/application/interview_artifact_adapters.py` (the `_glossary_term` adapter's rejection branch)
- Test: `backend/application/tests/test_milestone_m3_gate.py`

**Interfaces:**
- Consumes: `persistence.artifact_backing.ensure_artifact` (Task 17), `GlossaryTerm.artifact` (Task 18), `GlossaryService.create` (Task 19).
- Produces: `_glossary_term` adapter that creates a term instead of raising. This is the observable payoff the spec names in §4.4 and the dependency the Interview-Engine-Fix spec has on this one.

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_milestone_m3_gate.py`:

```python
"""Milestone M3 gate — all 10 artifact types are Artifact-backed.

Datenmodell-Konsolidierung Phase 3. The observable payoff (spec section 4.4) is
that multi-artifact interviews can finally create GlossaryTerms.
"""
import inspect
import uuid

import pytest

from application import interview_artifact_adapters


def test_glossary_adapter_no_longer_refuses():
    source = inspect.getsource(interview_artifact_adapters)
    assert "GlossaryTerm is not Artifact-backed yet" not in source


@pytest.mark.django_db
def test_interview_can_create_a_glossary_term(interview_env):
    from persistence.models import GlossaryTerm

    ctx, workspace_id = interview_env

    created = interview_artifact_adapters.create_artifact(
        artifact_type="GlossaryTerm",
        fields={"term": "Widget", "definition": "a thing"},
        workspace_id=workspace_id,
        ctx=ctx,
    )

    row = GlossaryTerm.objects.get(pk=created["id"])
    assert row.artifact_id is not None


@pytest.mark.django_db
def test_every_backed_type_reports_clean(interview_env):
    import io

    from django.core.management import call_command

    out = io.StringIO()
    call_command("check_artifact_backing", stdout=out)

    assert "All artifact types are consistently backed." in out.getvalue()


@pytest.fixture
def interview_env(db):
    from auth_tenancy.context import AuthContext
    from persistence.models import Tenant, Workspace
    from persistence.tenancy import set_tenant

    tenant = Tenant.objects.create(name="t-m3")
    set_tenant(str(tenant.id))
    workspace = Workspace.objects.create(tenant=tenant, name="ws-m3")
    ctx = AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        roles=["admin"],
        workspace_id=workspace.id,
    )
    return ctx, workspace.id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test pytest application/tests/test_milestone_m3_gate.py -v`
Expected: FAIL — `assert "GlossaryTerm is not Artifact-backed yet" not in source`

- [ ] **Step 3: Enable the adapter**

In `backend/application/interview_artifact_adapters.py`, replace the `_glossary_term` adapter's rejection branch with a real create that mirrors the sibling adapters:

```python
def _glossary_term(fields: dict, workspace_id: UUID, ctx: AuthContext) -> dict:
    """Create a GlossaryTerm from interview-collected fields.

    Datenmodell-Konsolidierung Phase 3: GlossaryTerm gained a backing Artifact
    row (spec §4), so the historical refusal no longer applies.
    """
    from application.glossary_service import GlossaryService

    dto = GlossaryService().create(
        ctx=ctx,
        workspace_id=workspace_id,
        term=fields["term"],
        definition=fields.get("definition", ""),
        synonyms=fields.get("synonyms"),
        abbreviation=fields.get("abbreviation", ""),
    )
    return {"id": dto.id, "artifact_type": "GlossaryTerm", "term": dto.term}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test pytest application/tests/test_milestone_m3_gate.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Run the interview and traceability suites**

Run: `docker-compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm -e DB_NAME=test_dmk backend-test pytest application/ traceability/ diagram/ icd/ -q`
Expected: PASS

- [ ] **Step 6: Verify a `diagram-ref` TraceLink in a running stack**

Run: `make up`, then in the SPA create a diagram and link it to a requirement. The link must save and appear in the trace graph — this path raised `SourceNotFoundError` for unbacked rows before the backfill.

- [ ] **Step 7: Commit — Milestone M3**

```bash
git add backend/application/interview_artifact_adapters.py backend/application/tests/test_milestone_m3_gate.py
git commit -m "feat: enable glossary term creation from interviews"
```
