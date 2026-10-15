/**
 * Issue #1257 — the personal level of the navigation tree configuration.
 *
 * Rendered in `UserProfileSettings`. Self-service: `ctx.user_id` is the whole
 * authorization boundary on the server, so this section takes no workspace
 * parameter and is available to every member regardless of role. Writes land in
 * `UserDisplayPreference.tree_display_fields`.
 */

import { TreeDisplayFieldsSection } from "../shared/TreeDisplayFields/TreeDisplayFieldsSection";

export function TreeDisplaySection(): JSX.Element {
  return (
    <TreeDisplayFieldsSection
      scope="user"
      titleKey="treeDisplay.user.title"
      hintKey="treeDisplay.user.hint"
      testId="user-tree-display"
    />
  );
}
