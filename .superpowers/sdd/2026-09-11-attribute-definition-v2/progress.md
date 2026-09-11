# SDD ledger — plan: docs/superpowers/plans/2026-09-11-attribute-definition-v2.md

Controller: background fork (no Agent tool available — implementer-only, no
self-dispatched independent review; the coordinator dispatches review rounds
separately after each phase/whole-branch).

## ⏸ RESUME POINT

**Last completed task: Task 4 (`AttributeTable` + view-mode toggle), committed `da2ac13d`.**
**Branch:** `feat/attribute-definition-v2`, worktree `.worktrees/attribute-definition-v2-impl`.
**Next: Task 5** (delete-collision-check helper `count_usages`, Phase D).
**No independent review has run on Tasks 1-4 yet** — this fork has no `Agent` tool; the coordinator needs to dispatch a `code-reviewer` pass before this branch is considered done, per this repo's SDD convention.
**Not manually verified in a live browser** (Task 3's plan Step 5 asked for this) — only component/API/typecheck-level coverage. Flag for the coordinator or a later manual pass.
**A full, untargeted backend `pytest -q` run was kicked off in the background right before this ledger update to catch anything the scoped regression sweeps might have missed across the whole app — check its result before trusting Task 4 is fully clean if resuming shortly after this point.**

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

## Task 3: `AttributeCreateDialog` component + wiring — DONE

- New `AttributeCreateDialog.tsx`/`.module.css`, built on the shared `<Dialog>` primitive (`components/shared/Dialog`): Name, Typ (10 `ATTRIBUTE_TYPES`), Pflichtfeld, Sektion (pre-filled/editable), and a minimal comma-separated options field for `enum`/`multi-enum` (each token becomes `{value, label_de, label_en}` — deliberately minimal, the real options editor is Task 6).
- Client-side pre-checks mirror the backend exactly: snake_case regex (`^[a-z][a-z0-9_]*$`, same as `validate_new_attribute_name`) and a name-collision check against `existingNames`. Server re-validates regardless — pre-check is UX only.
- API client: `createGlobalAttribute`/`createWorkspaceAttribute`/`deleteGlobalAttribute`/`deleteWorkspaceAttribute` added to `attribute-definitions.ts`, calling Task 1/2's endpoints (`kind: "extended"` is always injected client-side, never exposed as a choice).
- `AttributeList.tsx` gained a per-section `+ Attribut hinzufügen` button (new `onAddAttribute` prop — its only caller, `AttributeEditorPage.tsx`, updated). Creation is always an immediate API call + refetch (`load()`), NOT a locally-buffered edit like the rest of the page's meta-property changes (`moveAttribute`/`patchAttribute`/etc.) — a workspace-only attribute has no `source_global` counterpart to stage against.
- Also fixed: `ChangeRequest` was missing from the entity-type `<select>` list and its i18n label (same V5 drift Task 1 already fixed in the TS type union) — added to both.
- Tests: 10 new `AttributeCreateDialog.test.tsx` cases (all 10 types render, colliding-name / invalid-name / empty-options inline errors, well-formed `onCreate` call, workspace-only hint shown/hidden by scope, cancel, rejection keeps dialog open) + 6 new `attributeDefinitionsApi.test.ts` cases for the 4 new client functions. `tsc -p tsconfig.build.json --noEmit` clean. Full frontend suite: 1618/1618 passing (4 apparent failures on the first full parallel run were `testTimeout` resource-contention flakes under Docker, not real — each file re-run individually and scoped alongside the new tests passed clean).
- Commit: `d40d1e99` "feat(attributes): add AttributeCreateDialog + wiring (Task 3)".
- **Gap, flag for review/manual pass:** Step 5 of the plan ("run the frontend dev stack, actually create an attribute through the UI") was not done — no live-browser verification, only component/API/typecheck coverage.

## Task 4: `AttributeTable.tsx` + view-mode toggle — DONE

- **Backend prerequisite the plan flagged as needing verification, and it was in fact missing:** added a per-attribute `origins` map (`{name: "global"|"global_customized"|"workspace_only"}`) to `_workspace_payload` in `attribute_definition_service.py`. Computed by diffing the resolved attribute names against `row.source_global`'s stored attribute names.
- **Real bug caught by broad regression, not assumed safe:** the first implementation merged an `origin` key directly INTO each attribute dict (mutating the same list `resolve()["attributes"]` returns). This broke `requirement_bundle_service`'s schema export, which re-validates that exact list through `validate_definition_json` — its key allow-list rejected the unknown `origin` key (`AttributeSchemaError: ... unknown key(s): origin`), 6 test failures across `test_bundle_export_fields_from_definition.py`, `test_requirement_bundle_tool_group.py`, `test_goal_views.py`, `test_requirement_bundle_export.py`. Fixed by moving `origins` to a SEPARATE sibling key on the payload instead of mutating the shared attribute list — re-ran the full regression sweep (429 passed) after the fix. **Lesson for future tasks touching `_workspace_payload`/`resolve()`: that return value is shared verbatim by several unrelated consumers (bundle export, interview protocol, field validation) — a scoped test run is not enough, run the broader consumer list too (see the file list in this entry) before trusting a change to it.**
- `is_customized` being per-DEFINITION not per-attribute (Task 2's finding) means every inherited attribute reads `global_customized` once ANY workspace edit has landed, not just the touched one — documented as expected, not a bug, with a dedicated regression test.
- New `AttributeTable.tsx`: Name/Typ/Sektion/Pflicht/Sichtbar/Audience/Herkunft columns, `<table>` (tokens.css only, no inline styles — verified against the `ui-ratchet` tests), client-side sort with direction toggle on repeat header click, no persisted order (only the list view's section order persists).
- `AttributeEditorPage.tsx`: List/Tabelle toggle persisted to `localStorage` (`attributeEditor.viewMode`, wrapped in try/catch — a private-browsing/storage-disabled failure silently defaults to "list", never breaks the page). Both views read the same `attributes`/`origins` state, no second fetch.
- Tests: 3 new backend origin tests + 6 new `AttributeTable.test.tsx` cases. Scoped backend suite (429), frontend suite (39 across the 5 touched/new files), `tsc -p tsconfig.build.json --noEmit` all green.
- Commit: `da2ac13d` "feat(attributes): add AttributeTable + view-mode toggle (Task 4)".
- **A full untargeted `pytest -q` (whole backend suite, no path filter) was launched in the background as an extra confidence pass right after this commit** — its result should be checked before assuming Task 4 introduced zero side effects elsewhere in the app that the targeted consumer sweep didn't think to check.

## Tasks 5-12 — NOT STARTED

See plan file for full task list (Phases D-G: options editor,
section CRUD + grid layout, export/import REST+MCP, export/import UI,
section card polish).
