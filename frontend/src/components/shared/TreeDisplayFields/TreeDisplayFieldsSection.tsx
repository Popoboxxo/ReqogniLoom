/**
 * Issue #1257 — the reusable editor for one level of the tree-display
 * configuration.
 *
 * Mounted three times, once per level (`UserProfileSettings`,
 * `WorkspaceSettings`, `SystemSettings`); each mount edits exactly one scope and
 * shows the fields the server stores for it — never the resolved value, so an
 * admin editing the tenant-wide default does not confuse it with their own
 * personal override.
 *
 * Field keys come from the server catalogue (`GET …/tree-display-config/`), which
 * is built from the attribute-v3 field vocabulary plus the workspace's custom
 * attributes — a custom attribute is therefore configurable without any change
 * here.
 *
 * Interaction:
 *   - a stored list is edited in place: ↑/↓ reorder, × removes;
 *   - the `<select>` appends a not-yet-selected catalogue field;
 *   - "Auf Standard zurücksetzen" (`fields: null`) drops this level's entry, so
 *     resolution falls back to the next level;
 *   - every change is saved immediately (optimistic), and a rejected save is
 *     rolled back and surfaced — a failed save is never silently swallowed.
 *
 * An *unconfigured* item type is shown as "inherited" and its list starts empty:
 * an absent entry means "inherit", an *empty* entry means "render no fields" —
 * two different intentions that must not be conflated in the editor either.
 */

import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { extractApiErrorMessage } from "../../../api/client";
import {
  treeDisplayConfigApi,
  type TreeDisplayCatalogEntry,
  type TreeDisplayField,
  type TreeDisplayScope,
} from "../../../api/tree-display-config";
import {
  loadTreeDisplayFields,
  TREE_DISPLAY_ITEM_TYPES,
} from "../../../hooks/useTreeDisplayFields";
import styles from "./TreeDisplayFieldsSection.module.css";

export interface TreeDisplayFieldsSectionProps {
  /** Which level this mount edits. */
  scope: TreeDisplayScope;
  /** Required for the workspace scope; ignored otherwise. */
  workspaceId?: string | null;
  /** i18n key of the section heading. */
  titleKey: string;
  /** i18n key of the one-line explanation under the heading. */
  hintKey: string;
  /** Prefix for every `data-testid` this section renders. */
  testId: string;
}

type SelectionMap = Record<string, TreeDisplayField[]>;

export function TreeDisplayFieldsSection({
  scope,
  workspaceId,
  titleKey,
  hintKey,
  testId,
}: TreeDisplayFieldsSectionProps): JSX.Element {
  const { t } = useTranslation();

  /**
   * Translate `key`, falling back to `fallback` when the catalogue names a key
   * the locale bundle does not have — a workspace *custom attribute* has no
   * translated label, so its raw key is the honest fallback.
   *
   * Deliberately the single-argument form: i18next returns the key itself for a
   * missing entry, and the two-argument options object is not renderable in the
   * several test doubles that stub `t` minimally.
   */
  const translateOr = useCallback(
    (key: string, fallback: string): string => {
      const translated = t(key);
      return translated === key ? fallback : translated;
    },
    [t]
  );

  const [catalog, setCatalog] = useState<TreeDisplayCatalogEntry[]>([]);
  const [selection, setSelection] = useState<SelectionMap>({});
  const [isLoading, setIsLoading] = useState(true);
  const [pendingType, setPendingType] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setError(null);
    treeDisplayConfigApi
      .getScope(scope, { workspaceId: workspaceId ?? null })
      .then((payload) => {
        if (cancelled) return;
        const map =
          "config" in payload ? (payload.config as SelectionMap) : {};
        setSelection(map);
        setCatalog(payload.catalog);
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
  }, [scope, workspaceId]);

  const fieldLabel = useCallback(
    (key: string): string => {
      const entry = catalog.find((candidate) => candidate.key === key);
      return entry ? translateOr(entry.label_key, entry.label) : key;
    },
    [catalog, translateOr]
  );

  /**
   * Persist one item type's selection (or reset it) and keep the tree's store
   * in step. Optimistic: the local list updates first and rolls back on error.
   */
  const persist = useCallback(
    async (itemType: string, next: TreeDisplayField[] | null): Promise<void> => {
      const previous = selection[itemType];
      setPendingType(itemType);
      setError(null);
      setSelection((current) => {
        const updated = { ...current };
        if (next === null) delete updated[itemType];
        else updated[itemType] = next;
        return updated;
      });
      try {
        await treeDisplayConfigApi.set(
          scope,
          { itemType, fields: next },
          workspaceId ?? null
        );
        // The tree reads the *effective* value, which this save changes
        // indirectly — refresh the cache entry the tree uses. The workspace
        // section knows its workspace, so its entry matches exactly there; the
        // personal/tenant-wide surfaces are edited on their own pages, where no
        // tree is mounted, so the next mount picks the change up anyway.
        if (workspaceId) {
          await loadTreeDisplayFields(itemType, workspaceId, { force: true });
        }
      } catch (err: unknown) {
        setSelection((current) => {
          const rolledBack = { ...current };
          if (previous === undefined) delete rolledBack[itemType];
          else rolledBack[itemType] = previous;
          return rolledBack;
        });
        setError(extractApiErrorMessage(err) ?? "");
      } finally {
        setPendingType(null);
      }
    },
    [scope, workspaceId, selection]
  );

  const availableFields = useCallback(
    (stored: TreeDisplayField[] | undefined): TreeDisplayCatalogEntry[] => {
      const chosen = new Set((stored ?? []).map((entry) => entry.key));
      return catalog.filter((entry) => !chosen.has(entry.key));
    },
    [catalog]
  );

  return (
    <section className={styles.section} data-testid={testId}>
      <h3 className={styles.heading}>{t(titleKey)}</h3>
      <p className={styles.hint}>{t(hintKey)}</p>

      {error !== null && (
        <p role="alert" className={styles.error} data-testid={`${testId}-error`}>
          {error || t("treeDisplay.saveFailed")}
        </p>
      )}

      {isLoading ? (
        <p role="status" className={styles.hint} data-testid={`${testId}-loading`}>
          {t("treeDisplay.loading")}
        </p>
      ) : (
        <ul className={styles.itemTypes} data-testid={`${testId}-item-types`}>
          {TREE_DISPLAY_ITEM_TYPES.map((itemType) => {
            const stored = selection[itemType];
            const isPending = pendingType === itemType;
            const rows = stored ?? [];
            const addable = availableFields(stored);
            return (
              <li
                key={itemType}
                className={styles.itemType}
                data-testid={`${testId}-type-${itemType}`}
              >
                <div className={styles.itemTypeHeader}>
                  <span className={styles.itemTypeName}>
                    {translateOr(`treeDisplay.itemType.${itemType}`, itemType)}
                  </span>
                  <button
                    type="button"
                    className={`btn-ghost ${styles.linkButton}`}
                    disabled={isPending || stored === undefined}
                    onClick={() => void persist(itemType, null)}
                    data-testid={`${testId}-reset-${itemType}`}
                  >
                    {t("treeDisplay.reset")}
                  </button>
                </div>

                {stored === undefined ? (
                  <p
                    className={styles.inherited}
                    data-testid={`${testId}-inherited-${itemType}`}
                  >
                    {t("treeDisplay.inherited")}
                  </p>
                ) : (
                  <ol
                    className={styles.fieldList}
                    data-testid={`${testId}-fields-${itemType}`}
                  >
                    {rows.map((field, index) => (
                      <li
                        key={field.key}
                        className={styles.fieldRow}
                        data-testid={`${testId}-field-${itemType}-${field.key}`}
                      >
                        <span className={styles.fieldName}>{fieldLabel(field.key)}</span>
                        <button
                          type="button"
                          aria-label={t("treeDisplay.moveUp")}
                          title={t("treeDisplay.moveUp")}
                          className={`btn-icon ${styles.iconButton}`}
                          disabled={isPending || index === 0}
                          onClick={() => {
                            const next = [...rows];
                            [next[index - 1], next[index]] = [next[index], next[index - 1]];
                            void persist(itemType, next);
                          }}
                          data-testid={`${testId}-up-${itemType}-${field.key}`}
                        >
                          ↑
                        </button>
                        <button
                          type="button"
                          aria-label={t("treeDisplay.moveDown")}
                          title={t("treeDisplay.moveDown")}
                          className={`btn-icon ${styles.iconButton}`}
                          disabled={isPending || index === rows.length - 1}
                          onClick={() => {
                            const next = [...rows];
                            [next[index + 1], next[index]] = [next[index], next[index + 1]];
                            void persist(itemType, next);
                          }}
                          data-testid={`${testId}-down-${itemType}-${field.key}`}
                        >
                          ↓
                        </button>
                        <button
                          type="button"
                          aria-label={t("treeDisplay.remove")}
                          title={t("treeDisplay.remove")}
                          className={`btn-icon ${styles.iconButton}`}
                          disabled={isPending}
                          onClick={() =>
                            void persist(
                              itemType,
                              rows.filter((entry) => entry.key !== field.key)
                            )
                          }
                          data-testid={`${testId}-remove-${itemType}-${field.key}`}
                        >
                          ×
                        </button>
                      </li>
                    ))}
                  </ol>
                )}

                <select
                  className={styles.addSelect}
                  aria-label={t("treeDisplay.addField")}
                  value=""
                  disabled={isPending || addable.length === 0}
                  onChange={(event) => {
                    const key = event.target.value;
                    if (!key) return;
                    void persist(itemType, [
                      ...rows,
                      { key, width: "half" as const },
                    ]);
                  }}
                  data-testid={`${testId}-add-${itemType}`}
                >
                  <option value="">{t("treeDisplay.addField")}</option>
                  {addable.map((entry) => (
                    <option key={entry.key} value={entry.key}>
                      {translateOr(entry.label_key, entry.label)}
                    </option>
                  ))}
                </select>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
