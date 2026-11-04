# Ordnung und Allokation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persistent sibling order in the Requirements and Architecture trees, a hard N:1 Requirement→ArchitectureElement allocation with leaf-relative tiers, and views on it (connection view, card graph, visual groups), as one coherent change set (P0–P6).

**Architecture:** `Artifact.sort_key` (fractional index) plus one move service; allocation stays a `TraceLink(allocated-to)` made N:1 by a partial unique index and one write service; tier names come from a per-workspace ladder computed from the leaf side; one read object (`allocation-view`) feeds all renderers; the freeze comes from the existing workflow `freeze_on_enter`.

**Tech Stack:** Django 6.1 + DRF, Postgres (RLS), pytest; React 19 + TS, Vitest, Playwright, `@xyflow/react` + dagre, React Query.

**Spec:** `docs/superpowers/specs/2026-11-04-ordnung-allokation-design.md` (IDs E*, V*, B*, R*, O* below refer to it). Read it first. Evidence for file locations: spec §2 (`pfad:zeile`, state of `origin/main` e7de2215; **re-verify each location with grep before editing, lines drift**).

## Global Constraints

- Branch from `origin/main` (never from local `main`), name `feat/*` or `fix/*`; one PR per phase P0…P6. Phase order: **P0 → P1 and P2 → P4 → P3 → P5 → P6** (P7 is out of scope, own spec later, O5).
- Git mutations (branch, commit, push, PR) only through the `git` agent. Commit trailers: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01JYx6yrB2hSodcXeSkA5mAq`. Conventional Commits, English, first line ≤ 72 chars.
- Run test suites **sequentially** (≈5.8 GiB RAM). Backend RLS tests need the DB superuser: set `DB_USER` as in the repo's test notes (see `testing/`), otherwise every RLS test errors.
- Migration number = highest existing in `backend/persistence/migrations` + 1 (spec saw `0130`; check at start of each phase; Plan-Index `docs/plans/2026-10-21-backlog-umsetzung-index.md` §d queue rule).
- Every new REST route and MCP tool updates: `docs/agent-templates/tool-manifest.json`, `mcp_server/tool_registry.py`, `test_tool_manifest_drift.py`, OpenAPI tests (`test_openapi_list_params`, `test_schema_completeness_1388`). Counts in CLAUDE.md/README/`clients/registry.yaml` only via `agent-meta-manager` at the end (Task 6.4).
- Errors use the existing envelope; a rule violation by state is **409 `CONFLICT`** with the state name as reason; bad input is **400**.
- Reorder writes only via `QuerySet.update()` on `sort_key` (no `save()`, no signals, `version` and `modified_at` untouched, B3).
- N:1: DB-enforced partial unique index on `pl_tracelink(source)` where `link_type='allocated-to'`. Allocation replace = hard delete of old edge + insert in one transaction (B6).
- Groups never change tier or allocation (V7). Stakeholder Needs have no tier (O3). No fixed tier count; no clamp.
- UI: i18n DE+EN, design tokens only, `data-testid` on every interactive element, keyboard alternative for every drag action. View/Edit toggle is UI-only; enforcement is backend-only (§6.3).
- No literal `reqlo_` keys in config. Do not touch files outside the repo (write scratch to `.tmp/`).

## Review Focus

1. Move under own descendant, across workspace, or with wrong parent type (Req under Arch): must be 400 and change nothing. Pinned in Task 1.3.
2. Two simultaneous reorders in the same parent: no duplicate or crossed `sort_key`. Pinned in Task 1.3.
3. Allocation target is outdated (soft-deleted): edge stays, a finding is reported, tree and list hide the element (B7). Pinned in Task 2.6.
4. Compare of a baseline taken before `sort_key` existed with a new one: no crash, no mass diff. Pinned in Task 1.6.
5. Requirement without allocation and without `derives-from`/`decomposes`: tier stays `NULL`, `level_source='unresolved'`, never guessed; appending a child to a leaf shifts ancestors' tiers and triggers recompute. Pinned in Tasks 2.5, 2.6.
6. Frozen requirement hit by `decompose`/`derive`/import/rollback: skipped with an error entry, never silently moved. Pinned in Task 4.2.

## File Structure

| Area | Files |
|---|---|
| Ordering | `backend/persistence/sort_keys.py` (new), `persistence/models.py` (`Artifact.sort_key`), `application/artifact_service.py` (`move`), `application/validators.py`, `rest_api/views.py`+`urls.py`, `mcp_server/tools/cross_cutting.py` |
| Allocation | `application/trace_link_service.py` (`allocate`), `persistence/models.py` (index, `allocation_intent`, `tier_key`), `traceability/audit/hierarchy.py` (tier computation), `application/tier_ladder_service.py` (new) |
| Freeze | `workflow/precondition_rules.py`, `application/artifact_freeze.py` (new `is_frozen`) |
| Read model | `application/allocation_view_service.py` (new), `rest_api/` allocation views, MCP `allocation.*` |
| Frontend | `components/shared/WorkspaceTree/*`, `components/ConnectionView/*` (new), `components/AllocationGraph/*` (new, reuse `DiagramGraphEditor` internals), `components/WorkspaceSettings/TierLadderSection.tsx` (new), `api/`, `queries/`, `i18n/` |
| Docs | `docs/adr/ADR-027-*.md` (number: next free), `CHANGELOG.md` |

---

# P0 — Hardening and filters (#1660, #1668)

### Task 0.1: Harden hierarchy writes in `ArtifactService`

**Files:**
- Modify: `backend/application/artifact_service.py` (`create_artifact`, `update_artifact`), `backend/rest_api/serializers.py` (parent_id omitted vs null)
- Test: `backend/application/tests/test_artifact_service_hierarchy.py`

**Interfaces:**
- Produces: `UNSET` sentinel; `update_artifact(..., parent_id: UUID | None | UnsetType = UNSET)` where `UNSET`=leave, `None`=detach. `ArtifactService.validate_parent(artifact_type, workspace_id, artifact_id|None, parent_id) -> None` raising the existing validation error (→ 400) for: self-parent, parent in another workspace, parent of incompatible type, cycle through ancestors.

- [ ] **Step 1: Write failing tests** `test_self_parent_rejected`, `test_cross_workspace_parent_rejected`, `test_type_mismatch_rejected` (Requirement under ArchitectureElement), `test_cycle_via_ancestor_rejected`, `test_parent_none_detaches`, `test_omitted_parent_keeps_parent`, `test_tree_read_survives_legacy_self_parent_row` (insert a self-parent row with raw SQL, `get_tree` terminates). Each asserts the 400/exception and that DB state is unchanged.
- [ ] **Step 2:** Run `cd backend && pytest application/tests/test_artifact_service_hierarchy.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement `validate_parent` and call it from both create and update (replace the ineffective cycle check noted in spec §2). Add a depth/visited guard to the tree CTE so legacy cycles terminate.
- [ ] **Step 4:** Rerun the tests. Expected: PASS. Then run `pytest application/tests -k artifact -q` for regressions.
- [ ] **Step 5:** Commit `fix: validate artifact parent on create and update (#1660)`.

### Task 0.2: Filters `allocated` and `level` (#1668)

**Files:**
- Modify: Requirement list view and filterset in `backend/rest_api/views.py` (locate with `grep -n "class RequirementViewSet"`), `mcp_server/tools/` `requirement.query`
- Test: `backend/rest_api/tests/test_requirement_filters_allocation.py`

**Interfaces:**
- Produces: query params `?allocated=true|false` (exists/not exists a `TraceLink` with `link_type='allocated-to'` and `source=requirement artifact`), `?level=<int 1..4>`; any other value → 400 with the field name in the error.

- [ ] **Step 1: Failing tests:** `test_allocated_true_returns_only_allocated`, `test_allocated_false_returns_only_unallocated`, `test_level_filter`, `test_invalid_allocated_is_400` (`?allocated=maybe`), `test_invalid_level_is_400` (`?level=9`, `?level=x`), and the same for MCP `requirement.query`.
- [ ] **Step 2:** Run the file; expected FAIL.
- [ ] **Step 3:** Implement with an `Exists` subquery (no N+1). Reject invalid values in the filterset, not silently ignore.
- [ ] **Step 4:** Run; expected PASS. Update OpenAPI tests/manifest if params are listed there.
- [ ] **Step 5:** Commit `feat: add allocated and level filters to requirement list (#1668)`.

---

# P1 — Order (`sort_key`) and move

### Task 1.1: Fractional key helper

**Files:** Create `backend/persistence/sort_keys.py`; Test `backend/persistence/tests/test_sort_keys.py`

**Interfaces:**
- Produces: `key_between(before: str | None, after: str | None) -> str` (strictly between, `None` = open end, raises `ValueError` if `before >= after`); `rebalance_keys(n: int) -> list[str]` (n evenly spread ascending keys).

- [ ] **Step 1: Failing tests:** `test_between_is_strictly_ordered` (random 1000 inserts keep list sorted), `test_open_ends`, `test_equal_keys_raise`, `test_rebalance_sorted_and_unique`, `test_keys_use_ascii_only` (sorts identically under DB collation `C` and Python).
- [ ] **Step 2:** `pytest persistence/tests/test_sort_keys.py -v`; FAIL.
- [ ] **Step 3:** Implement base-62 midpoint algorithm (ASCII digits+letters in ascending code order).
- [ ] **Step 4:** PASS. **Step 5:** Commit `feat: add fractional sort key helper`.

### Task 1.2: `Artifact.sort_key` field, index, backfill

**Files:** Modify `backend/persistence/models.py` (Artifact); Create migration `backend/persistence/migrations/<next>_artifact_sort_key.py`; Test `backend/persistence/tests/test_sort_key_migration.py`

**Interfaces:**
- Produces: `Artifact.sort_key: CharField(max_length=64, null=True, db_collation="C")`, index `(parent, sort_key, id)`. Roots (`parent` NULL) group by `(workspace, artifact_type)`. Only Requirement and ArchitectureElement are backfilled (B4); others stay NULL.

- [ ] **Step 1: Failing test:** with parent P and children created at t1<t2<t3, after running the migration forward the keys ascend in `(created_at, id)` order; running twice changes nothing; reverse removes the column; other artifact types keep NULL.
- [ ] **Step 2:** Run; FAIL. **Step 3:** Write model field, migration (schema + idempotent `RunPython` backfill using `rebalance_keys` per sibling block, batched). **Step 4:** PASS. **Step 5:** Commit `feat: add Artifact.sort_key with backfill`.

### Task 1.3: `ArtifactService.move` and sorted reads

**Files:** Modify `backend/application/artifact_service.py`, `application/validators.py` (I1–I5 at `:11-15`), `application/requirement_service.py:~1250`, `application/architecture_service.py:~493`, tree CTE (`get_tree`, `list_child_summaries`); Test `backend/application/tests/test_artifact_move.py`

**Interfaces:**
- Consumes: `key_between`, `validate_parent` (0.1).
- Produces: `ArtifactService.move(*, artifact_id: UUID, new_parent_id: UUID | None, after_id: UUID | None | UnsetType = UNSET, actor) -> Artifact`. Semantics (B8): `UNSET` = append at end; `None` = first; otherwise `after_id` must be a child of `new_parent_id` else 400. Writes `sort_key` (and `parent_id` if changed) by `QuerySet.update()`, emits audit event `reordered` (who, from, to). New artifacts get `sort_key = key_between(last_sibling, None)`. All lists and the tree order by `sort_key ASC NULLS LAST, created_at, id`. Appends/rebalances lock the parent row (`select_for_update`).

- [ ] **Step 1: Failing tests:** `test_move_between_siblings_writes_one_row` (assert exactly one `UPDATE` via `CaptureQueriesContext`, `version` unchanged), `test_move_first_and_last`, `test_after_id_not_child_is_400`, `test_move_into_descendant_is_400`, `test_move_across_workspace_is_400`, `test_requirement_under_architecture_is_400`, `test_architecture_invariants_I1_I5`, `test_audit_event_reordered`, `test_lists_and_tree_follow_sort_key`, `test_new_child_appended_last`, `test_concurrent_moves_same_parent` (two threads/transactions; afterwards all keys unique and total order stable).
- [ ] **Step 2:** `pytest application/tests/test_artifact_move.py -v`; FAIL.
- [ ] **Step 3:** Implement `move`; switch all sibling orderings; hook point `_assert_not_frozen(artifact)` (no-op now, filled in Task 4.2). After a parent change on an ArchitectureElement call `recompute_requirement_levels` for the workspace (hook, wired fully in Task 2.6).
- [ ] **Step 4:** PASS; run `pytest application -q -k "requirement or architecture or artifact"`.
- [ ] **Step 5:** Commit `feat: add ArtifactService.move and ordered sibling reads`.

### Task 1.4: REST and MCP surface

**Files:** Modify `rest_api/views.py`, `rest_api/urls.py`, `mcp_server/tools/cross_cutting.py:~1380`, `mcp_server/tool_registry.py`, manifest; remove dead `_tree_node_to_dict`; Test `rest_api/tests/test_move_api.py`, `mcp_server/tests/test_artifact_move_tool.py`

**Interfaces:**
- Produces: `POST /api/v1/artifacts/{id}/move/` body `{parent_id, after_id}` (omit `after_id` = end, `null` = first) → 200 with the artifact; `GET /api/v1/workspaces/{id}/tree/?type=requirement|architecture` (sorted, soft-deleted hidden); MCP `artifact.move`, `artifact.get_tree` sorted.

- [ ] **Step 1: Failing tests:** 200 path, 400 cases from 1.3, 403 without write rights, tree order equals `sort_key`, MCP parity (same error codes), manifest drift test.
- [ ] **Step 2–4:** run, implement, run (also `test_tool_manifest_drift.py`, OpenAPI tests); regenerate manifest via the repo's `export_tool_manifest` command.
- [ ] **Step 5:** Commit `feat: expose artifact move and ordered tree via REST and MCP`.

### Task 1.5: Importers and decompose keep source order

**Files:** Modify ReqIF/CSV importers and `decompose` services (find with `grep -rn "create_artifact\|bulk_create" backend/application | grep -i "import\|decompose"`); Test next to each.

- [ ] **Step 1:** Failing test per source: `test_reqif_import_keeps_document_order`, `test_csv_import_keeps_row_order`, `test_decompose_keeps_llm_order` — children read back via the tree equal the source order.
- [ ] **Step 2–4:** run (FAIL), assign sequential `sort_key`s through one `rebalance_keys(n)` call per block, run (PASS).
- [ ] **Step 5:** Commit `feat: preserve source order on import and decompose`.

### Task 1.6: Baseline snapshot, diff, rollback classification

**Files:** Modify baseline `state_capture` and `Diff` (V8), `restorable_fields.py` (R9); Test `baseline/tests/test_sort_key_baseline.py`

**Interfaces:** Snapshot contains `sort_key`; diff reports `"Position geändert"` for a changed `sort_key`; a block rebuild yields **one** bundled event; snapshots without `sort_key` compare without error and without a diff entry.

- [ ] **Step 1: Failing tests:** `test_snapshot_contains_sort_key`, `test_single_move_one_diff_entry`, `test_old_snapshot_without_sort_key_no_crash_no_noise`, `test_rebalance_one_bundled_event`, `test_sort_key_classified_in_restorable_fields`.
- [ ] **Step 2–4:** run, implement, run. **Step 5:** Commit `feat: include sort_key in baseline snapshot and diff`.

### Task 1.7: Frontend — reorder and move in both trees

**Files:** Modify `frontend/src/components/shared/WorkspaceTree/workspace-tree.tsx:~306-335`, `tree-drag.ts`, `RequirementList.tsx:~118-130`, `ArchitectureEditors.tsx:~782`, `RequirementArtifactForm.tsx:50-52` (fix wrong comment), `api/`, `i18n/`; Create `MoveDialog.tsx`; Tests `workspace-tree.reorder.test.tsx`, `e2e/tests/tree-reorder.spec.ts`

**Interfaces:**
- Produces: `WorkspaceTree` prop `onReorder(nodeId: string, newParentId: string | null, afterId: string | null | undefined): Promise<void>`; `moveArtifact(id, {parent_id, after_id})` in `api/`; optimistic update with rollback on error; Alt+↑/↓ keyboard; "Move…" dialog with parent search.

- [ ] **Step 1: Failing tests:** drop between two nodes calls `onReorder` with the right `afterId`; failed call restores order and shows the error; Alt+↓ moves one step; dialog moves under a chosen parent; requirement tree now allows re-parenting (was missing); E2E: order survives reload in both trees.
- [ ] **Step 2–4:** `cd frontend && npx vitest run src/components/shared/WorkspaceTree`; implement; PASS; then the Playwright spec.
- [ ] **Step 5:** Commit `feat: reorder and re-parent in both workspace trees`.

---

# P2 — N:1 allocation, tiers

### Task 2.1: Unique index N:1

**Files:** Modify `persistence/models.py` (`TraceLink.Meta.constraints`); Create migration `<next>_tracelink_allocated_to_unique.py`; Test `persistence/tests/test_allocated_to_unique.py`

**Interfaces:** `UniqueConstraint(fields=["source"], condition=Q(link_type="allocated-to"), name="uniq_tracelink_allocated_to_source")`. The migration first runs a check query; on violations it raises with the list of requirement IDs (loud abort, R3). Work on `TraceLink.source/target` (Artifact IDs), not Requirement IDs (R1).

- [ ] **Step 1: Failing tests:** second `allocated-to` from the same source raises `IntegrityError`; other link types unaffected; migration with a seeded duplicate aborts and names the IDs; migration on clean data is idempotent.
- [ ] **Step 2–4:** run, implement, run. **Step 5:** Commit `feat: enforce N:1 allocation with partial unique index`.

### Task 2.2: One allocation write service

**Files:** Modify `application/trace_link_service.py:~1432` (`allocate`), generic create path (REST `/trace-links/`, MCP `traceability.create_link`), `derive`, `ArchitectureDecomposeService`, `ai_derivation.suggest_architecture_for_requirement`, `link_types/migration_ops.py`, seeds (find: `grep -rn "allocated-to" backend --include=*.py`); Test `application/tests/test_allocation_service.py`

**Interfaces:**
- Produces: `TraceLinkService.allocate(*, requirement_id, element_id, actor) -> TraceLink` (replace in one transaction, hard delete of old edge, validates I4 and workspace, hook `_assert_not_frozen`, triggers level recompute) and `deallocate(*, requirement_id, actor) -> None`. The generic create path with `link_type='allocated-to'` and an existing edge returns **409** (no duplicate, no silent replace).

- [ ] **Step 1: Failing tests:** `test_allocate_replaces_in_one_transaction` (failure after delete leaves old edge), `test_generic_second_target_is_409`, `test_allocate_to_ancestor_rejected_I4`, `test_each_writer_goes_through_allocate` (patch `allocate`, call derive/decompose/suggest-accept/seed path, assert called), `test_deallocate`.
- [ ] **Step 2–4:** run, implement, route every writer found by the grep through `allocate`, run. **Step 5:** Commit `feat: route all allocation writes through one service`.

### Task 2.3: `allocation_intent`

**Files:** Modify `persistence/models.py` (Requirement), migration, serializers, Coverage aggregation, MCP `requirement.update/query`; Test `traceability/tests/test_allocation_intent.py`

**Interfaces:** `Requirement.allocation_intent`: choices `allocated|not_allocatable|unassigned`, default `unassigned`; Coverage counts `not_allocatable` as "bewusst ausgenommen", not as gap. Setting `not_allocatable` on an allocated requirement is 400 (deallocate first).

- [ ] **Step 1–5:** tests `test_default_unassigned`, `test_not_allocatable_not_counted_as_gap`, `test_not_allocatable_with_edge_is_400`, `test_allocate_sets_intent_allocated`; implement; commit `feat: add Requirement.allocation_intent`.

### Task 2.4: Tier ladder model and API

**Files:** Create `persistence/models.py` `WorkspaceTier`, `application/tier_ladder_service.py`, migration (**with RLS policy copied from an existing tenant table migration**), REST `GET/PUT /api/v1/workspaces/{id}/tiers/`; Modify `Requirement` (+`tier_key` nullable, keep `level`), `level_source` choices (+`derived_allocation`, `derived_hierarchy`, `derived_type`, `unresolved`); Test `application/tests/test_tier_ladder.py`, RLS test

**Interfaces:**
- `WorkspaceTier(workspace, tier_key: slug, name: JSON {de,en}, position: int, rule: 'first'|'middle'|'from_end', from_end: int | None)`; unique `(workspace, tier_key)`. `TierLadderService.get(workspace_id) -> list[Tier]`, `replace(workspace_id, tiers, actor)` (workspace admin only), `seed_default(workspace_id)` = `erste`, `dazwischen`, `vorletzte (from_end=1)`, `letzte (from_end=0)` with the integer alias = position+1. Removing a tier referenced by `Requirement.tier_key` → 409 unless a `merge_into` tier is given. Renaming changes only `name`. Ladder must contain exactly one `first` and exactly one `from_end=0` and at most one `middle`.
- Migration seeds every existing workspace and maps existing `level` 1..4 to the seed tiers.

- [ ] **Step 1: Failing tests:** seed on new workspace; rename keeps `tier_key`; delete referenced tier is 409; merge moves requirements; non-admin 403; RLS: tenant B cannot read tenant A tiers; invalid ladder (two `first`) is 400; migration maps legacy levels.
- [ ] **Step 2–4:** run, implement, run. **Step 5:** Commit `feat: add per-workspace tier ladder`.

### Task 2.5: Leaf-relative tier computation and `recompute_requirement_levels`

**Files:** Modify `backend/traceability/audit/hierarchy.py:~665-720` (`recompute_requirement_levels`, remove `ARCHITECTURE_DEPTH_TO_LEVEL` use at `:218`); Test `traceability/tests/test_tier_compute.py`

**Interfaces:**
- Produces pure function `tier_for_element(element_id, ladder, tree) -> str | None` and `recompute_requirement_levels(workspace_id, *, dry_run: bool = False) -> list[LevelChange]`. Rules: root → `first`; else height h = longest path down to a leaf; `from_end` entry with `n == h` wins; otherwise the `middle` entry; no match → `None`. Source order per requirement (V6): `manual` (unchanged) > allocation (tier of target, `derived_allocation`) > `derives-from`/`decomposes` parent requirement's tier **moved one position toward the end of the ladder** (`derived_hierarchy`; **[Annahme, to confirm with the PO]**: from the last ladder entry the result is `None`/`unresolved`) > type default (`derived_type`) > `None` + `unresolved`. Writes `tier_key`, the integer alias `level`, `level_source` by bulk `UPDATE` (stays the single writer, ADR-005 successor). Nothing is clamped or guessed.

- [ ] **Step 1: Failing tests:** `test_root_is_first`, `test_leaf_is_last`, `test_parent_of_leaf_is_vorletzte`, `test_unequal_branch_depths` (3-deep and 6-deep branches), `test_single_node_tree_is_first`, `test_allocation_beats_derivation`, `test_manual_wins`, `test_unallocated_without_derivation_is_none_unresolved`, `test_dry_run_writes_nothing_and_lists_changes`, `test_appending_child_shifts_ancestor_tiers`.
- [ ] **Step 2–4:** run, implement, run. **Step 5:** Commit `feat: compute requirement tier from allocation leaf-relative`.

### Task 2.6: Triggers and findings

**Files:** Modify `application/trace_link_manager.py:~430,541,626,650`, `ArtifactService.move`/create/delete of ArchitectureElement; Test `application/tests/test_level_triggers.py`

**Interfaces:** Allocation create/change/remove, architecture parent change, child add/remove → recompute of the affected workspace (async via Celery if the existing recompute is async; otherwise inline, follow the existing pattern). Allocation to an outdated element is kept and appears in the findings list (B7).

- [ ] **Step 1: Failing tests:** `test_allocate_triggers_recompute`, `test_move_architecture_child_triggers_recompute`, `test_outdated_target_edge_kept_and_reported`, `test_reactivated_element_back_at_old_position`.
- [ ] **Step 2–4:** run, implement, run. **Step 5:** Commit `feat: recompute tiers on allocation and tree changes`.

### Task 2.7: Convert level consumers

**Files:** inventory first: `grep -rn "RequirementLevel\|\.level\b\|level_source\|ARCHITECTURE_DEPTH_TO_LEVEL\|stage_matrix" backend frontend/src --include=*.py --include=*.ts --include=*.tsx`. Expected: serializers, MCP tools, `stage_matrix.py`, bootstrap, audit rules VERIF-P8, ARCH-003, TRACE-P5, CONS-P13, exports, `RequirementList`, `TraceSpine`. Test: one per consumer.

**Interfaces:** Consumers read `tier_key` and the display name; they no longer assume values 1–4. CONS-P13 is replaced by "every requirement has `level_source` set". API keeps `level` (alias) and adds `tier_key`, `tier_name`.

- [ ] **Step 1:** write the inventory as a checklist in the PR description and one failing test per consumer using a ladder with 3 and with 6 entries.
- [ ] **Step 2–4:** run, convert, run (backend then frontend, sequentially).
- [ ] **Step 5:** Commit `refactor: read tiers from the workspace ladder`.

### Task 2.8: Dry-run report, one-shot backfill, ADR

**Files:** Modify `report_requirement_levels` management command (`--dry-run`, `fill_only`), Create `docs/adr/ADR-027-*.md` (use next free number), update ADR-005 `superseded_by`; Test `traceability/tests/test_level_backfill_command.py`

- [ ] **Step 1: Failing tests:** dry run prints counts per `level_source` and writes nothing; real run sets `level_source` for all requirements; second run changes 0 rows; old baselines unchanged.
- [ ] **Step 2–4:** run, implement; ADR records: leaf-relative tiers, no clamp, baseline-diff effect (R2/R11), `satisfies→function` as separate world (R10), literature caveat that clause numbers are unverified. **Step 5:** Commit `feat: add level backfill dry run and ADR-027`.

### Task 2.9: Allocation list API and MCP

**Files:** Modify `rest_api/` (+`GET /api/v1/allocations/`), `mcp_server` `allocation.query`; Test `rest_api/tests/test_allocations_api.py`

**Interfaces:** filters `requirement`, `element`, `allocated`, `level`/`tier`, `intent`; counters in the response meta.

- [ ] **Step 1–5:** tests for each filter, invalid value 400, tenant isolation; implement; manifest/OpenAPI; commit `feat: add allocations list API and allocation.query`.

### Task 2.10: Ladder names UI

**Files:** Create `frontend/src/components/WorkspaceSettings/TierLadderSection.tsx` (model on `TreeDisplaySection.tsx`), `api/tiers.ts`, i18n; Test `TierLadderSection.test.tsx`

- [ ] **Step 1: Failing tests:** lists tiers; rename saves; add/remove/reorder; invalid ladder shows the server error; non-admin sees read-only; the quick "3 names" helper builds `erste/dazwischen/letzte`.
- [ ] **Step 2–5:** run, implement, run, commit `feat: edit the tier ladder in workspace settings`.

---

# P4 — Freeze from workflow

### Task 4.1: `is_frozen` for Requirement and ArchitectureElement

**Files:** Create `application/artifact_freeze.py`; Modify `workflow/precondition_rules.py:~859-881`, `application/document_service.py:94` (reuse, do not duplicate); Test `application/tests/test_artifact_freeze.py`

**Interfaces:** `is_frozen(artifact) -> FreezeInfo | None` (`FreezeInfo.state_name`) based on the artifact's current workflow state `state_meta.freeze_on_enter`. Default presets contain no frozen states → nothing changes.

- [ ] **Step 1–5:** tests `test_frozen_state_detected`, `test_unfrozen_state_none`, `test_default_presets_have_no_frozen_state`, `test_document_behaviour_unchanged`; implement; commit `feat: generalise freeze check to requirements and elements`.

### Task 4.2: Enforce in move and allocation

**Files:** Modify `ArtifactService.move` (`_assert_not_frozen`), `TraceLinkService.allocate/deallocate`, `decompose`, `derive`, importers, rollback (ADR-025); Test `application/tests/test_freeze_enforcement.py`

**Interfaces (E6, B11):** frozen **requirement**: no move, no re-parent, no allocate/deallocate → 409 `CONFLICT` reason=state name. Frozen **element**: itself immovable but still valid allocation **target**. State of the **requirement** decides. `decompose`/`derive`/import/rollback skip frozen objects and return an error entry per skipped object.

- [ ] **Step 1: Failing tests:** `test_frozen_requirement_cannot_move`, `..._cannot_allocate`, `..._cannot_reallocate`, `test_frozen_element_accepts_allocation`, `test_frozen_element_cannot_move`, `test_decompose_skips_frozen_with_error_entry`, `test_import_skips_frozen`, `test_rollback_respects_freeze`.
- [ ] **Step 2–5:** run, implement, run, commit `feat: enforce workflow freeze on move and allocation`.

### Task 4.3: Configure freeze in the workflow editor

**Files:** Modify `workflow/definition_store.py:~438-450,1144`, workflow REST serializer, frontend workflow editor (find: `grep -rln "state_meta\|WorkflowEditor" frontend/src`); Test backend + `WorkflowEditor` test

**Interfaces:** per state a boolean "sperrt Bearbeitung" persisted as `state_meta.freeze_on_enter`; API accepts and returns it; UI hint explains what is locked (position, parent, allocation) (R8).

- [ ] **Step 1–5:** tests: API round-trip; toggling makes `is_frozen` true for artifacts in that state; UI toggle calls API; presets unchanged; commit `feat: configure state freeze in the workflow editor`.

### Task 4.4: Show the lock

**Files:** Modify `WorkspaceTree` node rendering, move/allocate error handling; Test `workspace-tree.lock.test.tsx`

- [ ] **Step 1–5:** failing tests: lock icon and tooltip with state name; drag disabled on frozen requirement; 409 shows the reason; commit `feat: show workflow lock in trees`.

---

# P3 — Connection view

### Task 3.1: `allocation-view` read object

**Files:** Create `application/allocation_view_service.py`, REST `GET /api/v1/workspaces/{id}/allocation-view/`, MCP `allocation.view`; Test `application/tests/test_allocation_view.py`, API test

**Interfaces (V10, B9):** flat rows, `page_size` default 200, max 500; each row: `{kind: 'requirement'|'element', id, parent_id, sort_key, title, state, tier_key, tier_name, type, category, allocated_to, allocation_intent, locked: {state}|null, findings: [...]}`. Filters: `allocated`, `intent`, `tier`, `type`, `category`, `state`, `group`, `element_subtree=<id>`, `q`, `open` (= state not final and not frozen), `locked`, `has_findings`. Response meta: `{unallocated, locked, findings, total}` computed over the filtered set.

- [ ] **Step 1: Failing tests:** each filter; combination is AND; `element_subtree` includes descendants; pagination caps at 500; counters; tenant isolation; query count constant (`assertNumQueries` for 50 vs 500 rows).
- [ ] **Step 2–5:** run, implement, run, manifest/OpenAPI, commit `feat: add allocation-view read object`.

### Task 3.2: View shell, filters, saved views

**Files:** Create `frontend/src/components/ConnectionView/{ConnectionView.tsx,FilterBar.tsx,useAllocationView.ts}`, route + nav entry, i18n; Test `ConnectionView.test.tsx`

**Interfaces:** header with view switcher `[Baum | Zwei Spalten | Matrix | Graph]` (default Baum = B, Graph appears in P5), quick filters Offen / Nicht allokiert / Gesperrt / Befunde, free filters, element-subtree picker; filters and selection survive switching; filter state in URL; saved views per user via the existing user-preference mechanism (find it with `grep -rn "preference" frontend/src/api`), counters from meta.

- [ ] **Step 1–5:** failing tests for filter→query params, URL round-trip, switcher keeps filters, saved view create/apply; implement; commit `feat: add connection view shell with smart filters`.

### Task 3.3: Renderer B (tree with requirements) and allocate/unlink

**Files:** Create `ConnectionView/TreeRenderer.tsx`; Test `TreeRenderer.test.tsx`

**Interfaces:** architecture tree by `parent_id`/`sort_key`, requirements as sub-lists, block "Nicht allokiert"; drag requirement onto element → `allocate`, drag to "Nicht allokiert" → `deallocate`; buttons "Allokieren auf …" (element picker with search) as keyboard path; frozen requirement not draggable; backend errors shown verbatim.

- [ ] **Step 1–5:** tests: grouping, counts, drag calls allocate, picker path, 409 shown; implement; commit `feat: connection view tree renderer`.

### Task 3.4: Renderers A (two columns) and C (matrix)

**Files:** Create `TwoColumnRenderer.tsx`, `MatrixRenderer.tsx`; Tests

**Interfaces:** A: selection highlights the counterpart on the other side, drag left→right allocates. C: rows requirements, columns elements of the chosen level, one dot per row max, footer sums, window = current page (B9) with an explicit "Seite x von y".

- [ ] **Step 1–5:** tests: highlight both ways, matrix never shows two dots per row, footer sums, paging; implement; commit `feat: two-column and matrix renderers`.

### Task 3.5: Allocation assistant

**Files:** Create `ConnectionView/AllocationAssistant.tsx`, backend batch endpoint `POST /api/v1/allocations/bulk/` (all-or-nothing) + MCP; Test both

**Interfaces:** multi-select + "Allokieren auf …" calls bulk (**whole batch rejected if one item fails, nothing written**, error lists the item); "Vorschläge" calls the existing `suggest_architecture_for_requirement` per unallocated item, shows target + reason, accept one or all; nothing is written without confirmation.

- [ ] **Step 1–5:** tests: bulk atomicity with one frozen requirement, suggestion accept writes via `allocate`, no write on cancel; implement; commit `feat: allocation assistant with bulk and suggestions`.

### Task 3.6: E2E main path

**Files:** Create `e2e/tests/connection-view.spec.ts`

- [ ] **Step 1:** write the spec: filter "Nicht allokiert" → count matches → allocate by picker → count decreases → switch to matrix and see the dot. **Step 2:** `cd e2e && npx playwright test connection-view.spec.ts`. Expected PASS. **Step 3:** Commit `test: e2e for connection view`.

---

# P5 — Card graph

### Task 5.1: Graph model builder

**Files:** Create `frontend/src/components/AllocationGraph/buildGraph.ts`; Test `buildGraph.test.ts`

**Interfaces:** `buildGraph(rows: AllocationRow[], opts: {collapsed: Set<string>, dimmed: (row) => boolean}) -> {nodes: Node[], edges: Edge[]}`; requirement cards left, element cards right, hierarchy edges grey, allocation edges dashed blue between sides; dagre layout with sibling order from `sort_key`; non-matching cards get `dimmed`, never removed; unallocated and frozen flags on node data.

- [ ] **Step 1–5:** tests: sibling order, edge per allocation (max one per requirement), collapsed branches hide descendants but keep aggregate count, dimmed not removed, 500 rows lays out under a time budget; implement; commit `feat: build card graph model from allocation rows`.

### Task 5.2: Cards and per-workspace card fields

**Files:** Create `AllocationGraph/{RequirementCard,ElementCard}.tsx`, `WorkspaceSettings/CardFieldsSection.tsx`, backend setting store (follow the `TreeDisplayFields` pattern from #1257 for System < Workspace < User rank); Tests

**Interfaces:** configurable fields for requirement cards and element cards separately (ID, title, state, tier, type, category, group, allocation count, lock, owner), order and row count; **lock, finding and unallocated markers are not hideable** (settings API rejects hiding them with 400).

- [ ] **Step 1–5:** tests: settings round-trip with rank resolution; hiding a mandatory marker is 400; card renders chosen fields; implement; commit `feat: configurable card fields per workspace`.

### Task 5.3: Graph interactions and View/Edit toggle

**Files:** Create `AllocationGraph/AllocationGraph.tsx`; extend `DiagramGraphEditor` internals only where needed (multi-select, external drop, handle→node binding without UUID entry); Test `AllocationGraph.test.tsx`

**Interfaces:** click highlights card connections; drag from requirement handle onto element card allocates; onto another element re-allocates; collapse/expand; zoom, pan, minimap; keyboard "Allokieren auf …"; mode toggle **Ansicht (default)** hides handles and disables drag, **Bearbeiten** requires write rights; the graph stores nothing of its own.

- [ ] **Step 1–5:** tests: view mode renders no handle and no write call can be triggered; edit mode drag calls `allocate`; frozen card has no handle; keyboard path works; implement; commit `feat: interactive allocation card graph`.

### Task 5.4: UI ↔ REST error parity and E2E

**Files:** Test `e2e/tests/allocation-graph.spec.ts`, `frontend/src/components/AllocationGraph/errors.test.tsx`

- [ ] **Step 1: Failing tests:** for lock, cycle (I4) and N:1 violation the graph shows the same error code the REST call returns (assert both from one fixture). **Step 2–4:** run, fix gaps, run. **Step 5:** Commit `test: graph error parity with REST`.

---

# P6 — Groups (visual clusters)

### Task 6.1: Group artifact, membership link, `TraceLink.sort_key`

**Files:** Modify `persistence/models.py` (artifact type `Group`, nullable `TraceLink.sort_key`), `link_types/builtin.py` (+`grouped-in`, requirement→group, many allowed), migration with RLS, Baseline capture; Test `persistence/tests/test_group_model.py`

**Interfaces:** a requirement may be in several groups (V11); membership order lives in `TraceLink.sort_key`, filled only for `grouped-in` edges; groups appear in baseline snapshots and diffs.

- [ ] **Step 1–5:** tests: requirement in two groups; membership sorted per group; baseline includes the group and its members; RLS isolation; commit `feat: add Group artifact and grouped-in link`.

### Task 6.2: Group service, REST, MCP

**Files:** Create `application/group_service.py`, REST `…/groups/`, `…/groups/{id}/members/`, `…/groups/{id}/members/{req}/move/`, MCP `group.*`; Test

**Interfaces:** create/update/outdate group (normal versions and workflow); `add_member`, `remove_member`, `move_member(group_id, requirement_id, after_id)` (uses `key_between`, one-row write); a frozen group blocks member changes; a group never alters `tier_key`, `level_source` or allocation (test asserts unchanged rows).

- [ ] **Step 1–5:** tests incl. freeze, no tier/allocation effect, tenant isolation; manifest/OpenAPI; commit `feat: group service with REST and MCP`.

### Task 6.3: Pseudo-folders in the UI

**Files:** Modify `WorkspaceTree` (toggle "Gruppen anzeigen"), `ConnectionView/FilterBar` (group filter), graph card field "group"; Create `GroupManager.tsx`; Test `groups.test.tsx`, `e2e/tests/groups.spec.ts`

**Interfaces:** toggle on → groups render as collapsible pseudo-folders containing their members (a requirement may appear under several groups, marked as such); drag inside a group reorders by group order; create group, add/remove members; toggle off → plain tree unchanged.

- [ ] **Step 1–5:** tests: toggle, multi-group display, reorder inside group calls `move_member`, toggle off identical to baseline tree; implement; commit `feat: show groups as pseudo-folders`.

### Task 6.4: Rollup — docs, counts, changelog

**Files:** Modify `CHANGELOG.md` (breaking: sibling sort order now `sort_key`; filters; `level` alias; N:1), `docs/` user docs for tiers/groups/freeze setting (internal docs German, external English)

- [ ] **Step 1:** write CHANGELOG and docs. **Step 2:** dispatch `agent-meta-manager` to update tool counts in CLAUDE.md, README and `clients/registry.yaml` from the regenerated manifest. **Step 3:** run the full suites sequentially: `cd backend && pytest -q`, then `cd frontend && npx vitest run`, then Playwright shards. Expected: all green except tests already known red on `origin/main` (list them in the PR). **Step 4:** Commit `docs: changelog and docs for ordering and allocation`.

---

## Open items carried into execution (do not guess; ask the PO)

- Integer alias `level`: how long it stays in exports and API (O3).
- How the baseline diff presents tier shifts after appending a child (O3).
- Task 2.5 derivation rule from the last ladder entry (marked **[Annahme]**).
- O4: layout limits for very deep trees; measure in Task 5.1 and file an issue if the budget is missed.
- Norm clause citations are unverified (R11); do not copy them into ADR-027 without checking the sources.
