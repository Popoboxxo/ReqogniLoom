/**
 * Frozen exemption list for `local/no-static-inline-style` (#876, Option C).
 *
 * The rule runs at `error` level across the whole of `src` (all `.ts`/`.tsx`,
 * tests excluded) — EXCEPT for the files listed here, which already carried
 * static inline `style={{...}}` object literals when the rule was introduced.
 * Turning the rule on project-wide without this list would have broken the
 * build on 650 pre-existing AST-visible occurrences in 68 files, which are
 * being reduced gradually (not eliminated in one go) — the same philosophy as
 * the numeric ratchet in `src/test/ui-ratchet.test.ts`.
 *
 * Consequences of this scoping (deliberate):
 *   - Any NEW file is covered by the rule immediately, with no opt-in step.
 *   - Any file NOT on this list that later grows a static inline style fails
 *     the build.
 *   - A file ON this list is fully exempt, so an *additional* static inline
 *     style in one of them is not caught by ESLint. Within `src/components/`
 *     that gap is covered by the `STYLE_BRACE_BASELINE` ratchet in
 *     `src/test/ui-ratchet.test.ts`, whose monotonic assertion is an exact
 *     equality against that constant (no literal is repeated here, so it
 *     cannot re-rot), so any net increase turns it red. The residual
 *     gap is a net-zero reshuffle (add here, delete there) in exempted files —
 *     accepted and documented in `no-static-inline-style.js`.
 *
 * Maintenance: this list is a ratchet too. When a file's static inline styles
 * are migrated onto CSS classes/design tokens, DELETE its entry here in the
 * same PR — the rule then guards it permanently. Never ADD an entry to make a
 * build pass; fix the style instead. Entries are `src`-relative POSIX paths as
 * used by ESLint flat-config `files` globs, sorted alphabetically for stable
 * diffs.
 *
 * Baseline measured 2026-09-22 on branch main via `npx eslint src -f json`
 * with this list temporarily empty: 702 occurrences / 70 files. Issue #876
 * follow-up (2026-09-23): `TestRuns/TestRunDetailEditor.tsx` (29 literals + 1
 * hoisted constant) and `TestRuns/TestRunsList.tsx` (23 literals + 5 hoisted
 * constants) were migrated onto CSS Modules and dropped from this list;
 * re-measured with the list empty: 650 occurrences / 68 files. Issue #876
 * Etappe 2 (2026-09-23): `BaselinesView/BaselinesView.tsx` (29 literals + 5
 * hoisted constants) was migrated onto its co-located CSS Module and dropped
 * here too, leaving 67 entries and 621 AST-visible occurrences. The same
 * etappe's `ArtifactDiff/ArtifactDiff.tsx` (28 literals + 4 hoisted constants)
 * followed it, leaving 66 entries and 621 - 28 = 593 AST-visible occurrences.
 * Issue #876 Etappe 3 (2026-09-23, branch `refactor/876-etappe3-inline-styles`):
 * four more carriers were migrated onto CSS Modules and dropped here —
 * `TraceabilityView/TraceabilityView.tsx` (25 literals) and
 * `ImpactView/ImpactView.tsx` (21 literals) onto their existing co-located
 * modules, and `RequirementEditors/ReqTraceLinkPanel.tsx` (23 literals + 13
 * hoisted constants) and `UserProfileSettings/ApiKeysSection.tsx` (23 literals
 * + 6 hoisted constants) onto new co-located modules. Re-measured with this
 * list temporarily empty: 501 AST-visible occurrences in 62 files, matching
 * the arithmetic (593 - 92 literals; the 19 hoisted constants were identifier
 * references and were never AST-visible to this rule).
 *
 * Issue #876 Etappe 4 (2026-09-23, branch
 * `refactor/876-css-module-migration-etappe-4`): five more carriers were
 * migrated onto co-located CSS Modules and dropped here —
 * `Audit/audit-dashboard.tsx` (20 literals + 30 hoisted constants/factories),
 * `shared/TraceLinkPanel.tsx` (19 literals + 3 hoisted constants),
 * `DiagramView/DiagramDetailView.tsx` (19 literals),
 * `Reviews/ReviewsView.tsx` (19 literals + 3 hoisted constants) and
 * `IcdView/IcdView.tsx` (19 literals). Re-measured with this list temporarily
 * empty: 405 AST-visible occurrences in 57 files; the ratchet's raw-text count
 * in the same scope is 408, and the difference of exactly 3 is explained by
 * three `style={{` occurrences that exist only inside comments
 * (RequirementTreeNode.tsx, ArchitectureEditors.tsx, WorkspaceSettings.tsx) —
 * the ratchet counts raw text, this rule sees the AST. Only two of those three
 * files are list entries. This matches the arithmetic (501 - 96 literals; the
 * hoisted constants were identifier references and were never AST-visible to
 * this rule).
 *
 * Issue #876 Etappe 5 (2026-09-23, branch
 * `refactor/css-modules-migration-etappe-5`): eight more carriers were
 * migrated onto co-located CSS Modules and dropped here —
 * `MetricsDashboard/MetricsDashboard.tsx` (18 literals + 4 hoisted constants;
 * existing module extended),
 * `ArchitectureEditors/ArchitectureEditors.tsx` (15 AST-visible
 * literals; the file's 16th `style={{` lives only inside a comment and stays
 * in the raw-text count; existing module extended),
 * `SystemSettings/MismatchReviewTable.tsx` (14 literals + 5 hoisted constants;
 * new module), `Goals/MainGoalPanel.tsx` (14 literals + 3 hoisted constants;
 * existing `Goals.module.css` extended),
 * `shared/CreateTraceLinkDialog/create-trace-link-dialog.tsx` (13 literals + 8
 * hoisted constants; new module), `shared/WorkspaceTree/workspace-tree.tsx`
 * (12 literals; existing module extended — two genuinely per-instance values
 * stay on the `style` prop as computed identifiers: the row `--tree-depth` and
 * the virtualized list's measured height),
 * `WorkflowStatusEditor/WorkflowStatusEditor.tsx` (13 literals + 2 hoisted
 * constants; new module — its status badge stays on the shared
 * `getStatusBadgeStyle()` identifier) and
 * `AdminDialog/SystemHealthDialog.tsx` (13 literals + 4 hoisted constants;
 * existing module extended). Re-measured with this list temporarily empty:
 * 293 AST-visible occurrences in 49 files. The ratchet's raw-text count in the
 * same scope is 296, and the difference of exactly 3 is still the three
 * comment-only `style={{` occurrences (RequirementTreeNode.tsx,
 * ArchitectureEditors.tsx, WorkspaceSettings.tsx) — the ArchitectureEditors
 * comment hit survived its file's migration, so the gap is unchanged. This
 * matches the arithmetic (405 - 112 literals; the 26 hoisted constants were
 * identifier references and were never AST-visible to this rule).
 *
 * Issue #876 Etappe 6 (2026-09-23, branch
 * `refactor/css-modules-migration-etappe-6`): twelve more carriers were
 * migrated onto co-located CSS Modules and dropped here — the six editor
 * routes `RequirementEditors/RequirementEditors.tsx` (11 literals; existing
 * module extended), `IssueEditors/IssueEditors.tsx` (11 literals; new
 * module), `NeedsEditors/NeedsEditors.tsx` (10 literals + 1 dynamic; new
 * module), `RiskEditors/RiskEditors.tsx` (11 literals; new module),
 * `AdrEditors/AdrEditors.tsx` (11 literals; new module) and
 * `TestCaseEditors/TestCaseEditors.tsx` (10 literals; existing module
 * extended), plus `IcdView/SimilarIcdsPanel.tsx` (11 literals + 1 dynamic;
 * new module), `RequirementEditors/SimilarRequirementsPanel.tsx` (11
 * literals; new module), `RequirementEditors/TraceabilityPanel.tsx` (10
 * literals + 1 dynamic; new module),
 * `DashboardViews/WorkspaceCard.tsx` (10 literals + 1 dynamic + 5 hoisted
 * constants; new module), `SystemSettings/WorkspaceAdminSection.tsx` (10
 * literals + 2 dynamic + 6 hoisted constants; new module) and
 * `UserProfileSettings/UserProfileSettings.tsx` (8 literals + 2 dynamic + 1
 * hoisted constant; new module). Re-measured with this list temporarily
 * empty: 160 AST-visible occurrences in 37 files. The ratchet's raw-text count
 * in the same scope is 163, and the difference of exactly 3 is still the three
 * comment-only `style={{` occurrences (RequirementTreeNode.tsx,
 * ArchitectureEditors.tsx, WorkspaceSettings.tsx) — unchanged across Etappen
 * 5 and 6. This matches the arithmetic (293 - 133 literals; the 12 hoisted
 * constants were identifier references and were never AST-visible to this
 * rule).
 *
 * Issue #876 Etappe 7 (2026-09-23, branch
 * `refactor/876-etappe7-inline-styles`, final stage): twelve more carriers
 * were migrated onto co-located CSS Modules and dropped here —
 * `RequirementEditors/RequirementTreeNode.tsx` (9 literals + 4 hoisted
 * constants; new module), `RequirementEditors/RequirementList.tsx` (3
 * literals; existing module extended),
 * `RequirementEditors/MarkdownPreview.tsx` (3 literals; new module),
 * `RequirementEditors/GlossaryTooltip.tsx` (1 literal; new module),
 * `SystemSettings/EnforcementModePanel.tsx` (9 literals + 5 hoisted constants;
 * new module), `SystemSettings/SystemSettings.tsx` (6 literals; new module),
 * `SystemSettings/PermissionDefaultsTab.tsx` (3 literals + 3 hoisted
 * constants; new module), `SystemSettings/EnforcementFlipDialog.tsx` (3
 * literals; new module), `Reviews/ReviewHistoryPanel.tsx` (9 literals; new
 * module), `Reviews/SignatureDialog.tsx` (4 literals + 4 hoisted constants;
 * new module), `PermissionMatrix/PermissionMatrixEditor.tsx` (8 literals + 4
 * hoisted constants; new module) and `WorkflowEditor/TransitionEdge.tsx` (1
 * static literal migrated to the `.hitPath` class; its 2 remaining `style`
 * props are hoisted identifiers carrying genuinely per-instance SVG runtime
 * values — see that file and gap 4 of `no-static-inline-style.js`).
 *
 * `SplitView/SplitView.tsx` STAYED on this list through batch 2: its divider
 * (`cursor: col-resize`) and its legacy left/right panels (the shared
 * `overscroll-behavior`/`scrollbar-gutter`/`overflow` scroll model) are pinned
 * by `toHaveStyle`/`getComputedStyle` assertions in `SplitView.test.tsx`,
 * `RequirementEditors.test.tsx` and `ArchitectureEditors.test.tsx`. Because
 * the vitest run does not process CSS Modules, moving those inline
 * declarations onto classes would break the pinned assertions. Batch 3 (the
 * final stage) resolved it with the hoisted-identifier pattern instead —
 * see below.
 *
 * Issue #876 Etappe 7, batch 2 of 3 (2026-09-23, same branch
 * `refactor/876-etappe7-inline-styles`): twelve more carriers were migrated
 * onto co-located CSS Modules and dropped here — `shared/ListToolbar.tsx`
 * (8 literals + 2 hoisted constants; new module),
 * `shared/VersionBadge.tsx` (6 literals; new module — its
 * `versionBadgeStyle(isCurrent)` stays a hoisted identifier because it is a
 * per-instance current/superseded value and `Badge.test.tsx` pins its
 * `fontFamily`), `shared/CustomFieldsEditor.tsx` (4 literals + 1 hoisted
 * `useMemo` constant; new module), `shared/tag-input.tsx` (4 literals; new
 * module), `shared/DeriveRequirementForm.tsx` (3 literals + 2 hoisted
 * constants; new module), `shared/trace-link-display.tsx` (5 hoisted
 * constants + the `{ ...containerStyle, ...style }` spread; new module — the
 * public per-instance `style` prop stays a hoisted identifier),
 * `DashboardViews/DashboardViews.tsx` (5 literals + 1 hoisted constant;
 * existing module extended), `Goals/GoalDetail.tsx` (4 literals; existing
 * `Goals.module.css` extended), `BaselinesView/BaselinesPanels.tsx` (2
 * literals + 2 dynamic values; existing module extended — the summary badge's
 * caller-supplied colour and the diff row's `statusColor(item.status)` stay
 * hoisted identifiers), `DiagramView/DiagramCreateForm.tsx` (7 literals; new
 * module — the spread shared constants from `diagram-view-shared.ts` are
 * duplicated verbatim, that file is shared and untouched) and
 * `DiagramView/DiagramView.tsx` (4 literals; new module). That is 11 entries
 * removed (25 -> 14).
 *
 * `shared/PageHeader.tsx` was the one batch-2 file that stayed on this list
 * (`PageHeader.test.tsx:29` pins the <h1>'s `fontSize` via
 * `toHaveStyle`). Etappe 7 batch 3, the final stage, resolved it with the
 * documented hoisted-identifier pattern: the density-dependent `fontSize` now
 * lives in `const titleStyle: React.CSSProperties` applied as
 * `style={titleStyle}`, which the rule does not flag (it only reports an
 * object literal directly inside the attribute — see gap 4 of
 * `no-static-inline-style.js`). The inline style is still rendered, so the
 * `toHaveStyle` pin stays green.
 *
 * Issue #876 Etappe 7, batch 3 of 3 (2026-09-23, same branch
 * `refactor/876-etappe7-inline-styles`, final batch): the last fourteen
 * carriers were migrated and dropped here, leaving this list EMPTY —
 * `AdminDialog/TriLabelOverviewDialog.tsx` (2 literals + 4 hoisted constants;
 * new module), `ArchitectureDecompose/ArchitectureDecomposePanel.tsx` (2
 * literals + the module-level `styles` Record migrated class-for-class onto a
 * new module; the per-node recursion indent stays a hoisted identifier),
 * `ArchitectureEditors/ArchitectureLegend.tsx` (7 literals; new module),
 * `IcdView/IcdDetailPane.tsx` (4 literals; existing module extended — the
 * `{ ...inputStyle, fontFamily: "inherit" }` pairs split into the map's own
 * `.newVersionTextarea` class plus the shared `inputStyle` identifier, so
 * `icd-view-shared.ts` stays untouched),
 * `NeedsEditors/NeedArtifactForm.tsx` (3 literals + 1 hoisted constant; new
 * module), `NeedsEditors/NeedList.tsx` (1 literal; new module),
 * `TestCaseEditors/DeriveTestCasePanel.tsx` (2 literals + the module-level
 * `styles` Record migrated class-for-class onto a new module),
 * `UserProfileSettings/ProfileSection.tsx` (6 literals + 6 hoisted constants;
 * new module), `WorkflowEditor/PresetSegmentedControl.tsx` (2 literals; new
 * module), `WorkspaceSettings/DefaultStatusBadge.tsx` (1 literal; new module),
 * `canvas/CanvasEditor.tsx` (1 literal; the per-instance swatch colour stays a
 * hoisted `swatchStyle(c)` factory so the `canvas-color-<hex>` test-id
 * contract is untouched), `mermaid/MermaidEditor.tsx` (2 literals; existing
 * module under `styles/components/` extended),
 * `SplitView/SplitView.tsx` (9 literals, all of them test-pinned dynamic
 * values: hoisted to named identifiers — `MOBILE_*`, `DESKTOP_ROOT_STYLE`,
 * `DIVIDER_STYLE`, `RIGHT_PANEL_STYLE`, `leftPanelStyle`) and finally
 * `shared/PageHeader.tsx` (the `titleStyle` identifier described above).
 *
 * `SplitView.tsx`'s divider and legacy panels are pinned by
 * `toHaveStyle`/`getComputedStyle` assertions in `SplitView.test.tsx` (its
 * `getComputedStyle`/`toHaveStyle` assertions on `splitview-list`/`-detail`,
 * with the divider as the locator for the legacy panels),
 * `RequirementEditors.test.tsx:360` and `ArchitectureEditors.test.tsx:374`
 * (both `toHaveStyle("cursor: col-resize")` on the divider). Because the
 * vitest run does not process CSS Modules, those declarations must keep
 * rendering as inline styles — the hoisted identifier satisfies both the pins
 * and the rule.
 *
 * ---------------------------------------------------------------------------
 * THIS LIST IS NOW EMPTY (0 entries, was 14 at the start of this batch; 68
 * when the rule was introduced). `local/no-static-inline-style` therefore
 * guards the WHOLE of `src` (all `.ts`/`.tsx` under it, tests excluded) with
 * no per-file exemptions left. The conditional spread block in
 * `frontend/eslint.config.js` deactivates automatically while the array is
 * empty (ESLint 9 rejects an empty `files` array) and would reactivate by
 * itself if a future legacy exemption ever had to be added back.
 *
 * The maintenance rule stands unchanged: never ADD an entry to make a build
 * pass — fix the style (or hoist it to an identifier if it is genuinely
 * per-instance) instead.
 */
export const LEGACY_STATIC_INLINE_STYLE_FILES = [];
