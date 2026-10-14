/**
 * ARCH-L1-001 ReactFrontend — MetricsWidgetConfig (Issue #1265).
 *
 * The dashboard's configurable header bar: one checkbox per registered
 * statistic, driving the caller's own `visible_metrics` display preference.
 * Presentational by design — the catalogue load and the persistence live in
 * `useMetricWidgets`, so this component stays a pure render of
 * `(catalog, visibleKeys)`.
 *
 * Titles come from the backend registry catalog entry (`title_key`, resolved
 * against `metrics.catalog.<key>.title` with the registry's English `title` as
 * the fallback), so adding a metric server-side surfaces it here without a
 * frontend change — only its tile spec is frontend-owned.
 */

import { useTranslation } from "react-i18next";

import type { MetricCatalogEntry } from "../../api/metrics";
import styles from "./MetricsDashboard.module.css";

export interface MetricsWidgetConfigProps {
  catalog: MetricCatalogEntry[];
  visibleKeys: string[];
  isLoading: boolean;
  isSaving: boolean;
  error: string | null;
  onToggle: (key: string, next: boolean) => void;
}

export function MetricsWidgetConfig({
  catalog,
  visibleKeys,
  isLoading,
  isSaving,
  error,
  onToggle,
}: MetricsWidgetConfigProps): JSX.Element | null {
  const { t } = useTranslation();

  // Nothing to configure before the catalogue arrives (or when it could not be
  // loaded) — the dashboard then shows its default tile set.
  if (catalog.length === 0) {
    if (!isLoading) return null;
    return (
      <p role="status" data-testid="metrics-widget-config-loading" className={styles.mutedText}>
        {t("metrics.widgetConfigLoading")}
      </p>
    );
  }

  return (
    <fieldset className={styles.widgetConfig} data-testid="metrics-widget-config">
      <legend className={styles.widgetConfigLegend}>
        {t("metrics.widgetConfigTitle")}
      </legend>
      <span className={styles.widgetConfigHint}>
        {t("metrics.widgetConfigHint")}
      </span>

      <div className={styles.widgetConfigList}>
        {catalog.map((entry) => (
          <label key={entry.key} className={styles.widgetConfigItem}>
            <input
              type="checkbox"
              className={styles.widgetConfigCheckbox}
              checked={visibleKeys.includes(entry.key)}
              disabled={isSaving}
              onChange={(event) => onToggle(entry.key, event.target.checked)}
              data-testid={`metrics-widget-toggle-${entry.key}`}
            />
            <span>
              {t(entry.title_key, entry.title)}
              {entry.expensive && (
                <span
                  className={styles.widgetConfigCost}
                  title={t("metrics.widgetConfigExpensive")}
                >
                  {" "}
                  ·
                </span>
              )}
            </span>
          </label>
        ))}
      </div>

      {error !== null && (
        <p role="alert" data-testid="metrics-widget-config-error" className={styles.errorBanner}>
          {error || t("metrics.widgetConfigError")}
        </p>
      )}
    </fieldset>
  );
}
