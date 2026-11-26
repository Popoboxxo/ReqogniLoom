/**
 * REQ-176/REQ-177 — Workflow Editor content: the shared, scope-agnostic editor.
 *
 * leaf_id: COMP-RF-001 (NavigationShell scope)
 * req_id:  REQ-176 (read-only, Phase 1), REQ-177 (edit mode, Phase 2)
 *
 * Composes the header, the 3-panel body (entity selector · React Flow canvas ·
 * inspector) and the status bar. Phase 2 adds an admin-gated edit mode that
 * owns the dialog state and mutation orchestration: add/edit/delete states and
 * transitions, initialize a workflow, and surface backend validation errors.
 *
 * P2.4: scope *resolution* is owned by the containers — no route or query
 * string is parsed here. ``WorkspaceWorkflowEditorPage`` (``/workflows/:entityType``)
 * and ``GlobalWorkflowDefaultsPage`` (query-parameter form) resolve the entity
 * type and preset and pass them in; ``isGlobal`` selects the scope semantics
 * the body still has to render (preset control, freeze action, global-only
 * copy). What deliberately stays shared is the *write* side of navigation:
 * selecting an entity or preset updates the address (route push in workspace
 * scope, query-string rewrite in global scope), because both scopes render the
 * same selector and the body owns its handlers.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { AlertCircle, Info } from "lucide-react";
import { useWorkspace } from "../../context/WorkspaceContext";
import { useAuth } from "../../context/AuthContext";
import type {
  WorkflowEntityType,
  WorkflowPresetKey,
} from "../../api/workflows";
import type { WorkspacePreset } from "../../types";
import {
  defaultWorkflowPreset,
  workflowPresetTier,
  type Selection,
  type WorkflowScope,
} from "./constants";
import { toMermaid } from "./mermaid-export";
import { useWorkflowData, workflowKeys } from "./useWorkflowData";
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

export interface WorkspaceScopeProps {
  isGlobal: false;
  entityType: WorkflowEntityType;
}

export interface GlobalScopeProps {
  isGlobal: true;
  entityType: WorkflowEntityType;
  /** The tenant-wide default being edited (SCR-205). */
  preset: WorkflowPresetKey;
  /** The canonical preset choices for ``entityType``. */
  presetOptions: readonly WorkflowPresetKey[];
}

/**
 * Discriminated by ``isGlobal``: the global-only inputs do not exist in
 * workspace scope, so the illegal combination (workspace scope plus an inert
 * preset) is not representable.
 */
export type WorkflowEditorContentProps =
  | WorkspaceScopeProps
  | GlobalScopeProps;

/** Stable empty list: a fresh ``[]`` per render would churn the props. */
const NO_PRESETS: readonly WorkflowPresetKey[] = [];

export function WorkflowEditorContent(
  props: WorkflowEditorContentProps
): JSX.Element {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const { activeWorkspace } = useWorkspace();
  const { roles } = useAuth();
  const isAdmin = roles.includes("admin");
  const queryClient = useQueryClient();

  const { entityType } = props;
  const isGlobal = props.isGlobal;
  // The union is narrowed once, here: ``globalProps`` is the global half of the
  // props or ``null`` in workspace scope. Everything global-scoped (its preset,
  // its options) is read from it instead of an inert duplicate prop.
  const globalProps = props.isGlobal ? props : null;
  const globalPreset = globalProps?.preset;
  const presetOptions = globalProps?.presetOptions ?? NO_PRESETS;

  const workflowScope: WorkflowScope = globalProps
    ? { kind: "global", preset: globalProps.preset }
    : {
        kind: "workspace",
        workspaceId: activeWorkspace?.id,
        preset: activeWorkspace?.preset,
      };

  const [selection, setSelection] = useState<Selection>({ kind: "none" });
  const [toast, setToast] = useState<string | null>(null);
  const [editMode, setEditMode] = useState(false);
  const [dialog, setDialog] = useState<DialogState>({ kind: "none" });

  // A workspace preset switch changes the resolved Requirement/WorkItem graph.
  // Invalidate every cached type for that workspace, while the preset-aware
  // query keys ensure the newly selected graph is fetched immediately.
  const previousWorkspaceRef = useRef<{
    id: string;
    preset: WorkspacePreset | undefined;
  } | null>(null);
  useEffect(() => {
    const workspaceId = activeWorkspace?.id;
    const preset = activeWorkspace?.preset;
    const previous = previousWorkspaceRef.current;
    if (
      !isGlobal &&
      workspaceId &&
      previous?.id === workspaceId &&
      previous.preset !== preset
    ) {
      void queryClient.invalidateQueries({
        queryKey: workflowKeys.workspace(workspaceId),
      });
    }
    previousWorkspaceRef.current = workspaceId ? { id: workspaceId, preset } : null;
  }, [isGlobal, activeWorkspace?.id, activeWorkspace?.preset, queryClient]);

  // UI-38: the toast auto-dismiss timers were fire-and-forget window.setTimeout
  // calls with no cleanup — if the component unmounted (route change) before
  // the timer fired, setToast(null) ran on an unmounted component. Track the
  // pending timer so it can be cleared on unmount or superseded by a newer
  // toast.
  const toastTimerRef = useRef<number | null>(null);

  const clearToastTimer = useCallback((): void => {
    if (toastTimerRef.current !== null) {
      window.clearTimeout(toastTimerRef.current);
      toastTimerRef.current = null;
    }
  }, []);

  const flashToast = useCallback(
    (message: string, durationMs = 3000): void => {
      clearToastTimer();
      setToast(message);
      toastTimerRef.current = window.setTimeout(() => {
        setToast(null);
        toastTimerRef.current = null;
      }, durationMs);
    },
    [clearToastTimer]
  );

  useEffect(() => clearToastTimer, [clearToastTimer]);

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

  const handleSelectEntity = useCallback(
    (type: WorkflowEntityType): void => {
      setSelection({ kind: "none" });
      setDialog({ kind: "none" });
      if (isGlobal) {
        const next = new URLSearchParams(searchParams);
        // ``globalPreset`` is always set in global scope; the guard keeps the
        // fallback identical for the (unreachable) workspace branch.
        const tier =
          (globalPreset && workflowPresetTier(globalPreset)) ?? "standard";
        next.set("entityType", type);
        next.set("preset", defaultWorkflowPreset(type, tier));
        setSearchParams(next, { replace: true });
      } else {
        navigate(`/workflows/${type}`);
      }
    },
    [navigate, isGlobal, globalPreset, searchParams, setSearchParams]
  );

  const handleSelectPreset = useCallback(
    (preset: WorkflowPresetKey): void => {
      if (!presetOptions.includes(preset)) return;
      setSelection({ kind: "none" });
      setDialog({ kind: "none" });
      setEditMode(false);
      const next = new URLSearchParams(searchParams);
      next.set("preset", preset);
      setSearchParams(next, { replace: true });
    },
    [presetOptions, searchParams, setSearchParams]
  );

  const handleCopyMermaid = useCallback((): void => {
    if (!graph) return;
    const text = toMermaid(graph);
    void navigator.clipboard
      ?.writeText(text)
      .then(() => flashToast(t("workflow.toast.copiedMermaid"), 2000))
      .catch(() => flashToast(t("workflow.toast.clipboardError"), 2000));
  }, [graph, t, flashToast]);

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

  const editActions = useMemo(() => {
    // P2.6: the per-state freeze flag exists only on the tenant-wide default.
    // The workspace mutation hook does not expose ``setStateFreeze`` at all, so
    // the action is handed off only when both the scope and the hook support it
    // — captured in a local so the narrowing survives into the callback.
    const setStateFreeze = isGlobal ? mutations.setStateFreeze : undefined;
    return {
      onEditState: (name: string) => openDialog({ kind: "editState", name }),
      onSetStateFreeze: setStateFreeze
        ? (name: string, freeze: boolean): void => {
            void setStateFreeze(name, freeze);
          }
        : undefined,
      onDeleteState: (name: string) =>
        openDialog({ kind: "confirmDeleteState", name }),
      onEditTransition: (from: string, to: string) =>
        openDialog({ kind: "editTransition", from, to }),
      onDeleteTransition: (from: string, to: string) =>
        openDialog({ kind: "confirmDeleteTransition", from, to }),
    };
  }, [openDialog, isGlobal, mutations]);

  const afterMutation = useCallback(
    (ok: boolean): void => {
      if (ok) {
        closeDialog();
        setSelection({ kind: "none" });
      }
    },
    [closeDialog]
  );

  // Global scope shows the preset being edited; a workspace definition derives
  // it from the graph (the workspace preset is a fallback for the empty state).
  const headerPreset =
    globalPreset ?? graph?.preset ?? activeWorkspace?.preset ?? "standard";

  const selectedTransition =
    dialog.kind === "editTransition" && graph
      ? graph.transitions.find(
          (t) => t.from_state === dialog.from && t.to_state === dialog.to
        )
      : undefined;

  return (
    <div className={styles.page} data-testid="workflow-editor-page">
      <WorkflowEditorHeader
        preset={headerPreset}
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
          globalProps && globalProps.presetOptions.length > 1 ? (
            <PresetSegmentedControl
              value={globalProps.preset}
              options={globalProps.presetOptions}
              onChange={handleSelectPreset}
            />
          ) : undefined
        }
      />

      <div
        className={styles.scopeNotice}
        role="note"
        data-testid="workflow-scope-notice"
      >
        <Info size={14} className={styles.scopeNoticeIcon} aria-hidden="true" />
        <span>
          {t(
            isGlobal
              ? "workflow.scope.globalHint"
              : "workflow.scope.workspaceHint"
          )}
        </span>
        <Link
          to={
            isGlobal
              ? "/workflows"
              : "/system-settings?tab=workflow-defaults"
          }
          className={styles.scopeNoticeLink}
          data-testid={
            isGlobal
              ? "workflow-workspace-definitions-link"
              : "workflow-global-defaults-link"
          }
        >
          {t(
            isGlobal
              ? "workflow.scope.workspaceDefinitionsLink"
              : "workflow.scope.globalDefaultsLink"
          )}
        </Link>
      </div>

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
            workspaceId={
              globalProps
                ? `global-${globalProps.preset}`
                : activeWorkspace?.id
            }
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
