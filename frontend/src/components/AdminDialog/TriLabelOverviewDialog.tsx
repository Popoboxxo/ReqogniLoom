/**
 * ARCH-L1-001 ReactFrontend — Tri-Label Overview Dialog (admin-only, read-only).
 *
 * leaf_id: COMP-RF-001 (NavigationShell — SystemSettings administration tab)
 *
 * Read-only admin screen listing the Tri-Label table for the eleven built-in
 * link types (DE + EN, downstream/upstream/neutral) — see
 * docs/UMSETZUNGSPLAN_SYSENG_2.0.md §1.3. The table is read directly from
 * the frontend fallback constant (`constants/traceLinkLabels.ts`); it does
 * not reflect per-workspace catalog customizations (Task 23 —
 * `context/LinkTypeContext.tsx` is the catalog source of truth, this dialog
 * stays a static built-in-types reference). Deliberately NOT editable.
 *
 * Modal chrome mirrors SystemHealthDialog's pattern (overlay/dialog/header/
 * body/footer + backdrop-click-to-close).
 */

import { useTranslation } from "react-i18next";
import { FALLBACK_TRI_LABELS } from "../../constants/traceLinkLabels";
import { Dialog } from "../shared/Dialog";
import styles from "./TriLabelOverviewDialog.module.css";

const BUILTIN_LINK_TYPES = Object.keys(FALLBACK_TRI_LABELS);

export interface TriLabelOverviewDialogProps {
  /** Controls modal visibility. */
  isOpen: boolean;
  /** Called when the user closes the dialog. */
  onClose: () => void;
}

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
        <>
          {/* issue #954: shared `.btn-*` footer button instead of a local
              inline style, matching the other admin dialogs. */}
          <button
            type="button"
            className="btn-primary"
            data-testid="tri-label-overview-done"
            onClick={onClose}
          >
            {t("common.close", "Close")}
          </button>
        </>
      }
    >
      <p className={styles.hint}>
        {t(
          "triLabelOverview.hint",
          "Read-only overview of the eleven built-in TraceLink types with their German/English downstream, upstream and neutral labels. Per-workspace catalog customizations are not reflected here."
        )}
      </p>

      <div className={styles.tableScroll}>
        <table
          data-testid="tri-label-overview-table"
          className={styles.table}
        >
          <thead>
            <tr>
              <th className={styles.th}>{t("triLabelOverview.columns.type", "Type")}</th>
              <th className={styles.th}>{t("triLabelOverview.columns.deDownstream", "DE Downstream")}</th>
              <th className={styles.th}>{t("triLabelOverview.columns.deUpstream", "DE Upstream")}</th>
              <th className={styles.th}>{t("triLabelOverview.columns.enDownstream", "EN Downstream")}</th>
              <th className={styles.th}>{t("triLabelOverview.columns.enUpstream", "EN Upstream")}</th>
              <th className={styles.th}>{t("triLabelOverview.columns.neutral", "Neutral (DE / EN)")}</th>
            </tr>
          </thead>
          <tbody>
            {BUILTIN_LINK_TYPES.map((lt) => {
              const entry = FALLBACK_TRI_LABELS[lt];
              return (
                <tr key={lt} data-testid={`tri-label-row-${lt}`}>
                  <td className={styles.typeCell} data-testid={`tri-label-row-${lt}-type`}>
                    {lt}
                  </td>
                  <td className={styles.td} data-testid={`tri-label-row-${lt}-de-downstream`}>
                    {entry.de.downstream}
                  </td>
                  <td className={styles.td} data-testid={`tri-label-row-${lt}-de-upstream`}>
                    {entry.de.upstream}
                  </td>
                  <td className={styles.td} data-testid={`tri-label-row-${lt}-en-downstream`}>
                    {entry.en.downstream}
                  </td>
                  <td className={styles.td} data-testid={`tri-label-row-${lt}-en-upstream`}>
                    {entry.en.upstream}
                  </td>
                  <td className={styles.td} data-testid={`tri-label-row-${lt}-neutral`}>
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
