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

import { useMemo, useState, type CSSProperties } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { useDashboardData } from "./useDashboardData";
import { WorkspaceCard } from "./WorkspaceCard";
import { useWorkspace } from "../../context/WorkspaceContext";
import type { WorkspaceWithMetrics } from "../../types";
import { ListToolbar } from "../shared/ListToolbar";
import { PageHeader } from "../shared/PageHeader";

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
 * that reason). Hoisted rather than an inline object literal — see the
 * frozen inline-style baseline in `src/test/ui-ratchet.test.ts`.
 */
const SEARCH_ROW_STYLE: CSSProperties = {
  maxWidth: "360px",
  marginBottom: "var(--space-4)",
};

/*
 * L-03: the card grid used to be a bare wrapping flex row. Because the cards
 * are individually bordered and the last row is usually ragged, the grid had
 * no visible end — the page just stopped, and on a tenant with many
 * workspaces it read as "cut off" rather than "finished". A hairline rule
 * under a padded region closes it off, and matches the bordered box the
 * empty state already renders in the same slot, so both states read as one
 * bounded area.
 *
 * The rule lives *inside* `[data-testid="workspace-list"]`, which
 * `e2e/tests/visual-regression.spec.ts` caps to a fixed height and masks —
 * so the dashboard baseline's geometry is unaffected.
 */
const WORKSPACE_GRID_STYLE: CSSProperties = {
  display: "flex",
  flexWrap: "wrap",
  gap: "var(--space-4)",
  paddingBottom: "var(--space-6)",
  borderBottom: "1px solid var(--color-border)",
};

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
      <p
        role="status"
        style={{
          fontSize: "var(--font-size-base)",
          color: "var(--color-text-muted)",
          padding: "var(--space-6)",
        }}
      >
        {t("loading")}
      </p>
    );
  }

  if (error) {
    return (
      <div
        role="alert"
        style={{
          background: "var(--color-surface)",
          border: "1px solid var(--color-danger)",
          borderRadius: "var(--radius-lg)",
          padding: "var(--space-6)",
          boxShadow: "var(--shadow-card)",
          maxWidth: "480px",
        }}
      >
        <p
          style={{
            color: "var(--color-danger)",
            fontSize: "var(--font-size-base)",
            fontWeight: 600,
            margin: 0,
            marginBottom: "var(--space-4)",
          }}
        >
          {error}
        </p>
        <button
          onClick={() => window.location.reload()}
          style={{
            background: "var(--color-primary)",
            color: "var(--color-surface)",
            border: "none",
            borderRadius: "var(--radius-md)",
            padding: "var(--space-2) var(--space-4)",
            fontSize: "var(--font-size-base)",
            fontWeight: 600,
            cursor: "pointer",
            transition: "var(--transition-fast)",
          }}
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
        <div style={SEARCH_ROW_STYLE}>
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
        <p
          data-testid="workspace-list-empty"
          style={{
            fontSize: "var(--font-size-base)",
            color: "var(--color-text-muted)",
            padding: "var(--space-6)",
            background: "var(--color-surface-raised)",
            borderRadius: "var(--radius-lg)",
            border: "1px dashed var(--color-border)",
          }}
        >
          {workspaces.length === 0
            ? t("dashboard.empty")
            : t("dashboard.noSearchMatch", { query: search.trim() })}
        </p>
      ) : (
        <div data-testid="workspace-list" style={WORKSPACE_GRID_STYLE}>
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
