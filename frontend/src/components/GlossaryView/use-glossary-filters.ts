/**
 * ARCH-L1-001 ReactFrontend — glossary list filters (#598 S2).
 *
 * Extracted from `GlossaryView.tsx`: search, scope mode, status filter and sort
 * key are list controls, independent of the term form, the synonym linking and
 * the AI derivation.
 *
 * `resetFilters()` restores the scope mode to "workspace" as well — that is
 * what the existing reset does, because the mode decides *which* terms are in
 * scope, not just how they are ordered.
 */

import { useCallback, useState } from "react";

import type { FilterMode, SortKey } from "./glossary-view-shared";

export interface UseGlossaryFiltersResult {
  searchTerm: string;
  setSearchTerm: (value: string) => void;
  filterMode: FilterMode;
  setFilterMode: (value: FilterMode) => void;
  statusFilter: string;
  setStatusFilter: (value: string) => void;
  sortKey: SortKey;
  setSortKey: (value: SortKey) => void;
  resetFilters: () => void;
}

export function useGlossaryFilters(): UseGlossaryFiltersResult {
  const [searchTerm, setSearchTerm] = useState("");
  const [filterMode, setFilterMode] = useState<FilterMode>("workspace");
  const [statusFilter, setStatusFilter] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("default");

  const resetFilters = useCallback((): void => {
    setSearchTerm("");
    setFilterMode("workspace");
    setStatusFilter("");
  }, []);

  return {
    searchTerm,
    setSearchTerm,
    filterMode,
    setFilterMode,
    statusFilter,
    setStatusFilter,
    sortKey,
    setSortKey,
    resetFilters,
  };
}
