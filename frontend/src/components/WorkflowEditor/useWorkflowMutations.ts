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
 *
 * P2.5 — every method is one entry in ``mutations`` whose body is a single
 * ``dispatch(globalOp, workspaceOp)`` call; the scope branch exists once, in
 * ``dispatch``. P2.6 — ``setStateFreeze`` is a global-defaults-only capability:
 * the workspace branch has no such field, so the key is absent from the returned
 * object instead of a silent ``Promise.resolve(false)`` no-op.
 *
 * Stable identity: the returned object is memoised against the primitives its
 * closures actually capture (@see normalizeScope for why the caller's scope
 * literal cannot serve as a dependency). Consumers keep ``mutations`` in their
 * own ``useMemo``/``useCallback`` dependency lists, so a per-render rebuild
 * would churn every dialog and inspector prop on each parent render.
 */

import { useCallback, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { WorkspacePreset } from "../../types";
import {
  extractWorkflowError,
  workflowsApi,
  type WorkflowEntityType,
  type WorkflowGraph,
  type WorkflowPresetKey,
} from "../../api/workflows";
import { workflowDefaultsApi } from "../../api/workflow-defaults";
import type { TransitionDraft } from "./TransitionDialog";
import { workflowKeys } from "./useWorkflowData";
import type { WorkflowScope } from "./constants";

export interface WorkflowMutations {
  busy: boolean;
  error: string | null;
  clearError: () => void;
  addState: (name: string) => Promise<boolean>;
  renameState: (oldName: string, newName: string) => Promise<boolean>;
  deleteState: (name: string) => Promise<boolean>;
  /**
   * Global-defaults scope only (P2.6). Absent in workspace scope: a workspace
   * workflow definition has no per-state freeze flag, so calling it there is
   * unsupported rather than a silent no-op.
   */
  setStateFreeze?: (name: string, freeze: boolean) => Promise<boolean>;
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

/**
 * Narrow a raw preset value to the workspace rigor tier.
 *
 * ``WorkspacePreset`` is a strict subset of ``WorkflowPresetKey``, so a plain
 * assignment from the wider type is exactly the cast this hook avoids: it would
 * also launder an absent value past the type system.
 */
function isWorkspacePreset(
  value: WorkflowPresetKey | undefined
): value is WorkspacePreset {
  return value === "minimal" || value === "standard" || value === "extended";
}

/**
 * Rebuild a scope from its primitive fields.
 *
 * Callers construct a fresh ``WorkflowScope`` literal on every render, so the
 * object identity changes even when nothing about the scope did — it can never
 * be a dependency of a meaningful memo. Its three fields are the real identity,
 * which is why the hook normalises them once and derives the cache key from the
 * result. The preset is narrowed to the branch that owns it instead of cast:
 * ``kind === "global"`` needs a ``WorkflowPresetKey``, ``kind === "workspace"``
 * an optional ``WorkspacePreset`` (see ``WorkflowScope``).
 *
 * Two fallbacks keep the returned type honest instead of asserting it:
 * a global scope without a preset cannot run (``canRun`` stays false) and falls
 * back to a workspace-shaped scope, and a value that is not a workspace rigor
 * tier yields ``preset: undefined`` on the workspace branch.
 */
function normalizeScope(
  kind: WorkflowScope["kind"],
  workspaceId: string | undefined,
  preset: WorkflowPresetKey | undefined
): WorkflowScope {
  if (kind === "global") {
    return preset !== undefined
      ? { kind: "global", preset }
      : { kind: "workspace", workspaceId: undefined, preset: undefined };
  }
  return {
    kind: "workspace",
    workspaceId,
    preset: isWorkspacePreset(preset) ? preset : undefined,
  };
}

export function useWorkflowMutations(
  entityType: WorkflowEntityType,
  scope: WorkflowScope,
  onPropagated?: (count: number) => void
): WorkflowMutations {
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const scopeKind = scope.kind;
  const isGlobal = scopeKind === "global";
  const workspaceId = scope.kind === "workspace" ? scope.workspaceId : undefined;
  const preset = scope.kind === "global" ? scope.preset : undefined;
  // The workspace branch keys the cache on its rigor tier as well, so the raw
  // (un-narrowed) preset has to survive into ``normalizeScope``.
  const scopePreset = scope.preset;

  const stableScope = useMemo(
    () => normalizeScope(scopeKind, workspaceId, scopePreset),
    [scopeKind, workspaceId, scopePreset]
  );
  const queryKey = useMemo(
    () => workflowKeys.graph(stableScope, entityType),
    [stableScope, entityType]
  );

  const canRun = isGlobal ? !!preset : !!workspaceId;

  const run = useCallback(
    async (op: () => Promise<OpResult>): Promise<boolean> => {
      if (!canRun) return false;
      setBusy(true);
      setError(null);
      try {
        const { graph, propagatedWorkspaceCount } = await op();
        queryClient.setQueryData(queryKey, graph);
        void queryClient.invalidateQueries({ queryKey });
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
    [queryKey, canRun, queryClient, onPropagated]
  );

  const clearError = useCallback(() => setError(null), []);

  /**
   * P2.5 — the single scope branch of this hook. Both arms are plain thunks, so
   * only the selected endpoint family is ever called while every method keeps
   * its original arguments and return type.
   */
  const dispatch = useCallback(
    (
      globalOp: () => Promise<OpResult>,
      workspaceOp: () => Promise<OpResult>
    ): Promise<boolean> => run(isGlobal ? globalOp : workspaceOp),
    [isGlobal, run]
  );

  // Memoised over the primitives the method bodies capture; ``busy``/``error``
  // are the only render-frequent entries (a solve-solve transition legitimately
  // rebuilds the object once per mutation).
  const mutations = useMemo<WorkflowMutations>(() => {
    // Adapt the workspace api (returns a bare WorkflowGraph) to the OpResult
    // shape. Pure, so it lives with the object it feeds instead of becoming a
    // (render-fresh) dependency of the memo.
    const wrapWs = (p: Promise<WorkflowGraph>): Promise<OpResult> =>
      p.then((graph) => ({ graph }));

    return {
      busy,
      error,
      clearError,
      addState: (name) =>
        dispatch(
          () => workflowDefaultsApi.createState(entityType, preset!, name),
          () => wrapWs(workflowsApi.createState(entityType, workspaceId!, name))
        ),
      renameState: (oldName, newName) =>
        dispatch(
          () =>
            workflowDefaultsApi.updateState(
              entityType,
              preset!,
              oldName,
              newName
            ),
          () =>
            wrapWs(
              workflowsApi.updateState(
                entityType,
                workspaceId!,
                oldName,
                newName
              )
            )
        ),
      deleteState: (name) =>
        dispatch(
          () => workflowDefaultsApi.deleteState(entityType, preset!, name),
          () => wrapWs(workflowsApi.deleteState(entityType, workspaceId!, name))
        ),
      addTransition: (draft) => {
        const payload = {
          from_state: draft.from_state,
          to_state: draft.to_state,
          allowed_roles: draft.allowed_roles,
          requires_change_reason: draft.requires_change_reason,
          signature_gate: draft.signature_gate,
        };
        return dispatch(
          () =>
            workflowDefaultsApi.createTransition(entityType, preset!, payload),
          () =>
            wrapWs(
              workflowsApi.createTransition(entityType, workspaceId!, payload)
            )
        );
      },
      updateTransition: (fromState, toState, patch) =>
        dispatch(
          () =>
            workflowDefaultsApi.updateTransition(
              entityType,
              preset!,
              fromState,
              toState,
              patch
            ),
          () =>
            wrapWs(
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
        dispatch(
          () =>
            workflowDefaultsApi.deleteTransition(
              entityType,
              preset!,
              fromState,
              toState
            ),
          () =>
            wrapWs(
              workflowsApi.deleteTransition(
                entityType,
                workspaceId!,
                fromState,
                toState
              )
            )
        ),
      initialize: () =>
        dispatch(
          () => workflowDefaultsApi.initialize(entityType, preset!),
          () => wrapWs(workflowsApi.initializeWorkflow(entityType, workspaceId!))
        ),
    };
  }, [busy, error, clearError, dispatch, entityType, preset, workspaceId]);

  // P2.6: the freeze flag only exists on the tenant-wide default. In workspace
  // scope the capability is missing, not a no-op — there is deliberately no
  // workspace counterpart to dispatch to, and the spread keeps the key absent
  // from the returned object rather than present-and-undefined.
  return useMemo<WorkflowMutations>(
    () =>
      isGlobal
        ? {
            ...mutations,
            setStateFreeze: (name, freeze) =>
              run(() =>
                workflowDefaultsApi.setStateFreeze(
                  entityType,
                  preset!,
                  name,
                  freeze
                )
              ),
          }
        : mutations,
    [isGlobal, mutations, run, entityType, preset]
  );
}
