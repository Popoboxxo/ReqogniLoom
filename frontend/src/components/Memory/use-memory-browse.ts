/**
 * ARCH-L1-001 ReactFrontend — workspace memory browse (#598 S2).
 *
 * Extracted from `MemoryPage.tsx`: the scope tab, the paged entry list, the
 * filters, the artifact selector source and the debounced query.
 *
 * Contract kept verbatim:
 *   - the artifact tab without a chosen artifact clears the list instead of
 *     requesting an unscoped page,
 *   - a monotonic request id keeps a stale response from overwriting fresh
 *     state,
 *   - a failed load clears the rows and keeps its own message; the page never
 *     falls through to the empty state,
 *   - the search box is debounced and the debounce timer is cleared on unmount,
 *   - the contributor filter applies on submit, not per keystroke,
 *   - a failed artifact load only disables the artifact selector.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type { TFunction } from "i18next";

import { getAllPages } from "../../api/client";
import { memoryApi, type MemoryEntry, type MemoryScope } from "../../api/memory";
import type { Artifact } from "../../types";
import { formatMemoryErrorMessage } from "./memory-format";

export const PAGE_SIZE = 25;
const FILTER_DEBOUNCE_MS = 300;

export type MemoryTab = Extract<MemoryScope, "workspace" | "user" | "artifact">;

export interface UseMemoryBrowseOptions {
  workspaceId: string | undefined;
  t: TFunction;
}

export interface UseMemoryBrowseResult {
  activeTab: MemoryTab;
  setActiveTab: (tab: MemoryTab) => void;
  entries: MemoryEntry[];
  total: number;
  page: number;
  setPage: (page: number) => void;
  isLoading: boolean;
  hasLoaded: boolean;
  loadError: string | null;
  isDegraded: boolean;
  setIsDegraded: (value: boolean) => void;
  filterInput: string;
  filterQuery: string;
  handleFilterChange: (value: string) => void;
  contributorInput: string;
  setContributorInput: (value: string) => void;
  contributorId: string;
  handleContributorApply: () => void;
  artifactId: string;
  setArtifactId: (value: string) => void;
  artifacts: Artifact[];
  loadEntries: (targetPage: number) => void;
  totalPages: number;
}

export function useMemoryBrowse({
  workspaceId,
  t,
}: UseMemoryBrowseOptions): UseMemoryBrowseResult {
  const [activeTab, setActiveTab] = useState<MemoryTab>("workspace");

  // --- entry list state -------------------------------------------------
  const [entries, setEntries] = useState<MemoryEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [isLoading, setIsLoading] = useState(false);
  const [hasLoaded, setHasLoaded] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isDegraded, setIsDegraded] = useState(false);

  // --- filters ----------------------------------------------------------
  const [filterInput, setFilterInput] = useState("");
  const [filterQuery, setFilterQuery] = useState("");
  const filterDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [contributorInput, setContributorInput] = useState("");
  const [contributorId, setContributorId] = useState("");
  const [artifactId, setArtifactId] = useState("");
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);

  // Monotonic request id so a stale response can never overwrite fresh state.
  const requestIdRef = useRef(0);

  // FE-04: drop a pending filter-debounce timer when the page unmounts.
  useEffect(() => {
    return () => {
      if (filterDebounceRef.current) clearTimeout(filterDebounceRef.current);
    };
  }, []);

  // Artifact selector source (all pages of the workspace's artifacts).
  useEffect(() => {
    if (!workspaceId) return;
    let cancelled = false;
    getAllPages<Artifact>("/artifacts/", { workspace_id: workspaceId })
      .then((items) => {
        if (!cancelled) setArtifacts(items);
      })
      .catch(() => {
        // A failed artifact load only disables the artifact tab selector;
        // it must not fail the whole page.
        if (!cancelled) setArtifacts([]);
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId]);

  const loadEntries = useCallback(
    (targetPage: number): void => {
      if (!workspaceId) return;
      if (activeTab === "artifact" && !artifactId) {
        setEntries([]);
        setTotal(0);
        setIsDegraded(false);
        setHasLoaded(true);
        setIsLoading(false);
        return;
      }
      const requestId = ++requestIdRef.current;
      setIsLoading(true);
      setLoadError(null);
      const query = filterQuery || undefined;

      const request =
        activeTab === "user"
          ? memoryApi
              .getSelfOverview({
                includeEntries: true,
                page: targetPage,
                pageSize: PAGE_SIZE,
              })
              .then((overview) => ({
                items: overview.entries ?? [],
                total: overview.total ?? 0,
                page: overview.page ?? targetPage,
                pageSize: overview.page_size ?? PAGE_SIZE,
                degraded: overview.degraded,
              }))
          : memoryApi
              .listWorkspaceEntries(workspaceId, {
                scope: activeTab,
                artifact_id: activeTab === "artifact" ? artifactId : undefined,
                contributor_user_id:
                  activeTab === "workspace" ? contributorId || undefined : undefined,
                q: query,
                page: targetPage,
                page_size: PAGE_SIZE,
              })
              .then((result) => ({
                items: result.items,
                total: result.total,
                page: result.page,
                pageSize: result.page_size,
                degraded: result.degraded,
              }));

      request
        .then((result) => {
          if (requestId !== requestIdRef.current) return;
          setEntries(result.items);
          setTotal(result.total);
          setPage(result.page);
          setIsDegraded(result.degraded);
          setHasLoaded(true);
        })
        .catch((err: unknown) => {
          if (requestId !== requestIdRef.current) return;
          setLoadError(
            formatMemoryErrorMessage(
              err,
              t("memory.loadError", "Gedächtnis konnte nicht geladen werden.")
            )
          );
          setEntries([]);
          setIsDegraded(false);
          setHasLoaded(true);
        })
        .finally(() => {
          if (requestId === requestIdRef.current) setIsLoading(false);
        });
    },
    [activeTab, workspaceId, artifactId, contributorId, filterQuery, t]
  );

  // Reload from page 1 whenever the tab or a filter changes.
  useEffect(() => {
    loadEntries(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, workspaceId, artifactId, contributorId, filterQuery]);

  const handleFilterChange = useCallback((value: string): void => {
    setFilterInput(value);
    if (filterDebounceRef.current) clearTimeout(filterDebounceRef.current);
    filterDebounceRef.current = setTimeout(
      () => setFilterQuery(value),
      FILTER_DEBOUNCE_MS
    );
  }, []);

  const handleContributorApply = useCallback((): void => {
    setContributorId(contributorInput.trim());
  }, [contributorInput]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return {
    activeTab,
    setActiveTab,
    entries,
    total,
    page,
    setPage,
    isLoading,
    hasLoaded,
    loadError,
    isDegraded,
    setIsDegraded,
    filterInput,
    filterQuery,
    handleFilterChange,
    contributorInput,
    setContributorInput,
    contributorId,
    handleContributorApply,
    artifactId,
    setArtifactId,
    artifacts,
    loadEntries,
    totalPages,
  };
}
