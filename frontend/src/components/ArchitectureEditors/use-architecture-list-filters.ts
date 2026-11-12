/**
 * ARCH-L1-001 ReactFrontend — architecture list filters (#598 S2).
 *
 * Extracted from `ArchitectureEditors.tsx`: the include-deleted switch, the
 * search box and the lifecycle-status filter are list controls, independent of
 * the create form, the derive flows, the decompose panel and the risk dialog.
 *
 * `resetFilters()` clears search and status only — that is what the empty-state
 * action has always done. The include-deleted switch stays on, because turning
 * it off is a data-visibility decision, not a filter reset.
 */

import { useCallback, useState } from "react";

export interface UseArchitectureListFiltersResult {
  includeDeleted: boolean;
  setIncludeDeleted: (value: boolean) => void;
  listSearch: string;
  setListSearch: (value: string) => void;
  statusFilter: string;
  setStatusFilter: (value: string) => void;
  resetFilters: () => void;
}

export function useArchitectureListFilters(): UseArchitectureListFiltersResult {
  const [includeDeleted, setIncludeDeleted] = useState(false);
  const [listSearch, setListSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");

  const resetFilters = useCallback((): void => {
    setListSearch("");
    setStatusFilter("");
  }, []);

  return {
    includeDeleted,
    setIncludeDeleted,
    listSearch,
    setListSearch,
    statusFilter,
    setStatusFilter,
    resetFilters,
  };
}
