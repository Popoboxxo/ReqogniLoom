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
 *     equality (`toBe(163)`), so any net increase turns it red. The residual
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
 * `SplitView/SplitView.tsx` deliberately STAYS on this list: its divider
 * (`cursor: col-resize`) and its legacy left/right panels (the shared
 * `overscroll-behavior`/`scrollbar-gutter`/`overflow` scroll model) are pinned
 * by `toHaveStyle`/`getComputedStyle` assertions in
 * `SplitView.test.tsx`, `RequirementEditors.test.tsx` and
 * `ArchitectureEditors.test.tsx`. Because the vitest run does not process CSS
 * Modules, moving those inline declarations onto classes would break the
 * pinned assertions; rewriting the tests is out of scope for this batch, so
 * the file stays exempt and the migration is left for a follow-up.
 */
export const LEGACY_STATIC_INLINE_STYLE_FILES = [
  "src/components/AdminDialog/TriLabelOverviewDialog.tsx",
  "src/components/ArchitectureDecompose/ArchitectureDecomposePanel.tsx",
  "src/components/ArchitectureEditors/ArchitectureLegend.tsx",
  "src/components/BaselinesView/BaselinesPanels.tsx",
  "src/components/DashboardViews/DashboardViews.tsx",
  "src/components/DiagramView/DiagramCreateForm.tsx",
  "src/components/DiagramView/DiagramView.tsx",
  "src/components/Goals/GoalDetail.tsx",
  "src/components/IcdView/IcdDetailPane.tsx",
  "src/components/NeedsEditors/NeedArtifactForm.tsx",
  "src/components/NeedsEditors/NeedList.tsx",
  "src/components/SplitView/SplitView.tsx",
  "src/components/TestCaseEditors/DeriveTestCasePanel.tsx",
  "src/components/UserProfileSettings/ProfileSection.tsx",
  "src/components/WorkflowEditor/PresetSegmentedControl.tsx",
  "src/components/WorkspaceSettings/DefaultStatusBadge.tsx",
  "src/components/canvas/CanvasEditor.tsx",
  "src/components/mermaid/MermaidEditor.tsx",
  "src/components/shared/CustomFieldsEditor.tsx",
  "src/components/shared/DeriveRequirementForm.tsx",
  "src/components/shared/ListToolbar.tsx",
  "src/components/shared/PageHeader.tsx",
  "src/components/shared/VersionBadge.tsx",
  "src/components/shared/tag-input.tsx",
  "src/components/shared/trace-link-display.tsx",
];
