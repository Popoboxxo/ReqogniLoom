/**
 * ARCH-L1-001 ReactFrontend — Connection View page (P3 Tasks 3.2–3.4).
 *
 * Route `/connections`. Header view switcher
 * [Baum | Zwei Spalten | Matrix | Graph] (default Baum; the card graph is the
 * P5 renderer), quick + free filters, counters from the read object's `meta`,
 * and per-user saved views. All filter state lives in the URL, so the
 * renderers switch without losing a filter and a reload/bookmark restores the
 * same view.
 */

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";

import { allocationViewApi } from "../../api/allocation-view";
import { useHasRole } from "../../hooks/useHasRole";
import { AllocationGraph } from "../AllocationGraph/AllocationGraph";
import { useCardFields } from "../AllocationGraph/useCardFields";
import {
  connectionViewsApi,
  type SavedConnectionView,
} from "../../api/connection-views";
import { FilterBar } from "./FilterBar";
import { MatrixRenderer } from "./MatrixRenderer";
import { TreeRenderer } from "./TreeRenderer";
import { TwoColumnRenderer } from "./TwoColumnRenderer";
import { useAllocationMutations } from "./useAllocationMutations";
import {
  DEFAULT_PAGE_SIZE,
  useAllocationView,
  type ConnectionViewMode,
} from "./useAllocationView";
import styles from "./ConnectionView.module.css";

const STALE_TIME_MS = 60 * 1000;

function newViewId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `view-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export function ConnectionView(): JSX.Element {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const {
    workspaceId,
    view,
    filters,
    requirements,
    allRequirements,
    elements,
    meta,
    isLoading,
    isFetching,
    error,
    setView,
    setFilters,
    resetFilters,
    setPage,
  } = useAllocationView();
  const { allocate, deallocate } = useAllocationMutations();
  const hasRole = useHasRole();
  const canEdit = hasRole("editor");
  const cardFields = useCardFields(workspaceId);

  const tiersQuery = useQuery({
    queryKey: ["workspace-tiers", workspaceId],
    queryFn: () => allocationViewApi.tiers(workspaceId as string),
    enabled: Boolean(workspaceId),
    staleTime: STALE_TIME_MS,
  });

  const [savedViews, setSavedViews] = useState<SavedConnectionView[]>([]);

  useEffect(() => {
    let active = true;
    void connectionViewsApi.load().then((views) => {
      if (!active) return;
      // A view saved while the read was in flight is newer than the response;
      // never let the initial load clobber it.
      setSavedViews((previous) => (previous.length > 0 ? previous : views));
    });
    return () => {
      active = false;
    };
  }, []);

  const states = useMemo(
    () =>
      Array.from(
        new Set(
          allRequirements
            .map((row) => row.state)
            .filter((state): state is string => Boolean(state))
        )
      ).sort((a, b) => a.localeCompare(b)),
    [allRequirements]
  );

  const categories = useMemo(
    () =>
      Array.from(
        new Set(
          allRequirements
            .map((row) => row.category)
            .filter((category): category is string => Boolean(category))
        )
      ).sort((a, b) => a.localeCompare(b)),
    [allRequirements]
  );

  const viewOptions: Array<{ mode: ConnectionViewMode; label: string }> = [
    { mode: "tree", label: t("connectionView.views.tree") },
    { mode: "two-column", label: t("connectionView.views.twoColumn") },
    { mode: "matrix", label: t("connectionView.views.matrix") },
    { mode: "graph", label: t("connectionView.views.graph") },
  ];

  const persistSavedViews = (views: SavedConnectionView[]): void => {
    setSavedViews(views);
    void connectionViewsApi.save(views);
  };

  const handleSaveView = (name: string): void => {
    const params: Record<string, string> = {};
    searchParams.forEach((value, key) => {
      params[key] = value;
    });
    persistSavedViews([
      ...savedViews,
      { id: newViewId(), name, params },
    ]);
  };

  const handleApplyView = (saved: SavedConnectionView): void => {
    setSearchParams(new URLSearchParams(saved.params), { replace: true });
  };

  const handleDeleteView = (id: string): void => {
    persistSavedViews(savedViews.filter((saved) => saved.id !== id));
  };

  return (
    <section className={styles.page} data-testid="connection-view">
      <header className={styles.header}>
        <h1 className={styles.title}>{t("connectionView.title")}</h1>
        <div
          className={styles.viewSwitcher}
          role="group"
          aria-label={t("connectionView.viewSwitcher")}
        >
          {viewOptions.map((option) => (
            <button
              key={option.mode}
              type="button"
              className={[
                "btn-ghost",
                styles.viewButton,
                view === option.mode ? styles.viewButtonActive : "",
              ]
                .filter(Boolean)
                .join(" ")}
              aria-pressed={view === option.mode}
              data-testid={`view-switch-${option.mode}`}
              onClick={() => setView(option.mode)}
            >
              {option.label}
            </button>
          ))}
        </div>
      </header>

      <FilterBar
        filters={filters}
        meta={meta}
        tiers={tiersQuery.data?.tiers ?? []}
        elements={elements}
        states={states}
        categories={categories}
        savedViews={savedViews}
        onChange={setFilters}
        onReset={resetFilters}
        onSaveView={handleSaveView}
        onApplyView={handleApplyView}
        onDeleteView={handleDeleteView}
      />

      {error && (
        <div
          role="alert"
          className={styles.error}
          data-testid="connection-view-error"
        >
          {error.message}
        </div>
      )}

      {isLoading ? (
        <p className={styles.status} data-testid="connection-view-loading">
          {t("connectionView.loading")}
        </p>
      ) : (
        <div
          className={styles.renderer}
          aria-busy={isFetching ? "true" : "false"}
        >
          {view === "tree" && (
            <TreeRenderer
              requirements={requirements}
              elements={elements}
              allocate={allocate}
              deallocate={deallocate}
            />
          )}
          {view === "two-column" && (
            <TwoColumnRenderer
              requirements={requirements}
              elements={elements}
              allocate={allocate}
              deallocate={deallocate}
            />
          )}
          {view === "matrix" && (
            <MatrixRenderer
              requirements={requirements}
              elements={elements}
              page={filters.page}
              pageSize={filters.pageSize || DEFAULT_PAGE_SIZE}
              onPageChange={setPage}
            />
          )}
          {view === "graph" && (
            <AllocationGraph
              requirements={requirements}
              elements={elements}
              allocate={allocate}
              canEdit={canEdit}
              cardFields={cardFields}
            />
          )}
        </div>
      )}
    </section>
  );
}
