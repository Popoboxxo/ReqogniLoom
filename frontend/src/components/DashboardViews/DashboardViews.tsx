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

import React from "react";
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

  if (isLoading) {
    return <p role="status">{t("loading")}</p>;
  }

  if (error) {
    return (
      <div role="alert">
        <p style={{ color: "red" }}>{error}</p>
        <button onClick={() => window.location.reload()}>
          {t("actions.reload")}
        </button>
      </div>
    );
  }

  return (
    <div>
      <h2>{t("nav.dashboard")}</h2>
      {workspaces.length === 0 ? (
        <p>{t("dashboard.empty")}</p>
      ) : (
        <div
          data-testid="workspace-list"
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: "1rem",
            marginTop: "1rem",
          }}
        >
          {workspaces.map((ws) => (
            <WorkspaceCard
              key={ws.id}
              workspace={ws}
              onSelect={handleSelectWorkspace}
            />
          ))}
        </div>
      )}
    </div>
  );
}
