/**
 * REQ-177 — Workflow Editor edit-mode mutations hook (Phase 2).
 *
 * Wraps the workflowsApi mutation calls with a single busy flag, a last-error
 * message (surfaced as a toast by the page) and TanStack Query cache updates:
 * each successful mutation returns the full re-derived graph, which is written
 * straight into the query cache (instant canvas refresh) and the query is
 * invalidated for consistency. Backend validation errors (409/400/403) are
 * caught and exposed via ``error`` instead of being thrown to the caller.
 */

import { useCallback, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  extractWorkflowError,
  workflowsApi,
  type WorkflowEntityType,
  type WorkflowGraph,
} from "../../api/workflows";
import type { TransitionDraft } from "./TransitionDialog";
import { workflowKeys } from "./useWorkflowData";

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

export function useWorkflowMutations(
  entityType: WorkflowEntityType,
  workspaceId: string | undefined
): WorkflowMutations {
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(
    async (op: () => Promise<WorkflowGraph>): Promise<boolean> => {
      if (!workspaceId) return false;
      setBusy(true);
      setError(null);
      try {
        const graph = await op();
        queryClient.setQueryData(
          workflowKeys.graph(workspaceId, entityType),
          graph
        );
        void queryClient.invalidateQueries({
          queryKey: workflowKeys.graph(workspaceId, entityType),
        });
        return true;
      } catch (err) {
        setError(extractWorkflowError(err));
        return false;
      } finally {
        setBusy(false);
      }
    },
    [entityType, workspaceId, queryClient]
  );

  const clearError = useCallback(() => setError(null), []);

  return {
    busy,
    error,
    clearError,
    addState: (name) =>
      run(() => workflowsApi.createState(entityType, workspaceId!, name)),
    renameState: (oldName, newName) =>
      run(() =>
        workflowsApi.updateState(entityType, workspaceId!, oldName, newName)
      ),
    deleteState: (name) =>
      run(() => workflowsApi.deleteState(entityType, workspaceId!, name)),
    addTransition: (draft) =>
      run(() =>
        workflowsApi.createTransition(entityType, workspaceId!, {
          from_state: draft.from_state,
          to_state: draft.to_state,
          allowed_roles: draft.allowed_roles,
          requires_change_reason: draft.requires_change_reason,
          signature_gate: draft.signature_gate,
        })
      ),
    updateTransition: (fromState, toState, patch) =>
      run(() =>
        workflowsApi.updateTransition(
          entityType,
          workspaceId!,
          fromState,
          toState,
          patch
        )
      ),
    deleteTransition: (fromState, toState) =>
      run(() =>
        workflowsApi.deleteTransition(
          entityType,
          workspaceId!,
          fromState,
          toState
        )
      ),
    initialize: () =>
      run(() => workflowsApi.initializeWorkflow(entityType, workspaceId!)),
  };
}
