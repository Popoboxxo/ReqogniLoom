## Workflow & Permissions: Global-Default-Modell + Settings-IA-Split — UI Specification

**ui_spec_id:** `UISPEC-2026-07-18-workflow-permissions-global-default`
**Status:** Proposed (design step, pipeline stage 4/7)
**Covers:** REQ-178, REQ-179, REQ-180, REQ-181, REQ-182, REQ-183, REQ-184, REQ-185, REQ-186, REQ-187
**Inputs read:** `docs/REQUIREMENTS.md` (section "Workflow & Permissions: Global-Default-Modell + Settings-IA-Split (2026-07-18)"), `docs/api/workflow-permissions-global-default.openapi.yaml`, `frontend/src/components/WorkspaceSettings/{WorkspaceSettings,WorkflowsSection,PermissionsSection}.tsx`, `frontend/src/components/WorkflowEditor/*`, `frontend/src/components/NavigationShell/{SidebarNavigation,NavigationShell}.tsx`
**Does not cover:** implementation, component code, backend logic. Framework/library names below (React Flow, TanStack Query, etc.) are cited only where the existing codebase already names them, to describe *reuse*, not to prescribe new tech choices.

---

## 1. Screen / route inventory

| Screen ID | Route | Screen name | Home surface | REQ-ID(s) | Change type |
|---|---|---|---|---|---|
| SCR-201 | `/settings` (shell, unchanged) | Workspace Settings | Workspace Settings | REQ-L2-RF-012 (existing) | Unchanged — tabs `general`/`traceability`/`visibility`/`llm` stay exactly as-is |
| SCR-202 | `/settings` → tab `workflows-permissions` | Workspace Settings — Workflows & Permissions | Workspace Settings | REQ-180, REQ-183, REQ-185 (primary); REQ-179, REQ-182 (regression protection); REQ-178, REQ-181 (references global source) | **Rebuilt** (replaces the `governance` tab) |
| SCR-203 | `/system-settings` (new shell) | System Settings | System Settings (new) | REQ-184 | **New** |
| SCR-204 | `/system-settings` → tab `administration` | System Settings — Administration | System Settings | REQ-184 (relocation only, no behavior change) | **Relocated** (was `/settings` tab `admin`) |
| SCR-205 | `/system-settings` → tab `workflow-defaults` | System Settings — Workflow Defaults | System Settings | REQ-178, REQ-179 (editor reuse), REQ-176/177 (reused component) | **New**, built on existing `WorkflowEditorPage` |
| SCR-206 | `/system-settings` → tab `permission-defaults` | System Settings — Permission Defaults | System Settings | REQ-181, REQ-186, REQ-187 | **New** |
| — | `/workflows/:entityType` (unchanged route) | Workflow Editor (workspace-scope) | top-level nav "Workflows" | REQ-176, REQ-177, REQ-179 | **Unchanged** — this is the editing surface SCR-202's "Edit" links point to |

Notes:
- No route below `/system-settings` gets deeper sub-routing beyond a `?tab=` query param (mirrors how `/settings` manages tabs today: local `useState`, no nested router paths). This matches the confirmed IA decision ("no deeper routing rework beyond the one new route").
- `PermissionsSection.tsx` (ItemPermission per-user/per-artifact CRUD, COMP-AT-005) is **unchanged** and keeps living inside SCR-202 — it is a distinct resource from the new Workspace Permission Definition matrix (REQ-182 explicitly protects it).

---

## 2. Navigation specification (REQ-184)

**New top-level nav entry:** `System Settings` (`labelKey: nav.systemSettings`).

Placement in `SidebarNavigation.tsx`'s `NAV_ITEMS` array: immediately **after** the existing `Settings` entry (last position in the current list), so the diff is additive and doesn't reorder anything else:

```
...
{ path: "/workflows", labelKey: "nav.workflows", feature: "dashboard" },
{ path: "/metrics",   labelKey: "nav.metrics",   feature: "metrics" },
{ path: "/settings",  labelKey: "nav.settings",  feature: "dashboard" },
{ path: "/system-settings", labelKey: "nav.systemSettings", feature: "dashboard" },   // NEW
```

- Visibility rule: identical convention to `/settings` today — the nav *link* is visible to every authenticated user (`feature: "dashboard"`, always-on), and the **page itself** gates on `roles.includes("admin")` with the same "you must be an admin" message pattern already implemented in `WorkspaceSettings.tsx` (early-return before the tab shell renders). Do not invent a separate role-gating mechanism for the nav item — reuse the page-level gate.
- Active-state highlighting: identical `NavLink` styling already used for every other item (`ACTIVE_BG` left-border treatment) — no new visual variant.
- No icon changes, no submenu/flyout — flat list entry like all current ones.

---

## 3. Screen specifications

### SCR-202 — Workspace Settings → "Workflows & Permissions" tab (rebuilt, REQ-185)

**Purpose:** Let a workspace admin see, at a glance, whether this workspace's workflow and permission configuration matches the tenant-wide global default or has been overridden, and give them one-click access to reset to default or to edit the override.
**Audience:** Workspace admin (same gate as the rest of `/settings`).
**Replaces:** the tab currently labelled `t("settings.tabs.governance", "Workflows & Berechtigungen")`, which embeds `WorkflowsSection` (raw artifact-id + free-text state name form) and `PermissionsSection`.

**Layout** (same card-stack pattern as every other Settings tab — `cardStyle`, `headingStyle`, `hintStyle` reused verbatim):

Card 1 — **"Workflow Configuration"** (per entity type, REQ-178/179/180):
- A compact list/table, one row per entity type (the same 7 types `WORKFLOW_ENTITY_TYPES` already enumerates: Requirement, StakeholderNeed, ArchitectureElement, Adr, Risk, TestCase, Issue).
- Row content: entity type label · `DefaultStatusBadge` (§4.1) · "Open in Workflow Editor" link (navigates to `/workflows/:entityType`, the existing unchanged editing surface) · "Reset to Default" button (§4.1), disabled/hidden when already on-default.
- Data source: one `GET /workflows/definition/?workspace_id&item_type` call per row (existing endpoint, additive fields `is_customized`/`on_default`/`source_global_id` — REQ-180). No new list endpoint needed; 7 parallel/staggered fetches is an acceptable, bounded cost (matches the existing per-entity-type fetch pattern the Workflow Editor's `EntityTypeSelector` already implies).
- Empty/edge state: if `source_global_id` is `null` (pre-REQ-178 workspace, or global row deleted) — the row shows a neutral "No global source" tag instead of the badge, and "Reset to Default" is disabled with a tooltip ("This workspace has no linked global default — initialize one in System Settings first"), mirroring the API's `NO_GLOBAL_SOURCE` 409 contract.

Card 2 — **"Permission Configuration"** (workspace matrix override, REQ-181/182/183):
- Single `DefaultStatusBadge` for the workspace's permission matrix (`GET /workspaces/{id}/permission-definition/`) + "Reset to Default" button (§4.1).
- Below the badge: a compact **read view** of the current effective 4×6 matrix (role rows × capability columns, ✓/— glyphs) — reuse the existing `permissions-table` (`thStyle`/`tdStyle`) visual language from `PermissionsSection.tsx`, not a new table style.
- "Override matrix…" button opens the same matrix-editor UI described in SCR-206 §4.3 (grid of checkboxes), scoped to `PUT/PATCH /workspaces/{workspace_id}/permission-definition/` instead of the global endpoint. Saving sets `is_customized=true` (per contract) → badge flips to "Customized" without a page reload (optimistic cache update, matching the existing `WorkflowEditorPage` mutation-hook pattern of writing the response straight into the query cache).
- The **existing** `PermissionsSection` component (per-user/per-artifact `ItemPermission` grant/revoke table, REQ-L1-039) renders unchanged directly below this card, exactly where it renders today — same heading, same grant form, same revoke table. No visual or functional change to this block.

**States:** loading (skeleton row per entity type + skeleton badge), empty (`source_global_id` null, see above), error (inline `role="alert"` banner, same red-border pattern already used for `saveError` in `WorkspaceSettings.tsx`), success (badges + tables rendered), partial-data (if one entity type's fetch fails, that row shows an inline error chip while the other 6 rows render normally — do not block the whole card on one failed row).

**Navigation:** entry via the `/settings` tablist (tab renamed from "Workflows & Berechtigungen" to "Workflows & Permissions" / `t("settings.tabs.governanceReplacement", "Workflows & Permissions")`); exits via the "Open in Workflow Editor" links (→ `/workflows/:entityType`) and implicitly via the sidebar.

**Interactions:** click badge row → no-op (informational); click "Reset to Default" → confirm dialog (`window.confirm`, same convention as `handleCloseWorkspace`/`handleRevoke`) → `POST` reset endpoint → refetch row → badge flips to "On Default", toast `settings.resetOk` ("Reset to the current global default."). Click "Override matrix…" → inline expand (not a modal, to stay consistent with the rest of the tab's inline-card style) showing the editable grid; "Save" / "Cancel" buttons at the bottom of the expanded block.

**Validation rules:** none client-side beyond disabling actions in invalid states (already-on-default rows disable "Reset"; matrix editor enforces the closed 4-role/6-capability shape by rendering exactly those cells — no free-text ever possible, so there is nothing to validate client-side beyond "at least render every cell").

**Accessibility:** each row is a `role="row"` inside a `role="table"` (or a semantic `<table>`, matching `PermissionsSection`'s existing `<table>` usage) with visible-text badge labels (never color-only — "On Default"/"Customized" text plus color, exactly like the existing `permission_level` pill which already pairs color with visible text). Reset buttons carry `aria-label` including the entity-type name (e.g. "Reset Requirement workflow to default") since multiple identical-looking buttons exist in one list. Confirm dialogs keep native `window.confirm` semantics (already screen-reader-announced by the browser, consistent with existing code).

---

### SCR-203/204 — System Settings shell + "Administration" tab (REQ-184)

**Purpose:** house tenant/system-wide configuration, separated from workspace-bound settings.
**Audience:** admin (same gate).
**Layout:** exact structural clone of `WorkspaceSettings.tsx`'s shell — page heading, `role="tablist"` tab row with the same underline-active styling, `role="tabpanel"` below, shared `cardStyle`/`headingStyle`/`hintStyle`. This is the literal reuse instructed by the constraint ("IA split, not a redesign") — no new chrome.

**Tabs (in order):**
1. `administration` (SCR-204) — the **relocated, otherwise unchanged** content of the old `/settings` "Administration" tab: the "System Health" card (`SystemHealthDialog` trigger, unchanged), the feature-flagged `BackupRestoreSection` (unchanged), and the "Workspace Administration" card (close/reactivate/delete/clone actions on `activeWorkspace`, unchanged — still governed by the sidebar's workspace switcher, since `useWorkspace()` context is global and not route-scoped). No behavior change, pure relocation per REQ-184's explicit text.
2. `workflow-defaults` (SCR-205, see below)
3. `permission-defaults` (SCR-206, see below)

**States/Navigation/Interactions/Validation/Accessibility for `administration`:** identical to today's admin tab — this document does not re-specify unchanged behavior in detail; only the *host* (route/tab shell) changed.

---

### SCR-205 — System Settings → "Workflow Defaults" tab (REQ-178, REQ-179 reuse)

**Purpose:** edit the tenant-wide, per-(item_type, preset) global workflow state machines that every new workspace inherits.
**Audience:** admin.

**Component reuse mandate:** this tab renders the **existing** `WorkflowEditorPage` composition (header + 3-panel layout: entity selector · React-Flow canvas · inspector + status bar + dialogs) with one new input dimension threaded through it — it is explicitly **not** a second graph editor.

**Parameterization (how the existing component is reused, described functionally — not as code):**
- The page gains an optional **scope** concept: `workspace` (today's only mode, default, zero behavior change — REQ-179 regression protection) vs. `global` (new). SCR-205 always renders it in `global` scope.
- In `global` scope:
  - Header title reads "Global Workflow Defaults" instead of "Workflow Editor".
  - The read-only preset **badge** in the header (today: a static label showing the workspace's own preset) is replaced by an interactive **preset selector** — a compact 3-way segmented control (Minimal / Standard / Extended), visually a smaller sibling of the existing settings-tab underline style, not a new widget language. Global defaults are defined *per preset*, so this is the one genuinely new control this reuse requires (REQ-178's "no cross-preset shared default" rule made concrete in the UI).
  - The left "selector" panel keeps the existing entity-type list (`EntityTypeSelector`, all 7 types, unchanged), now additionally showing a small dot/label per row indicating "seeded" vs. "not yet initialized" for the *currently selected preset* (derived from `initialized` on the fetched graph) — this reuses the exact same empty-graph → "Initialize Workflow" CTA already implemented in `WorkflowCanvas` for the workspace scope; in global scope, the same CTA calls the global initialize endpoint instead.
  - Canvas/inspector/edit-mode toggle/state-and-transition dialogs/Mermaid export: **all unchanged**, operating on the global graph shape instead of the workspace graph shape (the two response shapes are structurally compatible for rendering — `WorkflowGraphGlobal` is a subset of `WorkflowGraphWorkspace` missing only the `is_customized`/`on_default`/`source_global_id` fields, which the read-only/edit canvas never needed in the first place).
  - After any state/transition mutation, the response's `propagated_workspace_count` (per the OpenAPI contract) is surfaced as a toast using the page's existing toast mechanism: *"Change propagated to {N} workspace(s) currently on default."* This is the one genuinely new piece of feedback global-scope editing needs, since a global edit silently updates every non-customized workspace and that fact must not be invisible.
  - There is **no** "Reset to Default" action on this screen — this screen *is* the default; reset lives only on the consuming side (SCR-202, `/workflows/:entityType` is unaffected either way).

**States:** identical vocabulary to the existing Workflow Editor (loading/empty-uninitialized/error/read-only/editing), plus the preset-selector itself has no loading state of its own (it's a static enum, immediate re-fetch on change).

**Navigation:** entry via the System Settings tablist; the preset selector and entity-type selector are both in-page controls (no route change on switching them, consistent with how `/workflows/:entityType` already keeps entity-type switches as query-free path navigation — here, since preset is an *additional* dimension without its own path segment per the "no deeper routing rework" constraint, both entity type and preset are represented as query params, e.g. `/system-settings?tab=workflow-defaults&entityType=Requirement&preset=standard`, so the state is deep-linkable/bookmarkable without adding new path segments).

**Accessibility:** preset segmented control uses `role="tablist"`/`role="tab"` semantics identical to the outer Settings tabs (nested tab pattern is visually distinguished only by size/indent, per the "no new design system" constraint) with `aria-selected` wired the same way.

---

### SCR-206 — System Settings → "Permission Defaults" tab (REQ-181, REQ-186, REQ-187)

**Purpose:** edit the tenant-wide default role→capability matrix, and safely govern the shadow→authoritative enforcement cutover.
**Audience:** admin.

**Layout — three stacked cards in one tab** (same multi-card-per-tab convention as SCR-202 and the historic governance tab):

**Card 1 — Global Permission Matrix** (§4.3):
- Editable 4-role (admin/editor/viewer/approver) × 6-capability (read/write/workflow_transition/workflow_approval/workspace_config/assign_role) checkbox grid — closed shape, no add/remove row or column (matches `PermissionMatrix`'s `additionalProperties: false`).
- "Save" persists via `PUT /permission-defaults/` (full replace) — the UI always sends the complete matrix since it always renders the complete 4×6 grid, so PATCH's partial-merge capability is not needed by this screen (PATCH stays available for future/API-only partial updates, out of UI scope).
- The endpoint's `enforcement_mode` guard (`ENFORCEMENT_MODE_NOT_EDITABLE_HERE`) is enforced by construction: this card's save action never includes an `enforcement_mode` field — enforcement is exclusively Card 2's concern. This separation must be visually obvious: Card 1 has no mention of shadow/authoritative anywhere in it.
- On save, shows `propagated_workspace_count` toast, same pattern as SCR-205.

**Card 2 — Enforcement Mode** (§4.4, REQ-186/187 guarded flip):
- Current mode badge: "Shadow" (neutral/blue, informational tone) or "Authoritative" (green, matches the "on" states used elsewhere e.g. active preset highlighting) — reads from `GET /permission-defaults/enforcement/`.
- Meta line: `pending_mismatch_count` in the last `mismatch_window_days` days, `last_mismatch_at` (relative time), and the server's `advisory_note` text verbatim (do not paraphrase — it already contains the actionable guidance, e.g. "12 unreviewed mismatches in the last 30 days. Review via …").
- Primary action depends on current mode:
  - **Shadow → Authoritative:** button "Review & Flip to Authoritative" opens a guarded confirmation dialog (see interaction flow below). Never a single-click action.
  - **Authoritative → Shadow (rollback):** button "Roll Back to Shadow", single `window.confirm()` step, no count-gate (per contract: rollback needs no confirmation count).
- `ready_for_authoritative` is rendered as a soft hint only ("0 pending mismatches — ready to flip" / "12 pending — review recommended before flipping"), never as a disabling precondition on the button itself — per the OpenAPI's explicit note that this flag is advisory, not a hard gate. The actual safety mechanism is the count-echo in the dialog below.

**Guarded flip dialog (Shadow → Authoritative), step-by-step:**
1. On open, the dialog re-fetches `GET /permission-defaults/enforcement/` fresh (never reuses a stale count already on the page) and displays the current `pending_mismatch_count` prominently.
2. A link/button "View the {N} mismatches" scrolls to / expands Card 3 (Mismatch Review, below) in place — the dialog itself does not duplicate the table.
3. A required checkbox: *"I have reviewed the pending mismatches and accept the current count of {N} before switching to authoritative enforcement."* — this operationalizes REQ-187's "explicitly documented and consciously accepted" acceptance path at the granularity the schema allows (a reviewed total, not per-row triage — see the design-gap note in §6).
4. "Confirm & Flip" is disabled until the checkbox is checked. On submit, sends `confirm_pending_mismatch_count` equal to the count shown in step 1.
5. If the server responds `409 MISMATCH_COUNT_STALE` (count changed between dialog-open and submit), the dialog does **not** silently retry — it shows an inline error with the fresh count from the error body, unchecks the checkbox, and requires the user to re-read/re-confirm. This directly mirrors the contract's intent ("re-fetch and re-confirm").
6. On success: mode badge flips to "Authoritative", dialog closes, toast confirms the flip (audit trail is server-side, per contract — no separate UI needed for that).

**Card 3 — Mismatch Review** (§4.4, REQ-187):
- Always visible/expanded by default on this tab (not collapsed) — REQ-187's intent is to make regression risk *visible*, not hide it behind a toggle.
- Read-only, paginated table (`GET /permission-mismatches/`), columns: Time (`created_at`), Subject (icon by `subject_type` + truncated `subject_identifier`), Capability, Workspace (name if `workspace_id` present, else "tenant-wide"), Artifact (truncated id or "—"), Legacy Decision (✓/✗), New Decision (✓/✗). Every row in this table is by definition a mismatch (legacy ≠ new), so rows get a uniform soft-warning background tint (reuses the existing warning-color token, not a new palette entry) rather than per-row conditional styling.
- Filters above the table: Workspace (dropdown, optional — omit for tenant-wide), Capability (dropdown, 6 canonical keys), Subject type (user/apikey/agent), Since/Until (date pickers). Filter controls reuse the existing `inputStyle`/`selectStyle` form-control look from Settings, not new form components.
- Pagination: standard project list pagination (page/page_size, `count`/`next`/`previous`) — reuse whatever pagination control pattern is already used by other paginated list views in the app (e.g. Test Runs list), not a bespoke one for this table.
- No row-level actions (append-only, read-only — matches contract exactly: no DELETE/PATCH exposed).

**States:** loading/empty ("No mismatches recorded in this window — legacy and new decisions agree.")/error/success/partial (matrix save can fail independently of enforcement-panel fetch failing; each card handles its own error state, not one page-wide error blob).

**Navigation:** entry via System Settings tablist; internal anchor/scroll link from the flip dialog to Card 3.

**Validation rules:** matrix grid has no illegal states (checkbox grid can't produce a malformed shape); flip dialog's only "validation" is the checkbox-required + fresh-count-match, both described above.

**Accessibility:** matrix grid uses `<table>` semantics with `<th scope="col">` per capability and `<th scope="row">` per role so screen readers announce "Editor, write: checked" rather than a bare checkbox; enforcement mode badge pairs color with visible text ("Shadow"/"Authoritative", never color-only); the guarded-flip checkbox has a fully descriptive label (not just "I confirm"); mismatch table rows are real `<tr>`s with a text-based indicator for the tint (e.g. a small "⚠" glyph plus the tint) so the warning isn't conveyed by color alone.

---

## 4. Component breakdown

### 4.1 `DefaultStatusBadge` + reset action (shared, workflow and permission)

Used in: SCR-202 (both cards).

| Prop | Meaning |
|---|---|
| `isCustomized: boolean` | drives label + color |
| `hasSource: boolean` | when `false` (no `source_global_id`), renders the neutral "No global source" variant instead |

Visual spec (reusing existing tokens only):
- On Default: pill, `background: rgba(22,163,74,0.12)`, `color: var(--color-success, #16a34a)`, label text "On Default" — same pill shape/sizing as the existing `permission_level` badge in `PermissionsSection.tsx` (`border-radius: var(--radius-full)`, `padding: 1px var(--space-2)`, `font-size: var(--font-size-xs)`, `font-weight: 600`).
- Customized: same pill shape, `background: rgba(245,158,11,0.12)`, `color: var(--color-warning, #f59e0b)`, label "Customized".
- No global source: same pill shape, `background: var(--color-surface-raised)`, `color: var(--color-text-muted)`, label "No Global Source".

Reset action: a small text/outline button styled like the existing "Revoke" button in `PermissionsSection.tsx` (`background: transparent`, `border: 1px solid var(--color-danger)` — but reset is **not** destructive-tenant-wide, only workspace-local, so use the neutral/primary outline variant instead: `border: 1px solid var(--color-primary)`, `color: var(--color-primary)`), disabled (opacity 0.5, `cursor: not-allowed`) when `isCustomized === false` or `hasSource === false`.

### 4.2 Global Workflow Defaults Editor (SCR-205)

Not a new component — a **scope parameterization** of `WorkflowEditorPage` plus one new small component:

- **`PresetSegmentedControl`** (new, small): 3 buttons (minimal/standard/extended), `role="tablist"`/`role="tab"` semantics, visual sibling of the outer Settings tab underline style at a smaller scale. Emits `onChange(preset)`.
- `WorkflowEditorPage`, `WorkflowEditorHeader`, `WorkflowEditorLayout`, `EntityTypeSelector`, `WorkflowCanvas`, `InspectorPanel`, `StatusBar`, `StateDialog`, `TransitionDialog`, `ConfirmDialog`: all **reused as-is**, receiving data/mutation functions bound to the global endpoints instead of the workspace endpoints when `scope="global"`. No forked copies.

### 4.3 Global/Workspace Permission Matrix Editor (SCR-202 Card 2 "Override matrix", SCR-206 Card 1)

One editor component, parameterized by target (`global` vs a specific `workspace_id`):
- 4×6 checkbox grid, rows = roles, columns = capabilities (or transposed — either orientation is acceptable design-wise; recommend rows=roles/columns=capabilities since there are more capabilities (6) than roles (4), better for a typically-wider-than-tall settings card).
- Pre-filled from the current effective matrix (`permission_json`).
- "Save"/"Cancel" buttons, `primaryButtonStyle` reused verbatim.
- Unsaved-changes indicator: reuse the existing `savedOk`/`saveError` inline status pattern from `WorkspaceSettings.tsx`, not a new dirty-state UI.

### 4.4 Enforcement Mode Panel + guarded flip (SCR-206 Card 2)

- Mode badge (same pill visual language as 4.1, repurposed colors: Shadow = neutral/`color: var(--color-text-muted)` background `var(--color-surface-raised)`; Authoritative = success green).
- Meta line (plain text, `hintStyle`).
- Action button(s) as described in SCR-206.
- Guarded-flip dialog: reuse the existing `ConfirmDialog` component's chrome (title/message/busy/errorMessage/onClose/onConfirm) from the Workflow Editor, extended with the one additional required-checkbox field — same dialog *frame*, not a new modal system.

### 4.5 Mismatch Review Table (SCR-206 Card 3)

- Filter bar (selects + date inputs, existing `inputStyle`/`selectStyle`).
- `<table>` with `thStyle`/`tdStyle` reused from `PermissionsSection.tsx`.
- Pagination footer — reuse whatever the project's existing paginated-list convention is (page/page_size + prev/next), not a new pagination widget.

---

## 5. User journeys

| Journey | Persona | Goal | Steps | REQ coverage |
|---|---|---|---|---|
| "Check if my workspace still follows the house workflow" | Workspace Admin | Confirm this workspace's TestCase workflow hasn't silently diverged from the tenant standard | `/settings` → Workflows & Permissions tab (SCR-202) → sees "Customized" badge on TestCase row → clicks "Reset to Default" → confirms → badge flips to "On Default" | REQ-180, REQ-185 |
| "Roll out a new mandatory review step for all Standard-preset workspaces" | Tenant/System Admin | Add a `technical_review` state + gated transition to the global Standard-preset Requirement workflow, propagated to every non-customized workspace | Sidebar → System Settings (SCR-203) → Workflow Defaults tab (SCR-205) → select preset "Standard" → select entity type "Requirement" → enable Edit mode → add state/transition (existing `StateDialog`/`TransitionDialog`) → sees "Propagated to 14 workspaces" toast | REQ-178, REQ-179, REQ-184 |
| "Cut over permission enforcement without an outage" | Tenant/System Admin | Safely move from shadow to authoritative permission enforcement | System Settings (SCR-203) → Permission Defaults tab (SCR-206) → reviews Card 3 mismatch table (filters by capability) → opens Card 2's "Review & Flip" dialog → reads live pending count → checks the acceptance box → confirms → mode badge becomes "Authoritative"; if count changed mid-review, sees the stale-count error and re-confirms | REQ-186, REQ-187 |
| "Reset a workspace's permission override after a bad manual edit" | Workspace Admin | Undo a workspace-local permission mistake | `/settings` → Workflows & Permissions tab (SCR-202) Card 2 → sees "Customized" badge → "Reset to Default" → confirms | REQ-182, REQ-183 |

---

## 6. Design-system notes (reuse only — no new tokens/components introduced)

- Card container: `cardStyle` (`--color-surface`, `--radius-lg`, `--shadow-card`) — used unchanged everywhere above.
- Heading/hint text: `headingStyle`/`hintStyle` — unchanged.
- Tabs (both the outer Settings-style tabs and the new inner preset segmented control): the existing `role="tab"`/underline-on-active pattern from `WorkspaceSettings.tsx`'s tablist — reused at two nesting levels, not two different tab systems.
- Buttons: `primaryButtonStyle` for primary actions (Save, Confirm & Flip, Initialize); transparent-bordered outline buttons (existing "Revoke"/"Cancel" visual family) for secondary/reset actions.
- Badges/pills: existing `permission_level` pill shape (rounded-full, xs font, bold), only the background/color pairs are new (success/warning/muted — all already-defined CSS variables, no new colors invented).
- Status/error/success banners: existing `role="alert"` red-bordered box and `settings-saved-ok` green text pattern.
- Confirm dialogs: existing `window.confirm()` for simple single-step confirmations (reset actions, rollback); existing `ConfirmDialog` component frame for the one genuinely multi-step confirmation (guarded flip), since that one needs a checkbox + live-refetched data a native `confirm()` can't show.

---

## 7. Explicit flag for user/main-chat confirmation before execution

Per the task's constraint, the following is a **proposal**, not a executed decision — `senior-developer` must not delete/rewrite the following until the user (via main_chat) confirms:

> **Dismantling plan for the current "governance" tab:**
> 1. `frontend/src/components/WorkspaceSettings/WorkflowsSection.tsx` — proposed for **full deletion**. It has exactly one consumer (`WorkspaceSettings.tsx`'s governance tab) and its two operations (raw-artifact-ID "initialize workflow" and free-text "transition state") are legacy pre-REQ-166 admin tooling that duplicates capability now covered by (a) the per-entity-form `WorkflowStatusEditor` for actual transitions, and (b) `/workflows/:entityType` for structural workflow editing. No other screen depends on it (verified: only referenced from `WorkspaceSettings.tsx` and its own test file).
> 2. `PermissionsSection` embedding inside the governance tab — **not deleted**, only **relocated verbatim** to render inside SCR-202's rebuilt tab, unchanged. REQ-182 explicitly protects this component/resource.
> 3. The `governance` tab id/label in `WorkspaceSettings.tsx` is renamed and its content replaced per SCR-202 above.
>
> **Action needed from the user before implementation starts:** confirm point 1 (deleting `WorkflowsSection.tsx` and its test coverage) is acceptable, since it is the only non-additive, irreversible change in this spec. Everything else in this document is additive (new route, new nav entry, new tab, new components) or a verbatim relocation.

---

## Output contract

```
STATUS: done
SCREENS: 6 (SCR-202 rebuilt, SCR-203/204/205/206 new/relocated, plus 1 unchanged reference screen: /workflows/:entityType)
DESIGN_SYSTEM: 0 new tokens/components at the primitive level — 5 composite components specified via reuse (DefaultStatusBadge+Reset, PresetSegmentedControl, Global/Workspace Permission Matrix Editor, Enforcement Mode Panel w/ guarded-flip dialog, Mismatch Review Table)
JOURNEYS: 4
SPEC_FILE: docs/ui/workflow-permissions-global-default-ui-spec.md
ARTIFACTS: [docs/ui/workflow-permissions-global-default-ui-spec.md]
ERRORS: none
FLAG_FOR_USER: WorkflowsSection.tsx deletion (see §7) requires explicit user confirmation before senior-developer executes; PermissionsSection is relocated unchanged, not deleted.
```
