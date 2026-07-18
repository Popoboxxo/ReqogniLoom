/**
 * REQ-176/REQ-177 — WorkflowEditorPage: visual workflow state-machine editor.
 *
 * leaf_id: COMP-RF-001 (NavigationShell scope)
 * req_id:  REQ-176 (read-only, Phase 1), REQ-177 (edit mode, Phase 2)
 *
 * Composes the header, the 3-panel body (entity selector · React Flow canvas ·
 * inspector) and the status bar. Phase 2 adds an admin-gated edit mode that
 * owns the dialog state and mutation orchestration: add/edit/delete states and
 * transitions, initialize a workflow, and surface backend validation errors.
 */

import "@xyflow/react/dist/style.css";

import { useCallback, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { AlertCircle } from "lucide-react";
import { useWorkspace } from "../../context/WorkspaceContext";
import { useAuth } from "../../context/AuthContext";
import type { WorkflowEntityType } from "../../api/workflows";
import {
  DEFAULT_ENTITY_TYPE,
  entityTypeFromSlug,
  type Selection,
} from "./constants";
import { toMermaid } from "./mermaid-export";
import { useWorkflowData } from "./useWorkflowData";
import { useWorkflowMutations } from "./useWorkflowMutations";
import { WorkflowEditorHeader } from "./WorkflowEditorHeader";
import { WorkflowEditorLayout } from "./WorkflowEditorLayout";
import { EntityTypeSelector } from "./EntityTypeSelector";
import { WorkflowCanvas } from "./WorkflowCanvas";
import { InspectorPanel } from "./InspectorPanel";
import { StatusBar } from "./StatusBar";
import { StateDialog } from "./StateDialog";
import { TransitionDialog, type TransitionDraft } from "./TransitionDialog";
import { ConfirmDialog } from "./ConfirmDialog";
import styles from "./WorkflowEditor.module.css";

type DialogState =
  | { kind: "none" }
  | { kind: "addState" }
  | { kind: "editState"; name: string }
  | { kind: "addTransition"; from: string; to?: string }
  | { kind: "editTransition"; from: string; to: string }
  | { kind: "confirmDeleteState"; name: string }
  | { kind: "confirmDeleteTransition"; from: string; to: string };

export function WorkflowEditorPage(): JSX.Element {
  const { entityType: entitySlug } = useParams<{ entityType: string }>();
  const navigate = useNavigate();
  const { activeWorkspace } = useWorkspace();
  const { roles } = useAuth();
  const isAdmin = roles.includes("admin");

  const entityType: WorkflowEntityType =
    entityTypeFromSlug(entitySlug) ?? DEFAULT_ENTITY_TYPE;

  const [selection, setSelection] = useState<Selection>({ kind: "none" });
  const [toast, setToast] = useState<string | null>(null);
  const [editMode, setEditMode] = useState(false);
  const [dialog, setDialog] = useState<DialogState>({ kind: "none" });

  const { graph, isLoading, error } = useWorkflowData(entityType);
  const mutations = useWorkflowMutations(entityType, activeWorkspace?.id);

  const handleSelectEntity = useCallback(
    (type: WorkflowEntityType): void => {
      setSelection({ kind: "none" });
      setDialog({ kind: "none" });
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

  const toggleEditMode = useCallback((): void => {
    setEditMode((v) => {
      const next = !v;
      if (!next) {
        setDialog({ kind: "none" });
        setSelection({ kind: "none" });
      }
      return next;
    });
  }, []);

  const openDialog = useCallback(
    (next: DialogState): void => {
      mutations.clearError();
      setDialog(next);
    },
    [mutations]
  );
  const closeDialog = useCallback((): void => setDialog({ kind: "none" }), []);

  // --- canvas interaction handlers ---------------------------------------
  const handleConnectStates = useCallback(
    (from: string, to: string): void =>
      openDialog({ kind: "addTransition", from, to }),
    [openDialog]
  );

  const handleRenameState = useCallback(
    (oldName: string, newName: string): void => {
      void mutations.renameState(oldName, newName);
    },
    [mutations]
  );

  const handleDeleteSelection = useCallback((): void => {
    if (selection.kind === "state") {
      openDialog({ kind: "confirmDeleteState", name: selection.id });
    } else if (selection.kind === "transition" && graph) {
      const t = graph.transitions.find((x) => x.id === selection.id);
      if (t) openDialog({ kind: "confirmDeleteTransition", from: t.from_state, to: t.to_state });
    }
  }, [selection, graph, openDialog]);

  const editActions = useMemo(
    () => ({
      onEditState: (name: string) => openDialog({ kind: "editState", name }),
      onDeleteState: (name: string) =>
        openDialog({ kind: "confirmDeleteState", name }),
      onEditTransition: (from: string, to: string) =>
        openDialog({ kind: "editTransition", from, to }),
      onDeleteTransition: (from: string, to: string) =>
        openDialog({ kind: "confirmDeleteTransition", from, to }),
    }),
    [openDialog]
  );

  const afterMutation = useCallback(
    (ok: boolean): void => {
      if (ok) {
        closeDialog();
        setSelection({ kind: "none" });
      }
    },
    [closeDialog]
  );

  const preset = graph?.preset ?? activeWorkspace?.preset ?? "standard";

  const selectedTransition =
    dialog.kind === "editTransition" && graph
      ? graph.transitions.find(
          (t) => t.from_state === dialog.from && t.to_state === dialog.to
        )
      : undefined;

  return (
    <div className={styles.page} data-testid="workflow-editor-page">
      <WorkflowEditorHeader
        preset={preset}
        onCopyMermaid={handleCopyMermaid}
        canExport={!!graph && graph.states.length > 0}
        editMode={editMode}
        onToggleEditMode={toggleEditMode}
        canEdit={isAdmin}
      />

      <WorkflowEditorLayout
        selector={
          <EntityTypeSelector selected={entityType} onSelect={handleSelectEntity} />
        }
        canvas={
          <WorkflowCanvas
            graph={graph}
            entityType={entityType}
            workspaceId={activeWorkspace?.id}
            isLoading={isLoading}
            error={error}
            selection={selection}
            onSelect={setSelection}
            onCopyMermaid={handleCopyMermaid}
            editMode={editMode}
            onConnectStates={handleConnectStates}
            onRenameState={handleRenameState}
            onDeleteSelection={handleDeleteSelection}
            onAddStateRequest={() => openDialog({ kind: "addState" })}
            onInitialize={() => void mutations.initialize()}
            initializing={mutations.busy}
          />
        }
        inspector={
          <InspectorPanel
            graph={graph}
            selection={selection}
            onSelect={setSelection}
            editMode={editMode}
            edit={editActions}
          />
        }
      />

      <StatusBar graph={graph} />

      {/* Page-level toast — hidden while a modal is open (the dialog shows its
          own inline error). */}
      {toast && dialog.kind === "none" && (
        <div className={styles.statusBar} role="status" data-testid="workflow-toast">
          {toast}
        </div>
      )}
      {editMode && mutations.error && dialog.kind === "none" && (
        <div className={`${styles.toast} ${styles.toastError}`} role="alert" data-testid="workflow-error-toast">
          <AlertCircle size={16} className={styles.toastIcon} aria-hidden="true" />
          {mutations.error}
        </div>
      )}

      {/* --- Dialogs (REQ-177) --- */}
      {dialog.kind === "addState" && (
        <StateDialog
          mode="add"
          busy={mutations.busy}
          errorMessage={mutations.error}
          onClose={closeDialog}
          onSubmit={async (name) => afterMutation(await mutations.addState(name))}
        />
      )}
      {dialog.kind === "editState" && (
        <StateDialog
          mode="edit"
          initialName={dialog.name}
          busy={mutations.busy}
          errorMessage={mutations.error}
          onClose={closeDialog}
          onSubmit={async (name) =>
            afterMutation(await mutations.renameState(dialog.name, name))
          }
        />
      )}
      {dialog.kind === "addTransition" && graph && (
        <TransitionDialog
          mode="add"
          states={graph.states}
          fromState={dialog.from}
          toState={dialog.to}
          busy={mutations.busy}
          errorMessage={mutations.error}
          onClose={closeDialog}
          onSubmit={async (draft: TransitionDraft) =>
            afterMutation(await mutations.addTransition(draft))
          }
        />
      )}
      {dialog.kind === "editTransition" && graph && (
        <TransitionDialog
          mode="edit"
          states={graph.states}
          fromState={dialog.from}
          toState={dialog.to}
          initial={{
            allowed_roles: selectedTransition?.required_role
              ? selectedTransition.required_role.split(",").map((r) => r.trim())
              : [],
            requires_change_reason: selectedTransition?.change_reason_required,
            signature_gate: selectedTransition?.signature_gate,
          }}
          busy={mutations.busy}
          errorMessage={mutations.error}
          onClose={closeDialog}
          onSubmit={async (draft: TransitionDraft) =>
            afterMutation(
              await mutations.updateTransition(dialog.from, dialog.to, {
                allowed_roles: draft.allowed_roles,
                requires_change_reason: draft.requires_change_reason,
                signature_gate: draft.signature_gate,
              })
            )
          }
        />
      )}
      {dialog.kind === "confirmDeleteState" && (
        <ConfirmDialog
          title="Delete State"
          message={`Delete state "${dialog.name}"? This cannot be undone. The state must have no transitions and no items in it.`}
          busy={mutations.busy}
          errorMessage={mutations.error}
          onClose={closeDialog}
          onConfirm={async () =>
            afterMutation(await mutations.deleteState(dialog.name))
          }
        />
      )}
      {dialog.kind === "confirmDeleteTransition" && (
        <ConfirmDialog
          title="Delete Transition"
          message={`Delete the transition ${dialog.from} → ${dialog.to}? This cannot be undone.`}
          busy={mutations.busy}
          errorMessage={mutations.error}
          onClose={closeDialog}
          onConfirm={async () =>
            afterMutation(await mutations.deleteTransition(dialog.from, dialog.to))
          }
        />
      )}
    </div>
  );
}

export default WorkflowEditorPage;
