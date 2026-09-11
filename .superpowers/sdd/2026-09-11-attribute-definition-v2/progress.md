# SDD ledger — plan: docs/superpowers/plans/2026-09-11-attribute-definition-v2.md

Controller: background fork (no Agent tool available — implementer-only, no
self-dispatched independent review; the coordinator dispatches review rounds
separately after each phase/whole-branch).

## ⏸ RESUME POINT

**Last completed task: Task 2 (workspace create/delete + MCP tools), committed `fa02f72d`.**
**Branch:** `feat/attribute-definition-v2`, worktree `.worktrees/attribute-definition-v2-impl`.
**Next: Task 3** (`AttributeCreateDialog` frontend component + wiring, Phase B).
**No independent review has run on Tasks 1-2 yet** — this fork has no `Agent` tool; the coordinator needs to dispatch a `code-reviewer` pass before this branch is considered done, per this repo's SDD convention.

## Migration numbers (re-verified, plan text is stale)

- `attribute_definitions` app: last migration is `0007_risk_interview_elicits_probability_impact.py` (added by the parallel `interview-engine-fix` branch after this plan was written) → next free is `0008`, not the plan's stated `0007`.
- `persistence` app: last is `0083_interview_transcript_summary.py` (from PR #903) → next free is `0084`, not the plan's stated `0082` (`0082_merge_traceability_and_attribute_branches.py` already exists).
- Verify again before any `makemigrations` — these apps get touched by other in-flight branches.

## Task 1: Service-layer create/delete + REST endpoints, global scope — DONE

- `create_global`/`delete_global` added to `AttributeDefinitionService` (`backend/application/attribute_definition_service.py`) as thin wrappers around `update_global`, reusing its core-lock/locked/propagation/audit validation unchanged.
- `validate_new_attribute_name(name, existing_attributes, *, reserved_field_names=())` added to `backend/attribute_definitions/schema.py`: rejects non-snake_case, name collisions, and (for `kind="extended"`) model-field-name collisions.
- Model field names resolved via `AttributeDefinitionService._model_field_names`, which reuses `bootstrap_attribute_definitions.MODEL_LOCATIONS`/`_resolve_model` (inline import, no module-load-time Django management import) instead of re-deriving the item-type → model mapping.
- REST: `AttributeDefaultsDetailView` gained `.post` (201, create) and `.delete` (200, `?name=` query param) on the SAME existing URL (`attribute-defaults/<item_type>/<preset>/`) — no `urls.py` change needed, since the URL already existed for GET/PUT.
- Frontend: `AttributeItemType` union gained `"ChangeRequest"` (V5 spec-drift fix from the plan's spec-verification section).
- Tests: 8 new service-level tests, 6 new REST tests. Full scoped run green: `application/tests/test_attribute_definition_service.py` + `rest_api/tests/test_attribute_definition_views.py` = 46 passed. Architecture ratchet (`test_architecture.py`, ORM-access + import-allowlist) + `attribute_definitions/tests/` = 224 passed, no regressions.
- Commit: `26a9e861` "feat(attributes): add global create/delete (Task 1)".

## Task 2: Service-layer create/delete + MCP tools, workspace scope — DONE

- `create_workspace`/`delete_workspace` added to `AttributeDefinitionService`, mirroring Task 1's global wrappers but materializing the workspace row first (`self._workspace.resolve(...)`, same as `resolve()`) so they work on the very first touch of an item type in a workspace.
- **Resolved the plan's open edge case** (deleting an attribute the workspace only ever *inherited* from global, no prior local override): it behaves exactly like any other workspace edit — `update_workspace` flips `is_customized=True`, and since `GlobalAttributeDefinitionStore._propagate`/`_derived_row_filter` only ever rewrite `is_customized=False` rows, a later global update does NOT resurrect the deleted attribute. Verified with a dedicated round-trip test (materialize → delete inherited extended attribute → `update_global` → `resolve` again → attribute still gone), not assumed.
- 4 new MCP tools: `attribute_definition.create`/`.delete` (global), `.create_workspace`/`.delete_workspace` (workspace) — same `CrossTenantWorkspaceError` → `PERMISSION_DENIED` guard as the existing `_handle_get` on the two workspace-scoped handlers. Tool count assertion updated 4 → 8.
- REST: `WorkspaceAttributeDefinitionView` gained `.post` (201) / `.delete` (200, `?name=`) on the existing URL — no `urls.py` change needed (same pattern as Task 1).
- Tests: 8 new service tests, 5 new REST tests, 10 new MCP tests (all in the pre-existing files). Full scoped run: `test_attribute_definition_service.py` + `test_attribute_definition_views.py` + `test_attribute_definition_tools.py` + `attribute_definitions/tests/` + `test_architecture.py` = 302 passed. `test_attribute_definition_enforcement.py` (3 tests, separately named in the plan) also unaffected/green.
- Commit: `fa02f72d` "feat(attributes): add workspace create/delete + MCP parity (Task 2)".

## Tasks 3-12 — NOT STARTED

See plan file for full task list (Phases B-G: frontend create dialog, type
pickers, options editor, section CRUD + grid layout, export/import REST+MCP,
export/import UI, section card polish).
