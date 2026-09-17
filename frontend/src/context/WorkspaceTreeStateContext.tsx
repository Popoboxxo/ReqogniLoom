/**
 * Issue #665 — session store for `WorkspaceTree`'s expand/collapse state.
 *
 * The sidebar (`SidebarNavigation`) owns section routing, while the
 * hierarchical artifact tree lives *inside* each section's split view
 * (`RequirementEditors`, `ArchitectureEditors`). Every section switch used to
 * unmount that tree, so it re-mounted with the auto-expanded roots and the
 * user lost the branch they had opened — the concrete "sidebar links and
 * in-page tree are decoupled" symptom from #665.
 *
 * The tree itself stays a controlled, presentational component: callers opt in
 * by passing a stable `stateKey`, and this provider (mounted once around the
 * routed pages) remembers the expanded node ids of every key across mounts.
 *
 * The default context value is a no-op, so a `WorkspaceTree` rendered without
 * a provider (every existing unit test, and any isolated embed) behaves
 * exactly as before.
 */

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

export interface WorkspaceTreeStateValue {
  /** Persisted expand state for `key`, or `null` if none was stored yet. */
  getExpanded: (key: string) => string[] | null;
  /** Stores `ids` as the expand state for `key`. */
  setExpanded: (key: string, ids: string[]) => void;
}

const NOOP_STATE: WorkspaceTreeStateValue = {
  getExpanded: () => null,
  setExpanded: () => undefined,
};

const WorkspaceTreeStateContext =
  createContext<WorkspaceTreeStateValue>(NOOP_STATE);

/** Order-insensitive membership check — avoids re-render churn on write. */
function sameIds(a: readonly string[], b: readonly string[]): boolean {
  if (a.length !== b.length) return false;
  const set = new Set(a);
  return b.every((id) => set.has(id));
}

export function WorkspaceTreeStateProvider({
  children,
}: {
  children: ReactNode;
}): JSX.Element {
  const [expandedByKey, setExpandedByKey] = useState<
    Record<string, string[]>
  >({});

  const getExpanded = useCallback(
    (key: string): string[] | null => expandedByKey[key] ?? null,
    [expandedByKey],
  );

  const setExpanded = useCallback((key: string, ids: string[]): void => {
    setExpandedByKey((prev) => {
      const current = prev[key];
      if (current && sameIds(current, ids)) return prev;
      return { ...prev, [key]: [...ids] };
    });
  }, []);

  const value = useMemo(
    () => ({ getExpanded, setExpanded }),
    [getExpanded, setExpanded],
  );

  return (
    <WorkspaceTreeStateContext.Provider value={value}>
      {children}
    </WorkspaceTreeStateContext.Provider>
  );
}

/** Reads the tree-state store; returns a no-op store outside a provider. */
export function useWorkspaceTreeState(): WorkspaceTreeStateValue {
  return useContext(WorkspaceTreeStateContext);
}
