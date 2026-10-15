/**
 * Issue #1257 — the workspace level of the navigation tree configuration.
 *
 * Rendered in `WorkspaceSettings`'s "Darstellung" tab. The override applies to
 * every member of the workspace and therefore needs write authority, which the
 * server re-asserts (`TreeDisplayConfigService.set_config(scope="workspace")`).
 */

import { TreeDisplayFieldsSection } from "../shared/TreeDisplayFields/TreeDisplayFieldsSection";

export interface TreeDisplaySectionProps {
  /** The workspace whose override this section edits. */
  workspaceId: string;
}

export function TreeDisplaySection({
  workspaceId,
}: TreeDisplaySectionProps): JSX.Element {
  return (
    <TreeDisplayFieldsSection
      scope="workspace"
      workspaceId={workspaceId}
      titleKey="treeDisplay.workspace.title"
      hintKey="treeDisplay.workspace.hint"
      testId="workspace-tree-display"
    />
  );
}
