/**
 * ARCH-L1-001 ReactFrontend — memory search (#598 S2).
 *
 * Extracted from `MemoryPage.tsx`: the semantic search box and its result set
 * are independent of the browse list, the filters and the per-entry actions.
 *
 * Contract kept verbatim:
 *   - a blank query does nothing (no request, no state change),
 *   - the artifact tab requires a chosen artifact and reports it as its own
 *     error instead of sending an unscoped request,
 *   - a successful search also carries the backend's `degraded` flag (the
 *     panel has to say when embeddings were unavailable),
 *   - a failed search clears the results and keeps its message.
 */

import { useCallback, useEffect, useState } from "react";
import type { TFunction } from "i18next";

import { memoryApi, type MemoryEntry, type MemoryScope } from "../../api/memory";
import { formatMemoryErrorMessage } from "./memory-format";

export interface UseMemorySearchOptions {
  workspaceId: string | undefined;
  scope: MemoryScope;
  artifactId: string;
  t: TFunction;
  /** The backend's `degraded` flag drives the page's degradation banner. */
  onDegraded: (degraded: boolean) => void;
  /**
   * Changes whenever the browse context changes (tab, workspace, artifact,
   * filters). A stale result set from the old context must not stay on screen,
   * so the hook drops results and error — but keeps what the user typed.
   */
  resetKey: string;
}

export interface UseMemorySearchResult {
  searchInput: string;
  searchResults: MemoryEntry[] | null;
  isSearching: boolean;
  searchError: string | null;
  setSearchInput: (value: string) => void;
  handleSearch: () => void;
  clearSearch: () => void;
}

export function useMemorySearch({
  workspaceId,
  scope,
  artifactId,
  t,
  onDegraded,
  resetKey,
}: UseMemorySearchOptions): UseMemorySearchResult {
  const [searchInput, setSearchInput] = useState("");
  const [searchResults, setSearchResults] = useState<MemoryEntry[] | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  useEffect(() => {
    setSearchResults(null);
    setSearchError(null);
  }, [resetKey]);

  const handleSearch = useCallback((): void => {
    const query = searchInput.trim();
    if (!query || !workspaceId) return;
    if (scope === "artifact" && !artifactId) {
      setSearchError(
        t("memory.artifactRequired", "Bitte zuerst ein Artefakt auswählen.")
      );
      return;
    }
    setIsSearching(true);
    setSearchError(null);
    memoryApi
      .searchWorkspaceMemory(workspaceId, {
        q: query,
        scope,
        artifact_id: scope === "artifact" ? artifactId : undefined,
        top_k: 20,
      })
      .then((result) => {
        setSearchResults(result.items);
        onDegraded(result.degraded);
      })
      .catch((err: unknown) => {
        setSearchResults([]);
        setSearchError(
          formatMemoryErrorMessage(err, t("memory.searchError", "Suche fehlgeschlagen."))
        );
      })
      .finally(() => setIsSearching(false));
  }, [searchInput, workspaceId, scope, artifactId, t, onDegraded]);

  const clearSearch = useCallback((): void => {
    setSearchInput("");
    setSearchResults(null);
    setSearchError(null);
  }, []);

  return {
    searchInput,
    searchResults,
    isSearching,
    searchError,
    setSearchInput,
    handleSearch,
    clearSearch,
  };
}
