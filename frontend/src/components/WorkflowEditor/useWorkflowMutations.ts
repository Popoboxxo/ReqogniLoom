/**
 * REQ-177 — Workflow Editor edit-mode mutations hook (Phase 2).
 *
 * Wraps the workflowsApi mutation calls with a single busy flag, a last-error
 * message (surfaced as a toast by the page) and TanStack Query cache updates:
 * each successful mutation returns the full re-derived graph, which is written
 * straight into the query cache (instant canvas refresh) and the query is
 * invalidated for consistency. Backend validation errors (409/400/403) are
 * caught and exposed via ``error`` instead of being thrown to the caller.
 *
 * REQ-178/179 — scope-aware: ``workspace`` scope dispatches to the per-workspace
 * endpoints (unchanged); ``global`` scope dispatches to the tenant-wide
 * ``/workflow-defaults/`` endpoints and surfaces the optional
 * ``propagated_workspace_count`` via ``onPropagated`` (SCR-205 toast).
 */

import { useCallback, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  extractWorkflowError,
  workflowsApi,
  type WorkflowEntityType,
  type WorkflowGraph,
} from "../../api/workflows";
import { workflowDefaultsApi } from "../../api/workflow-defaults";
import type { TransitionDraft } from "./TransitionDialog";
import { workflowKeys, scopeCacheKey } from "./useWorkflowData";
import type { WorkflowScope } from "./constants";

export interface WorkflowMutations {
  busy: boolean;
  error: string | null;
  clearError: () => void;
  addState: (name: string) => Promise<boolean>;
  renameState: (oldName: string, newName: string) => Promise<boolean>;
  deleteState: (name: string) => Promise<boolean>;
  addTransition: (draft: TransitionDraft) => Promise<boolean>;
  updateTransition: (
    fromState: string,
    toState: string,
    patch: {
      allowed_roles?: string[];
      requires_change_reason?: boolean;
      signature_gate?: boolean;
    }
  ) => Promise<boolean>;
  deleteTransition: (fromState: string, toState: string) => Promise<boolean>;
  initialize: () => Promise<boolean>;
}

/** Internal shape every dispatched op resolves to. */
interface OpResult {
  graph: WorkflowGraph;
  propagatedWorkspaceCount?: number;
}

export function useWorkflowMutations(
  entityType: WorkflowEntityType,
  scope: WorkflowScope,
  onPropagated?: (count: number) => void
): WorkflowMutations {
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isGlobal = scope.kind === "global";
  const workspaceId = scope.kind === "workspace" ? scope.workspaceId : undefined;
  const preset = scope.kind === "global" ? scope.preset : undefined;
  const cacheKey = scopeCacheKey(scope);

  const canRun = isGlobal ? !!preset : !!workspaceId;

  const run = useCallback(
    async (op: () => Promise<OpResult>): Promise<boolean> => {
      if (!canRun) return false;
      setBusy(true);
      setError(null);
      try {
        const { graph, propagatedWorkspaceCount } = await op();
        queryClient.setQueryData(
          workflowKeys.graph(cacheKey, entityType),
          graph
        );
        void queryClient.invalidateQueries({
          queryKey: workflowKeys.graph(cacheKey, entityType),
        });
        if (typeof propagatedWorkspaceCount === "number") {
          onPropagated?.(propagatedWorkspaceCount);
        }
        return true;
      } catch (err) {
        setError(extractWorkflowError(err));
        return false;
      } finally {
        setBusy(false);
      }
    },
    [entityType, cacheKey, canRun, queryClient, onPropagated]
  );

  const clearError = useCallback(() => setError(null), []);

  // Adapt the workspace api (returns a bare WorkflowGraph) to the OpResult shape.
  const wrapWs = (p: Promise<WorkflowGraph>): Promise<OpResult> =>
    p.then((graph) => ({ graph }));

  return {
    busy,
    error,
    clearError,
    addState: (name) =>
      run(() =>
        isGlobal
          ? workflowDefaultsApi.createState(entityType, preset!, name)
          : wrapWs(workflowsApi.createState(entityType, workspaceId!, name))
      ),
    renameState: (oldName, newName) =>
      run(() =>
        isGlobal
          ? workflowDefaultsApi.updateState(entityType, preset!, oldName, newName)
          : wrapWs(
              workflowsApi.updateState(entityType, workspaceId!, oldName, newName)
            )
      ),
    deleteState: (name) =>
      run(() =>
        isGlobal
          ? workflowDefaultsApi.deleteState(entityType, preset!, name)
          : wrapWs(workflowsApi.deleteState(entityType, workspaceId!, name))
      ),
    addTransition: (draft) => {
      const payload = {
        from_state: draft.from_state,
        to_state: draft.to_state,
        allowed_roles: draft.allowed_roles,
        requires_change_reason: draft.requires_change_reason,
        signature_gate: draft.signature_gate,
      };
      return run(() =>
        isGlobal
          ? workflowDefaultsApi.createTransition(entityType, preset!, payload)
          : wrapWs(
              workflowsApi.createTransition(entityType, workspaceId!, payload)
            )
      );
    },
    updateTransition: (fromState, toState, patch) =>
      run(() =>
        isGlobal
          ? workflowDefaultsApi.updateTransition(
              entityType,
              preset!,
              fromState,
              toState,
              patch
            )
          : wrapWs(
              workflowsApi.updateTransition(
                entityType,
                workspaceId!,
                fromState,
                toState,
                patch
              )
            )
      ),
    deleteTransition: (fromState, toState) =>
      run(() =>
        isGlobal
          ? workflowDefaultsApi.deleteTransition(
              entityType,
              preset!,
              fromState,
              toState
            )
          : wrapWs(
              workflowsApi.deleteTransition(
                entityType,
                workspaceId!,
                fromState,
                toState
              )
            )
      ),
    initialize: () =>
      run(() =>
        isGlobal
          ? workflowDefaultsApi.initialize(entityType, preset!)
          : wrapWs(workflowsApi.initializeWorkflow(entityType, workspaceId!))
      ),
  };
}
