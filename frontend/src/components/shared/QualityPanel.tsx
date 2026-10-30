/**
 * ARCH-L1-001 ReactFrontend — <QualityPanel> (Plan B / B5-T5, #378).
 *
 * Expanded advisory assessment: score, reasoning, suggestions, history.
 * `reasoning`/`suggestions` are LLM output and are rendered as PLAIN TEXT
 * (no dangerouslySetInnerHTML, no Markdown renderer — KA-B-15). The score is
 * advisory and never gates a transition.
 */
import { useTranslation } from "react-i18next";

import { extractErrorMessage } from "../../api/client";
import { isLlmUnavailableError, type QualityEntityType } from "../../api/quality";
import { useHasRole } from "../../hooks/useHasRole";
import {
  isAssessmentStale,
  useAssessQuality,
  useQualityHistory,
} from "../../queries/quality";
import type { UUID } from "../../types";
import { formatQualityScore } from "./QualityBadge";
import styles from "./QualityPanel.module.css";

export interface QualityPanelProps {
  workspaceId: UUID;
  entityType: QualityEntityType;
  entityId: UUID;
  entityVersion?: number;
}

export function QualityPanel({
  workspaceId,
  entityType,
  entityId,
  entityVersion,
}: QualityPanelProps): JSX.Element {
  const { t } = useTranslation();
  const canAssess = useHasRole()("editor");
  const history = useQualityHistory(workspaceId, entityType, entityId);
  const assess = useAssessQuality(workspaceId, entityType, entityId);
  const latest = history.data?.latest ?? null;
  const stale = isAssessmentStale(latest, entityVersion);
  const assessError = assess.error
    ? isLlmUnavailableError(assess.error)
      ? t("quality.error.unavailable")
      : extractErrorMessage(assess.error)
    : null;

  return (
    <section
      id="quality-panel"
      className={styles.panel}
      data-testid="quality-panel"
      aria-label={t("quality.badge.label")}
    >
      <div className={styles.header}>
        <h3 className={styles.title}>{t("quality.badge.label")}</h3>
        {latest ? <span className={styles.score}>{formatQualityScore(latest.score)}</span> : <span className={styles.muted}>{t("quality.badge.none")}</span>}
        {canAssess ? (
          <button
            type="button"
            className="btn-secondary"
            data-testid="quality-assess-button"
            disabled={assess.isPending}
            aria-busy={assess.isPending || undefined}
            onClick={() => assess.mutate({ force: Boolean(latest) })}
          >
            {latest ? t("quality.reassess") : t("quality.assess")}
          </button>
        ) : null}
      </div>

      <p className={styles.advisory}>{t("quality.advisoryNote")}</p>
      {stale ? <p className={styles.advisory}>{t("quality.stale")}</p> : null}
      {assessError ? (
        <div role="alert" className={styles.error} data-testid="quality-error">{assessError}</div>
      ) : null}
      {history.isError ? (
        <div role="alert" className={styles.error} data-testid="quality-history-error">{extractErrorMessage(history.error)}</div>
      ) : null}

      {latest && latest.reasoning.trim() !== "" ? (
        <div className={styles.block}>
          <h4 className={styles.sectionTitle}>{t("quality.reasoning")}</h4>
          {/* Plain text; whitespace preserved, never parsed as HTML/Markdown. */}
          <p className={styles.reasoning}>{latest.reasoning}</p>
        </div>
      ) : null}

      {latest && latest.suggestions.length > 0 ? (
        <div className={styles.block}>
          <h4 className={styles.sectionTitle}>{t("quality.suggestions")}</h4>
          <ul className={styles.suggestions}>
            {latest.suggestions.map((suggestion, index) => <li key={index}>{suggestion}</li>)}
          </ul>
        </div>
      ) : null}

      <div className={styles.block}>
        <h4 className={styles.sectionTitle}>{t("quality.history")}</h4>
        {history.data && history.data.assessments.length > 0 ? (
          <ul className={styles.history}>
            {history.data.assessments.map((assessment, index) => (
              <li key={assessment.assessment_id} className={styles.historyRow} data-testid={`quality-history-row-${index}`}>
                <span>{new Date(assessment.assessed_at).toLocaleDateString()}</span>
                <span>{formatQualityScore(assessment.score)}</span>
                <span className={styles.muted}>{assessment.prompt_scope}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className={styles.muted}>{t("quality.badge.none")}</p>
        )}
      </div>
    </section>
  );
}
