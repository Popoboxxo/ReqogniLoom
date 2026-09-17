import { useTranslation } from "react-i18next";

import styles from "../ArtifactForm.module.css";
import type { WidgetProps } from "../widget-registry";

/** Mirrors ``Risk._PROB_NUMERIC`` on the backend. */
export const RISK_PROBABILITY_SCORE: Record<string, number> = {
  low: 1,
  medium: 2,
  high: 3,
};

/** Mirrors ``Risk._IMPACT_NUMERIC`` on the backend. */
export const RISK_IMPACT_SCORE: Record<string, number> = {
  low: 1,
  medium: 2,
  high: 3,
};

/**
 * Risk Priority Number = probability x impact x detection.
 *
 * Kept byte-compatible with ``Risk.rpn`` (backend/persistence/models.py): an
 * unrecognised probability/impact scores 1, a missing/zero detection falls
 * back to 5 (mirrors the backend's `self.detection or 5`). A divergence here
 * would show the user a number the server never stores.
 */
export function computeRpn(
  probability: unknown,
  impact: unknown,
  detection: unknown
): number {
  const p = RISK_PROBABILITY_SCORE[String(probability)] ?? 1;
  const i = RISK_IMPACT_SCORE[String(impact)] ?? 1;
  const d = typeof detection === "number" && detection > 0 ? detection : 5;
  return p * i * d;
}

const LEVEL_OPTIONS = ["low", "medium", "high"] as const;

export function RiskMatrixRpz({
  attribute,
  values,
  onChange,
  disabled,
  errors,
  testId,
}: WidgetProps): JSX.Element {
  const { t } = useTranslation();
  const rpn = computeRpn(values.probability, values.impact, values.detection);

  return (
    <div className={styles.widget} data-testid={testId}>
      <span className={styles.label}>{t("risks.matrix")}</span>
      <div className={styles.matrixGrid}>
        {(["probability", "impact"] as const).map((field) => (
          <label key={field} className={styles.field}>
            <span className={styles.label}>{t(`risks.${field}`)}</span>
            <select
              className={styles.control}
              data-testid={`${testId}-${field}`}
              value={String(values[field] ?? "")}
              disabled={disabled}
              onChange={(event) => onChange(field, event.target.value || null)}
            >
              {LEVEL_OPTIONS.map((level) => (
                <option key={level} value={level}>
                  {t(`risks.level.${level}`)}
                </option>
              ))}
            </select>
          </label>
        ))}
        <label className={styles.field}>
          <span className={styles.label}>{t("risks.detection")}</span>
          <input
            className={styles.control}
            data-testid={`${testId}-detection`}
            type="number"
            min={1}
            max={10}
            value={typeof values.detection === "number" ? values.detection : ""}
            disabled={disabled}
            onChange={(event) =>
              onChange("detection", event.target.value === "" ? null : Number(event.target.value))
            }
          />
        </label>
      </div>
      <output className={styles.help} data-testid={`${testId}-rpn`}>
        {t("risks.rpn", { value: rpn })}
      </output>
      {attribute.fields
        .flatMap((field) => errors?.[field] ?? [])
        .map((message) => (
          <span key={message} className={styles.errors} role="alert">
            {message}
          </span>
        ))}
    </div>
  );
}
