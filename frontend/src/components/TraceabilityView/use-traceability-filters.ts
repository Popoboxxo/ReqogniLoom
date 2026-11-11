/**
 * ARCH-L1-001 ReactFrontend — traceability list filters (#598 S2).
 *
 * Extracted from `TraceabilityView.tsx`: the search box, the link-type filter
 * and the "uncovered only" switch are view state, independent of the data
 * load, the create dialog and the PDF export.
 *
 * The filter state is deliberately *not* persisted: traceability is an
 * analysis view whose result changes with the filters, and the route has always
 * started unfiltered (unlike the artifact lists, which persist per workspace).
 */

import { useCallback, useState } from "react";

export interface UseTraceabilityFiltersResult {
  listSearch: string;
  setListSearch: (value: string) => void;
  linkTypeFilter: string;
  setLinkTypeFilter: (value: string) => void;
  showUncoveredOnly: boolean;
  setShowUncoveredOnly: (value: boolean) => void;
  resetFilters: () => void;
}

export function useTraceabilityFilters(): UseTraceabilityFiltersResult {
  const [listSearch, setListSearch] = useState<string>("");
  const [linkTypeFilter, setLinkTypeFilter] = useState<string>("");
  const [showUncoveredOnly, setShowUncoveredOnly] = useState<boolean>(false);

  const resetFilters = useCallback((): void => {
    setListSearch("");
    setLinkTypeFilter("");
    setShowUncoveredOnly(false);
  }, []);

  return {
    listSearch,
    setListSearch,
    linkTypeFilter,
    setLinkTypeFilter,
    showUncoveredOnly,
    setShowUncoveredOnly,
    resetFilters,
  };
}
