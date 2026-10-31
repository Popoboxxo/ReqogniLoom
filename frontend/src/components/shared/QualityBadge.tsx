/**
 * ARCH-L1-001 ReactFrontend — <QualityBadge> (Plan B / B5-T5, #378).
 *
 * Header badge for the advisory assessment: none / score / stale. It is only
 * a disclosure toggle for the sibling panel and never a gate; chrome comes
 * from the shared `btn-secondary` class, so the button height is --btn-h-md.
 */
import { useTranslation } from "react-i18next";

import type { QualityAssessment } from "../../api/quality";
import styles from "./QualityBadge.module.css";

/** 0..1 → whole-percent label ("37%"). */
export function formatQualityScore(score: number): string {
  return `${Math.round(score * 100)}%`;
}

export interface QualityBadgeProps {
  latest: QualityAssessment | null;
  /** Only ever true when the assessment's version is known and older. */
  stale?: boolean;
  open?: boolean;
  onToggle: () => void;
}

export function QualityBadge({
  latest,
  stale = false,
  open = false,
  onToggle,
}: QualityBadgeProps): JSX.Element {
  const { t } = useTranslation();
  return (
    <button
      type="button"
      className={`btn-secondary ${styles.badge}`}
      data-testid="quality-badge"
      aria-expanded={open}
      onClick={onToggle}
    >
      <span className={styles.label}>{t("quality.badge.label")}</span>
      {latest ? (
        <span className={styles.score} data-testid="quality-badge-score">
          {formatQualityScore(latest.score)}
        </span>
      ) : (
        <span className={styles.muted}>{t("quality.badge.none")}</span>
      )}
      {stale ? (
        <span className={styles.staleHint} data-testid="quality-stale-hint">
          {t("quality.stale")}
        </span>
      ) : null}
    </button>
  );
}
