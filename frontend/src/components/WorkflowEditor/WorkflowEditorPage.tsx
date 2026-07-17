/**
 * REQ-176 — WorkflowEditorPage: visual workflow state-machine editor (Phase 1).
 *
 * leaf_id: COMP-RF-001 (NavigationShell scope)
 * req_id:  REQ-176 (Visual Workflow Editor — read-only)
 *
 * Top-level page composing the header, the 3-panel body (entity selector ·
 * React Flow canvas · inspector) and the status bar. Read-only: it renders the
 * complete state machine for the selected entity type from
 * ``GET /api/v1/workflows/definition/`` and lets the user inspect states and
 * transitions. Edit mode is Phase 2 and out of scope here.
 */

import "@xyflow/react/dist/style.css";

import { useCallback, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useWorkspace } from "../../context/WorkspaceContext";
import type { WorkflowEntityType } from "../../api/workflows";
import {
  DEFAULT_ENTITY_TYPE,
  entityTypeFromSlug,
  type Selection,
} from "./constants";
import { toMermaid } from "./mermaid-export";
import { useWorkflowData } from "./useWorkflowData";
import { WorkflowEditorHeader } from "./WorkflowEditorHeader";
import { WorkflowEditorLayout } from "./WorkflowEditorLayout";
import { EntityTypeSelector } from "./EntityTypeSelector";
import { WorkflowCanvas } from "./WorkflowCanvas";
import { InspectorPanel } from "./InspectorPanel";
import { StatusBar } from "./StatusBar";
import styles from "./WorkflowEditor.module.css";

export function WorkflowEditorPage(): JSX.Element {
  const { entityType: entitySlug } = useParams<{ entityType: string }>();
  const navigate = useNavigate();
  const { activeWorkspace } = useWorkspace();

  const entityType: WorkflowEntityType =
    entityTypeFromSlug(entitySlug) ?? DEFAULT_ENTITY_TYPE;

  const [selection, setSelection] = useState<Selection>({ kind: "none" });
  const [toast, setToast] = useState<string | null>(null);

  const { graph, isLoading, error } = useWorkflowData(entityType);

  const handleSelectEntity = useCallback(
    (type: WorkflowEntityType): void => {
      setSelection({ kind: "none" });
      navigate(`/workflows/${type}`);
    },
    [navigate]
  );

  const handleCopyMermaid = useCallback((): void => {
    if (!graph) return;
    const text = toMermaid(graph);
    void navigator.clipboard
      ?.writeText(text)
      .then(() => setToast("Copied Mermaid diagram to clipboard"))
      .catch(() => setToast("Could not access clipboard"));
    window.setTimeout(() => setToast(null), 2000);
  }, [graph]);

  const preset = graph?.preset ?? activeWorkspace?.preset ?? "standard";

  return (
    <div className={styles.page} data-testid="workflow-editor-page">
      <WorkflowEditorHeader
        preset={preset}
        onCopyMermaid={handleCopyMermaid}
        canExport={!!graph && graph.states.length > 0}
      />

      <WorkflowEditorLayout
        selector={
          <EntityTypeSelector selected={entityType} onSelect={handleSelectEntity} />
        }
        canvas={
          <WorkflowCanvas
            graph={graph}
            isLoading={isLoading}
            error={error}
            selection={selection}
            onSelect={setSelection}
            onCopyMermaid={handleCopyMermaid}
          />
        }
        inspector={
          <InspectorPanel
            graph={graph}
            selection={selection}
            onSelect={setSelection}
          />
        }
      />

      <StatusBar graph={graph} />

      {toast && (
        <div className={styles.statusBar} role="status" data-testid="workflow-toast">
          {toast}
        </div>
      )}
    </div>
  );
}

export default WorkflowEditorPage;
