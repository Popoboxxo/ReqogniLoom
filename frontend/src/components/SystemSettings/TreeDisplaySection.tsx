/**
 * Issue #1257 — the tenant-wide level of the navigation tree configuration.
 *
 * Rendered in `SystemSettings`'s "Darstellung" tab. The default every workspace
 * inherits unless it overrides it. Writes need the `admin` role; the service
 * re-asserts that on top of the view's ADMIN-tier API-key capability gate.
 */

import { TreeDisplayFieldsSection } from "../shared/TreeDisplayFields/TreeDisplayFieldsSection";

export function TreeDisplaySection(): JSX.Element {
  return (
    <TreeDisplayFieldsSection
      scope="global"
      titleKey="treeDisplay.global.title"
      hintKey="treeDisplay.global.hint"
      testId="global-tree-display"
    />
  );
}
