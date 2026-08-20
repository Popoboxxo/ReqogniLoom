/**
 * Frozen exemption list for `local/no-hex-color-in-inline-style` (Task 7.3).
 *
 * The rule runs at `error` level across the whole of `src/**` — EXCEPT for the
 * files listed here, which already contained hex literals in inline styles
 * when the rule was introduced. Turning the rule on project-wide without this
 * list would have broken the build on 43 pre-existing violations in 21 files,
 * which are being reduced gradually (not eliminated in one go) — the same
 * philosophy as the numeric ratchet in `src/test/ui-ratchet.test.ts`.
 *
 * Consequences of this scoping (deliberate):
 *   - Any NEW file is covered by the rule immediately, with no opt-in step.
 *   - Any file NOT on this list that later grows a violation fails the build.
 *   - A file ON this list is fully exempt, so an *additional* hex literal in
 *     one of them is not caught by ESLint. That gap is covered by the
 *     `HEX_LITERAL_OCCURRENCE_BASELINE` / `HEX_LITERAL_FILE_BASELINE` ratchet
 *     in `src/test/ui-ratchet.test.ts`, which fails as soon as the total
 *     count rises anywhere.
 *
 * Maintenance: this list is a ratchet too. When a file's inline hex literals
 * are migrated onto design tokens, DELETE its entry here in the same PR — the
 * rule then guards it permanently. Never ADD an entry to make a build pass;
 * fix the color instead. Entries are `src`-relative POSIX paths as used by
 * ESLint flat-config `files` globs.
 *
 * Baseline measured 2026-08-05 on branch feat/ui-konzept-phase7-enforcement-gates
 * via `npx eslint src` with the rule temporarily unscoped: 43 violations / 21 files.
 */
export const LEGACY_INLINE_STYLE_HEX_FILES = [
  "src/components/AdminDialog/AttributeVisibilityAdmin.tsx",
  "src/components/ArchitectureEditors/ArchitectureEditors.tsx",
  "src/components/ArtifactDiff/ArtifactDiff.tsx",
  "src/components/BaselinesView/BaselinesView.tsx",
  "src/components/ImpactView/ImpactView.tsx",
  "src/components/MetricsDashboard/MetricsDashboard.tsx",
  "src/components/NavigationShell/CreateWorkspaceModal.tsx",
  "src/components/NavigationShell/ErrorBoundary.tsx",
  "src/components/PermissionMatrix/PermissionMatrixEditor.tsx",
  "src/components/RequirementEditors/ReqTraceLinkPanel.tsx",
  "src/components/Reviews/ReviewsView.tsx",
  "src/components/SystemSettings/EnforcementModePanel.tsx",
  "src/components/SystemSettings/PermissionDefaultsTab.tsx",
  "src/components/SystemSettings/WorkspaceAdminSection.tsx",
  "src/components/TraceabilityView/TraceLinksForm.tsx",
  "src/components/TraceabilityView/TraceabilityView.tsx",
  "src/components/UserProfileSettings/ApiKeysSection.tsx",
  "src/components/WorkspaceSettings/BackupRestoreSection.tsx",
  "src/components/WorkspaceSettings/WorkspaceSettings.tsx",
  // #568 Phase 2 checkpoint 1: TraceLinkPanel.tsx and
  // shared/CreateTraceLinkDialog/create-trace-link-dialog.tsx entries
  // removed here — both fully migrated onto design tokens, no remaining
  // hex literals. The rule now guards them permanently.
];
