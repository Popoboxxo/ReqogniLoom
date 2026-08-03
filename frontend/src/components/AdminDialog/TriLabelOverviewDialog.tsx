/**
 * ARCH-L1-001 ReactFrontend — Tri-Label Overview Dialog (admin-only, read-only).
 *
 * leaf_id: COMP-RF-001 (NavigationShell — SystemSettings administration tab)
 *
 * Read-only admin screen listing the complete Tri-Label table for all 14
 * `LinkType` values (DE + EN, downstream/upstream/neutral) — see
 * docs/UMSETZUNGSPLAN_SYSENG_2.0.md §1.3. The table is read directly from
 * the frontend constant (`constants/traceLinkLabels.ts`, the single source
 * of truth); no backend endpoint is involved since the Tri-Label data lives
 * purely in the frontend. Deliberately NOT editable in this phase.
 *
 * Modal chrome mirrors SystemHealthDialog's pattern (overlay/dialog/header/
 * body/footer + backdrop-click-to-close).
 */

import type { CSSProperties } from "react";
import { useTranslation } from "react-i18next";
import {
  ALL_LINK_TYPES,
  LINK_TYPE_TRI_LABELS,
} from "../../constants/traceLinkLabels";
import { Dialog } from "../shared/Dialog";

export interface TriLabelOverviewDialogProps {
  /** Controls modal visibility. */
  isOpen: boolean;
  /** Called when the user closes the dialog. */
  onClose: () => void;
}

// ---------------------------------------------------------------------------
// Styles — the overlay/panel/header chrome now comes from <Dialog>; only the
// content-specific styles remain here.
// ---------------------------------------------------------------------------

const footerStyle: CSSProperties = {
  display: "flex",
  justifyContent: "flex-end",
  gap: "var(--space-2)",
};

const hintStyle: CSSProperties = {
  fontSize: "var(--font-size-sm)",
  color: "var(--color-text-muted)",
  margin: "0 0 var(--space-4) 0",
};

const thStyle: CSSProperties = {
  textAlign: "left",
  padding: "var(--space-2) var(--space-3)",
  fontSize: "var(--font-size-xs)",
  fontWeight: 600,
  color: "var(--color-text-muted)",
  textTransform: "uppercase",
  letterSpacing: "0.05em",
  borderBottom: "1px solid var(--color-border)",
  whiteSpace: "nowrap",
};

const tdStyle: CSSProperties = {
  padding: "var(--space-2) var(--space-3)",
  fontSize: "var(--font-size-sm)",
  color: "var(--color-text)",
  borderBottom: "1px solid var(--color-border)",
  verticalAlign: "middle",
};

const typeCellStyle: CSSProperties = {
  ...tdStyle,
  fontFamily: "monospace",
  fontWeight: 600,
  whiteSpace: "nowrap",
};

const primaryButtonStyle: CSSProperties = {
  background: "var(--color-primary)",
  color: "white",
  border: "none",
  borderRadius: "var(--radius-sm)",
  padding: "var(--space-2) var(--space-4)",
  cursor: "pointer",
  fontSize: "var(--font-size-sm)",
  fontWeight: 600,
  fontFamily: "inherit",
};

/**
 * Admin-only, read-only Tri-Label overview — full DE/EN
 * downstream/upstream/neutral table for all 14 LinkType values. No edit
 * controls (schreibgeschützt per current phase scope).
 */
export function TriLabelOverviewDialog({
  isOpen,
  onClose,
}: TriLabelOverviewDialogProps): JSX.Element | null {
  const { t } = useTranslation();

  if (!isOpen) return null;

  return (
    <Dialog
      title={t("triLabelOverview.title", "Tri-Label Overview")}
      onClose={onClose}
      size="lg"
      testId="tri-label-overview-dialog"
      footer={
        <div style={footerStyle}>
          <button
            type="button"
            data-testid="tri-label-overview-done"
            onClick={onClose}
            style={primaryButtonStyle}
          >
            {t("common.close", "Close")}
          </button>
        </div>
      }
    >
      <p style={hintStyle}>
        {t(
          "triLabelOverview.hint",
          "Read-only overview of all 14 TraceLink types with their German/English downstream, upstream and neutral labels. Not editable in this phase."
        )}
      </p>

      <div style={{ overflowX: "auto" }}>
        <table
          data-testid="tri-label-overview-table"
          style={{ width: "100%", borderCollapse: "collapse" }}
        >
          <thead>
            <tr>
              <th style={thStyle}>{t("triLabelOverview.columns.type", "Type")}</th>
              <th style={thStyle}>{t("triLabelOverview.columns.deDownstream", "DE Downstream")}</th>
              <th style={thStyle}>{t("triLabelOverview.columns.deUpstream", "DE Upstream")}</th>
              <th style={thStyle}>{t("triLabelOverview.columns.enDownstream", "EN Downstream")}</th>
              <th style={thStyle}>{t("triLabelOverview.columns.enUpstream", "EN Upstream")}</th>
              <th style={thStyle}>{t("triLabelOverview.columns.neutral", "Neutral (DE / EN)")}</th>
            </tr>
          </thead>
          <tbody>
            {ALL_LINK_TYPES.map((lt) => {
              const entry = LINK_TYPE_TRI_LABELS[lt];
              return (
                <tr key={lt} data-testid={`tri-label-row-${lt}`}>
                  <td style={typeCellStyle} data-testid={`tri-label-row-${lt}-type`}>
                    {lt}
                  </td>
                  <td style={tdStyle} data-testid={`tri-label-row-${lt}-de-downstream`}>
                    {entry.de.downstream}
                  </td>
                  <td style={tdStyle} data-testid={`tri-label-row-${lt}-de-upstream`}>
                    {entry.de.upstream}
                  </td>
                  <td style={tdStyle} data-testid={`tri-label-row-${lt}-en-downstream`}>
                    {entry.en.downstream}
                  </td>
                  <td style={tdStyle} data-testid={`tri-label-row-${lt}-en-upstream`}>
                    {entry.en.upstream}
                  </td>
                  <td style={tdStyle} data-testid={`tri-label-row-${lt}-neutral`}>
                    {entry.de.neutral} / {entry.en.neutral}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Dialog>
  );
}
