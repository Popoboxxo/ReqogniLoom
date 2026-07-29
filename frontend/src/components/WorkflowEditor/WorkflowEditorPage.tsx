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
import { useTranslation } from "react-i18next";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { AlertCircle } from "lucide-react";
import { useWorkspace } from "../../context/WorkspaceContext";
import { useAuth } from "../../context/AuthContext";
import type { WorkflowEntityType } from "../../api/workflows";
import type { WorkspacePreset } from "../../types";
import {
  DEFAULT_ENTITY_TYPE,
  entityTypeFromSlug,
  WORKFLOW_PRESETS,
  type Selection,
  type WorkflowScope,
} from "./constants";
import { toMermaid } from "./mermaid-export";
import { useWorkflowData } from "./useWorkflowData";
import { useWorkflowMutations } from "./useWorkflowMutations";
import { WorkflowEditorHeader } from "./WorkflowEditorHeader";
import { WorkflowEditorLayout } from "./WorkflowEditorLayout";
import { EntityTypeSelector } from "./EntityTypeSelector";
import { PresetSegmentedControl } from "./PresetSegmentedControl";
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
  const { t } = useTranslation();
  const isGlobal = scope === "global";
  const { entityType: entitySlug } = useParams<{ entityType: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const { activeWorkspace } = useWorkspace();
  const { roles } = useAuth();
  const isAdmin = roles.includes("admin");

  const entityType: WorkflowEntityType =
    entityTypeFromSlug(isGlobal ? searchParams.get("entityType") ?? undefined : entitySlug) ??
    DEFAULT_ENTITY_TYPE;

  // Global scope is defined per preset; read it from the query string.
  const globalPreset: WorkspacePreset =
    (WORKFLOW_PRESETS.find((p) => p === searchParams.get("preset")) ??
      "standard") as WorkspacePreset;

  const workflowScope: WorkflowScope = isGlobal
    ? { kind: "global", preset: globalPreset }
    : { kind: "workspace", workspaceId: activeWorkspace?.id };

  const [selection, setSelection] = useState<Selection>({ kind: "none" });
  const [toast, setToast] = useState<string | null>(null);
  const [editMode, setEditMode] = useState(false);
  const [dialog, setDialog] = useState<DialogState>({ kind: "none" });

  const flashToast = useCallback((message: string): void => {
    setToast(message);
    window.setTimeout(() => setToast(null), 3000);
  }, []);

  const handlePropagated = useCallback(
    (count: number): void => {
      flashToast(t("workflow.toast.propagated", { count }));
    },
    [flashToast, t]
  );

  const { graph, isLoading, error } = useWorkflowData(entityType, workflowScope);
  const mutations = useWorkflowMutations(
    entityType,
    workflowScope,
    isGlobal ? handlePropagated : undefined
  );

  const setEntityQueryParam = useCallback(
    (type: WorkflowEntityType): void => {
      const next = new URLSearchParams(searchParams);
      next.set("entityType", type);
      setSearchParams(next, { replace: true });
    },
    [searchParams, setSearchParams]
  );

  const handleSelectEntity = useCallback(
    (type: WorkflowEntityType): void => {
      setSelection({ kind: "none" });
      setDialog({ kind: "none" });
      if (isGlobal) {
        setEntityQueryParam(type);
      } else {
        navigate(`/workflows/${type}`);
      }
    },
    [navigate, isGlobal, setEntityQueryParam]
  );

  const handleSelectPreset = useCallback(
    (preset: WorkspacePreset): void => {
      setSelection({ kind: "none" });
      setDialog({ kind: "none" });
      setEditMode(false);
      const next = new URLSearchParams(searchParams);
      next.set("preset", preset);
      setSearchParams(next, { replace: true });
    },
    [searchParams, setSearchParams]
  );

  const handleCopyMermaid = useCallback((): void => {
    if (!graph) return;
    const text = toMermaid(graph);
    void navigator.clipboard
      ?.writeText(text)
      .then(() => setToast(t("workflow.toast.copiedMermaid")))
      .catch(() => setToast(t("workflow.toast.clipboardError")));
    window.setTimeout(() => setToast(null), 2000);
  }, [graph, t]);

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

  const preset = isGlobal
    ? globalPreset
    : graph?.preset ?? activeWorkspace?.preset ?? "standard";

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
        title={
          isGlobal
            ? t("workflow.header.titleGlobal")
            : t("workflow.header.titleDefault")
        }
        presetControl={
          isGlobal ? (
            <PresetSegmentedControl value={globalPreset} onChange={handleSelectPreset} />
          ) : undefined
        }
      />

      <WorkflowEditorLayout
        selector={
          <EntityTypeSelector
            selected={entityType}
            onSelect={handleSelectEntity}
            scope={workflowScope}
          />
        }
        canvas={
          <WorkflowCanvas
            graph={graph}
            entityType={entityType}
            workspaceId={isGlobal ? `global-${globalPreset}` : activeWorkspace?.id}
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
          title={t("workflow.confirmDialog.deleteState.title")}
          message={t("workflow.confirmDialog.deleteState.message", {
            name: dialog.name,
          })}
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
          title={t("workflow.confirmDialog.deleteTransition.title")}
          message={t("workflow.confirmDialog.deleteTransition.message", {
            from: dialog.from,
            to: dialog.to,
          })}
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
