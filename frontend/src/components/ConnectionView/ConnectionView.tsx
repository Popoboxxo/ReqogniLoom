/**
 * ARCH-L1-001 ReactFrontend — Connection View page (P3 Tasks 3.2–3.4).
 *
 * Route `/connections`. Header view switcher
 * [Bäume | Architektur | Zwei Spalten | Matrix | Graph] plus the "Verbindungen
 * anzeigen" switch that owns the edge overlay (V.5), quick + free filters,
 * counters from the read object's `meta`, and per-user saved views. All filter
 * state lives in the URL, so the renderers switch without losing a filter and
 * a reload/bookmark restores the same view.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";

import { allocationViewApi } from "../../api/allocation-view";
import { useHasRole } from "../../hooks/useHasRole";
import { AllocationGraph } from "../AllocationGraph/AllocationGraph";
import { useCardFields } from "../AllocationGraph/useCardFields";
import { useToast } from "../shared/Toast/useToast";
import {
  connectionViewsApi,
  loadFiltersExpanded,
  loadShowEdges,
  saveFiltersExpanded,
  saveShowEdges,
  type SavedConnectionView,
} from "../../api/connection-views";
import { AllocationAssistant } from "./AllocationAssistant";
import { AllocationTreesRenderer } from "./AllocationTreesRenderer";
import { FilterBar } from "./FilterBar";
import { MatrixRenderer } from "./MatrixRenderer";
import { TreeRenderer } from "./TreeRenderer";
import { TwoColumnRenderer } from "./TwoColumnRenderer";
import { useAllocationMutations } from "./useAllocationMutations";
import { useAllocationSelection } from "./useAllocationSelection";
import {
  DEFAULT_PAGE_SIZE,
  useAllocationView,
  type ConnectionViewMode,
} from "./useAllocationView";
import styles from "./ConnectionView.module.css";

const STALE_TIME_MS = 60 * 1000;

/**
 * V.5: the edge overlay's on/off switch is a user preference
 * (`ui.connection_view.show_edges`, plan V.0) and defaults to on. Until the
 * preference read resolves — and when it fails — the documented default keeps
 * the edges visible, so a broken preference store cannot hide them silently.
 */
const SHOW_EDGES_DEFAULT = true;

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
    groups,
    meta,
    isLoading,
    isFetching,
    error,
    elementsError,
    elementsLoading,
    setView,
    setFilters,
    resetFilters,
    setPage,
  } = useAllocationView();
  const { allocate, allocateBulk, deallocate } = useAllocationMutations();
  const hasRole = useHasRole();
  const canEdit = hasRole("editor");
  const cardFields = useCardFields(workspaceId);
  // V.3: the tree renderer's selection. It is created here (not inside the
  // renderer) so the V.4 action bar reads the same selection instead of keeping
  // a second one. The assistant is presentational since V.4 — this hook is the
  // only selection state in the connection view.
  const selection = useAllocationSelection(requirements);

  const tiersQuery = useQuery({
    queryKey: ["workspace-tiers", workspaceId],
    queryFn: () => allocationViewApi.tiers(workspaceId as string),
    enabled: Boolean(workspaceId),
    staleTime: STALE_TIME_MS,
  });

  const [savedViews, setSavedViews] = useState<SavedConnectionView[]>([]);
  // A rejected preference write is reported here instead of surfacing as an
  // unhandled promise rejection; the in-memory list is kept so the user can
  // retry the save without re-entering the name.
  const { message: savedViewsError, show: showSavedViewsError } = useToast();

  // V.4: the "Weitere Filter" row's visibility is a user preference, not URL
  // state (design §5.5). The local value is authoritative; a failed write only
  // adds a message, it never closes the popover.
  const [filtersExpanded, setFiltersExpanded] = useState(false);
  const [filtersExpandedError, setFiltersExpandedError] = useState<
    string | null
  >(null);
  /** A click before the preference read resolves wins over the stored value. */
  const filtersToggledRef = useRef(false);

  useEffect(() => {
    let active = true;
    void loadFiltersExpanded().then((expanded) => {
      if (!active || filtersToggledRef.current) return;
      setFiltersExpanded(expanded);
    });
    return () => {
      active = false;
    };
  }, []);

  const toggleFiltersExpanded = (): void => {
    filtersToggledRef.current = true;
    const next = !filtersExpanded;
    setFiltersExpanded(next);
    setFiltersExpandedError(null);
    void saveFiltersExpanded(next).catch((err: unknown) => {
      // Keep the popover open: the local state is what the user just asked for.
      setFiltersExpandedError(
        t("connectionView.filters.preferenceFailed", {
          message: err instanceof Error ? err.message : String(err),
        })
      );
    });
  };

  // V.5: the header switch "Verbindungen anzeigen" owns the edge overlay. It is
  // a user preference, never URL state — and it only hides the overlay, the
  // target text on every row stays.
  const [showEdges, setShowEdges] = useState(SHOW_EDGES_DEFAULT);
  const [showEdgesError, setShowEdgesError] = useState<string | null>(null);
  /** A click before the preference read resolves wins over the stored value. */
  const showEdgesToggledRef = useRef(false);

  useEffect(() => {
    let active = true;
    void loadShowEdges().then((enabled) => {
      if (!active || showEdgesToggledRef.current) return;
      setShowEdges(enabled);
    });
    return () => {
      active = false;
    };
  }, []);

  const toggleShowEdges = (): void => {
    showEdgesToggledRef.current = true;
    const next = !showEdges;
    setShowEdges(next);
    setShowEdgesError(null);
    void saveShowEdges(next).catch((err: unknown) => {
      // The local state stays authoritative: a failed write must not flip the
      // switch back under the user's hand.
      setShowEdgesError(
        t("connectionView.showEdgesFailed", {
          message: err instanceof Error ? err.message : String(err),
        })
      );
    });
  };

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
    // V.5: five entries, `Bäume` first and default (S0 = option a).
    { mode: "trees", label: t("connectionView.views.trees") },
    { mode: "architecture", label: t("connectionView.views.architecture") },
    { mode: "two-column", label: t("connectionView.views.twoColumn") },
    { mode: "matrix", label: t("connectionView.views.matrix") },
    { mode: "graph", label: t("connectionView.views.graph") },
  ];

  const persistSavedViews = (views: SavedConnectionView[]): void => {
    setSavedViews(views);
    void connectionViewsApi.save(views).catch((err: unknown) => {
      showSavedViewsError(
        t("connectionView.savedViews.saveFailed", {
          message: err instanceof Error ? err.message : String(err),
        })
      );
    });
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
        <div className={styles.viewControls}>
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
          {/*
           * V.5 (spec 5.1/5.8.13): the switch hides the edge overlay only. The
           * target text on every row ("→ Bremse" / "nicht allokiert") stays, so
           * the allocation never depends on a line being drawn.
           */}
          <label className={styles.checkboxLabel}>
            <input
              type="checkbox"
              data-testid="connection-view-show-edges"
              checked={showEdges}
              onChange={toggleShowEdges}
            />
            {t("connectionView.showEdges")}
          </label>
        </div>
      </header>

      {showEdgesError && (
        <p
          role="alert"
          className={styles.error}
          data-testid="connection-view-show-edges-error"
        >
          {showEdgesError}
        </p>
      )}

      <AllocationAssistant
        selection={selection}
        requirements={requirements}
        elements={elements}
        allocateBulk={allocateBulk}
        suggestArchitecture={allocationViewApi.suggestArchitecture}
        canEdit={canEdit}
      />

      <FilterBar
        filters={filters}
        meta={meta}
        tiers={tiersQuery.data?.tiers ?? []}
        elements={elements}
        groups={groups}
        states={states}
        categories={categories}
        savedViews={savedViews}
        expanded={filtersExpanded}
        onToggleExpanded={toggleFiltersExpanded}
        expandedError={filtersExpandedError}
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

      {savedViewsError && (
        <p
          role="alert"
          className={styles.error}
          data-testid="connection-view-saved-views-error"
        >
          {savedViewsError}
        </p>
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
          {view === "architecture" && (
            <TreeRenderer
              requirements={requirements}
              elements={elements}
              allocate={allocate}
              deallocate={deallocate}
              elementsError={elementsError}
              elementsLoading={elementsLoading}
            />
          )}
          {view === "two-column" && (
            <TwoColumnRenderer
              requirements={requirements}
              elements={elements}
              allocate={allocate}
              deallocate={deallocate}
              elementsError={elementsError}
              elementsLoading={elementsLoading}
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
          {view === "trees" && (
            <AllocationTreesRenderer
              requirements={requirements}
              elements={elements}
              selection={selection}
              showEdges={showEdges}
              onAllocate={allocate}
              onDeallocate={deallocate}
              canEdit={canEdit}
            />
          )}
        </div>
      )}
    </section>
  );
}
