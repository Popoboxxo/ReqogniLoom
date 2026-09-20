/**
 * ARCH-L1-001 ReactFrontend -- MemoryPage ("Gedächtnis", RFC #1002, PR D).
 *
 * Workspace-visible hub over the three memory tiers:
 *   - Team     (`scope="workspace"`) -- workspace-scoped facts.
 *   - Meins    (`scope="user"`)      -- the caller's own user-scoped facts.
 *   - Artefakt (`scope="artifact"`)  -- facts of a chosen artifact.
 *
 * Supports semantic search (`/memory/search/`) alongside a plain substring
 * filter (the list endpoint's `q`), a contributor filter, an add-fact dialog
 * and per-row promote (own user facts, Editor+) / forget (owner or
 * Workspace-Admin -- mirrors `memory/policy.py`'s delete matrix).
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { getAllPages, extractApiErrorMessage } from "../../api/client";
import { memoryApi, type MemoryEntry, type MemoryScope } from "../../api/memory";
import { useWorkspace } from "../../context/WorkspaceContext";
import { useHasRole } from "../../hooks/useHasRole";
import type { Artifact } from "../../types";
import { ConfirmDialog } from "../shared/ConfirmDialog";
import { PageHeader } from "../shared/PageHeader";
import { AddMemoryFactDialog } from "./AddMemoryFactDialog";
import { contributorLabel, formatMemoryDate } from "./memory-format";
import styles from "./MemoryPage.module.css";

type MemoryTab = Extract<MemoryScope, "workspace" | "user" | "artifact">;

const PAGE_SIZE = 25;
const FILTER_DEBOUNCE_MS = 300;

const TABS: MemoryTab[] = ["workspace", "user", "artifact"];

const TAB_LABEL_KEYS: Record<MemoryTab, string> = {
  workspace: "memory.tab.workspace",
  user: "memory.tab.user",
  artifact: "memory.tab.artifact",
};

const SCOPE_LABEL_KEYS: Record<MemoryScope, string> = {
  workspace: "memory.scope.workspace",
  user: "memory.scope.user",
  artifact: "memory.scope.artifact",
};

export function MemoryPage(): JSX.Element {
  const { t } = useTranslation();
  const { activeWorkspace } = useWorkspace();
  const hasRole = useHasRole();
  const workspaceId = activeWorkspace?.id;

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

  // --- semantic search --------------------------------------------------
  const [searchInput, setSearchInput] = useState("");
  const [searchResults, setSearchResults] = useState<MemoryEntry[] | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  // --- actions ----------------------------------------------------------
  const [showAddFact, setShowAddFact] = useState(false);
  const [pendingForget, setPendingForget] = useState<MemoryEntry | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  // Monotonic request id so a stale response can never overwrite fresh state.
  const requestIdRef = useRef(0);

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
                artifact_id:
                  activeTab === "artifact" ? artifactId : undefined,
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
            extractApiErrorMessage(err) ??
              t("memory.loadError", "Gedächtnis konnte nicht geladen werden.")
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
    setSearchResults(null);
    setSearchError(null);
    loadEntries(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, workspaceId, artifactId, contributorId, filterQuery]);

  const handleFilterChange = (value: string): void => {
    setFilterInput(value);
    if (filterDebounceRef.current) clearTimeout(filterDebounceRef.current);
    filterDebounceRef.current = setTimeout(
      () => setFilterQuery(value),
      FILTER_DEBOUNCE_MS
    );
  };

  const handleContributorApply = (): void => {
    setContributorId(contributorInput.trim());
  };

  const handleSearch = (): void => {
    const query = searchInput.trim();
    if (!query || !workspaceId) return;
    if (activeTab === "artifact" && !artifactId) {
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
        scope: activeTab,
        artifact_id: activeTab === "artifact" ? artifactId : undefined,
        top_k: 20,
      })
      .then((result) => {
        setSearchResults(result.items);
        setIsDegraded(result.degraded);
      })
      .catch((err: unknown) => {
        setSearchResults([]);
        setSearchError(
          extractApiErrorMessage(err) ??
            t("memory.searchError", "Suche fehlgeschlagen.")
        );
      })
      .finally(() => setIsSearching(false));
  };

  const clearSearch = (): void => {
    setSearchInput("");
    setSearchResults(null);
    setSearchError(null);
  };

  const handlePromote = async (entry: MemoryEntry): Promise<void> => {
    if (!workspaceId) return;
    setBusyId(entry.entry_id);
    setActionError(null);
    try {
      await memoryApi.promoteEntry(entry.entry_id, { workspace_id: workspaceId });
      loadEntries(page);
    } catch (err: unknown) {
      setActionError(
        extractApiErrorMessage(err) ??
          t("memory.action.promoteError", "Befördern fehlgeschlagen.")
      );
    } finally {
      setBusyId(null);
    }
  };

  const handleForget = async (): Promise<void> => {
    if (!pendingForget) return;
    const entryId = pendingForget.entry_id;
    setPendingForget(null);
    setBusyId(entryId);
    setActionError(null);
    try {
      await memoryApi.forgetEntry(entryId);
      loadEntries(page);
    } catch (err: unknown) {
      setActionError(
        extractApiErrorMessage(err) ??
          t("memory.action.forgetError", "Vergessen fehlgeschlagen.")
      );
    } finally {
      setBusyId(null);
    }
  };

  const handleCreated = (): void => {
    setShowAddFact(false);
    loadEntries(1);
  };

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const isShowingSearch = searchResults !== null;

  const renderEntry = (entry: MemoryEntry): JSX.Element => {
    const isBusy = busyId === entry.entry_id;
    const canPromote = entry.scope === "user" && hasRole("editor");
    const canForget = entry.scope === "user" || hasRole("admin");
    return (
      <li
        key={entry.entry_id}
        className={styles.row}
        data-testid={`memory-row-${entry.entry_id}`}
      >
        <div className={styles.rowMain}>
          <p className={styles.content}>{entry.content}</p>
          <div className={styles.metaRow}>
            <span
              className={styles.scopeBadge}
              data-testid={`memory-scope-${entry.entry_id}`}
            >
              {t(SCOPE_LABEL_KEYS[entry.scope], entry.scope)}
            </span>
            <span
              className={styles.badge}
              data-testid={`memory-contributor-${entry.entry_id}`}
            >
              {contributorLabel(entry, t)}
            </span>
            <span className={styles.meta} data-testid={`memory-date-${entry.entry_id}`}>
              {formatMemoryDate(entry.created_at)}
            </span>
          </div>
        </div>
        <div className={styles.rowActions}>
          {canPromote && (
            <button
              type="button"
              className="btn-secondary"
              data-testid={`memory-promote-${entry.entry_id}`}
              disabled={isBusy}
              onClick={() => void handlePromote(entry)}
            >
              {t("memory.action.promote", "Als Team-Fakt befördern")}
            </button>
          )}
          {canForget && (
            <button
              type="button"
              className={styles.forgetBtn}
              data-testid={`memory-forget-${entry.entry_id}`}
              disabled={isBusy}
              onClick={() => {
                setActionError(null);
                setPendingForget(entry);
              }}
            >
              {t("memory.action.forget", "Vergessen")}
            </button>
          )}
        </div>
      </li>
    );
  };

  const summary = useMemo(() => {
    if (!hasLoaded) return undefined;
    return t("memory.summary", {
      count: total,
      defaultValue: "{{count}} Fakten",
    });
  }, [hasLoaded, total, t]);

  // RFC #1002 PR D: the hub is workspace-bound. Without an active workspace
  // every scope would resolve to a phantom id, so render one explicit empty
  // state instead — while keeping `data-testid="memory-page"` mounted so the
  // `/memory` route never looks broken.
  if (!activeWorkspace) {
    return (
      <div data-testid="memory-page" className={styles.page}>
        <PageHeader title={t("memory.title", "Gedächtnis")} />
        <p data-testid="memory-no-workspace" className={styles.empty}>
          {t("memory.noWorkspace", "Kein Workspace ausgewählt.")}
        </p>
      </div>
    );
  }

  return (
    <div data-testid="memory-page" className={styles.page}>
      <PageHeader title={t("memory.title", "Gedächtnis")} summary={summary} />

      <p className={styles.hint}>
        {t(
          "memory.pageHint",
          "Fakten, die die KI sich über Team, dich oder einzelne Artefakte gemerkt hat. Du kannst suchen, filtern, Fakten hinzufügen, ins Team befördern oder vergessen."
        )}
      </p>

      <div className={styles.tabRow} role="tablist" aria-label={t("memory.title", "Gedächtnis")}>
        {TABS.map((tab) => (
          <button
            key={tab}
            type="button"
            role="tab"
            aria-selected={activeTab === tab}
            data-testid={`memory-tab-${tab}`}
            className={activeTab === tab ? styles.tabActive : styles.tab}
            onClick={() => setActiveTab(tab)}
          >
            {t(TAB_LABEL_KEYS[tab], tab)}
          </button>
        ))}
        <div className={styles.tabSpacer} />
        {hasRole("editor") && (
          <button
            type="button"
            className="btn-primary"
            data-testid="memory-add-fact-btn"
            onClick={() => setShowAddFact(true)}
          >
            {t("memory.add.title", "Fakt hinzufügen")}
          </button>
        )}
      </div>

      {isDegraded && (
        <p
          role="status"
          data-testid="memory-degraded-banner"
          className={styles.degraded}
        >
          {t("memory.degraded", "Gedächtnis aktuell nicht erreichbar.")}
        </p>
      )}

      <div className={styles.controlsRow}>
        <div className={styles.searchGroup}>
          <input
            type="search"
            data-testid="memory-search-input"
            className={styles.input}
            value={searchInput}
            placeholder={t("memory.searchPlaceholder", "Semantisch suchen …")}
            aria-label={t("memory.searchPlaceholder", "Semantisch suchen …")}
            onChange={(e) => setSearchInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                handleSearch();
              }
            }}
          />
          <button
            type="button"
            className="btn-secondary"
            data-testid="memory-search-submit"
            disabled={isSearching || !searchInput.trim()}
            onClick={handleSearch}
          >
            {isSearching ? "…" : t("memory.searchButton", "Suchen")}
          </button>
          {isShowingSearch && (
            <button
              type="button"
              className={styles.linkBtn}
              data-testid="memory-search-clear"
              onClick={clearSearch}
            >
              {t("memory.searchClear", "Suche zurücksetzen")}
            </button>
          )}
        </div>

        <div className={styles.filterGroup}>
          <input
            type="text"
            data-testid="memory-filter-input"
            className={styles.input}
            value={filterInput}
            placeholder={t("memory.filterPlaceholder", "Textfilter …")}
            aria-label={t("memory.filterPlaceholder", "Textfilter …")}
            onChange={(e) => handleFilterChange(e.target.value)}
          />
          {activeTab === "workspace" && (
            <>
              <input
                type="text"
                data-testid="memory-contributor-input"
                className={styles.input}
                value={contributorInput}
                placeholder={t("memory.contributorPlaceholder", "Beitragender (UUID)")}
                aria-label={t("memory.contributorPlaceholder", "Beitragender (UUID)")}
                onChange={(e) => setContributorInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    handleContributorApply();
                  }
                }}
              />
              <button
                type="button"
                className="btn-secondary"
                data-testid="memory-contributor-apply"
                onClick={handleContributorApply}
              >
                {t("memory.contributorApply", "Filter anwenden")}
              </button>
            </>
          )}
          {activeTab === "artifact" && (
            <select
              data-testid="memory-artifact-select"
              className={styles.input}
              aria-label={t("memory.artifactSelect", "Artefakt auswählen")}
              value={artifactId}
              onChange={(e) => setArtifactId(e.target.value)}
            >
              <option value="">
                {t("memory.artifactSelectPlaceholder", "Artefakt auswählen …")}
              </option>
              {artifacts.map((artifact) => (
                <option key={artifact.id} value={artifact.id}>
                  {`${artifact.artifact_type} · ${artifact.id.slice(0, 8)}`}
                </option>
              ))}
            </select>
          )}
        </div>
      </div>

      {searchError && (
        <p role="alert" data-testid="memory-search-error" className={styles.error}>
          {searchError}
        </p>
      )}
      {loadError && (
        <p role="alert" data-testid="memory-load-error" className={styles.error}>
          {loadError}
        </p>
      )}
      {actionError && (
        <p role="alert" data-testid="memory-action-error" className={styles.error}>
          {actionError}
        </p>
      )}

      {isLoading && !isShowingSearch && (
        <p role="status" data-testid="memory-loading" className={styles.loading}>
          {t("loading", "Loading...")}
        </p>
      )}

      {isShowingSearch && (
        <div data-testid="memory-search-results">
          {isSearching && (
            <p role="status" data-testid="memory-search-loading" className={styles.loading}>
              {t("loading", "Loading...")}
            </p>
          )}
          {!isSearching && searchResults.length === 0 && !searchError && (
            <p data-testid="memory-search-empty" className={styles.empty}>
              {t("memory.searchEmpty", "Keine Treffer.")}
            </p>
          )}
          {!isSearching && searchResults.length > 0 && (
            <ul className={styles.list} data-testid="memory-search-list">
              {searchResults.map(renderEntry)}
            </ul>
          )}
        </div>
      )}

      {!isShowingSearch && !isLoading && !loadError && hasLoaded && entries.length === 0 && (
        <p data-testid="memory-empty" className={styles.empty}>
          {activeTab === "artifact" && !artifactId
            ? t("memory.artifactRequired", "Bitte zuerst ein Artefakt auswählen.")
            : t("memory.empty", "Noch keine Fakten in diesem Bereich.")}
        </p>
      )}

      {!isShowingSearch && !isLoading && entries.length > 0 && (
        <>
          <ul className={styles.list} data-testid="memory-list">
            {entries.map(renderEntry)}
          </ul>
          {total > PAGE_SIZE && (
            <div className={styles.pagination}>
              <button
                type="button"
                className={styles.pageButton}
                data-testid="memory-page-prev"
                disabled={page <= 1 || isLoading}
                onClick={() => loadEntries(page - 1)}
              >
                {t("systemSettings.memory.viz.prev", "Zurück")}
              </button>
              <span className={styles.pageInfo}>
                {t("systemSettings.memory.viz.pageInfo", "Seite {{page}} / {{totalPages}}", {
                  page,
                  totalPages,
                })}
              </span>
              <button
                type="button"
                className={styles.pageButton}
                data-testid="memory-page-next"
                disabled={page >= totalPages || isLoading}
                onClick={() => loadEntries(page + 1)}
              >
                {t("systemSettings.memory.viz.next", "Weiter")}
              </button>
            </div>
          )}
        </>
      )}

      {showAddFact && (
        <AddMemoryFactDialog
          workspaceId={workspaceId}
          artifacts={artifacts}
          defaultScope={activeTab === "artifact" ? "artifact" : "workspace"}
          onClose={() => setShowAddFact(false)}
          onCreated={handleCreated}
        />
      )}

      {pendingForget && (
        <ConfirmDialog
          title={t("memory.action.forget", "Vergessen")}
          message={t(
            "memory.action.forgetConfirm",
            "Diesen Fakt endgültig vergessen? Das kann nicht rückgängig gemacht werden."
          )}
          confirmLabel={t("memory.action.forget", "Vergessen")}
          onConfirm={() => void handleForget()}
          onCancel={() => setPendingForget(null)}
          testId="memory-forget-confirm"
        />
      )}
    </div>
  );
}
