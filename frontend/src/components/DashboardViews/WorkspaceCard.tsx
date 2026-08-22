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
  // GESAMTTEST_BERICHT_2026-08-21.md §6 item 2: never let the flex row
  // shrink this pill — the workspace-name span below is the one that
  // truncates instead, so the pill stays fully legible and clear of the
  // absolutely positioned preset badge.
  flexShrink: 0,
};

// GESAMTTEST_BERICHT_2026-08-21.md §6 item 2: truncates a long workspace
// name with an ellipsis instead of letting the title row's flex children
// (name + active pill, default flex-shrink) overflow past the paddingRight
// reserved for the preset badge above and visually collide with it. Hoisted
// — see the ui-ratchet.test.ts frozen baseline note above.
const NAME_TRUNCATE_STYLE: CSSProperties = {
  overflow: "hidden",
  textOverflow: "ellipsis",
  whiteSpace: "nowrap",
  minWidth: 0,
};

// GESAMTTEST_BERICHT_2026-08-21.md §5 finding 6: the mode/preset badge used
// to be a real <button> nested inside this card's outer `role="button"` div
// — an invalid, screen-reader-confusing nested-interactive-element pattern.
// Fixed by rendering the button as a *sibling* of the card (not a
// descendant) and absolutely positioning it over the card's top-right
// corner via this positioning-context wrapper, so the visual layout is
// unchanged while the accessibility tree no longer nests the two
// interactive elements. Hoisted (not an inline object literal) — see the
// ui-ratchet.test.ts frozen baseline note above.
const CARD_WRAPPER_STYLE: CSSProperties = {
  position: "relative",
  minWidth: "260px",
  maxWidth: "320px",
  flex: "1 1 260px",
};

// Sibling positioning for the preset/mode badge button — see
// CARD_WRAPPER_STYLE above for why this is no longer nested inside the
// card's role="button" div.
const PRESET_BADGE_POSITION_STYLE: CSSProperties = {
  position: "absolute",
  top: "var(--space-6)",
  right: "var(--space-6)",
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
      style={CARD_WRAPPER_STYLE}
    >
      <div
        data-testid="workspace-card-clickable-region"
        role="button"
        tabIndex={0}
        onClick={() => onSelect(workspace)}
        onKeyDown={(e) => e.key === "Enter" && onSelect(workspace)}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
        style={{
          background: "var(--color-surface)",
          borderRadius: "var(--radius-lg)",
          boxShadow: isHovered
            ? "var(--shadow-md)"
            : "var(--shadow-card)",
          padding: "var(--space-6)",
          width: "100%",
          height: "100%",
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
              // Room for the sibling preset/mode badge button absolutely
              // positioned over this corner (see PRESET_BADGE_POSITION_STYLE)
              // so the title text doesn't run underneath it.
              paddingRight: "var(--space-8)",
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
                // GESAMTTEST_BERICHT_2026-08-21.md §6 item 2: with the
                // default flex-shrink behavior, a long workspace name pushed
                // the active-pill (and the whole title row) past the
                // paddingRight reserved above for the absolutely positioned
                // preset badge, causing the two to overlap. minWidth: 0 lets
                // the name span below actually shrink instead of overflowing.
                minWidth: 0,
              }}
            >
              <span style={NAME_TRUNCATE_STYLE}>{workspace.name}</span>
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
        style={{
          ...PRESET_BADGE_POSITION_STYLE,
          background: "var(--color-badge-draft)",
          color: "var(--color-badge-draft-text)",
          borderRadius: "var(--radius-full)",
          fontSize: "var(--font-size-sm)",
          padding: "2px 10px",
          fontWeight: 600,
          whiteSpace: "nowrap",
          border: "none",
          cursor: "pointer",
          font: "inherit",
        }}
      >
        {workspace.preset}
      </button>
    </div>
  );
}
