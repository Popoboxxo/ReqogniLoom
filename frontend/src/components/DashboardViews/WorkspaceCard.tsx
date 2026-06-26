/**
 * ARCH-L1-001 ReactFrontend — WorkspaceCard.
 *
 * leaf_id: COMP-RF-002 (DashboardViews)
 * req_id:  REQ-L3-RF002-001 (Workspace-Kartenliste mit Metriken),
 *          REQ-L3-RF002-002 (Terminologie-Profil-Label-Rendering),
 *          REQ-L3-RF002-003 (Navigation von Dashboard zu Workspace-Detail)
 */

import React, { useState } from "react";
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
  const [isHovered, setIsHovered] = useState(false);

  // Use terminology-profile-aware label (REQ-L3-RF002-002)
  const reqLabel = terminologyLabel("requirements");

  const terminologyText =
    workspace.terminology_profile === "dev_mode"
      ? t("settings.devMode")
      : t("settings.seMode");

  return (
    <div
      data-testid="workspace-card"
      role="button"
      tabIndex={0}
      onClick={() => onSelect(workspace)}
      onKeyDown={(e) => e.key === "Enter" && onSelect(workspace)}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      style={{
        position: "relative",
        background: "var(--color-surface)",
        borderRadius: "var(--radius-lg)",
        boxShadow: isHovered
          ? "var(--shadow-md)"
          : "var(--shadow-card)",
        padding: "var(--space-6)",
        minWidth: "260px",
        maxWidth: "320px",
        flex: "1 1 260px",
        cursor: "pointer",
        transition: "var(--transition-normal)",
        transform: isHovered ? "translateY(-2px)" : "translateY(0)",
        border: "1px solid var(--color-border)",
        display: "flex",
        flexDirection: "column",
        gap: "var(--space-4)",
        boxSizing: "border-box",
      }}
    >
      <div>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-start",
            gap: "var(--space-2)",
            marginBottom: "var(--space-3)",
          }}
        >
          <h3
            style={{
              margin: 0,
              fontSize: "var(--font-size-xl)",
              fontWeight: 700,
              color: "var(--color-text)",
              lineHeight: 1.3,
            }}
          >
            {workspace.name}
          </h3>
          <span
            style={{
              background: "var(--color-badge-draft)",
              color: "var(--color-badge-draft-text)",
              borderRadius: "var(--radius-full)",
              fontSize: "var(--font-size-sm)",
              padding: "2px 10px",
              fontWeight: 600,
              whiteSpace: "nowrap",
              flexShrink: 0,
            }}
          >
            {workspace.preset}
          </span>
        </div>
        <div
          style={{
            fontSize: "var(--font-size-sm)",
            color: "var(--color-text-muted)",
          }}
        >
          {terminologyText}
        </div>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "var(--space-4)",
          paddingTop: "var(--space-4)",
          borderTop: "1px solid var(--color-border)",
        }}
      >
        <div style={{ display: "flex", flexDirection: "column" }}>
          <strong
            style={{
              fontSize: "var(--font-size-2xl)",
              fontWeight: 700,
              color: "var(--color-primary)",
              lineHeight: 1.1,
            }}
          >
            {workspace.requirement_count}
          </strong>
          <span
            style={{
              fontSize: "var(--font-size-sm)",
              color: "var(--color-text-muted)",
              marginTop: "var(--space-1)",
            }}
          >
            {reqLabel}
          </span>
        </div>
        <div style={{ display: "flex", flexDirection: "column" }}>
          <strong
            style={{
              fontSize: "var(--font-size-2xl)",
              fontWeight: 700,
              color: "var(--color-primary)",
              lineHeight: 1.1,
            }}
          >
            {workspace.open_item_count}
          </strong>
          <span
            style={{
              fontSize: "var(--font-size-sm)",
              color: "var(--color-text-muted)",
              marginTop: "var(--space-1)",
            }}
          >
            {t("dashboard.openItems")}
          </span>
        </div>
      </div>
    </div>
  );
}
