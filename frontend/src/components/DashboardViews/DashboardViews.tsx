/**
 * ARCH-L1-001 ReactFrontend — DashboardViews (COMP-RF-002).
 *
 * leaf_id: COMP-RF-002
 * req_id:  REQ-L2-RF-002 (Dashboard mit Projektübersicht),
 *          REQ-L3-RF002-001 (Workspace-Kartenliste mit Metriken),
 *          REQ-L3-RF002-002 (Terminologie-Profil-Label-Rendering),
 *          REQ-L3-RF002-003 (Navigation von Dashboard zu Workspace-Detail)
 *
 * Interfaces implemented:
 *   IF-RF-INT-001  ← NavigationShell activates this view
 *   IF-RF-INT-002  ← I18nService via useTranslation + TerminologyContext
 *   IF-RF-EXT-OUT-001 → GET /api/v1/requirements/ (for metrics)
 */

import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { useDashboardData } from "./useDashboardData";
import { WorkspaceCard } from "./WorkspaceCard";
import { useWorkspace } from "../../context/WorkspaceContext";
import type { WorkspaceWithMetrics } from "../../types";
import { ListToolbar } from "../shared/ListToolbar";
import { PageHeader } from "../shared/PageHeader";
import styles from "./DashboardViews.module.css";

/*
 * UI-consistency P2: the dashboard grid renders every workspace of the
 * tenant (86+ on a long-lived stack) with no way to narrow it down — the
 * sidebar's global search targets artifacts, not workspaces. `ListToolbar`
 * is the project's existing search-control pattern, but it is built for the
 * narrow left-hand list panels of the artifact routes and stretches its
 * input to 100% of its container; this wrapper caps it at a sensible width
 * on the full-page dashboard.
 *
 * Deliberately no `countLabel`: PageHeader's summary already states the
 * total, and a second, unmasked, environment-dependent count next to the
 * grid would make `visual-regression.spec.ts`'s dashboard screenshot
 * volatile (it masks `workspace-list` and `page-header-count` for exactly
 * that reason). The wrapper now uses `.searchRow` from the module (Issue
 * #876, Etappe 7) instead of a hoisted inline-style constant.
 */

/*
 * L-03: the card grid's closing rule (and the responsive column contract from
 * #806 — `auto-fit` tracks so a short list fills the row instead of leaving
 * the rest of it empty) now live in `DashboardViews.module.css`.
 *
 * The rule lives *inside* `[data-testid="workspace-list"]`, which
 * `e2e/tests/visual-regression.spec.ts` caps to a fixed height and masks —
 * so the dashboard baseline's geometry is unaffected.
 */
export default function DashboardViews(): JSX.Element {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { activeWorkspace, setActiveWorkspace } = useWorkspace();
  const { workspaces, isLoading, error } = useDashboardData();
  const [search, setSearch] = useState("");

  // Client-side only: `useDashboardData` has already loaded the full list,
  // so filtering by name needs no additional request.
  const visibleWorkspaces = useMemo(() => {
    const needle = search.trim().toLowerCase();
    if (needle === "") return workspaces;
    return workspaces.filter((ws) => ws.name.toLowerCase().includes(needle));
  }, [workspaces, search]);

  // REQ-L3-RF002-003: navigate to requirements when workspace selected
  const handleSelectWorkspace = (workspace: WorkspaceWithMetrics): void => {
    setActiveWorkspace(workspace);
    navigate("/requirements");
  };

  // UI-06: navigate to workspace settings (SE-mode switch) from the dashboard card
  const handleOpenSettings = (workspace: WorkspaceWithMetrics): void => {
    setActiveWorkspace(workspace);
    navigate("/settings");
  };

  if (isLoading) {
    return (
      <p role="status" className={styles.loading}>
        {t("loading")}
      </p>
    );
  }

  if (error) {
    return (
      <div role="alert" className={styles.errorBox}>
        <p className={styles.errorText}>
          {error}
        </p>
        <button
          onClick={() => window.location.reload()}
          className={styles.reloadBtn}
        >
          {t("actions.reload")}
        </button>
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title={t("nav.dashboard")}
        summary={
          // While a search is active the plain total would contradict what
          // the grid shows, so the summary switches to "shown of total".
          visibleWorkspaces.length === workspaces.length
            ? t("dashboard.summary", { count: workspaces.length })
            : t("dashboard.summaryFiltered", {
                shown: visibleWorkspaces.length,
                total: workspaces.length,
              })
        }
      />
      {workspaces.length > 0 && (
        <div className={styles.searchRow}>
          <ListToolbar
            testIdPrefix="workspace"
            searchValue={search}
            onSearchChange={setSearch}
            searchPlaceholder={t("dashboard.searchPlaceholder")}
            countLabel={null}
          />
        </div>
      )}
      {visibleWorkspaces.length === 0 ? (
        <p data-testid="workspace-list-empty" className={styles.emptyState}>
          {workspaces.length === 0
            ? t("dashboard.empty")
            : t("dashboard.noSearchMatch", { query: search.trim() })}
        </p>
      ) : (
        <div data-testid="workspace-list" className={styles.workspaceGrid}>
          {visibleWorkspaces.map((ws) => (
            <WorkspaceCard
              key={ws.id}
              workspace={ws}
              onSelect={handleSelectWorkspace}
              onOpenSettings={handleOpenSettings}
              isActive={ws.id === activeWorkspace?.id}
            />
          ))}
        </div>
      )}
    </div>
  );
}
