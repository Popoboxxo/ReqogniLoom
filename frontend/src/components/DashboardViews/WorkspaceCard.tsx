/**
 * ARCH-L1-001 ReactFrontend — WorkspaceCard.
 *
 * leaf_id: COMP-RF-002 (DashboardViews)
 * req_id:  REQ-L3-RF002-001 (Workspace-Kartenliste mit Metriken),
 *          REQ-L3-RF002-002 (Terminologie-Profil-Label-Rendering),
 *          REQ-L3-RF002-003 (Navigation von Dashboard zu Workspace-Detail)
 */

import React from "react";
import { useTranslation } from "react-i18next";
import type { WorkspaceWithMetrics } from "../../types";
import { useWorkspace } from "../../context/WorkspaceContext";

interface WorkspaceCardProps {
  workspace: WorkspaceWithMetrics;
  onSelect: (workspace: WorkspaceWithMetrics) => void;
}

export function WorkspaceCard({
  workspace,
  onSelect,
}: WorkspaceCardProps): JSX.Element {
  const { t } = useTranslation();
  const { terminologyLabel } = useWorkspace();

  // Use terminology-profile-aware label (REQ-L3-RF002-002)
  const reqLabel = terminologyLabel("requirements");

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => onSelect(workspace)}
      onKeyDown={(e) => e.key === "Enter" && onSelect(workspace)}
      style={{
        border: "1px solid #ddd",
        borderRadius: "8px",
        padding: "1.25rem",
        cursor: "pointer",
        background: "#fff",
        transition: "box-shadow 0.15s",
        minWidth: "220px",
      }}
      onMouseEnter={(e) =>
        ((e.currentTarget as HTMLDivElement).style.boxShadow =
          "0 2px 8px rgba(0,0,0,0.12)")
      }
      onMouseLeave={(e) =>
        ((e.currentTarget as HTMLDivElement).style.boxShadow = "none")
      }
    >
      <h3 style={{ margin: "0 0 0.75rem" }}>{workspace.name}</h3>
      <div style={{ fontSize: "0.9rem", color: "#444" }}>
        <div>
          {reqLabel}: <strong>{workspace.requirement_count}</strong>
        </div>
        <div>
          {t("dashboard.openItems")}:{" "}
          <strong>{workspace.open_item_count}</strong>
        </div>
        <div style={{ marginTop: "0.5rem", fontStyle: "italic", fontSize: "0.8rem" }}>
          {t("dashboard.preset")}: {workspace.preset} |{" "}
          {workspace.terminology_profile === "dev_mode"
            ? t("settings.devMode")
            : t("settings.seMode")}
        </div>
      </div>
    </div>
  );
}
