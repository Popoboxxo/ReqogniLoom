/**
 * Schema-driven backend settings (Plan A T-A0b-5, #1316).
 *
 * The server declares each backend's knobs in `backends.<name>.schema`; this
 * fieldset renders exactly those fields. Nothing here knows about Honcho or
 * Qdrant specifically — adding a field server-side makes it appear without a
 * frontend change.
 *
 * Contract notes:
 * - `secret` fields are write-only: the API only reports presence
 *   (`secrets_set`), so the input starts empty and an empty submission removes
 *   the staged value instead of storing "".
 * - an empty text/number input stages `null` (clear the override), never "".
 * - `choice` fields always keep an explicit "default" option (clear override).
 */
import { useTranslation } from "react-i18next";
import type { BackendSettingField } from "../../api/system-memory-settings";
import styles from "./MemorySystemSettingsSection.module.css";

export interface BackendOptionsFieldsetProps {
  backend: string;
  fields: BackendSettingField[];
  values: Record<string, unknown>;
  isOverride: Record<string, boolean>;
  secretsSet: Record<string, boolean>;
  stagedOptions: Record<string, unknown>;
  stagedSecrets: Record<string, string>;
  onOptionChange: (field: string, value: unknown) => void;
  onSecretChange: (field: string, value: string) => void;
  /**
   * Prefix for the generated `data-testid`s. Defaults to the historical
   * `memory-settings` prefix so existing E2E selectors keep working; the
   * artifact vector-store surface passes `artifact-vector-settings`.
   */
  testIdPrefix?: string;
}

function kebab(name: string): string {
  return name.replace(/_/g, "-");
}

function humanize(name: string): string {
  const spaced = name.replace(/_/g, " ");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

function stagedValue(
  staged: Record<string, unknown>,
  values: Record<string, unknown>,
  field: string
): unknown {
  return Object.prototype.hasOwnProperty.call(staged, field) ? staged[field] : values[field];
}

export function BackendOptionsFieldset({
  backend,
  fields,
  values,
  isOverride,
  secretsSet,
  stagedOptions,
  stagedSecrets,
  onOptionChange,
  onSecretChange,
  testIdPrefix = "memory-settings",
}: BackendOptionsFieldsetProps): JSX.Element {
  const { t } = useTranslation();

  if (fields.length === 0) {
    return <p className={styles.hint}>{t("systemSettings.memorySettings.backendNoFields")}</p>;
  }

  return (
    <>
      {fields.map((field) => {
        const suffix = kebab(field.name);
        const testId = `${testIdPrefix}-${backend}-${suffix}`;
        const label = field.label_key
          ? t(field.label_key, { defaultValue: humanize(field.name) })
          : humanize(field.name);
        const badge = isOverride[field.name] ? (
          <span
            data-testid={`${backend}-${suffix}-override-badge`}
            className={styles.overrideBadge}
          >
            {t("systemSettings.memorySettings.overrideBadge")}
          </span>
        ) : null;

        if (field.type === "secret") {
          const staged = stagedSecrets[field.name] ?? "";
          const isSet = Boolean(secretsSet[field.name]) || staged !== "";
          return (
            <label key={field.name} className={styles.field}>
              {label}
              <input
                type="password"
                data-testid={testId}
                aria-describedby={`${testId}-status`}
                placeholder={
                  isSet
                    ? t("systemSettings.memorySettings.secretSetPlaceholder")
                    : t("systemSettings.memorySettings.secretUnsetPlaceholder")
                }
                value={staged}
                onChange={(e) => onSecretChange(field.name, e.target.value)}
              />
              {/* The "is a secret configured" state must not live only in the
                  placeholder: it disappears as soon as the field is typed into
                  and is not part of the field's description (WCAG 3.3.2). */}
              <span
                id={`${testId}-status`}
                className={styles.hint}
                data-testid={`${testId}-status`}
              >
                {isSet
                  ? t("systemSettings.memorySettings.secretStatusSet")
                  : t("systemSettings.memorySettings.secretStatusUnset")}
              </span>
              {badge}
            </label>
          );
        }

        if (field.type === "bool") {
          return (
            <label key={field.name} className={styles.field}>
              {label}
              <input
                type="checkbox"
                data-testid={testId}
                checked={Boolean(stagedValue(stagedOptions, values, field.name))}
                onChange={(e) => onOptionChange(field.name, e.target.checked)}
              />
              {badge}
            </label>
          );
        }

        if (field.type === "choice") {
          const raw = stagedValue(stagedOptions, values, field.name);
          const valid =
            raw === "" || (typeof raw === "string" && field.choices.includes(raw));
          return (
            <label key={field.name} className={styles.field}>
              {label}
              <select
                data-testid={testId}
                value={valid && typeof raw === "string" ? raw : ""}
                onChange={(e) =>
                  onOptionChange(field.name, e.target.value === "" ? null : e.target.value)
                }
              >
                <option value="">
                  {t("systemSettings.memorySettings.backendDefaultOption")}
                </option>
                {field.choices.map((choice) => (
                  <option key={choice} value={choice}>
                    {choice}
                  </option>
                ))}
              </select>
              {badge}
            </label>
          );
        }

        const raw = stagedValue(stagedOptions, values, field.name);
        const display = raw === null || raw === undefined ? "" : String(raw);
        return (
          <label key={field.name} className={styles.field}>
            {label}
            <input
              type={field.type === "str" ? "text" : "number"}
              min={field.type !== "str" && field.min_value !== null ? field.min_value : undefined}
              data-testid={testId}
              value={display}
              onChange={(e) => {
                const text = e.target.value;
                if (text === "") {
                  onOptionChange(field.name, null);
                  return;
                }
                onOptionChange(field.name, field.type === "str" ? text : Number(text));
              }}
            />
            {badge}
          </label>
        );
      })}
    </>
  );
}
