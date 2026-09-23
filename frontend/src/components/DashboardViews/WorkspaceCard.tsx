/**
 * ARCH-L1-001 ReactFrontend — WorkspaceCard.
 *
 * leaf_id: COMP-RF-002 (DashboardViews)
 * req_id:  REQ-L3-RF002-001 (Workspace-Kartenliste mit Metriken),
 *          REQ-L3-RF002-002 (Terminologie-Profil-Label-Rendering),
 *          REQ-L3-RF002-003 (Navigation von Dashboard zu Workspace-Detail)
 */

import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { WorkspaceWithMetrics } from "../../types";
import { useWorkspace } from "../../context/WorkspaceContext";
import styles from "./WorkspaceCard.module.css";

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
    // GESAMTTEST_BERICHT_2026-08-21.md §5 finding 6: `data-testid="workspace-card"`
    // stays on this OUTER, non-interactive wrapper (not on the role="button"
    // region below) — several e2e specs (e.g. dashboard.spec.ts's terminology
    // label test) read `firstCard.innerText()` expecting it to include BOTH
    // the card content AND the preset/mode badge text, and `firstCard.click()`
    // expecting a click at this element's center to select the workspace.
    // Putting role="button" directly on this element instead would recreate
    // the original violation (a role="button" element containing a real
    // <button> descendant), since the badge button must remain a descendant
    // of this wrapper for those innerText() checks to keep seeing it.
    <div
      data-testid="workspace-card"
      data-active={isActive ? "true" : "false"}
      className={styles.cardWrapper}
    >
      <div
        data-testid="workspace-card-clickable-region"
        role="button"
        tabIndex={0}
        onClick={() => onSelect(workspace)}
        onKeyDown={(e) => {
          // WCAG 2.1.1 (Keyboard): a role="button" element must respond to
          // both activation keys, not just Enter — Space is the native
          // <button> activation key too.
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onSelect(workspace);
          }
        }}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
        className={
          styles.card +
          (isHovered ? " " + styles.cardHovered : "") +
          (isActive ? " " + styles.cardActive : "")
        }
      >
        <div>
          <div className={styles.titleRow}>
            <h3 className={styles.title}>
              <span title={workspace.name} className={styles.nameTruncate}>
                {workspace.name}
              </span>
            </h3>
          </div>
          <div className={styles.metaRow}>
            <span>{terminologyText}</span>
            {isActive && (
              <span
                data-testid="workspace-card-active-badge"
                title={t("dashboard.activeWorkspace")}
                className={styles.activeBadge}
              >
                {t("dashboard.activeWorkspace")}
              </span>
            )}
          </div>
        </div>

        <div className={styles.statsGrid}>
          <div className={styles.statColumn}>
            <strong className={styles.statValue}>
              {workspace.requirement_count}
            </strong>
            <span className={styles.statLabel}>
              {reqLabel}
            </span>
          </div>
          <div className={styles.statColumn}>
            <strong className={styles.statValue}>
              {workspace.open_item_count}
            </strong>
            <span className={styles.statLabel}>
              {t("dashboard.openItems")}
            </span>
          </div>
        </div>
      </div>
      {/*
        GESAMTTEST_BERICHT_2026-08-21.md §5 finding 6: rendered as a sibling
        of the card above (not nested inside its role="button" div) to avoid
        an accessibility-tree violation (button-inside-button). stopPropagation
        still guards against also triggering the card's onSelect.
      */}
      <button
        type="button"
        data-testid="workspace-card-preset-badge"
        title={t("dashboard.changeMode")}
        aria-label={t("dashboard.changeMode")}
        onClick={(e) => {
          e.stopPropagation();
          onOpenSettings(workspace);
        }}
        className={styles.presetBadge}
      >
        {workspace.preset}
      </button>
    </div>
  );
}
