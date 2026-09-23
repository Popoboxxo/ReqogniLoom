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
 *     equality (`toBe(596)`), so any net increase turns it red. The residual
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
 */
export const LEGACY_STATIC_INLINE_STYLE_FILES = [
  "src/components/AdminDialog/SystemHealthDialog.tsx",
  "src/components/AdminDialog/TriLabelOverviewDialog.tsx",
  "src/components/AdrEditors/AdrEditors.tsx",
  "src/components/ArchitectureDecompose/ArchitectureDecomposePanel.tsx",
  "src/components/ArchitectureEditors/ArchitectureEditors.tsx",
  "src/components/ArchitectureEditors/ArchitectureLegend.tsx",
  "src/components/Audit/audit-dashboard.tsx",
  "src/components/BaselinesView/BaselinesPanels.tsx",
  "src/components/DashboardViews/DashboardViews.tsx",
  "src/components/DashboardViews/WorkspaceCard.tsx",
  "src/components/DiagramView/DiagramCreateForm.tsx",
  "src/components/DiagramView/DiagramDetailView.tsx",
  "src/components/DiagramView/DiagramView.tsx",
  "src/components/Goals/GoalDetail.tsx",
  "src/components/Goals/MainGoalPanel.tsx",
  "src/components/IcdView/IcdDetailPane.tsx",
  "src/components/IcdView/IcdView.tsx",
  "src/components/IcdView/SimilarIcdsPanel.tsx",
  "src/components/ImpactView/ImpactView.tsx",
  "src/components/IssueEditors/IssueEditors.tsx",
  "src/components/MetricsDashboard/MetricsDashboard.tsx",
  "src/components/NeedsEditors/NeedArtifactForm.tsx",
  "src/components/NeedsEditors/NeedList.tsx",
  "src/components/NeedsEditors/NeedsEditors.tsx",
  "src/components/PermissionMatrix/PermissionMatrixEditor.tsx",
  "src/components/RequirementEditors/GlossaryTooltip.tsx",
  "src/components/RequirementEditors/MarkdownPreview.tsx",
  "src/components/RequirementEditors/ReqTraceLinkPanel.tsx",
  "src/components/RequirementEditors/RequirementEditors.tsx",
  "src/components/RequirementEditors/RequirementList.tsx",
  "src/components/RequirementEditors/RequirementTreeNode.tsx",
  "src/components/RequirementEditors/SimilarRequirementsPanel.tsx",
  "src/components/RequirementEditors/TraceabilityPanel.tsx",
  "src/components/Reviews/ReviewHistoryPanel.tsx",
  "src/components/Reviews/ReviewsView.tsx",
  "src/components/Reviews/SignatureDialog.tsx",
  "src/components/RiskEditors/RiskEditors.tsx",
  "src/components/SplitView/SplitView.tsx",
  "src/components/SystemSettings/EnforcementFlipDialog.tsx",
  "src/components/SystemSettings/EnforcementModePanel.tsx",
  "src/components/SystemSettings/MismatchReviewTable.tsx",
  "src/components/SystemSettings/PermissionDefaultsTab.tsx",
  "src/components/SystemSettings/SystemSettings.tsx",
  "src/components/SystemSettings/WorkspaceAdminSection.tsx",
  "src/components/TestCaseEditors/DeriveTestCasePanel.tsx",
  "src/components/TestCaseEditors/TestCaseEditors.tsx",
  "src/components/TraceabilityView/TraceabilityView.tsx",
  "src/components/UserProfileSettings/ApiKeysSection.tsx",
  "src/components/UserProfileSettings/ProfileSection.tsx",
  "src/components/UserProfileSettings/UserProfileSettings.tsx",
  "src/components/WorkflowEditor/PresetSegmentedControl.tsx",
  "src/components/WorkflowEditor/TransitionEdge.tsx",
  "src/components/WorkflowStatusEditor/WorkflowStatusEditor.tsx",
  "src/components/WorkspaceSettings/DefaultStatusBadge.tsx",
  "src/components/canvas/CanvasEditor.tsx",
  "src/components/mermaid/MermaidEditor.tsx",
  "src/components/shared/CreateTraceLinkDialog/create-trace-link-dialog.tsx",
  "src/components/shared/CustomFieldsEditor.tsx",
  "src/components/shared/DeriveRequirementForm.tsx",
  "src/components/shared/ListToolbar.tsx",
  "src/components/shared/PageHeader.tsx",
  "src/components/shared/TraceLinkPanel.tsx",
  "src/components/shared/VersionBadge.tsx",
  "src/components/shared/WorkspaceTree/workspace-tree.tsx",
  "src/components/shared/tag-input.tsx",
  "src/components/shared/trace-link-display.tsx",
];
