/**
 * Issue #1263 — the reusable editor for one level of the create-dialog form
 * definition, with a live preview of the resulting "new artifact" dialog.
 *
 * Mounted once per level (`WorkspaceSettings` for the workspace override,
 * `SystemSettings` for the tenant-wide default); each mount edits exactly one
 * scope and shows the entries the server stores for it — never the resolved
 * value, so an admin editing the tenant-wide default does not confuse it with
 * their own personal override.
 *
 * The selectable fields come from the server catalogue (the resolved Attribute-v3
 * definition projected to form entries), so a custom attribute is configurable
 * without any change here. Per field the editor exposes exactly the four knobs
 * the issue names — visible, required, order (↑/↓) and default (via the
 * attribute definition, carried through unchanged) — and the preview beside it
 * renders the visible fields, in order, with their required markers, so the
 * effect of an edit is visible immediately.
 *
 * Every change is saved immediately (optimistic); a rejected save is rolled back
 * and surfaced — a failed save is never silently swallowed. "Auf Standard
 * zurücksetzen" (`fields: null`) drops this level's entry, so resolution falls
 * back to the next level.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { extractApiErrorMessage } from "../../../api/client";
import {
  createFormConfigApi,
  type CreateFormFieldEntry,
  type CreateFormScope,
} from "../../../api/create-form-config";
import {
  CREATE_FORM_ITEM_TYPES,
  mergeCreateFormEntries,
} from "../../../hooks/useCreateFormFields";
import styles from "./CreateFormFieldsSection.module.css";

export interface CreateFormFieldsSectionProps {
  /** Which level this mount edits. */
  scope: CreateFormScope;
  /** Required for the workspace scope; ignored otherwise. */
  workspaceId?: string | null;
  /** i18n key of the section heading. */
  titleKey: string;
  /** i18n key of the one-line explanation under the heading. */
  hintKey: string;
  /** Prefix for every `data-testid` this section renders. */
  testId: string;
}

function sortEntries(entries: CreateFormFieldEntry[]): CreateFormFieldEntry[] {
  return [...entries].sort(
    (a, b) => a.order - b.order || a.field_key.localeCompare(b.field_key)
  );
}

/** Re-number `order` to the list position, so move/reset stay dense. */
function withDenseOrder(entries: CreateFormFieldEntry[]): CreateFormFieldEntry[] {
  return entries.map((entry, index) => ({ ...entry, order: index }));
}

export function CreateFormFieldsSection({
  scope,
  workspaceId,
  titleKey,
  hintKey,
  testId,
}: CreateFormFieldsSectionProps): JSX.Element {
  const { t } = useTranslation();

  /**
   * Translate `key`, falling back to `fallback` when the catalogue names a key
   * the locale bundle does not have — a workspace *custom attribute* has no
   * translated label, so its raw key is the honest fallback.
   */
  const translateOr = useCallback(
    (key: string, fallback: string): string => {
      const translated = t(key);
      return translated === key ? fallback : translated;
    },
    [t]
  );

  const [itemType, setItemType] = useState<string>(CREATE_FORM_ITEM_TYPES[0]);
  const [catalog, setCatalog] = useState<CreateFormFieldEntry[]>([]);
  const [stored, setStored] = useState<CreateFormFieldEntry[] | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isPending, setIsPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setError(null);
    createFormConfigApi
      .getScope(scope, { itemType, workspaceId: workspaceId ?? null })
      .then((payload) => {
        if (cancelled) return;
        setCatalog(payload.catalog ?? []);
        setStored(payload.fields ?? null);
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
  }, [scope, workspaceId, itemType]);

  /** The level's effective entries: the base overlaid with its stored row. */
  const effective = useMemo(
    () => mergeCreateFormEntries(catalog, stored),
    [catalog, stored]
  );

  /** The visible fields, in order — what the create dialog would render. */
  const preview = useMemo(
    () => effective.filter((entry) => entry.visible),
    [effective]
  );

  const persist = useCallback(
    async (next: CreateFormFieldEntry[] | null): Promise<void> => {
      const previous = stored;
      setIsPending(true);
      setError(null);
      setStored(next);
      try {
        await createFormConfigApi.set(
          scope,
          { itemType, fields: next },
          workspaceId ?? null
        );
      } catch (err: unknown) {
        setStored(previous);
        setError(extractApiErrorMessage(err) ?? "");
      } finally {
        setIsPending(false);
      }
    },
    [itemType, scope, workspaceId, stored]
  );

  /**
   * Apply a mutation on the effective list. Starting from `effective` (not from
   * `stored`) means the first edit of an *inherited* level materializes the full
   * entry list — so the level then owns every field's flags, which is what a
   * "set here" state means.
   */
  const mutate = useCallback(
    (transform: (entries: CreateFormFieldEntry[]) => CreateFormFieldEntry[]) => {
      void persist(withDenseOrder(transform(effective)));
    },
    [effective, persist]
  );

  const fieldLabel = useCallback(
    (key: string): string => {
      const entry = catalog.find((candidate) => candidate.field_key === key);
      return entry
        ? translateOr(`createForm.field.${key}`, key)
        : key;
    },
    [catalog, translateOr]
  );

  return (
    <section className={styles.section} data-testid={testId}>
      <h3 className={styles.heading}>{t(titleKey)}</h3>
      <p className={styles.hint}>{t(hintKey)}</p>

      {error !== null && (
        <p role="alert" className={styles.error} data-testid={`${testId}-error`}>
          {error || t("createForm.saveFailed")}
        </p>
      )}

      <div className={styles.toolbar}>
        <label className={styles.hint} htmlFor={`${testId}-item-type`}>
          {t("createForm.itemType")}
        </label>
        <select
          id={`${testId}-item-type`}
          className={styles.itemTypeSelect}
          value={itemType}
          onChange={(event) => setItemType(event.target.value)}
          data-testid={`${testId}-item-type`}
        >
          {CREATE_FORM_ITEM_TYPES.map((type) => (
            <option key={type} value={type}>
              {translateOr(`treeDisplay.itemType.${type}`, type)}
            </option>
          ))}
        </select>
        <button
          type="button"
          className={`btn-ghost ${styles.linkButton}`}
          disabled={isPending || stored === null}
          onClick={() => void persist(null)}
          data-testid={`${testId}-reset-${itemType}`}
        >
          {t("createForm.reset")}
        </button>
      </div>

      {isLoading ? (
        <p role="status" className={styles.hint} data-testid={`${testId}-loading`}>
          {t("createForm.loading")}
        </p>
      ) : (
        <div className={styles.columns}>
          <div className={styles.panel}>
            <h4 className={styles.panelTitle}>{t("createForm.fieldsTitle")}</h4>
            {stored === null && (
              <p
                className={styles.inherited}
                data-testid={`${testId}-inherited-${itemType}`}
              >
                {t("createForm.inherited")}
              </p>
            )}
            <ul className={styles.fieldList} data-testid={`${testId}-fields`}>
              {sortEntries(effective).map((entry, index) => (
                <li
                  key={entry.field_key}
                  className={styles.fieldRow}
                  data-testid={`${testId}-field-${entry.field_key}`}
                >
                  <span className={styles.fieldName}>
                    {fieldLabel(entry.field_key)}
                  </span>
                  <label className={styles.checkboxLabel}>
                    <input
                      type="checkbox"
                      checked={entry.visible}
                      disabled={isPending}
                      onChange={(event) =>
                        mutate((entries) =>
                          entries.map((candidate) =>
                            candidate.field_key === entry.field_key
                              ? { ...candidate, visible: event.target.checked }
                              : candidate
                          )
                        )
                      }
                      data-testid={`${testId}-visible-${entry.field_key}`}
                    />
                    {t("createForm.visible")}
                  </label>
                  <label className={styles.checkboxLabel}>
                    <input
                      type="checkbox"
                      checked={entry.required}
                      disabled={isPending || !entry.visible}
                      onChange={(event) =>
                        mutate((entries) =>
                          entries.map((candidate) =>
                            candidate.field_key === entry.field_key
                              ? { ...candidate, required: event.target.checked }
                              : candidate
                          )
                        )
                      }
                      data-testid={`${testId}-required-${entry.field_key}`}
                    />
                    {t("createForm.required")}
                  </label>
                  <button
                    type="button"
                    aria-label={t("createForm.moveUp")}
                    title={t("createForm.moveUp")}
                    className={`btn-icon ${styles.iconButton}`}
                    disabled={isPending || index === 0}
                    onClick={() =>
                      mutate((entries) => {
                        const next = sortEntries(entries);
                        [next[index - 1], next[index]] = [
                          next[index],
                          next[index - 1],
                        ];
                        return next;
                      })
                    }
                    data-testid={`${testId}-up-${entry.field_key}`}
                  >
                    ↑
                  </button>
                  <button
                    type="button"
                    aria-label={t("createForm.moveDown")}
                    title={t("createForm.moveDown")}
                    className={`btn-icon ${styles.iconButton}`}
                    disabled={isPending || index === effective.length - 1}
                    onClick={() =>
                      mutate((entries) => {
                        const next = sortEntries(entries);
                        [next[index + 1], next[index]] = [
                          next[index],
                          next[index + 1],
                        ];
                        return next;
                      })
                    }
                    data-testid={`${testId}-down-${entry.field_key}`}
                  >
                    ↓
                  </button>
                </li>
              ))}
            </ul>
          </div>

          <div className={styles.panel}>
            <h4 className={styles.panelTitle}>{t("createForm.previewTitle")}</h4>
            <div className={styles.preview} data-testid={`${testId}-preview`}>
              {preview.length === 0 ? (
                <p className={styles.previewEmpty} data-testid={`${testId}-preview-empty`}>
                  {t("createForm.previewEmpty")}
                </p>
              ) : (
                preview.map((entry) => (
                  <div
                    key={entry.field_key}
                    className={styles.previewField}
                    data-testid={`${testId}-preview-field-${entry.field_key}`}
                  >
                    <span>
                      {fieldLabel(entry.field_key)}
                      {entry.required ? (
                        <span
                          className={styles.previewRequired}
                          aria-hidden="true"
                        >
                          {" *"}
                        </span>
                      ) : null}
                    </span>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
