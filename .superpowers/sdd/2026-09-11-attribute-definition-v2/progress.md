# SDD ledger — plan: docs/superpowers/plans/2026-09-11-attribute-definition-v2.md

Controller: background fork (no Agent tool available — implementer-only, no
self-dispatched independent review; the coordinator dispatches review rounds
separately after each phase/whole-branch).

## ⏸ RESUME POINT

**Last completed task: Task 11 (Export/Import UI), committed `3ae56b93`.**
**Branch:** `feat/attribute-definition-v2`, worktree `.worktrees/attribute-definition-v2-impl`.
**Next: Task 12** (section card boundaries, origin badges, type icons — the LAST task in the plan, Phase G).
**No independent review has run on Tasks 1-10 yet** — this fork has no `Agent` tool; the coordinator needs to dispatch a `code-reviewer` pass before this branch is considered done, per this repo's SDD convention.
**Not manually verified in a live browser** across any task so far — only component/API/typecheck-level coverage. Flag for the coordinator or a later manual pass.
**The full, untargeted whole-backend `pytest -q` background run (task id `bbz34th2h`, launched after Task 4) never produced any output in ~2 hours and was confirmed hung (still `status: running`, 0-byte output file) — killed via TaskStop rather than trusted further.** Per this repo's own background-agent-watchdog convention (memory: `feedback_background_agent_watchdog`), a `status: running` with no progress for this long is not proof of anything; the targeted `attribute_definitions`-consumer sweeps after each task (360+121=481 backend tests, 88 frontend tests, all passing as of Task 10) are the real evidence base, not that stuck run. If the coordinator wants a genuine full-suite pass, re-run it fresh rather than resuming/trusting the old one.
**Deviation from the plan's literal Task 9 interface, worth flagging to a reviewer:** the plan's snippet for `export_definition`/`import_definition` only showed `workspace_id` as the scope discriminator; the real global scope needs a `preset` too (same as every other global-scope method in this service), so both methods take keyword-only `preset=None`/`workspace_id=None` with exactly one expected to be given. REST/MCP surfaces (Task 10) reflect this real signature, not the plan's literal one.

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

## Task 12 — NOT STARTED (final task)

Section card boundaries, origin badges, type icons — `AttributeEditor.module.css`
(radius token reuse) + `AttributeList.tsx`/`AttributeTable.tsx` (origin badge using
Task 4's per-attribute origin marker, type icon per row via `lucide-react`, already
imported in `AttributeList.tsx`). See plan file (Phase G, "Task 12") for full text.
