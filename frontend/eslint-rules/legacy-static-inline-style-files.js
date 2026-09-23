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
 *     equality (`toBe(408)`), so any net increase turns it red. The residual
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
 */
export const LEGACY_STATIC_INLINE_STYLE_FILES = [
  "src/components/AdminDialog/TriLabelOverviewDialog.tsx",
  "src/components/AdrEditors/AdrEditors.tsx",
  "src/components/ArchitectureDecompose/ArchitectureDecomposePanel.tsx",
  "src/components/ArchitectureEditors/ArchitectureLegend.tsx",
  "src/components/BaselinesView/BaselinesPanels.tsx",
  "src/components/DashboardViews/DashboardViews.tsx",
  "src/components/DashboardViews/WorkspaceCard.tsx",
  "src/components/DiagramView/DiagramCreateForm.tsx",
  "src/components/DiagramView/DiagramView.tsx",
  "src/components/Goals/GoalDetail.tsx",
  "src/components/IcdView/IcdDetailPane.tsx",
  "src/components/IcdView/SimilarIcdsPanel.tsx",
  "src/components/IssueEditors/IssueEditors.tsx",
  "src/components/NeedsEditors/NeedArtifactForm.tsx",
  "src/components/NeedsEditors/NeedList.tsx",
  "src/components/NeedsEditors/NeedsEditors.tsx",
  "src/components/PermissionMatrix/PermissionMatrixEditor.tsx",
  "src/components/RequirementEditors/GlossaryTooltip.tsx",
  "src/components/RequirementEditors/MarkdownPreview.tsx",
  "src/components/RequirementEditors/RequirementEditors.tsx",
  "src/components/RequirementEditors/RequirementList.tsx",
  "src/components/RequirementEditors/RequirementTreeNode.tsx",
  "src/components/RequirementEditors/SimilarRequirementsPanel.tsx",
  "src/components/RequirementEditors/TraceabilityPanel.tsx",
  "src/components/Reviews/ReviewHistoryPanel.tsx",
  "src/components/Reviews/SignatureDialog.tsx",
  "src/components/RiskEditors/RiskEditors.tsx",
  "src/components/SplitView/SplitView.tsx",
  "src/components/SystemSettings/EnforcementFlipDialog.tsx",
  "src/components/SystemSettings/EnforcementModePanel.tsx",
  "src/components/SystemSettings/PermissionDefaultsTab.tsx",
  "src/components/SystemSettings/SystemSettings.tsx",
  "src/components/SystemSettings/WorkspaceAdminSection.tsx",
  "src/components/TestCaseEditors/DeriveTestCasePanel.tsx",
  "src/components/TestCaseEditors/TestCaseEditors.tsx",
  "src/components/UserProfileSettings/ProfileSection.tsx",
  "src/components/UserProfileSettings/UserProfileSettings.tsx",
  "src/components/WorkflowEditor/PresetSegmentedControl.tsx",
  "src/components/WorkflowEditor/TransitionEdge.tsx",
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
