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

import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { useDashboardData } from "./useDashboardData";
import { WorkspaceCard } from "./WorkspaceCard";
import { useWorkspace } from "../../context/WorkspaceContext";
import type { WorkspaceWithMetrics } from "../../types";

export default function DashboardViews(): JSX.Element {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { setActiveWorkspace } = useWorkspace();
  const { workspaces, isLoading, error } = useDashboardData();

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
      <h1
        style={{
          fontSize: "var(--font-size-2xl)",
          fontWeight: 700,
          color: "var(--color-text)",
          marginTop: 0,
          marginBottom: "var(--space-6)",
        }}
      >
        {t("nav.dashboard")}
      </h1>
      {workspaces.length === 0 ? (
        <p
          style={{
            fontSize: "var(--font-size-base)",
            color: "var(--color-text-muted)",
            padding: "var(--space-6)",
            background: "var(--color-surface-raised)",
            borderRadius: "var(--radius-lg)",
            border: "1px dashed var(--color-border)",
          }}
        >
          {t("dashboard.empty")}
        </p>
      ) : (
        <div
          data-testid="workspace-list"
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: "var(--space-4)",
          }}
        >
          {workspaces.map((ws) => (
            <WorkspaceCard
              key={ws.id}
              workspace={ws}
              onSelect={handleSelectWorkspace}
              onOpenSettings={handleOpenSettings}
            />
          ))}
        </div>
      )}
    </div>
  );
}
