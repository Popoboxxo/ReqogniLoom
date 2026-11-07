/**
 * P5 Task 5.2 — workspace-level card-field configuration for the allocation
 * graph.
 *
 * Two card types are edited separately: requirement cards and element cards.
 * Per type the administrator chooses the visible fields, their order and the
 * number of visual rows. The lock marker is mandatory (checkbox disabled, no
 * remove action) and finding/unallocated markers are not configurable at all —
 * they are rendered by the cards unconditionally.
 *
 * Persistence goes through the preference API (`workspace` scope) and nowhere
 * else. A rejected save is surfaced through the section's error state, never
 * swallowed, and "reset" writes the built-in defaults through the same normal
 * save path.
 */

import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  CARD_FIELD_KEYS,
  MAX_CARD_ROWS,
  MIN_CARD_ROWS,
  MANDATORY_CARD_FIELDS,
  cardFieldsApi,
  defaultCardFieldConfigMap,
  validateCardFieldConfig,
  type CardFieldConfig,
  type CardFieldConfigMap,
  type CardFieldKey,
  type CardKind,
} from "../AllocationGraph/cardFields";
import styles from "./CardFieldsSection.module.css";

export interface CardFieldsSectionProps {
  workspaceId: string;
}

const KIND_ORDER: readonly CardKind[] = ["requirement", "element"];

export function CardFieldsSection({ workspaceId }: CardFieldsSectionProps): JSX.Element {
  const { t } = useTranslation();
  const [config, setConfig] = useState<CardFieldConfigMap>(() =>
    defaultCardFieldConfigMap()
  );
  const [kind, setKind] = useState<CardKind>("requirement");
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    void cardFieldsApi.load(workspaceId).then((loaded) => {
      if (cancelled) return;
      setConfig(loaded);
      setIsLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [workspaceId]);

  const current = config[kind];

  const updateCurrent = useCallback(
    (next: CardFieldConfig) => {
      setSaved(false);
      setConfig((previous) => ({ ...previous, [kind]: next }));
    },
    [kind]
  );

  const moveField = (index: number, direction: -1 | 1): void => {
    const fields = current.fields.slice();
    const target = index + direction;
    if (target < 0 || target >= fields.length) return;
    [fields[index], fields[target]] = [fields[target], fields[index]];
    updateCurrent({ ...current, fields });
  };

  const toggleVisible = (key: CardFieldKey, visible: boolean): void => {
    if (MANDATORY_CARD_FIELDS.includes(key) && !visible) return;
    updateCurrent({
      ...current,
      fields: current.fields.map((field) =>
        field.key === key ? { ...field, visible } : field
      ),
    });
  };

  const removeField = (key: CardFieldKey): void => {
    if (MANDATORY_CARD_FIELDS.includes(key)) return;
    updateCurrent({
      ...current,
      fields: current.fields.filter((field) => field.key !== key),
    });
  };

  const addField = (key: CardFieldKey): void => {
    if (current.fields.some((field) => field.key === key)) return;
    updateCurrent({
      ...current,
      fields: [...current.fields, { key, visible: true }],
    });
  };

  const handleSave = async (): Promise<void> => {
    setError(null);
    setSaved(false);
    try {
      validateCardFieldConfig("requirement", config.requirement);
      validateCardFieldConfig("element", config.element);
      setIsSaving(true);
      await cardFieldsApi.save(workspaceId, config);
      setSaved(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsSaving(false);
    }
  };

  const handleReset = async (): Promise<void> => {
    const defaults = defaultCardFieldConfigMap();
    setConfig(defaults);
    setError(null);
    setSaved(false);
    setIsSaving(true);
    try {
      await cardFieldsApi.save(workspaceId, defaults);
      setSaved(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsSaving(false);
    }
  };

  const available = CARD_FIELD_KEYS[kind].filter(
    (key) => !current.fields.some((field) => field.key === key)
  );

  return (
    <section className={styles.section} data-testid="card-fields-section">
      <h3 className={styles.heading}>{t("settings.cardFields.title")}</h3>
      <p className={styles.hint}>{t("settings.cardFields.hint")}</p>

      <div
        className={styles.kindSwitcher}
        role="group"
        aria-label={t("settings.cardFields.title")}
      >
        {KIND_ORDER.map((option) => (
          <button
            key={option}
            type="button"
            className={`btn-ghost ${styles.kindButton} ${
              kind === option ? styles.kindButtonActive : ""
            }`}
            data-testid={`card-fields-kind-${option}`}
            aria-pressed={kind === option}
            onClick={() => setKind(option)}
          >
            {option === "requirement"
              ? t("settings.cardFields.kindRequirement")
              : t("settings.cardFields.kindElement")}
          </button>
        ))}
      </div>

      {isLoading ? (
        <p className={styles.status} data-testid="card-fields-loading">
          {t("settings.cardFields.loading")}
        </p>
      ) : (
        <>
          <label className={styles.rowsRow}>
            {t("settings.cardFields.rows")}
            <input
              type="number"
              className={styles.rowsInput}
              data-testid="card-fields-rows"
              min={MIN_CARD_ROWS}
              max={MAX_CARD_ROWS}
              value={current.rows}
              onChange={(event) =>
                updateCurrent({
                  ...current,
                  rows: Number.parseInt(event.target.value, 10) || MIN_CARD_ROWS,
                })
              }
            />
          </label>

          <ol className={styles.fieldList}>
            {current.fields.map((field, index) => {
              const mandatory = MANDATORY_CARD_FIELDS.includes(field.key);
              return (
                <li
                  key={field.key}
                  className={styles.fieldItem}
                  data-testid={`card-fields-field-${field.key}`}
                >
                  <label className={styles.fieldLabel}>
                    <input
                      type="checkbox"
                      checked={field.visible}
                      disabled={mandatory}
                      data-testid={`card-fields-visible-${field.key}`}
                      onChange={(event) =>
                        toggleVisible(field.key, event.target.checked)
                      }
                    />
                    {t(`allocationGraph.fields.${field.key}`)}
                  </label>
                  {mandatory && (
                    <span
                      className={styles.mandatory}
                      data-testid={`card-fields-mandatory-${field.key}`}
                    >
                      {t("settings.cardFields.mandatory")}
                    </span>
                  )}
                  <div className={styles.fieldActions}>
                    <button
                      type="button"
                      className={`btn-ghost ${styles.iconButton}`}
                      data-testid={`card-fields-up-${field.key}`}
                      aria-label={t("settings.cardFields.moveUp")}
                      disabled={index === 0}
                      onClick={() => moveField(index, -1)}
                    >
                      ↑
                    </button>
                    <button
                      type="button"
                      className={`btn-ghost ${styles.iconButton}`}
                      data-testid={`card-fields-down-${field.key}`}
                      aria-label={t("settings.cardFields.moveDown")}
                      disabled={index === current.fields.length - 1}
                      onClick={() => moveField(index, 1)}
                    >
                      ↓
                    </button>
                    <button
                      type="button"
                      className={`btn-ghost ${styles.iconButton}`}
                      data-testid={`card-fields-remove-${field.key}`}
                      aria-label={t("settings.cardFields.remove")}
                      disabled={mandatory}
                      onClick={() => removeField(field.key)}
                    >
                      ×
                    </button>
                  </div>
                </li>
              );
            })}
          </ol>

          {available.length > 0 && (
            <label className={styles.addRow}>
              {t("settings.cardFields.addField")}
              <select
                className={styles.addSelect}
                data-testid="card-fields-add"
                value=""
                onChange={(event) => {
                  if (event.target.value) {
                    addField(event.target.value as CardFieldKey);
                  }
                }}
              >
                <option value="" />
                {available.map((key) => (
                  <option key={key} value={key}>
                    {t(`allocationGraph.fields.${key}`)}
                  </option>
                ))}
              </select>
            </label>
          )}

          {error && (
            <p role="alert" className={styles.error} data-testid="card-fields-error">
              {error}
            </p>
          )}
          {saved && (
            <p role="status" className={styles.saved} data-testid="card-fields-saved">
              {t("settings.cardFields.saved")}
            </p>
          )}

          <div className={styles.actions}>
            <button
              type="button"
              className="btn-primary"
              data-testid="card-fields-save"
              disabled={isSaving}
              onClick={() => void handleSave()}
            >
              {t("settings.cardFields.save")}
            </button>
            <button
              type="button"
              className="btn-secondary"
              data-testid="card-fields-reset"
              disabled={isSaving}
              onClick={() => void handleReset()}
            >
              {t("settings.cardFields.reset")}
            </button>
          </div>
        </>
      )}
    </section>
  );
}
