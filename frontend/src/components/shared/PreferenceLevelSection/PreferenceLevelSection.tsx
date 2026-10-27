/**
 * Q1 generic preference section (Plan C, T-C2-5) — one level, rendered from the
 * server's key registry.
 *
 * Mounted three times, once per level: `/profile` (user), the workspace
 * settings' "Darstellung" tab (workspace) and `/system-settings` (global). The
 * component never declares a key: everything it renders comes from
 * `GET /api/v1/preference-values/registry/`, filtered to the keys that
 *
 *   1. carry a generic `ui_editor` (`checkbox` / `select`) — a key with a
 *      dedicated UI (e.g. the sidebar layout) must not be duplicated here, and
 *   2. allow *this* level (`scope ∈ levels`) — a user-only key on the system
 *      page would be a write the server rejects, and
 *   3. are not claimed by a sibling section on the same page (`excludeKeys`;
 *      `/profile` keeps `ui.ids.show_readable` in `IdentifiersSection`).
 *
 * Two reads, two questions
 * ------------------------
 * - **level** (`…/preference-values/`): what does *this* level store. An absent
 *   key means "inherit", so "Zurücksetzen" is only available for a key that is
 *   actually set here.
 * - **effective** (`…/preference-values/effective/`): what the caller gets
 *   today and which level supplied it. That is the value an inherited input
 *   shows, and `source` is what the "Geerbt von …" hint names.
 *
 * `source` alone cannot decide "set here": a personal override sits above the
 * workspace level, so on the workspace page it can report `user` even when the
 * workspace value is set. The level payload is therefore authoritative for
 * that question — hence both reads.
 *
 * Writing
 * -------
 * Every edit PATCHes immediately, wrapped as `{values: {<key>: <value> | null}}`
 * (`null` = reset this level, delete the row). One row is `aria-busy`-style
 * disabled while its own write is in flight; a rejected write is announced
 * through `preference-error` (`role="alert"`) and never silently swallowed. A
 * successful write invalidates the `preferences` namespace, so both reads
 * refresh together.
 */

import { useTranslation } from "react-i18next";

import { extractApiErrorMessage } from "../../../api/client";
import type {
  PreferenceKeySpec,
  PreferenceScope,
  PreferenceSource,
} from "../../../api/preference-values";
import {
  useEffectivePreferences,
  usePatchPreferenceLevel,
  usePreferenceLevel,
  usePreferenceRegistry,
} from "../../../queries/preferences";
import styles from "./PreferenceLevelSection.module.css";

export interface PreferenceLevelSectionProps {
  /** Which level this mount edits. */
  scope: PreferenceScope;
  /** Required by the workspace scope; ignored by the other two. */
  workspaceId?: string;
  /** Keys a sibling section on the same page owns (not rendered here). */
  excludeKeys?: readonly string[];
}

/** Resolve a translated label, falling back to a raw identifier. */
function labelOr(
  t: (key: string) => string,
  key: string,
  fallback: string
): string {
  const translated = t(key);
  return translated === key ? fallback : translated;
}

export function PreferenceLevelSection({
  scope,
  workspaceId,
  excludeKeys,
}: PreferenceLevelSectionProps): JSX.Element {
  const { t } = useTranslation();

  const registry = usePreferenceRegistry();
  const level = usePreferenceLevel(scope, workspaceId);
  // The workspace route is the only one that resolves *with* a workspace level;
  // the account-wide read covers `user > global > default` for the other two.
  const effective = useEffectivePreferences(
    scope === "workspace" ? workspaceId ?? null : null
  );
  const patch = usePatchPreferenceLevel(scope, workspaceId);

  const excluded = new Set(excludeKeys ?? []);
  const specs: PreferenceKeySpec[] = (registry.data?.keys ?? []).filter(
    (spec) =>
      spec.ui_editor !== null &&
      spec.levels.includes(scope) &&
      !excluded.has(spec.key)
  );

  const storedValues = level.data?.values ?? {};
  const effectiveValues = effective.data?.values ?? {};

  const isLoading =
    registry.isLoading || level.isLoading || effective.isLoading;
  const loadError = registry.error ?? level.error ?? effective.error ?? null;
  const error = patch.error ?? loadError;
  const errorMessage =
    error === null
      ? null
      : extractApiErrorMessage(error) ?? t("errors.generic");

  // TanStack keeps the variables of the in-flight write, which is the only
  // pending row — so a slow save disables exactly one control.
  const pendingKey =
    patch.isPending && patch.variables
      ? Object.keys(patch.variables)[0] ?? null
      : null;

  const inheritedLabel = (source: PreferenceSource): string =>
    t("preferences.inherited", {
      source: labelOr(t, `preferences.source.${source}`, source),
    });

  return (
    <section className={styles.section} data-testid={`preference-section-${scope}`}>
      <h3 className={styles.heading}>{t("preferences.title")}</h3>

      {errorMessage !== null && (
        <p role="alert" className={styles.error} data-testid="preference-error">
          {errorMessage}
        </p>
      )}

      {isLoading ? (
        <p
          role="status"
          className={styles.hint}
          data-testid={`preference-section-${scope}-loading`}
        >
          {t("loading")}
        </p>
      ) : (
        <div className={styles.rows}>
          {specs.map((spec) => {
            const isSet = Object.prototype.hasOwnProperty.call(
              storedValues,
              spec.key
            );
            const effectiveEntry = effectiveValues[spec.key];
            const source: PreferenceSource = effectiveEntry?.source ?? "default";
            const storedValue = isSet ? storedValues[spec.key] : undefined;
            const inheritedValue = effectiveEntry?.value ?? spec.default;

            const pendingValue =
              pendingKey === spec.key && patch.variables
                ? patch.variables[spec.key]
                : undefined;
            // `undefined` = no write in flight; `null` = a pending reset, which
            // falls back to the inherited value the refetch will report.
            const value =
              pendingValue === undefined
                ? storedValue ?? inheritedValue
                : pendingValue ?? inheritedValue;
            const setNow =
              pendingValue === undefined ? isSet : pendingValue !== null;

            const inputId = `preference-input-${spec.key}`;
            const label = labelOr(
              t,
              `preferences.key.${spec.key}`,
              spec.key
            );

            return (
              <div
                key={spec.key}
                className={styles.row}
                data-testid={`preference-row-${spec.key}`}
              >
                <label className={styles.control} htmlFor={inputId}>
                  {spec.ui_editor === "checkbox" ? (
                    <input
                      id={inputId}
                      type="checkbox"
                      className={styles.checkbox}
                      checked={Boolean(value)}
                      disabled={pendingKey !== null}
                      onChange={(event) =>
                        patch.mutate({ [spec.key]: event.target.checked })
                      }
                      data-testid={`preference-input-${spec.key}`}
                    />
                  ) : (
                    <select
                      id={inputId}
                      className="field-select"
                      value={typeof value === "string" ? value : ""}
                      disabled={pendingKey !== null}
                      onChange={(event) =>
                        patch.mutate({ [spec.key]: event.target.value })
                      }
                      data-testid={`preference-input-${spec.key}`}
                    >
                      {(spec.choices ?? []).map((choice) => (
                        <option key={choice} value={choice}>
                          {labelOr(
                            t,
                            `preferences.choice.${spec.key}.${choice}`,
                            choice
                          )}
                        </option>
                      ))}
                    </select>
                  )}
                  <span
                    className={styles.keyLabel}
                    title={spec.key}
                  >
                    {label}
                  </span>
                </label>

                <span
                  className={`${styles.source} ${setNow ? styles.sourceSet : ""}`}
                  data-testid={`preference-source-${spec.key}`}
                >
                  {setNow ? t("preferences.setHere") : inheritedLabel(source)}
                </span>

                <button
                  type="button"
                  className={`btn-ghost btn-sm ${styles.reset}`}
                  disabled={!setNow || pendingKey !== null}
                  onClick={() => patch.mutate({ [spec.key]: null })}
                  // The visible label is the action only ("Zurücksetzen"); the
                  // accessible name states the object, so a screen-reader user
                  // does not get N identical "Reset" buttons in a row.
                  aria-label={`${t("preferences.reset")}: ${label}`}
                  data-testid={`preference-reset-${spec.key}`}
                >
                  {t("preferences.reset")}
                </button>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
