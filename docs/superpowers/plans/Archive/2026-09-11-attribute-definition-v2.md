# Attribute-Definition v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the six confirmed v1 gaps: no create path at either scope (only edit-existing works), list-only UI with no columns, no UI for the already-whitelisted `options[]` meta-property, no section-level visibility, no section grid layout, no export/import of a *definition* (as opposed to the already-existing `export_attributes()`, which is something else entirely — see Spec-Verification Findings V3). The catalog concept (spec §5) is explicitly OUT OF SCOPE for this plan — it is marked in the spec itself as a non-blocking future extension; no task below implements it, and no task should be extended to cover it without a new spec amendment.

**Architecture:** No new Django app, no new top-level model. `GlobalAttributeDefinition`/`WorkspaceAttributeDefinition` (`backend/attribute_definitions/models.py`) keep their materialized-copy shape; `definition_json` gains a sibling key `sections` (parallel to the existing `attributes` list) for section-level visibility/layout metadata. Create/delete are built as thin wrappers around the *existing* `update_global`/`update_workspace` service methods — read the current attribute list, splice in or remove one entry, delegate to the update path that already owns validation, propagation and audit logging. This is deliberately not a new write path: `validate_meta_only_change` (`schema.py:418-486`) already rejects a smuggled-in `kind="core"` entry or an illegally-set `locked` flag on any list it's handed, so create/delete get that protection for free rather than re-implementing it.

**Tech Stack:** Python 3.x / Django 5.2 (1 schema-adjacent migration for `sections`, no data migration needed — additive), DRF (4 new endpoints across 2 existing view modules + 2 new ones), MCP (4 new tool handlers in the existing `AttributeDefinitionToolGroup`), React 18 + TS strict (1 new component, 3 modified, 2 new CSS module blocks), i18n de/en. No new runtime dependency (export/import reuses `json`, drag-reorder reuses the existing native HTML5 drag code, no D&D library).

**Spec:** docs/superpowers/specs/2026-09-11-attribute-definition-v2-design.md

## Global Constraints

- **`kind="core"` is immutable — name, type, and existence are fixed by the Django model.** Every create/delete task MUST reuse `validate_meta_only_change` (via the existing `update_global`/`update_workspace` service methods) rather than hand-rolling a second check. A create call that tries to introduce `kind="core"` must fail with the existing message `"{name}: a core attribute may not be added through the API"` (`schema.py:481`) — do not write a new error message for the same case.
- **`locked` may only ever be set by the bootstrap script** (`schema.py:452,483`) — create must always normalize new entries with `locked=False` and reject a caller-supplied `locked=True`, same message as the existing check.
- **Two distinct "export" concepts must not collide.** `AttributeDefinitionService.export_attributes()` (`backend/application/attribute_definition_service.py:227-235`) already exists and returns the *subset of attributes flagged `export=true`*, consumed by ReqIF/CSV/Bundle export (spec v1 §7) — it has nothing to do with this plan. This plan's export/import (spec §6) serializes the *whole definition* (all attributes + the new `sections` array) as a downloadable/importable JSON document. Name the new service methods `export_definition`/`import_definition` — never `export_attributes`/anything that shadows or is confusable with the existing method.
- **`ATTRIBUTE_TYPES` already has 10 values** (`backend/attribute_definitions/schema.py:38-43`: `text, textarea, number, boolean, enum, multi-enum, date, reference, user, widget`) — no new attribute type is in scope. The create dialog's type dropdown enumerates these 10, nothing more.
- **`CORE_EDITABLE_META_PROPERTIES` already whitelists `options`** (`schema.py:59-64`) — the backend write path for editing a core attribute's `options` already works today; this plan is UI-only for that piece (Task 4), not a backend change.
- **`ITEM_TYPES` is 11 values, not 10** (`backend/attribute_definitions/schema.py:22-34`: adds `ChangeRequest` to the 10 the frontend's `AttributeItemType` union currently lists — `frontend/src/api/attribute-definitions.ts:16-26` is missing it). This is a genuine, small, pre-existing drift this plan's Task 1 fixes in passing since it touches the same file; it is not itself spec-driven.
- **No ORM in `rest_api/`/`mcp_server/tools/`** — enforced by `rest_api/tests/test_architecture.py::test_no_new_direct_orm_access` (REST) and `::test_no_new_direct_orm_access_mcp_tools` (MCP), both counting `.objects.` occurrences including inside docstrings. Every new endpoint/tool handler calls `AttributeDefinitionService`, never the ORM directly.
- **Every DRF view calls `get_auth_context(request)`** before any service call — sets tenant context; a query without it returns an empty RLS-filtered set silently, not an error. Every new view in this plan follows the exact `_require_admin(request)` pattern already used in `attribute_definition_views.py:33-42`.
- **`CrossTenantWorkspaceError` must be mapped to 403/PERMISSION_DENIED, never left to fall through to a generic 500** — both `WorkspaceAttributeDefinitionView.get` (REST, `attribute_definition_views.py:137-143`) and `_handle_get` (MCP, `attribute_definition.py:168-179`) already carry this guard with the same rationale comment; every new workspace-scoped endpoint/tool this plan adds must carry the identical guard.
- **No inline styles in `frontend/src/components/`** — a UI ratchet test fails on new `style={{`. Use CSS modules + custom properties from `frontend/src/styles/tokens.css`, matching the existing `AttributeEditor.module.css`.
- **`data-testid` on every interactive element** — follow the existing naming convention in `AttributeList.tsx` exactly (`attribute-row-{name}-{action}`, `attribute-section-{name}-{action}`) for any new button/control so existing test-selector patterns extend naturally rather than fragmenting into a second convention.
- **Named exports only** (React components PascalCase files, Python snake_case) — preserve existing naming, do not rename any existing file touched by this plan.
- **`AttributeEditor.module.css`/`AttributeList.tsx`/`AttributeInspector.tsx`/`AttributeEditorPage.tsx`/`attribute-edits.ts` are the five existing frontend files this plan's tasks touch or sit beside** — read the actual current content of each before editing (this plan cites line numbers verified against `main` on 2026-09-11; other work may have landed on `main` since — re-check before trusting a cited line number blindly, same caveat the interview-engine-fix plan documents for its own migration-number citation).
- **Migration numbers below are the next free ones as of 2026-09-11**: `backend/persistence/migrations/` ends at `0082_merge_traceability_and_attribute_branches.py`, `backend/attribute_definitions/migrations/` ends at `0006_relax_adr_description_required.py`. Before `makemigrations`, run `ls backend/*/migrations/ | tail -3` per app and use the actual next-free prefix — two other plans (`ki-vorschlag-als-zustand`, `interview-engine-fix`) are executing in parallel worktrees right now and may land migrations first; a collision here is a number conflict, not a content conflict, and is resolved the same way `persistence/0082` was resolved this session (`makemigrations --merge`).
- **Local test runs are scoped** — run only the modules this plan's tasks touch plus their direct dependents. The full backend suite (7,100+ tests, ~35 min) and full Playwright run are not this plan's job to run repeatedly; run them once at the final whole-branch review.

### Commands used throughout

Backend test (a unique `DB_NAME` avoids collision with a concurrently running suite — both parallel worktrees use their own unique names):

```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=test_adv2 backend-test pytest <path> -v
```

Frontend test:

```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm frontend-test sh -c "npx vitest run <path> --testTimeout=30000"
```

Migrations (DB owner role required for DDL):

```bash
docker compose -f deploy/docker-compose.yml --project-directory . exec backend python manage.py makemigrations attribute_definitions --name attribute_sections
docker compose -f deploy/docker-compose.yml --project-directory . exec backend python manage.py migrate
```

Frontend container restart (mandatory after every frontend edit before a browser/E2E check — Vite has no working HMR on Windows in this dev setup):

```bash
docker compose -f deploy/docker-compose.yml --project-directory . restart frontend
```

---

## Spec-Verification Findings (read before Task 1)

Verified against the live tree on `main` (post-PR #901 merge, 2026-09-11).

| # | Spec claim | Reality | Resolution |
|---|---|---|---|
| V1 | §3.1: no `create`/`delete` MCP or REST operations exist | **CONFIRMED.** `attribute_definition.py` has exactly `list`/`get`/`update`/`reset` (`_TOOL_MAP`, line 70-75). `attribute_definition_views.py` has exactly `GET`/`PUT` on both defaults views + `POST .../reset/`. | Tasks 1-3. |
| V2 | §4.3: `options` is whitelisted in the backend but has no UI | **CONFIRMED, exact citation found.** `CORE_EDITABLE_META_PROPERTIES` (`schema.py:59-64`) includes `"options"`. `AttributeInspector.tsx` (150 lines total) has no `options` field in its rendered form. | Task 6. |
| V3 | §6 implies export/import of the *definition* is new | **NEEDS DISAMBIGUATION, not a spec error but a naming trap.** `AttributeDefinitionService.export_attributes()` already exists (`attribute_definition_service.py:227-235`) but returns the `export=true`-flagged attribute subset for ReqIF/CSV/Bundle — a completely different feature from spec §6's "download/upload the whole definition as JSON". See Global Constraints. | Tasks 9-11 name their new methods `export_definition`/`import_definition`, never touching or renaming the existing `export_attributes`. |
| V4 | §4.4/4.5: sections have no structure beyond being a string on each attribute | **CONFIRMED.** No `sections` key anywhere in `schema.py`'s `ALLOWED_KEYS`/`_DEFAULTS`; `AttributeList.tsx` derives section list purely from `sectionNames(attributes)` (`attribute-edits.ts`) — a pure aggregation of the free-text `section` field on each attribute row, not a first-class object. | Tasks 7-8 introduce `definition_json["sections"]` as a new, additive, lazily-materialized array. |
| V5 | (not claimed by spec) | **BUG-ADJACENT DRIFT FOUND.** `frontend/src/api/attribute-definitions.ts`'s `AttributeItemType` union (lines 16-26) lists 10 item types; the backend's `ITEM_TYPES` (`schema.py:22-34`) has 11 — `ChangeRequest` is missing frontend-side. Harmless today (nothing constructs a `ChangeRequest`-scoped attribute UI yet) but Task 1 touches this exact file for the create-dialog type dropdown, so fixing the drift there costs one line. | Task 1 adds `"ChangeRequest"` to the union. |
| V6 | (not claimed by spec) | **MCP/REST asymmetry, pre-existing, not a bug.** MCP's `AttributeDefinitionToolGroup` has no global-write tool (`update_global` is REST-only today, per `attribute_definition_views.py`'s `AttributeDefaultsDetailView.put`). This plan's new global-scope create/delete (Task 1) is offered on BOTH REST and MCP for consistency going forward — a deliberate parity improvement, not something the spec mandated. Flagging here so nobody "reverts" it as scope creep during review; it is a 2-line addition per surface reusing 100% existing validation. | Task 1, Task 2 (MCP). |

**OFFENE FRAGE:** none — every ambiguity above resolved inline above or inside its task.

---

## File Structure

```
backend/
  application/
    attribute_definition_service.py       MODIFY  +create_global/+delete_global,
                                                    +create_workspace/+delete_workspace,
                                                    +export_definition/+import_definition
    tests/
      test_attribute_definition_service.py MODIFY  (or CREATE if it doesn't yet exist — check)
  attribute_definitions/
    schema.py                              MODIFY  +sections vocabulary/validation, +name-collision check
    global_definition_store.py             MODIFY  materialize sections[] lazily on first read (Task 7)
    workspace_definition_store.py          MODIFY  same, workspace side
    migrations/
      0007_attribute_sections.py           CREATE  additive, no data migration (lazy materialization)
    tests/
      test_schema.py                       MODIFY  new validation cases
  rest_api/
    attribute_definition_views.py          MODIFY  +create/delete endpoints (both scopes),
                                                    +export/import endpoints (both scopes)
    urls.py                                MODIFY  new routes
    tests/
      test_attribute_definition_views.py   MODIFY
  mcp_server/
    tools/attribute_definition.py          MODIFY  +create/delete tools (both scopes)
    tests/
      test_attribute_definition_tools.py   MODIFY
      test_attribute_definition_enforcement.py MODIFY (core/locked negative cases for create/delete)

frontend/
  src/
    api/attribute-definitions.ts           MODIFY  +ChangeRequest, +create/delete/export/import client calls
    components/AttributeEditor/
      AttributeEditorPage.tsx              MODIFY  +create dialog trigger, +view-mode toggle, +import trigger
      AttributeCreateDialog.tsx            CREATE  Task 3
      AttributeCreateDialog.module.css     CREATE
      AttributeTable.tsx                   CREATE  Task 4
      AttributeList.tsx                    MODIFY  +section visibility toggle, +section layout selector (Task 7/8)
      AttributeInspector.tsx               MODIFY  +options editor (Task 6), +section audience/layout fields
      AttributeInspector.module.css        MODIFY or reuse AttributeEditor.module.css — check which exists
      attribute-edits.ts                   MODIFY  +sections-aware helpers
      AttributeEditor.module.css           MODIFY  +grid layout, +card boundaries, +origin badge, +type icon
    i18n/locales/de.json                   MODIFY  new keys
    i18n/locales/en.json                   MODIFY  same keys
    test/ui-ratchet.test.ts                MODIFY  baseline bump if new inline-style-adjacent patterns are introduced (should be zero — verify, don't assume)
```

---

## Phase A — Backend: Create/Delete API (spec §3)

### Task 1: Service-layer create/delete + REST endpoints, global scope

**Why:** No create path exists at all (V1). Reusing `update_global`'s existing validation is the whole point — this task is a thin wrapper, not a new write path.

**Files:**
- Modify: `backend/application/attribute_definition_service.py` (add `create_global`, `delete_global` near `update_global` at line 239)
- Modify: `backend/attribute_definitions/schema.py` — add a `validate_new_attribute_name(name, existing_attributes)` helper: rejects a name that collides (case-sensitive) with any existing `core` or `extended` attribute, rejects a name that collides with a Django model field name for `kind="extended"` creates (query the target model's field names at call time — `django.apps.apps.get_model("persistence", item_type)._meta.get_fields()` or the equivalent this codebase already uses for `kind=core` bootstrapping, check `bootstrap_attribute_definitions.py:383` `_attribute_type()` for the existing field-introspection pattern and reuse it rather than re-deriving), rejects non-`snake_case` (reuse or adapt the regex the rest of this module already has access to via `import re`).
- Modify: `backend/rest_api/attribute_definition_views.py` — add `AttributeDefaultsDetailView.post` (create) and `.delete` (delete, query param `?name=`) OR two new view classes if this codebase's `urls.py` convention prefers one-verb-per-URL (check `urls.py` for how `reset/` was wired — mirror whichever pattern is already dominant instead of introducing a third).
- Modify: `backend/rest_api/urls.py` — wire the new route(s).
- Modify: `frontend/src/api/attribute-definitions.ts` — add `"ChangeRequest"` to `AttributeItemType` (V5).

**Interfaces:**
```python
def create_global(
    self, ctx: AuthContext, item_type: str, preset: str, attribute: dict[str, Any]
) -> dict[str, Any]:
    """Add one new kind="extended" attribute to the global default.

    Reuses update_global's full validation (core-lock, locked-lock,
    propagation, audit log) by reading the current row, appending the
    normalized new entry, and delegating. Raises AttributeSchemaError if
    `attribute["kind"] == "core"` (schema.py:481's existing check fires),
    or if the name collides (new validate_new_attribute_name check).
    """

def delete_global(
    self, ctx: AuthContext, item_type: str, preset: str, name: str
) -> dict[str, Any]:
    """Remove one kind="extended" attribute from the global default.

    Refuses (AttributeSchemaError) if `name` resolves to a kind="core"
    attribute (schema.py:439's existing check fires when the entry
    disappears from the new list). Does NOT check for existing
    CustomFieldValue data here -- that's Task 5's soft-delete flow at the
    API-caller layer; this method is the hard-delete primitive both the
    soft- and force-delete UI flows call after their own confirmation.
    """
```

- [ ] **Step 1: Write failing tests** for `create_global`/`delete_global` in `backend/application/tests/test_attribute_definition_service.py` (check if this file exists — if not, create it; there is definitely `backend/attribute_definitions/tests/` and `backend/rest_api/tests/test_attribute_definition_views.py`, but verify whether a service-level test file already exists before assuming). Cover: successful create, create with `kind="core"` rejected, create with colliding name rejected, create with a name matching a Django model field rejected, delete of an `extended` attribute succeeds, delete of a `core` attribute rejected.
- [ ] **Step 2: Run, confirm failure** (`AttributeError: 'AttributeDefinitionService' object has no attribute 'create_global'`).
- [ ] **Step 3: Implement** `create_global`/`delete_global` + `validate_new_attribute_name` per the interfaces above.
- [ ] **Step 4: Wire REST** — `AttributeDefaultsDetailView` gains `post`/`delete` (or new view classes, per the urls.py convention check above), same `_require_admin` gate, same error mapping (`AttributeSchemaError` → 400, `AttributeDefinitionNotFound` → 404).
- [ ] **Step 5: REST tests** in `test_attribute_definition_views.py` — 200 on valid create/delete, 400 on core/collision, 403 for non-admin.
- [ ] **Step 6: Run scoped tests, confirm green.**

### Task 2: Service-layer create/delete + MCP tools, workspace scope (+ global MCP parity, V6)

**Why:** Workspace-scope create is the core of the user's ask ("ich aber im Projekt theoretisch andere Attribute anlegen kann") — a workspace attribute with no `source_global` counterpart at all, not just a meta-override. Also adds MCP tools for both scopes per V6.

**Files:**
- Modify: `backend/application/attribute_definition_service.py` — `create_workspace`, `delete_workspace`.
- Modify: `backend/mcp_server/tools/attribute_definition.py` — 4 new tools: `attribute_definition.create` (global), `attribute_definition.delete` (global), `attribute_definition.create_workspace`, `attribute_definition.delete_workspace`. Same `CrossTenantWorkspaceError` → `PERMISSION_DENIED` guard as `_handle_get` (line 168-179) on the two workspace-scoped handlers.
- Modify: `backend/rest_api/attribute_definition_views.py` — `WorkspaceAttributeDefinitionView.post`/`.delete`.
- Modify: `backend/rest_api/urls.py`.

**Interfaces:**
```python
def create_workspace(
    self, ctx: AuthContext, item_type: str, workspace_id: UUID, attribute: dict[str, Any]
) -> dict[str, Any]:
    """Add a workspace-only attribute (no source_global counterpart).

    Sets is_customized=True on the WorkspaceAttributeDefinition row --
    identical divergence semantics to any other workspace edit (spec v1
    §3): once a workspace has ANY local addition it stops receiving
    global propagation until reset_workspace() re-copies the global.
    Reuses update_workspace's full validation the same way
    create_global reuses update_global's.
    """
```

- [ ] **Step 1: Failing tests** — workspace create (no global counterpart, `is_customized` flips to `True`), delete of a workspace-only attribute, attempted delete of an attribute the workspace inherited from global (should this be rejected, or should it fall through to `update_workspace` treating the name as newly-absent and thus... check: does removing an INHERITED entry from a workspace's own list currently mean anything coherent, or does the next global propagation just re-add it? Verify against `global_definition_store.py`'s propagation logic before writing this test — this is a real edge case the spec doesn't explicitly cover and needs a concrete, tested answer, not an assumption).
- [ ] **Step 2: Run, confirm failure.**
- [ ] **Step 3: Implement** `create_workspace`/`delete_workspace`.
- [ ] **Step 4: MCP tools** — 4 handlers + schema entries in `get_tool_schemas()`, following the exact `require_param`/`require_uuid` pattern already used by `_handle_update`.
- [ ] **Step 5: REST** — `WorkspaceAttributeDefinitionView.post`/`.delete`.
- [ ] **Step 6: Tests** across `test_attribute_definition_service.py`, `test_attribute_definition_tools.py`, `test_attribute_definition_views.py`, `test_attribute_definition_enforcement.py` (core/locked negative cases at the new surfaces).
- [ ] **Step 7: Run scoped tests, confirm green.**

## Phase B — Frontend: Create Flow (spec §4.1)

### Task 3: `AttributeCreateDialog` component + wiring

**Why:** Zero "add attribute" affordance exists anywhere in the UI (V1). This is what actually makes attribute creation discoverable.

**Files:**
- Create: `frontend/src/components/AttributeEditor/AttributeCreateDialog.tsx`, `.module.css`
- Modify: `frontend/src/components/AttributeEditor/AttributeEditorPage.tsx` — add a "+ Attribut hinzufügen" button per section (reuse `AttributeList`'s existing section-header badge row as the mount point) and a page-level "+ Neue Sektion" button next to it.
- Modify: `frontend/src/api/attribute-definitions.ts` — add `createGlobalAttribute`/`createWorkspaceAttribute`/`deleteGlobalAttribute`/`deleteWorkspaceAttribute` client functions calling Task 1/2's new endpoints.
- Modify: `frontend/src/i18n/locales/{de,en}.json` — new keys for the dialog's fields/labels/errors.

**Interfaces:**
```typescript
export interface AttributeCreateDialogProps {
  scope: "global" | "workspace";
  section: string;               // pre-filled from the section the + button was clicked in
  existingNames: string[];       // client-side collision pre-check (server re-validates)
  onCreate: (attribute: NewAttributeInput) => Promise<void>;
  onClose: () => void;
}
```

- [ ] **Step 1: Component test** (`AttributeCreateDialog.test.tsx`) — renders all 10 `ATTRIBUTE_TYPES` in the type dropdown, shows an inline error on a colliding name (client pre-check), calls `onCreate` with a well-formed `NewAttributeInput` on submit, shows "existiert nur in diesem Workspace" hint when `scope="workspace"` (spec §4.1).
- [ ] **Step 2: Run, confirm failure** (component doesn't exist).
- [ ] **Step 3: Implement** the dialog — Name, Typ (`<select>` over the 10 types), for `enum`/`multi-enum` immediately show a minimal inline options list (full editor is Task 6 — here just enough to create a non-empty `options[]`, since `schema.py:308-309` requires it for those two types), Pflichtfeld toggle, Sektion (pre-filled, editable).
- [ ] **Step 4: Wire into `AttributeEditorPage.tsx`** — button opens dialog, `onCreate` calls the new API client function, on success refetches the resolved definition (reuse whatever refetch/mutate pattern the page already uses for its existing PUT calls).
- [ ] **Step 5: E2E-adjacent test or manual verification** — run the frontend dev stack, actually create an attribute through the UI, confirm it appears in the list. Cite the exact `make up` / `docker compose ... restart frontend` sequence from Commands above.
- [ ] **Step 6: Run scoped frontend tests, confirm green.**

## Phase C — Frontend: Table View (spec §4.2)

### Task 4: `AttributeTable.tsx` + view-mode toggle

**Why:** V-confirmed list-only UI (no columns).

**Files:**
- Create: `frontend/src/components/AttributeEditor/AttributeTable.tsx`
- Modify: `frontend/src/components/AttributeEditor/AttributeEditorPage.tsx` — view-mode toggle (List/Tabelle), state persisted to `localStorage` (key e.g. `attributeEditor.viewMode`), both views read the same resolved-definition state, no second data fetch.
- Modify: `frontend/src/components/AttributeEditor/AttributeEditor.module.css` — table styles (CSS Grid or `<table>`, tokens.css only).

**Interfaces:** `AttributeTableProps` mirrors `AttributeListProps` (same `attributes`, `selected`, `onSelect` — table doesn't need `onMove`/section-reorder props, sorting is client-side and doesn't persist order).

- [ ] **Step 1: Failing test** — `AttributeTable.test.tsx`: renders one row per attribute, columns `Name | Typ | Sektion | Pflicht | Sichtbar | Audience | Herkunft`, clicking a column header sorts by it, clicking a row calls `onSelect`.
- [ ] **Step 2: Run, confirm failure.**
- [ ] **Step 3: Implement.** "Herkunft" column: `global` (inherited, not customized), `global (angepasst)` (inherited + `is_customized` on the workspace row — note this is currently a per-DEFINITION flag not per-ATTRIBUTE, so every row shows the same value in workspace scope; that's correct, not a bug, until/unless a future plan makes divergence per-attribute), `workspace-eigen` (created via Task 2, no `source_global` counterpart — the resolved payload needs a per-attribute marker for this; check whether `resolve()` already carries enough information to distinguish "inherited-and-unmodified" from "workspace-only" per attribute, or whether Task 2's `create_workspace` needs to stamp a marker field like `_workspace_only: true` into the stored entry for the UI to read back. Verify against `workspace_definition_store.py`'s resolve/materialize logic before assuming the data is already there).
- [ ] **Step 4: Toggle wiring** in `AttributeEditorPage.tsx`.
- [ ] **Step 5: Run scoped tests, confirm green.**

## Phase D — Options Editor (spec §4.3)

### Task 5: Delete-collision-check helper (shared by Task 2's delete AND Task 6's option-removal)

**Why:** Both "delete an attribute" and "remove a select-option value" need the same shape of check: does existing `CustomFieldValue` data reference what's about to disappear? Building this once avoids duplicating the warning-dialog logic.

**Files:**
- Modify: `backend/application/attribute_definition_service.py` — add `count_usages(ctx, item_type, workspace_id, attribute_name, option_value=None)` returning an integer count of artifacts whose `custom_fields` (or core field, if `kind=core`) reference the given attribute name (and, if `option_value` given, specifically that option value).
- Modify: `backend/rest_api/attribute_definition_views.py` / `mcp_server/tools/attribute_definition.py` — expose as a read endpoint/tool the delete/remove UI calls before showing its confirmation dialog.
- Modify frontend: shared confirmation-dialog usage in both the delete-attribute flow (Task 1/2's UI wiring, revisit `AttributeList.tsx`'s existing delete button) and Task 6's option-removal flow.

**Interfaces:**
```python
def count_usages(
    self, ctx: AuthContext, item_type: str, workspace_id: UUID,
    attribute_name: str, option_value: str | None = None,
) -> int:
    """Count artifacts of item_type in this workspace whose value for
    attribute_name is set (or, if option_value given, equals it)."""
```

- [ ] **Step 1: Failing test** for `count_usages` — 0 for an unused attribute, N for one referenced by N artifacts, correctly scoped by `option_value` when given.
- [ ] **Step 2: Run, confirm failure.**
- [ ] **Step 3: Implement.** Check whether an existing query pattern for "artifacts with a given custom_field key set" already exists somewhere in this codebase (search `custom_fields__` ORM lookups in `application/`) before writing a new one from scratch.
- [ ] **Step 4: Wire read endpoint/tool.**
- [ ] **Step 5: Run scoped tests, confirm green.**

### Task 6: Options editor in `AttributeInspector`

**Why:** V2-confirmed: backend already accepts `options` via meta-only PUT, zero UI exists.

**Files:**
- Modify: `frontend/src/components/AttributeEditor/AttributeInspector.tsx` (currently 150 lines — read the full current content first, this plan's line citations for other files are pre-verified but this file's internal structure needs a fresh read since it's the one most tasks in this phase touch).
- Modify: `frontend/src/components/AttributeEditor/attribute-edits.ts` if it holds the client-side attribute-mutation helpers this new editor needs (check first).

**Interfaces:** New sub-section in the inspector, rendered only when `attribute.type` is `"enum"` or `"multi-enum"`: rows of `{value, label_de, label_en}` with add/remove/reorder controls, matching `schema.py:148-172`'s `_normalize_options` contract exactly (all three fields required, no extras).

- [ ] **Step 1: Failing test** — options section hidden for `type="text"`, shown and editable for `type="enum"`, add/remove/reorder work, removing a value that `count_usages(..., option_value=...)` (Task 5) reports as referenced shows a warning with the count before confirming.
- [ ] **Step 2: Run, confirm failure.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run scoped tests, confirm green.**

## Phase E — Sections: Visibility + Grid Layout (spec §4.4/4.5)

### Task 7: `sections[]` schema + lazy materialization

**Why:** V4-confirmed: sections have no structure today, purely derived from the free-text `section` field.

**Files:**
- Modify: `backend/attribute_definitions/schema.py` — add `SECTION_LAYOUTS: frozenset[str] = frozenset({"full", "half"})`, a `normalize_section(raw)` function mirroring `normalize_attribute`'s shape (`{name, order, visible: bool, layout: "full"|"half"}`), and a `validate_definition_json` extension (or a sibling `validate_sections_json`) that also normalizes a `sections` list when present.
- Modify: `backend/attribute_definitions/global_definition_store.py` / `workspace_definition_store.py` — on read, if `definition_json` has no `sections` key, materialize one from `sectionNames`-equivalent aggregation of the current `attributes` list (`{name, order: <ascending index>, visible: true, layout: "full"}` for each), write it back so subsequent reads don't re-derive (the spec's own §4.4 "additive, no data migration" framing — verify this write-back-on-read approach doesn't fight the existing caching layer `invalidate_workspace_caches` guards; check how that cache is populated relative to a plain read, since a lazy write during what looks like a GET is an unusual side effect worth a comment explaining why it's safe here).
- Create: `backend/attribute_definitions/migrations/0007_attribute_sections.py` — this is likely a no-op migration (no new DB column, `sections` lives inside the existing `definition_json` JSONField) — confirm whether a real migration is needed at all, or whether this task needs zero Django migration and the "materialization" is purely an application-layer concern. Don't create an empty migration file if genuinely nothing schema-level changed.

- [ ] **Step 1: Failing test** — reading a definition with no `sections` key returns one materialized from the attribute list; reading one that already has `sections` returns it unchanged; `normalize_section` rejects an unknown `layout` value.
- [ ] **Step 2: Run, confirm failure.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run scoped tests, confirm green.**

### Task 8: Section visibility + grid layout in the UI

**Why:** Completes spec §4.4/4.5 — the schema exists (Task 7), now render it.

**Files:**
- Modify: `frontend/src/components/AttributeEditor/AttributeList.tsx` — per-section visibility toggle and layout selector (`full`/`half`) in the section header badge row, alongside the existing rename/move-up/move-down/delete buttons (same `data-testid` convention: `attribute-section-{name}-visible`, `attribute-section-{name}-layout`).
- Modify: `frontend/src/components/AttributeEditor/AttributeEditor.module.css` — the actual consuming CSS Grid lives in the ArtifactForm renderer (v1 §6), not the editor itself — find that component (likely `frontend/src/components/shared/ArtifactForm/` per the v1 spec's own file references) and add `grid-template-columns: repeat(2, 1fr)` there, with each section applying `grid-column: span 2` (full) or `span 1` (half). Verify the actual current path of the v1-delivered `ArtifactForm` renderer before writing this — v1's own spec cites `shared/ArtifactForm/` but re-confirm it landed there exactly.
- Modify: `frontend/src/api/attribute-definitions.ts` — extend the resolved-definition TS type with the new `sections` array shape.

- [ ] **Step 1: Failing test** — toggling a section's visibility persists (PUT with the updated `sections` array); a `visible=false` section and all its attributes are absent from `ArtifactForm`'s render regardless of individual attribute `visible` flags (spec §4.4's AND-condition); two consecutive `layout="half"` sections render side-by-side; a lone `half` section leaves the second grid column empty (no reflow).
- [ ] **Step 2: Run, confirm failure.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run scoped tests, confirm green.**

## Phase F — Export / Import (spec §6)

### Task 9: `export_definition`/`import_definition` service methods

**Why:** V3-disambiguated — this is a new capability, distinct from the existing `export_attributes`.

**Files:**
- Modify: `backend/application/attribute_definition_service.py` — `export_definition(ctx, item_type, workspace_id_or_none)` (global when `workspace_id_or_none is None`, resolved-workspace when given) returns `{"schema_version": 1, "item_type": ..., "attributes": [...], "sections": [...]}`. `import_definition(ctx, item_type, workspace_id_or_none, payload, on_collision: Literal["skip","overwrite","rename"])` validates via the existing `validate_definition_json`/new `validate_sections_json` (Task 7), then for each incoming attribute checks name collision against the target's current list and applies `on_collision`.

**Interfaces:**
```python
def export_definition(
    self, ctx: AuthContext, item_type: str, workspace_id: UUID | None = None,
) -> dict[str, Any]:
    """Serialize a whole definition (global if workspace_id is None, else
    the resolved workspace copy) for download. schema_version=1 so a
    future format change can be detected on import rather than silently
    misread."""

def import_definition(
    self, ctx: AuthContext, item_type: str, payload: dict[str, Any],
    workspace_id: UUID | None = None, on_collision: str = "skip",
) -> dict[str, Any]:
    """Import previously-exported attributes into a definition. On
    global scope this is 'like an edit' (spec §6) -- goes through
    update_global, so propagation to non-customized workspaces applies
    exactly as any other global edit would, no special-cased path."""
```

- [ ] **Step 1: Failing tests** — export produces a re-importable document; import with `on_collision="skip"` leaves existing entries untouched and adds only new names; `"overwrite"` replaces; `"rename"` suffixes (`name_2`, `name_3`, ...); import rejects a `schema_version` it doesn't recognize; import of a `kind="core"` entry from the file is rejected (same core-lock as create).
- [ ] **Step 2: Run, confirm failure.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run scoped tests, confirm green.**

### Task 10: REST + MCP surface for export/import

**Files:**
- Modify: `backend/rest_api/attribute_definition_views.py` + `urls.py` — `GET .../export/` (both scopes), `POST .../import/` (both scopes, body = the exported JSON + `on_collision` query/body param).
- Modify: `backend/mcp_server/tools/attribute_definition.py` — `attribute_definition.export`/`.export_workspace`/`.import`/`.import_workspace` (or fold scope into a parameter the way `list`/`get` already do with optional `item_type` — check whether this codebase's MCP naming convention prefers a scope parameter over a scope-suffixed tool name before picking; V6 already established a suffix precedent with `create_workspace`/`delete_workspace`, follow that same precedent here for consistency rather than introducing a parameter-based alternative in the same tool group).

- [ ] **Step 1: Failing tests** across REST/MCP test files.
- [ ] **Step 2: Run, confirm failure.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run scoped tests, confirm green.**

### Task 11: Export/Import UI

**Files:**
- Modify: `frontend/src/components/AttributeEditor/AttributeEditorPage.tsx` — "Export" button (triggers a browser download of the JSON via the existing REST client, not a new download mechanism — check whether this codebase already has a shared "trigger file download from a JSON response" helper, e.g. used by ReqIF/CSV export elsewhere, and reuse it rather than writing a second one), "Import" button opens a file picker + the collision-resolution UI (radio: überspringen/überschreiben/umbenennen, matching spec §6).
- Modify: `frontend/src/api/attribute-definitions.ts` — client functions.

- [ ] **Step 1: Failing test** — export button triggers download with correct filename/content-type; import file picker + collision UI renders; each `on_collision` choice sends the right value.
- [ ] **Step 2: Run, confirm failure.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run scoped tests, confirm green.**

## Phase G — Design Polish (spec §7)

### Task 12: Section card boundaries, origin badges, type icons

**Why:** Spec §7 — concretized, not vague "prettier".

**Files:**
- Modify: `frontend/src/components/AttributeEditor/AttributeEditor.module.css` — section card border/radius using an existing `tokens.css` radius stage (check `frontend/src/styles/tokens.css` for the actual token names in use elsewhere, e.g. what `Dialog`/`ArtifactRow` already use, and match rather than inventing a new radius value).
- Modify: `AttributeList.tsx` + `AttributeTable.tsx` (Task 4) — origin badge (global/customized/workspace-eigen, reusing Task 4's per-attribute origin marker), type icon per row (reuse the existing icon library already imported in this file — `lucide-react`, per `AttributeList.tsx:12` — pick one icon per `ATTRIBUTE_TYPES` value, no new icon dependency).

- [ ] **Step 1: Failing test** — each row renders a type icon matching its `type`; origin badge renders with the correct of three states; visual check (not a snapshot test unless this codebase already uses snapshot testing for similar components — check before adding one).
- [ ] **Step 2: Run, confirm failure.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run scoped tests, confirm green.**

---

## Final Review

Per the `subagent-driven-development` skill's own process: a whole-branch final review happens automatically after the last task above, on the most capable available model, followed by its own fix wave and scoped re-review — this is not a separate numbered task in this plan (matching how `interview-engine-fix`/`ki-vorschlag-als-zustand` also leave it to the skill rather than a Task N+1 entry). Run the FULL backend + frontend suite at that point, not just the scoped subsets each task above ran.
