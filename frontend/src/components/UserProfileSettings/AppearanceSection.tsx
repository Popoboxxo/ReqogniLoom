/**
 * ARCH-L1-001 ReactFrontend — AppearanceSection (UserProfileSettings).
 *
 * leaf_id: COMP-RF-006 (UserProfileSettings — user-owned data controls)
 *
 * Task 2 (Schnitt 1b). Two INDEPENDENT user-level display switches:
 *  - show the horizontal trace-spine footer (`trace_footer_enabled`);
 *  - show the artifact inspector (`inspector_enabled`).
 *
 * Both live HERE, in the user profile, NOT in the WorkspaceSettings
 * "Darstellung" tab — they follow the account across workspaces/devices. The
 * Q1 keys behind them are backend-internal; this section only reads and writes
 * the two snake_case fields of `displayPreferencesApi`.
 *
 * Each toggle flips its OWN module store optimistically, PATCHes only its OWN
 * field, applies only that field from the server response, and rolls back only
 * that field on a rejected save. Toggling one can therefore never move the
 * other — and both can be on simultaneously.
 *
 * States
 * ------
 *  - **loading** (`isLoading`): both switches are disabled and a `role="status"`
 *    line explains why, while the stores show the cached/default values;
 *  - **empty** (no field on the response, e.g. an older backend): the cached
 *    values stay put — no blank/NaN UI, no silent overwrite;
 *  - **error**: a `role="alert"` carries the API message (or a localized
 *    fallback) for a failed load or save, and a failed save is rolled back;
 *  - **success**: both switches reflect the server values and are interactive.
 *
 * Accessibility baseline (APG switch pattern): a native `<button>` with
 * `role="switch"` and `aria-checked`, keyboard-operable with Space/Enter, in the
 * natural tab order. The visible focus ring comes from the global
 * `:focus-visible` rule in `styles/global.css`. The WCAG verdict itself stays
 * with `accessibility-specialist`.
 */

import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { extractApiErrorMessage } from "../../api/client";
import {
  displayPreferencesApi,
  type DisplayPreferences,
} from "../../api/display-preferences";
import { useInspectorVisible } from "../../hooks/useInspectorVisible";
import { useTraceFooterVisible } from "../../hooks/useTraceFooterVisible";
import styles from "./AppearanceSection.module.css";

type ToggleKey = "trace_footer_enabled" | "inspector_enabled";

export function AppearanceSection(): JSX.Element {
  const { t } = useTranslation();
  const [traceFooterVisible, setTraceFooterVisible] = useTraceFooterVisible();
  const [inspectorVisible, setInspectorVisible] = useInspectorVisible();
  const [isLoading, setIsLoading] = useState(true);
  const [saving, setSaving] = useState<ToggleKey | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setError(null);
    displayPreferencesApi
      .get()
      .then((prefs) => {
        if (cancelled) return;
        // Only apply fields the server actually answered — an older backend
        // must not blank the cached first-render values (the "empty" state).
        if (prefs.trace_footer_enabled !== undefined) {
          setTraceFooterVisible(prefs.trace_footer_enabled);
        }
        if (prefs.inspector_enabled !== undefined) {
          setInspectorVisible(prefs.inspector_enabled);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(extractApiErrorMessage(err) ?? "");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // Mount-only: the module-level setters are stable across renders.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleToggle = useCallback(
    async (key: ToggleKey, next: boolean): Promise<void> => {
      if (saving !== null) return;
      const previous =
        key === "trace_footer_enabled" ? traceFooterVisible : inspectorVisible;
      const setter =
        key === "trace_footer_enabled" ? setTraceFooterVisible : setInspectorVisible;
      const changes: Partial<DisplayPreferences> =
        key === "trace_footer_enabled"
          ? { trace_footer_enabled: next }
          : { inspector_enabled: next };

      setError(null);
      setSaving(key);
      // Optimistic: only this store flips, so every consumer of this flag
      // reacts at once and the other flag is left completely alone.
      setter(next);
      try {
        const prefs = await displayPreferencesApi.update(changes);
        // The server's returned field wins — never assume the click took effect,
        // and never apply the OTHER field (strict independence).
        const returned = prefs[key];
        if (returned !== undefined) setter(returned);
      } catch (err: unknown) {
        setter(previous);
        setError(extractApiErrorMessage(err) ?? "");
      } finally {
        setSaving(null);
      }
    },
    [
      saving,
      traceFooterVisible,
      inspectorVisible,
      setTraceFooterVisible,
      setInspectorVisible,
    ],
  );

  const isBusy = isLoading || saving !== null;

  return (
    <section className={styles.section} data-testid="appearance-section">
      <h2 className={styles.heading}>{t("appearance.title")}</h2>
      <p className={styles.hint}>{t("appearance.hint")}</p>

      <div className={styles.row}>
        <button
          type="button"
          role="switch"
          aria-checked={traceFooterVisible}
          className={`btn-ghost ${styles.switch}`}
          disabled={isBusy}
          onClick={() => void handleToggle("trace_footer_enabled", !traceFooterVisible)}
          data-testid="appearance-trace-footer-switch"
        >
          <span
            className={styles.switchTrack}
            data-checked={traceFooterVisible}
            aria-hidden="true"
          />
          <span className={styles.label}>{t("appearance.traceFooter")}</span>
        </button>
        <p className={styles.rowHint}>{t("appearance.traceFooterHint")}</p>
      </div>

      <div className={styles.row}>
        <button
          type="button"
          role="switch"
          aria-checked={inspectorVisible}
          className={`btn-ghost ${styles.switch}`}
          disabled={isBusy}
          onClick={() => void handleToggle("inspector_enabled", !inspectorVisible)}
          data-testid="appearance-inspector-switch"
        >
          <span
            className={styles.switchTrack}
            data-checked={inspectorVisible}
            aria-hidden="true"
          />
          <span className={styles.label}>{t("appearance.inspector")}</span>
        </button>
        <p className={styles.rowHint}>{t("appearance.inspectorHint")}</p>
      </div>

      {isLoading && (
        <p role="status" data-testid="appearance-loading" className={styles.rowHint}>
          {t("appearance.loading")}
        </p>
      )}

      {error !== null && (
        <p role="alert" data-testid="appearance-error" className={styles.error}>
          {error || t("appearance.syncFailed")}
        </p>
      )}

      <p className={styles.accountNote}>{t("appearance.accountNote")}</p>
    </section>
  );
}
