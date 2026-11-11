/**
 * ARCH-L1-001 ReactFrontend — need list filters (#598 S2).
 *
 * Extracted from `NeedList.tsx`: search, status filter and sort key are view
 * state, independent of the create form, the tree and the selection.
 *
 * `resetFilters()` deliberately clears search and status only — that is what
 * the empty-state's "reset" action has always done. The chosen sort survives a
 * reset, because it is an ordering preference, not a filter that can hide rows.
 */

import { useCallback, useState } from "react";

export type NeedSortKey = "default" | "title" | "status" | "updated";

export interface UseNeedListFiltersResult {
  listSearch: string;
  setListSearch: (value: string) => void;
  statusFilter: string;
  setStatusFilter: (value: string) => void;
  sortKey: NeedSortKey;
  setSortKey: (value: NeedSortKey) => void;
  resetFilters: () => void;
}

export function useNeedListFilters(): UseNeedListFiltersResult {
  const [listSearch, setListSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [sortKey, setSortKey] = useState<NeedSortKey>("default");

  const resetFilters = useCallback((): void => {
    setListSearch("");
    setStatusFilter("");
  }, []);

  return {
    listSearch,
    setListSearch,
    statusFilter,
    setStatusFilter,
    sortKey,
    setSortKey,
    resetFilters,
  };
}
