/**
 * ARCH-L1-001 ReactFrontend — WorkspaceCard.
 *
 * leaf_id: COMP-RF-002 (DashboardViews)
 * req_id:  REQ-L3-RF002-001 (Workspace-Kartenliste mit Metriken),
 *          REQ-L3-RF002-002 (Terminologie-Profil-Label-Rendering),
 *          REQ-L3-RF002-003 (Navigation von Dashboard zu Workspace-Detail)
 */

import { useState, type CSSProperties } from "react";
import { useTranslation } from "react-i18next";
import type { WorkspaceWithMetrics } from "../../types";
import { useWorkspace } from "../../context/WorkspaceContext";

// Hoisted, not an inline object literal on the element itself — see the
// ui-ratchet.test.ts frozen baseline (Task 7.4 "Sperrklinke") for inline
// style usage in components/: the count must never increase, only decrease.
const ACTIVE_BADGE_STYLE: CSSProperties = {
  fontSize: "var(--font-size-xs)",
  fontWeight: 600,
  color: "var(--color-badge-info-text)",
  background: "var(--color-badge-info-bg)",
  border: "1px solid var(--color-primary)",
  borderRadius: "var(--radius-full)",
  padding: "1px 8px",
  whiteSpace: "nowrap",
  lineHeight: 1.6,
};

interface WorkspaceCardProps {
  workspace: WorkspaceWithMetrics;
  onSelect: (workspace: WorkspaceWithMetrics) => void;
  onOpenSettings: (workspace: WorkspaceWithMetrics) => void;
  /**
   * BUG-18 (docs/SYSTEMAUDIT_2026-08-18.md §4): the Dashboard workspace grid
   * previously had no way to tell which of the (potentially dozens of)
   * cards was the currently active workspace — unlike the sidebar
   * workspace switcher, which already marks the active entry.
   */
  isActive?: boolean;
}

export function WorkspaceCard({
  workspace,
  onSelect,
  onOpenSettings,
  isActive = false,
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
      data-active={isActive ? "true" : "false"}
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
        // BUG-18: the active card gets a distinct accent border/ring so it
        // stands out from the rest of the grid at a glance, in addition to
        // the explicit text badge below (border color alone is not
        // sufficient for a11y — WCAG SC 1.4.1 Use of Color).
        border: isActive
          ? "2px solid var(--color-primary)"
          : "1px solid var(--color-border)",
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
              display: "flex",
              alignItems: "center",
              gap: "var(--space-2)",
            }}
          >
            {workspace.name}
            {isActive && (
              <span
                data-testid="workspace-card-active-badge"
                title={t("dashboard.activeWorkspace")}
                style={ACTIVE_BADGE_STYLE}
              >
                {t("dashboard.activeWorkspace")}
              </span>
            )}
          </h3>
          <button
            type="button"
            data-testid="workspace-card-preset-badge"
            title={t("dashboard.changeMode")}
            aria-label={t("dashboard.changeMode")}
            onClick={(e) => {
              e.stopPropagation();
              onOpenSettings(workspace);
            }}
            style={{
              background: "var(--color-badge-draft)",
              color: "var(--color-badge-draft-text)",
              borderRadius: "var(--radius-full)",
              fontSize: "var(--font-size-sm)",
              padding: "2px 10px",
              fontWeight: 600,
              whiteSpace: "nowrap",
              flexShrink: 0,
              border: "none",
              cursor: "pointer",
              font: "inherit",
            }}
          >
            {workspace.preset}
          </button>
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
