/**
 * REQ-176/REQ-177 (workspace) + REQ-178/REQ-179 (global default) — entry point
 * of the visual workflow state-machine editor.
 *
 * leaf_id: COMP-RF-001 (NavigationShell scope)
 *
 * P2.4: the page is a scope switch, nothing more. Each scope resolves its own
 * addressing (route slug vs. query parameters, preset canonicalisation,
 * invalid-entity notice) in its own container:
 *
 *   ``workspace`` → ``WorkspaceWorkflowEditorPage``  (/workflows/:entityType)
 *   ``global``    → ``GlobalWorkflowDefaultsPage``   (System Settings → Workflow
 *                                                     Defaults, SCR-205)
 *
 * Both render the same ``WorkflowEditorContent``, so the editor itself stays
 * singular.
 */

import "@xyflow/react/dist/style.css";

import { GlobalWorkflowDefaultsPage } from "./GlobalWorkflowDefaultsPage";
import { WorkspaceWorkflowEditorPage } from "./WorkspaceWorkflowEditorPage";

interface WorkflowEditorPageProps {
  /**
   * ``workspace`` (default) — edits the active workspace's definition, entity
   * type from the ``/workflows/:entityType`` route (unchanged, REQ-176/177).
   * ``global`` — edits the tenant-wide default per preset (System Settings →
   * Workflow Defaults, SCR-205); entity type and preset live in query params.
   */
  scope?: "workspace" | "global";
}

export function WorkflowEditorPage({
  scope = "workspace",
}: WorkflowEditorPageProps = {}): JSX.Element {
  return scope === "global" ? (
    <GlobalWorkflowDefaultsPage />
  ) : (
    <WorkspaceWorkflowEditorPage />
  );
}

export default WorkflowEditorPage;
