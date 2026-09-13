/**
 * AttributeCatalogDialog (WS5 #942, spec section 8).
 *
 * The "Aus Katalog hinzufügen" entry point: search/browse the tenant's
 * item-type-independent template library, pick one entry and resolve a name
 * collision, then copy it into the currently edited definition.
 *
 * Shaped after `AttributeImportDialog`: the actual apply is owned by
 * `AttributeEditorPage` (it knows the scope — global preset vs. workspace id),
 * so this dialog stays a pure picker and receives `onAdd` as a callback. It
 * loads the catalog itself, because the search/browse state is local to the
 * dialog.
 *
 * State matrix (mandatory): `loading` (initial fetch / debounced search),
 * `error` (fetch failed), `empty` (no match) and `success` (entry list
 * rendered); the apply step additionally carries its own `submitting` and
 * error state so a rejected copy keeps the dialog open with the reason shown.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  attributeCatalogApi,
  type AttributeCatalogEntry,
} from "../../api/attributeCatalog";
import type { AttributeItemType, OnCollision } from "../../api/attribute-definitions";
import { extractErrorMessage } from "../../api/client";
import { Dialog } from "../shared/Dialog";
import editorStyles from "./AttributeEditor.module.css";
import styles from "./AttributeCatalogDialog.module.css";

const CHOICES: OnCollision[] = ["skip", "overwrite", "rename"];

/**
 * Keystroke debounce for the search field. Long enough to avoid one request
 * per character, short enough that the result still feels live; tests wait on
 * the rendered outcome, not on the timer.
 */
const SEARCH_DEBOUNCE_MS = 250;

export interface AttributeCatalogDialogProps {
  /** Item type the currently edited definition belongs to. */
  itemType: AttributeItemType;
  /** Applies one entry into the current definition (parent owns scope + reload). */
  onAdd: (entry: AttributeCatalogEntry, onCollision: OnCollision) => Promise<void>;
  onClose: () => void;
}

export function AttributeCatalogDialog({
  itemType,
  onAdd,
  onClose,
}: AttributeCatalogDialogProps): JSX.Element {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const [includeDeprecated, setIncludeDeprecated] = useState(false);
  const [entries, setEntries] = useState<AttributeCatalogEntry[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [onCollision, setOnCollision] = useState<OnCollision>("skip");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const trimmedQuery = query.trim();

  useEffect(() => {
    let active = true;
    setLoading(true);
    setLoadError(null);
    const timer = window.setTimeout(() => {
      const filters = { includeDeprecated };
      const request = trimmedQuery
        ? attributeCatalogApi.searchEntries(trimmedQuery, filters)
        : attributeCatalogApi.listEntries(filters);
      request
        .then((result) => {
          if (!active) return;
          setEntries(result);
        })
        .catch((exc: unknown) => {
          if (!active) return;
          setEntries([]);
          setLoadError(extractErrorMessage(exc));
        })
        .finally(() => {
          if (active) setLoading(false);
        });
    }, SEARCH_DEBOUNCE_MS);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [trimmedQuery, includeDeprecated]);

  const selectedEntry = useMemo(
    () => entries?.find((entry) => entry.id === selectedId) ?? null,
    [entries, selectedId]
  );

  const handleConfirm = useCallback(async (): Promise<void> => {
    if (!selectedEntry) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      await onAdd(selectedEntry, onCollision);
      onClose();
    } catch (exc: unknown) {
      setSubmitError(extractErrorMessage(exc));
    } finally {
      setSubmitting(false);
    }
  }, [onAdd, onClose, onCollision, selectedEntry]);

  const busy = submitting || loading;

  return (
    <Dialog
      title={t("attributes.catalog.dialogTitle")}
      description={t("attributes.catalog.itemTypeHint", {
        itemType: t(`attributes.entityTypes.${itemType}`, { defaultValue: itemType }),
      })}
      onClose={onClose}
      testId="attribute-catalog-dialog"
      closeOnBackdropClick={!submitting}
      footer={
        <>
          <button
            type="button"
            data-testid="attribute-catalog-cancel"
            onClick={onClose}
            disabled={submitting}
          >
            {t("actions.cancel")}
          </button>
          <button
            type="button"
            data-testid="attribute-catalog-add"
            onClick={() => void handleConfirm()}
            disabled={!selectedEntry || busy}
          >
            {t("attributes.catalog.add")}
          </button>
        </>
      }
    >
      <div className={styles.catalogForm}>
        <label className={editorStyles.field}>
          <span>{t("attributes.catalog.searchLabel")}</span>
          <input
            className={editorStyles.control}
            type="search"
            data-testid="attribute-catalog-search"
            value={query}
            placeholder={t("attributes.catalog.searchPlaceholder")}
            autoFocus
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>

        <label className={styles.checkboxLabel}>
          <input
            type="checkbox"
            data-testid="attribute-catalog-include-deprecated"
            checked={includeDeprecated}
            onChange={(event) => setIncludeDeprecated(event.target.checked)}
          />
          {t("attributes.catalog.includeDeprecated")}
        </label>

        {loadError ? (
          <div
            className={editorStyles.error}
            role="alert"
            data-testid="attribute-catalog-error"
          >
            {t("attributes.catalog.error")}
            {loadError ? ` — ${loadError}` : ""}
          </div>
        ) : null}

        {submitError ? (
          <div
            className={editorStyles.error}
            role="alert"
            data-testid="attribute-catalog-submit-error"
          >
            {submitError}
          </div>
        ) : null}

        {loading && entries === null ? (
          <p className={styles.status} data-testid="attribute-catalog-loading">
            {t("attributes.catalog.loading")}
          </p>
        ) : entries !== null && entries.length === 0 ? (
          <p className={styles.status} data-testid="attribute-catalog-empty">
            {t("attributes.catalog.empty")}
          </p>
        ) : (
          <ul
            className={styles.entryList}
            role="radiogroup"
            aria-label={t("attributes.catalog.entriesLabel")}
            data-testid="attribute-catalog-entries"
          >
            {(entries ?? []).map((entry) => {
              const selected = entry.id === selectedId;
              return (
                <li key={entry.id}>
                  <label
                    className={
                      selected
                        ? `${styles.entryLabel} ${styles.entryLabelSelected}`
                        : styles.entryLabel
                    }
                  >
                    <input
                      type="radio"
                      name="attribute-catalog-entry"
                      data-testid={`attribute-catalog-entry-${entry.id}`}
                      checked={selected}
                      onChange={() => setSelectedId(entry.id)}
                    />
                    <span className={styles.entryMain}>
                      <span className={styles.entryName}>{entry.name}</span>
                      <span className={styles.entryMeta}>
                        <span className={styles.badge}>
                          {entry.category || t("attributes.catalog.noCategory")}
                        </span>
                        {entry.tags.map((tag) => (
                          <span key={tag} className={styles.badge}>
                            {tag}
                          </span>
                        ))}
                        {entry.deprecated ? (
                          <span
                            className={`${styles.badge} ${styles.deprecatedBadge}`}
                            data-testid={`attribute-catalog-entry-${entry.id}-deprecated`}
                          >
                            {t("attributes.catalog.deprecatedBadge")}
                          </span>
                        ) : null}
                      </span>
                    </span>
                  </label>
                </li>
              );
            })}
          </ul>
        )}

        {selectedEntry ? (
          <fieldset className={styles.collisionFieldset}>
            <legend>{t("attributes.catalog.onCollisionLabel")}</legend>
            {CHOICES.map((choice) => (
              <label key={choice} className={styles.radioLabel}>
                <input
                  type="radio"
                  name="attribute-catalog-on-collision"
                  data-testid={`attribute-catalog-on-collision-${choice}`}
                  checked={onCollision === choice}
                  disabled={submitting}
                  onChange={() => setOnCollision(choice)}
                />
                {t(`attributes.catalog.onCollision.${choice}`)}
              </label>
            ))}
          </fieldset>
        ) : (
          <p className={styles.hint}>{t("attributes.catalog.selectHint")}</p>
        )}
      </div>
    </Dialog>
  );
}
