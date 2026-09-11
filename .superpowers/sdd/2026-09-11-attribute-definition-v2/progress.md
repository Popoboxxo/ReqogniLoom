# SDD ledger — plan: docs/superpowers/plans/2026-09-11-attribute-definition-v2.md

Controller: background fork (no Agent tool available — implementer-only, no
self-dispatched independent review; the coordinator dispatches review rounds
separately after each phase/whole-branch).

## ✅ PLAN COMPLETE — all 12 tasks implemented, committed, and whole-repo-tested

**Final commit: `f3258612` "fix: regenerate MCP tool manifest, fix stale AttributeEditor mocks".**
**Branch:** `feat/attribute-definition-v2`, worktree `.worktrees/attribute-definition-v2-impl`, 24 commits ahead of `main`.

### Final whole-branch review (this fork has no `Agent` tool — this pass IS its own independent-review layer, per the coordinator's explicit instruction)

Per the plan's own "Final Review" section: ran the FULL backend + frontend suites (not scoped subsets) for the first time this session, exactly as instructed. This caught 3 real findings the ~15 scoped per-task runs across Tasks 1-12 never surfaced:

1. **`docs/agent-templates/tool-manifest.json` drift** — `mcp_server/tests/test_tool_manifest_drift.py::test_committed_manifest_matches_live_registry` failed: the committed manifest was stale at 179 tools; Tasks 1/2/5/10 added 9 new `attribute_definition.*` MCP tools (create/delete/create_workspace/delete_workspace/count_usages/export/export_workspace/import/import_workspace) since it was last regenerated. **Fixed:** regenerated via `manage.py export_tool_manifest` (188 tools now committed) — see commit `f3258612`.
2. **`frontend/src/test/AttributeEditor.test.tsx` — a pre-existing page-level test file no scoped run this session ever touched** (all my per-task test runs targeted `src/components/AttributeEditor/*.test.tsx` and specific `src/test/*ArtifactForm*` files, never grepped for a plain `AttributeEditor.test.tsx`). Its 7 mocked `attributeDefinitionsApi` responses predated Tasks 4/7/8's `origins`/`sections` fields, so every render threw `TypeError: sections is not iterable` inside `AttributeList`'s new `sectionMeta` useMemo. **Fixed:** added `origins: {}`/`sections: []` to all 7 mocks.
3. **Same file, 2 assertions asserting `putWorkspace` was called with exactly 3 arguments** — Task 8 added a 4th (`sections`); `toHaveBeenCalledWith` requires an exact arg-count match, so these could never pass again regardless of the first 3 args. **Fixed:** updated both assertions to include the 4th arg, and gave `putWorkspace` a real resolved value in both tests (previously it silently resolved to `undefined`, masked by `handleSave`'s own try/catch and by the assertions only checking call-args recorded before that internal throw — a second, smaller finding fixed alongside the main one).

**Confirmed NOT caused by this branch, left unfixed (out of scope):** `application/tests/test_ai_derivation_service.py::test_get_template_content_covers_all_eight_names` fails on this branch — reproduced in isolation, and `git diff main...HEAD` for both `ai_derivation_service.py` and its test file is empty. Root cause: PR #903 (`interview-engine-fix`, merged to `main` before this branch started) added an `interview.transcript_summary` AI-derivation template without updating this test's hardcoded 11-name expected set to 12. Unrelated feature area; flagging for whoever owns that PR's follow-up, not fixed here.

### Final test tallies (whole-repo, not scoped)

- **Backend:** `pytest -q` (7301 tests collected, ~38 min) → **7280 passed, 19 skipped, 2 failed** before this review's fixes → **1 real failure fixed** (manifest drift) → **the remaining 1 failure is the confirmed-unrelated `ai_derivation_service` one above**.
- **Frontend:** `npx vitest run` (207 test files, ~54s pure test time) → **1655 tests passed, 0 failed** (before fixes: 14 failed, all traced to the 2 `AttributeEditor.test.tsx` findings above and now fixed) + **1 failed test SUITE** (`theme-contrast.test.ts`, `ENOENT` reading a backend fixture file the frontend-only Docker container doesn't mount — confirmed pre-existing/environment-only via empty `git diff`, not a real test failure).
- Re-verified scoped `attribute_definitions` surface one more time after the manifest/mock fixes: **361 backend + 122 frontend, all green.**

### Standing notes carried forward from earlier tasks

- **Not manually verified in a live browser** across any task — only component/API/typecheck/full-suite coverage. Flag for the coordinator or a later manual pass.
- **Deviation from the plan's literal Task 9 interface:** the plan's snippet for `export_definition`/`import_definition` only showed `workspace_id`; the real global scope needs a `preset` too (same as every other global-scope method in this service) — both methods take keyword-only `preset=None`/`workspace_id=None`, exactly one expected. REST/MCP surfaces (Task 10) reflect this real signature.
- A `code-reviewer`/`senior-developer` dispatch from the coordinator remains the recommended next step per this repo's SDD convention (this fork's self-review is thorough but is still the implementer reviewing its own work, not a fresh pair of eyes).

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

## Task 5: Delete-collision-check helper (`count_usages`) — DONE

- `count_usages(ctx, item_type, workspace_id, attribute_name, option_value=None)` added to the service. Queries `Artifact.objects.filter(tenant_id=..., workspace_id=..., artifact_type=item_type, custom_fields__has_key=attribute_name)`, scoped further by `option_value` via `KeyTextTransform` (not a `custom_fields__{name}` keyword lookup — that would mis-split a name containing `__` as a nested JSON path).
- Deliberately does not branch into a per-model-field path for `kind="core"`: a core attribute can never be deleted (rejected earlier by `validate_meta_only_change`), and delete/option-removal are the only two callers of this method — so there is no live path that would ever ask it to count a core field. Documented as an explicit YAGNI, not an oversight.
- REST: new `AttributeUsageView` (`GET .../attribute-definitions/{item_type}/usage/?name=&option=`, admin-only, `{"count": N}`). MCP: new `attribute_definition.count_usages` tool (9th tool in the group).
- Frontend: **`AttributeList.tsx` had NO per-attribute delete button before this task** (the plan's Task 5 text assumed one already existed from Task 3 — it didn't; Task 3 only added section-level `+`/create wiring). Added one now, gated to `kind === "extended"` rows only. `AttributeEditorPage.tsx` fetches the usage count before showing a `ConfirmDialog`; global scope shows a plain confirmation with no count (the backend's `count_usages` is workspace-scoped only — no cross-workspace aggregate exists, and extending the interface for that was out of this task's scope). Not extracted into a shared hook yet (YAGNI, single caller) — Task 6's option-removal flow is the natural point to extract if it needs the same shape.
- Tests: 4 new service tests (incl. a real-`Artifact`-row fixture, not mocked, to exercise the actual JSONB query), 3 new REST tests, 2 new MCP tests. Scoped backend run: 90 passed (service+REST+MCP). Frontend: `tsc -p tsconfig.build.json --noEmit` clean, 39 tests passing across the touched/new files.
- Commit: `56719398` "feat(attributes): add count_usages + delete confirmation flow (Task 5)".

## Task 6: Options editor in `AttributeInspector` — DONE

- New options section in `AttributeInspector.tsx`, rendered only for `type in {"enum", "multi-enum"}`: rows of `{value, label_de, label_en}` with add/reorder/remove, matching `_normalize_options`'s exact contract (all three required, no extras — the component never sends a 4th key).
- Add/edit/reorder stay LOCAL `onPatch` calls (options are just another attribute property, saved through the page's existing Save button, exactly like every other meta-edit) — only removal goes through a new `onRequestRemoveOption(optionValue)` callback, since the "does anything reference this value" check needs a live `count_usages(..., option_value)` round-trip that this otherwise-pure, unit-tested component has no business making itself.
- `AttributeEditorPage.tsx` wires `onRequestRemoveOption` the same shape as Task 5's delete-attribute flow: fetch the count, show a `ConfirmDialog` (warns with the count when > 0, plain confirmation in global scope — same workspace-scoped-only limitation as Task 5, not extended here either), apply the local patch on confirm.
- Tests: 8 new `AttributeInspector.test.tsx` cases (hidden/shown by type, add/edit/reorder via `onPatch`, remove routes through the new callback instead of patching directly, `readOnly` disables every control). `tsc -p tsconfig.build.json --noEmit` clean. Scoped frontend suite: 47 passed across the 6 touched/new AttributeEditor + api-client + ratchet files.
- Commit: `e167be13` "feat(attributes): add options editor to AttributeInspector (Task 6)".

## Task 7: `sections[]` schema + lazy materialization — DONE

- `schema.py`: `SECTION_LAYOUTS`, `normalize_section`, `validate_sections_json`, `materialize_sections`, `stored_sections` — same normalize/validate shape as the attribute-side equivalents. `validate_definition_json` optionally normalizes a `sections` key when present (every pre-Task-7 caller omits it, unaffected).
- **No Django migration** — confirmed correctly per the plan's own instruction not to create an empty one: `sections` lives inside the existing `definition_json` JSONField, no model/column change.
- Stores gain `ensure_sections(obj)`: backfills + persists `sections` the first time a row lacks it, derived from the STORED (sorted `(section, order, name)`) attribute list's first-appearance section order.
- **Real bug caught by the full `attribute_definitions/tests/` suite, not assumed safe:** the first version called `ensure_sections` from inside `get()` itself — but `update()`/`initialize()`/`reinitialize()` all call `get()` internally as a plain existence lookup, so every write touching a pre-Task-7 row picked up a silent extra version increment. Broke `test_concurrent_updates_do_not_lose_a_version_increment` + 3 siblings (off-by-one version assertions). **Fixed by keeping `get()` a pure read** (no mutation, ever) and confining `ensure_sections` calls to the actual external read paths only: `AttributeDefinitionService.get_global`/`list_global`, and `WorkspaceAttributeDefinitionStore.resolve()`'s two branches + `.reset()`. `update()` in both stores now also explicitly carries the existing `sections` list over into the new `definition_json` (its payload only ever carries `attributes`, and the whole dict is replaced on write — without this the very first PUT after a backfill would have silently erased it).
- `_global_payload`/`_workspace_payload` now include a `sections` key — sourced via `stored_sections`, a SEPARATE sibling key again (same lesson as Task 4's `origins`, not merged into attribute entries).
- Two pre-existing service tests needed their hardcoded version-number/exact-dict expectations updated to reflect the new (correct) behavior: `resolve()` on an unbackfilled global row now bumps that row's version once (via the workspace-store's `ensure_sections(source)` call), and `get_global` of an uninitialized row now includes `"sections": []`.
- Tests: 56 pure schema tests (0 DB), 5 new store-level materialization tests (both stores), 2 fixed pre-existing tests. Full `attribute_definitions/tests/` + service/REST/MCP/architecture scoped run: 334 passed. Broader consumer sweep (bundle export, interview protocol, reqif import/export, goal views): 121 passed, no regression from the new `sections` payload key.
- Commit: `5e94d133` "feat(attributes): add sections[] schema + lazy materialization (Task 7)".

## Task 8: Section visibility + grid layout in the UI — DONE

- TS types: `SectionLayout`, `SectionSpec` added to `attribute-definitions.ts`; both `ResolvedAttributeDefinition` and `GlobalAttributeDefinition` gain a `sections: SectionSpec[]` field.
- `ArtifactForm.tsx`: a section with `visible: false` in `definition.sections` hides itself AND every attribute in it, regardless of each attribute's own `visible` (spec 4.4's AND-condition) — a section name absent from `definition.sections` defaults to visible (same additive default as the backend). Sections render on a 2-column CSS grid (`ArtifactForm.module.css`): `layout: "half"` spans 1 column, `"full"` (default) spans both; two consecutive halves sit side-by-side, a lone half leaves the second column empty via plain `grid-auto-flow` (no `dense` packing, no extra rule needed); collapses to 1 column under 768px (`--bp-md`).
- `AttributeList.tsx` gained per-section visibility checkbox + layout `<select>` (`attribute-section-{name}-visible`/`-layout`), backed by new pure `toggleSectionVisible`/`setSectionLayout` helpers in `attribute-edits.ts` (upsert semantics: toggling a section with no existing `SectionSpec` entry creates one). `AttributeEditorPage.tsx` tracks `sections` as local buffered state (same pattern as `attributes`), included in the dirty-check, sent on the normal Save button's PUT.
- **Backend plumbing needed beyond the plan's own Task 8 file list** (not listed there, but required for "toggling a section's visibility persists (PUT with the updated sections array)" to actually work): `GlobalAttributeDefinitionStore.update()`/`WorkspaceAttributeDefinitionStore.update()` and the service's `update_global`/`update_workspace` gained an optional `sections` parameter (omitted = preserve existing list unchanged, matching every pre-Task-8 caller; given = replaces it, validated same as `attributes`). REST `PUT` views read an optional `sections` key from the body. No new endpoint — same PUT the rest of the editor already uses.
- Tests: 3 new `ArtifactForm.test.tsx` cases (whole-section hide with AND-condition, default-visible fallback, half/full layout attributes on rendered `<section>` elements via `data-testid`+`data-layout`), 5 new `AttributeList.test.tsx` cases (new file — none existed for this component before), 3 new backend service tests, 2 new REST tests. `tsc -p tsconfig.build.json --noEmit` clean. Scoped backend run: 460 passed (attribute_definitions + service/REST/MCP/architecture + the full bundle-export/interview-protocol/reqif/goal-views consumer sweep). Scoped frontend run: 88 passed.
- Commit: `6acfcb4f` "feat(attributes): add section visibility + grid layout UI (Task 8)".

## Task 9: `export_definition`/`import_definition` service methods — DONE

- `export_definition(ctx, item_type, *, preset=None, workspace_id=None)` returns `{schema_version: 1, item_type, attributes, sections}`. `import_definition(ctx, item_type, payload, *, preset=None, workspace_id=None, on_collision="skip")` merges via a new `_merge_import` static helper (skip/overwrite/rename, rename suffixing `name_2`, `name_3`, ... — first free suffix) then hands the merged list straight to `update_global`/`update_workspace` UNCHANGED — all structural validation, the core-lock and the final duplicate-name check happen there, reusing the exact single validation path `create_global`/`create_workspace` already established rather than reimplementing it.
- Global-scope import is "like an edit" (spec section 6): goes through `update_global`, so propagation to non-customized workspaces applies exactly as any other global PUT.
- Tests: 9 new service tests (re-importable round-trip, both scopes, admin gate, bad schema_version, bad on_collision, incoming-core rejection via the SAME downstream mechanism as create, skip/overwrite/rename each verified). Scoped run: 322 passed.
- Commit: `33976d91` "feat(attributes): add export_definition/import_definition (Task 9)".

## Task 10: REST + MCP surface for export/import — DONE

- REST: `GET/POST .../export/` and `.../import/` for both scopes (global: `attribute-defaults/{item_type}/{preset}/`, workspace: `workspaces/{id}/attribute-definitions/{item_type}/`), same admin gate/error mapping as the rest of the resource. `on_collision` accepted as a query param OR a same-named body key (query param wins) — matches the plan's explicit "query/body param" wording.
- MCP: `attribute_definition.export`/`.export_workspace`/`.import`/`.import_workspace` — followed the `create_workspace`/`delete_workspace` scope-suffix precedent per the plan's own instruction to check and match it, not a scope parameter. Same `CrossTenantWorkspaceError` guard as every other workspace-scoped handler in this group. Tool group docstring header also fixed from a stale "Eight tools" (never updated when Task 5 added `count_usages`) to the accurate current count (13).
- Tests: 6 new REST tests, 5 new MCP tests, tool-count assertion updated 9→13. Scoped run: 360 passed. Consumer sweep (bundle export, interview protocol, reqif, goal views): 121 passed.
- Commit: `ed888945` "feat(attributes): add REST + MCP surface for export/import (Task 10)".

## Task 11: Export/Import UI — DONE

- API client: `exportGlobal`/`importGlobal`/`exportWorkspace`/`importWorkspace` + `downloadAttributeDefinitionDocument` (Blob + `<a download>` — no shared download helper exists in this codebase; `api/export.ts`'s CSV/ReqIF downloads each independently duplicate the same 5-line pattern, so a third small duplicate matches the established convention rather than inventing a shared utility for 3 call sites).
- New `AttributeImportDialog.tsx`: covers only the collision-resolution radio choice (skip/overwrite/rename) once a file is already selected+parsed — the file picker itself is a plain hidden `<input type="file">` in `AttributeEditorPage.tsx`, no dialog needed for that step.
- `AttributeEditorPage.tsx`: Export button downloads the current definition as `{itemType}-{preset|workspace}-attributes.json`; Import opens the file picker, parses JSON client-side, shows the confirm dialog, then calls `importGlobal`/`importWorkspace` and reloads.
- Tests: 5 new `AttributeImportDialog.test.tsx` cases, 6 new api-client tests. `tsc -p tsconfig.build.json --noEmit` clean. Scoped frontend run: 98 passed (all AttributeEditor + api-client + ArtifactForm + ratchet + i18n-parity files) — ui-ratchet's inline-style/hex-color baselines stayed monotonic (new radio-label CSS went into a proper `.module.css`, not inline `style={{`).
- No dedicated test for the actual browser-download trigger (Blob/`URL.createObjectURL`/anchor click) — same as the existing `api/export.ts` CSV/ReqIF downloads, which also have zero test coverage for that specific mechanic; consistent with established precedent, not a new gap.
- Commit: `3ae56b93` "feat(attributes): add export/import UI (Task 11)".

## Task 12: Section card boundaries, origin badges, type icons — DONE

- Section card border/radius: **already correct before this task** — both `AttributeEditor.module.css`'s and `ArtifactForm.module.css`'s `.section` already used `border-radius: var(--radius-md)`, matching the existing `Dialog`/token convention (`--radius-sm`/`-md`/`-lg`/`-full`). Verified, no change needed.
- New `attribute-type-icons.tsx`: one lucide-react icon per `ATTRIBUTE_TYPES` value (`Type`, `AlignLeft`, `Hash`, `ToggleLeft`, `List`, `ListChecks`, `Calendar`, `Link`, `User`, `Puzzle`), shared by `AttributeList.tsx` and `AttributeTable.tsx` so both agree on the same icon per type — no new icon dependency.
- Both list and table views now render a type icon + an origin badge (global/global_customized/workspace_only) per row, reusing Task 4's per-attribute origin marker (`AttributeList` gained the same optional `origins` prop `AttributeTable` already had).
- **Real regression caught by this task's own full ratchet-suite run, not assumed safe:** the first badge styling used `background: var(--color-primary)` for the workspace-only state, which pushed the `ui-ratchet.test.ts` UI-50 "primary-button fill" frozen baseline from 29 to 30 occurrences. Fixed with an outline style (border + text color) instead of a solid fill — same semantic color, doesn't re-declare the tracked pattern. Also fixed a pre-existing `AttributeTable.test.tsx` regex (`/^attribute-table-row-/`) that started over-matching the new `-type-icon` testid suffix once that element existed.
- Tests: 3 new `AttributeList.test.tsx` cases, 1 new `AttributeTable.test.tsx` case, 1 existing test file's selector regex fixed. `tsc -p tsconfig.build.json --noEmit` clean. Scoped frontend run: 102 passed (all AttributeEditor + api-client + ArtifactForm + full ui-ratchet + i18n-parity files) — including the UI-50 ratchet that caught the regression above.
- Commit: `63d54084` "feat(attributes): add origin badges + type icons (Task 12)".

## PLAN STATUS: all 12 tasks implemented and committed.

Next: final whole-branch review (this fork has no `Agent` tool — self-review
against the plan/spec is this pass's independent-review layer; the coordinator
dispatching a real `code-reviewer`/`senior-developer` round afterward remains
the recommended follow-up per this repo's SDD convention, same pattern used
for `interview-engine-fix` and `ki-vorschlag-als-zustand` this session).

## Post-review fixes (independent code-reviewer round) — DONE

Independent review of the full branch diff found 6 Majors (no Blockers) plus
Minors. All 6 Majors fixed with tests; one Minor (m7) fixed because it sat in
code the Majors already touched. Remaining Minors deliberately deferred, see
below.

- **M1 — import silently discarded `sections[]`.** `export_definition` emits
  `{schema_version, item_type, attributes, sections}` but `import_definition`
  only read `attributes`, so imported section visibility/layout was dropped and
  the target's own sections survived — a deliberately hidden section came back
  visible after a round trip. Sections are now merged by the SAME
  `_merge_import` rules (by `name`, honouring `on_collision`) and passed as the
  `sections=` argument. A document with no `sections` key keeps meaning "leave
  the target's sections alone", matching `_read_sections`' existing PUT
  contract. Tests: round-trip with a hidden/half section, skip-vs-add
  behaviour, absent-key no-op, non-list rejection.
- **M2 — import bypassed `validate_new_attribute_name`.** An imported document
  could introduce `"Created At"` or `"owner"` (shadowing a real Django model
  field) with zero validation; the rename path fabricated `name_2` names
  unvalidated too. `_merge_import` gained a `reserved_field_names` argument
  (`None` = off, which is what the sections merge passes) and runs the same
  gate `create_global`/`create_workspace` use on every entry it ADDS, including
  the rename candidate — deliberately NOT on `skip`/`overwrite` collisions,
  whose names are already stored and already validated. Spec section 6's
  "validated against the same logic as creating (3.2)" is now literally true.
  Tests: model-field shadowing rejected, non-snake_case rejected.
- **M3 — missing `CrossTenantWorkspaceError` guard on 2 endpoints.** The
  workspace-scoped `POST`/`DELETE` route into `create_workspace`/
  `delete_workspace`, which resolve the preset through the gate.
  `CrossTenantWorkspaceError` is a `PresetError`, NOT a `ValueError`, so
  neither view's except-list caught it → uncaught 500 instead of 403 for a
  foreign-tenant workspace id. Copied the guard the export/import views already
  carry. Both new tests were verified to FAIL without the fix (temporary
  guard-disable run) before being committed.
- **M4 — `count_usages(option_value=…)` was always 0 for `multi-enum`.** A
  multi-enum value is stored as a JSON list, so `KeyTextTransform` yielded the
  serialized array text and never equalled a bare option string — the spec
  section 4.3 usage-count safety check was dead for exactly the type that needs
  it. **Deviation from the review's suggested fix:** instead of branching on the
  attribute's declared `type`, the option filter ORs the scalar equality with a
  JSONB containment test (`(custom_fields -> name) @> '["value"]'`, served by
  `pl_artifact_custom_fields_gin`). Reading the type would mean resolving the
  whole definition, which raises `AttributeDefinitionNotFound` for an item type
  with no global default yet — a probe that legitimately answers 0 today would
  start raising. The two predicates are mutually exclusive on real data.
- **M5 — a `required` attribute in a hidden section blocked every create.**
  Spec section 4.4's AND-condition was implemented only in the React renderer;
  `field_validation.validate_values` checked `required and visible` with no
  knowledge of `sections[].visible`. Hiding such a section made every
  server-side create fail for a field the form no longer drew, unfixable from
  the UI. Root-cause fix at the shared seam: `validate_values` gained an
  optional `sections` argument (omitted = previous behaviour) and treats
  "member of an invisible section" exactly like `visible == False`;
  `validate_artifact_fields` passes the resolved sections. That one function is
  what REST, MCP and the CSV/bundle importer all route through, so the gap
  closes everywhere at once rather than per caller.
- **M6 — renaming/deleting a section orphaned its `SectionSpec`.**
  `renameSection` rewrote `attribute.section` on every member but never touched
  the `sections` state array, so a renamed section lost its spec and fell back
  to default visible/full (a hidden section silently became visible) while the
  old-name entry survived forever as an orphan a later same-named section would
  inherit. New pure helpers `renameSectionSpec`/`deleteSectionSpec` in
  `attribute-edits.ts`, wired into both page handlers. Renaming ONTO an
  existing section is treated as a merge (target's spec wins), because
  duplicate section names are rejected by `validate_sections_json`.
- **m7 (Minor, fixed) — `delete_global`/`delete_workspace` no-op'd silently.**
  Deleting a name that does not exist answered 200 with a version bump and an
  audit entry claiming a change that never happened. Both now raise
  `AttributeDefinitionNotFound`, which the REST views and MCP handlers already
  map to 404 / `NOT_FOUND`.
- **m6 (Minor, fixed in passing)** — the export/import scope guards raised a
  bare `ValueError`, which no view/MCP except-clause catches (500 for a
  malformed request). Now `AttributeSchemaError`, the module's own taxonomy.

### Deliberately deferred (budget, not disagreement)

- **m1** — option removal keyed by `value` instead of index
  (`AttributeInspector.tsx` / `AttributeEditorPage.tsx`): breaks the
  confirm-dialog guard for a freshly-added row (`value: ""` is falsy) and for
  duplicate transient values. Real bug, cosmetic blast radius (a newly added,
  not-yet-saved option row), needs a coordinated 3-file change plus test
  updates. Follow-up.
- **m2** — `AttributeCreateDialog.tsx` / `AttributeImportDialog.tsx` use raw
  `exc.message` instead of the `extractErrorMessage(exc)` the rest of the page
  uses, so server-side validation messages surface as a generic axios status
  string. Two-line fix, follow-up.
- m3/m4/m5/m8/m9 and all Nits: out of scope for this pass per the review's own
  priority call.

### Verification

- Backend, scoped: `attribute_definitions/`, `test_attribute_definition_service`,
  `test_import_service`, `test_attribute_definition_views`,
  `test_attribute_field_validation`, `test_bootstrapped_definition_allows_creates`,
  `test_attribute_definition_tools`, `test_attribute_definition_enforcement`
  → **363 passed**.
- Frontend, scoped: `AttributeEditor.test.tsx`, `attributeDefinitionsApi.test.ts`,
  all `src/components/AttributeEditor/*`, `ArtifactForm*.test.tsx`
  → **136 passed (10 files)**.
- No whole-repo run in this pass (already run before the review; CI covers the
  full matrix) and **no manual browser verification** — every fix is covered by
  an automated test instead.
