# Multi-Palette Theming — Phase 2 (Hex/Inline-Style Migration) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the remaining raw hex-color literals in `.tsx`/`.css` source
onto the existing `var(--color-*)` semantic tokens (adding a new semantic
token only when no existing one fits), lowering the frozen ratchet in
`frontend/src/test/ui-ratchet.test.ts` (`HEX_LITERAL_OCCURRENCE_BASELINE`/
`HEX_LITERAL_FILE_BASELINE` for `.tsx`, `HEX_LITERAL_CSS_OCCURRENCE_BASELINE`/
`HEX_LITERAL_CSS_FILE_BASELINE` for CSS) checkpoint by checkpoint, and
shrinking `frontend/eslint-rules/legacy-inline-style-hex-files.js` as files
become clean.

**Architecture:** Bounded, mechanical migration mirroring this codebase's
own established precedent (see `ui-ratchet.test.ts`'s comment history: Task
1.6, 2.1, 2.2, 8.1 all did this exact kind of migration already). No new
design decisions — every replacement either reuses an existing
`--color-*` token from `frontend/src/styles/tokens.css`, or (if genuinely
no semantic token fits the use) adds one new `--color-*` entry that
references an existing `--palette-*` primitive (never a fresh raw hex
value). **`tokens.css`'s own ~40 primitive-layer (`--palette-*`) hex
values are NOT migration targets** — they are the intentional, permanent
bottom of the two-layer architecture (§2 of the design spec); the ratchet
counts them, but they are excluded from every checkpoint below.

**Spec:** `docs/superpowers/specs/2026-08-20-multi-palette-theming-design.md` §4.3

**Current, precisely-measured scope (2026-08-21, via a script mirroring
`ui-ratchet.test.ts`'s own `countNonCommentOccurrences`/file-collection
logic exactly — not a naive grep):**

- `.tsx`: 90 occurrences / 27 files (matches the current frozen baseline).
- `.css` (excluding `tokens.css`'s primitive layer): 14 occurrences / 4
  files (`WorkflowEditor.module.css` 5, `CanvasEditor.module.css` 4,
  `global.css` 4, `MermaidEditor.module.css` 1).
- `LEGACY_INLINE_STYLE_HEX_FILES` (`frontend/eslint-rules/legacy-inline-style-hex-files.js`): 21 files.

## Global Constraints

- Never touch `frontend/src/styles/tokens.css`'s `:root` primitive block
  (`--palette-*` declarations) — those hex values are correct and
  permanent. The `:root[data-theme="light"]` semantic block (if it exists
  in that file) IS in scope if it has raw hex instead of `var(--palette-*)`
  references — check before touching.
- Every replacement must reference an EXISTING `--color-*` token if one
  semantically fits (same role: text, background, border, status color,
  etc.). Only add a new `--color-*` token when nothing fits — and the new
  token's value must be `var(--palette-*)`, never a fresh raw hex literal.
- After each checkpoint: lower `HEX_LITERAL_OCCURRENCE_BASELINE`/
  `HEX_LITERAL_FILE_BASELINE` (or the CSS pair) in
  `frontend/src/test/ui-ratchet.test.ts` to the new measured value, with a
  one-paragraph comment in that file's existing history-comment style
  (matches the file's own established convention — see the many prior
  entries there for the exact tone/format).
- If a checkpoint fully migrates a file that's listed in
  `LEGACY_INLINE_STYLE_HEX_FILES`, delete that file's entry in the same
  commit (per that file's own maintenance rule).
- Commit after each checkpoint (standing instruction: every intermediate
  state gets saved).
- No behavior/visual change beyond the color source — this is a pure
  refactor. If a file's existing color doesn't precisely match any
  available token, prefer the CLOSEST existing token over inventing a new
  primitive value; flag anything genuinely ambiguous in the task report
  rather than guessing.

---

### Checkpoint 1: `shared/` — highest leverage (used everywhere)

**Files (8 occurrences, 3 files):**
- `frontend/src/components/shared/WorkspaceTree/workspace-tree.tsx` (5)
- `frontend/src/components/shared/TraceLinkPanel.tsx` (2)
- `frontend/src/components/shared/CreateTraceLinkDialog/create-trace-link-dialog.tsx` (1)

- [ ] Read each file, identify every raw hex literal and its CSS role (text color, background, border, status indicator, etc.)
- [ ] For each, find the matching `--color-*` token in `tokens.css` (search by role/value) and replace the literal with `var(--color-*)`
- [ ] If a hex value has no matching token, add one to `tokens.css`'s semantic block, referencing the nearest existing `--palette-*` primitive (not a new raw value)
- [ ] Run `cd frontend && npx vitest run` — confirm no regressions (existing tests for these 3 files plus anything that imports them)
- [ ] Update `HEX_LITERAL_OCCURRENCE_BASELINE`/`HEX_LITERAL_FILE_BASELINE` in `ui-ratchet.test.ts` to the new measured totals, with a history comment
- [ ] Run `cd frontend && npx vitest run src/test/ui-ratchet.test.ts` — confirm the ratchet test passes at the new, lower baseline
- [ ] Run `cd frontend && npx eslint src` — confirm no new violations
- [ ] Commit: `refactor: migrate shared/ hex colors to design tokens (theming phase 2, checkpoint 1)`

---

### Checkpoint 2: Diagram/canvas editors

**Files (22 occurrences, 3 files):**
- `frontend/src/components/canvas/CanvasEditor.tsx` (15)
- `frontend/src/components/DiagramGraphEditor/GraphEdge.tsx` (5)
- `frontend/src/components/WorkflowEditor/TransitionEdge.tsx` (2)

Plus the matching CSS Modules if they also have raw hex (check
`frontend/src/styles/components/CanvasEditor.module.css` — 4 occurrences —
and `frontend/src/components/WorkflowEditor/WorkflowEditor.module.css` — 5
occurrences — while working in this area, since they style the same
components).

Same method as Checkpoint 1: read, find/add matching token, replace,
verify, lower baseline, commit.

- [ ] Migrate `CanvasEditor.tsx` + `CanvasEditor.module.css`
- [ ] Migrate `GraphEdge.tsx`
- [ ] Migrate `TransitionEdge.tsx` + `WorkflowEditor.module.css`
- [ ] Run `cd frontend && npx vitest run` — confirm no regressions
- [ ] Update ratchet baselines (both `.tsx` and CSS pairs) with history comments
- [ ] Run `cd frontend && npx vitest run src/test/ui-ratchet.test.ts` — confirm passes
- [ ] Run `cd frontend && npx eslint src` — confirm no new violations
- [ ] Commit: `refactor: migrate diagram/canvas editor hex colors to design tokens (theming phase 2, checkpoint 2)`

---

### Checkpoint 3: Requirement/architecture/traceability/test editors

**Files (26 occurrences, 6 files):**
- `frontend/src/components/ArtifactDiff/ArtifactDiff.tsx` (12)
- `frontend/src/components/TestRuns/TestRunDetailEditor.tsx` (3)
- `frontend/src/components/RequirementEditors/RequirementList.tsx` (4)
- `frontend/src/components/RequirementEditors/ReqTraceLinkPanel.tsx` (2)
- `frontend/src/components/ArchitectureEditors/ArchitectureEditors.tsx` (2)
- `frontend/src/components/TraceabilityView/TraceLinksForm.tsx` (2)
- `frontend/src/components/TraceabilityView/TraceabilityView.tsx` (2)
- `frontend/src/components/PermissionMatrix/PermissionMatrixEditor.tsx` (1)

`ArtifactDiff.tsx` is the file this project's own investigation earlier
already sampled (`STATUS_STYLES` constant with `added`/`removed`/
`modified`/`unchanged` hex colors) — migrate it onto the existing
`--color-success`/`--color-danger`/`--color-warning`-family tokens (or the
closest match; a diff view's "added" color is conventionally a
success-family green, "removed" a danger-family red, "modified" a
warning-family amber — verify against what's already in `tokens.css`
rather than assuming).

Same method as Checkpoint 1.

- [ ] Migrate all 8 files
- [ ] Run `cd frontend && npx vitest run` — confirm no regressions
- [ ] Update ratchet baselines with history comments
- [ ] Run `cd frontend && npx vitest run src/test/ui-ratchet.test.ts` — confirm passes
- [ ] Run `cd frontend && npx eslint src` — confirm no new violations
- [ ] Commit: `refactor: migrate requirement/architecture/traceability editor hex colors to design tokens (theming phase 2, checkpoint 3)`

---

### Checkpoint 4: Settings/admin surfaces

**Files (remaining ~34 occurrences across ~13 files):**
- `frontend/src/components/SystemSettings/WorkspaceAdminSection.tsx` (6)
- `frontend/src/components/SystemSettings/EnforcementModePanel.tsx` (5)
- `frontend/src/components/AdminDialog/AttributeVisibilityAdmin.tsx` (3)
- `frontend/src/components/AdminDialog/SystemHealthDialog.tsx` (3)
- `frontend/src/components/UserProfileSettings/ApiKeysSection.tsx` (2)
- `frontend/src/components/SystemSettings/PermissionDefaultsTab.tsx` (1)
- `frontend/src/components/WorkspaceSettings/BackupRestoreSection.tsx` (1)
- `frontend/src/components/WorkspaceSettings/WorkspaceSettings.tsx` (1)
- `frontend/src/components/NavigationShell/CreateWorkspaceModal.tsx` (1)
- `frontend/src/components/NavigationShell/ErrorBoundary.tsx` (1)
- `frontend/src/components/NavigationShell/SidebarNavigation.tsx` (1)
- `frontend/src/components/MetricsDashboard/MetricsDashboard.tsx` (6)
- `frontend/src/components/BaselinesView/BaselinesView.tsx` (1)

Plus remaining CSS: `frontend/src/styles/global.css` (4),
`frontend/src/styles/components/MermaidEditor.module.css` (1).

Re-measure the exact file/occurrence list at the START of this checkpoint
(re-run the same counting method Checkpoints 1-3 used) rather than trusting
this list verbatim — earlier checkpoints may shift what's left, and this
was the last, least-precisely-scoped group when this plan was written.

Same method as Checkpoint 1.

- [ ] Re-measure current hex occurrences project-wide, confirm/adjust this checkpoint's file list
- [ ] Migrate all remaining files
- [ ] Run `cd frontend && npx vitest run` — confirm no regressions
- [ ] Update ratchet baselines with history comments — this checkpoint should bring both `.tsx` and CSS (non-`tokens.css`) counts to (or very near) 0
- [ ] Run `cd frontend && npx vitest run src/test/ui-ratchet.test.ts` — confirm passes
- [ ] Run `cd frontend && npx eslint src` — confirm no new violations
- [ ] Confirm `LEGACY_INLINE_STYLE_HEX_FILES` is now empty (or document exactly what's left and why)
- [ ] Commit: `refactor: migrate settings/admin/dashboard hex colors to design tokens (theming phase 2, checkpoint 4)`

---

### Checkpoint 5: Close-out

- [ ] Run the full frontend suite once more (`cd frontend && npx vitest run`) and `tsc --noEmit`
- [ ] Update `docs/superpowers/specs/2026-08-20-multi-palette-theming-design.md`'s Phase 2 row
- [ ] Push, open a PR against `main` summarizing the 4 checkpoints and final ratchet numbers
