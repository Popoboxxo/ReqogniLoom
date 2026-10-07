/**
 * ARCH-L1-001 ReactFrontend — IdentifiersSection (UserProfileSettings).
 *
 * leaf_id: COMP-RF-006 (UserProfileSettings — user-owned data controls)
 *
 * Issue #1094. The user's note reads: *"diese lesbaren automatisch
 * hochgezählten IDs ein- und ausblendbar machen im Profil des Users. Kopiert
 * werden soll aber die System-ID!"* — three asks, and this section is where the
 * two user-facing ones live:
 *
 *  1. **hideable** — the checkbox. It drives one module-level store
 *     (`hooks/useReadableIdsVisible`), so every `<IdChip>` in the app follows
 *     immediately, including the hundreds of rows a virtualized list mounts.
 *  2. **in the user profile** — the section itself, plus the `<IdChip>` that
 *     the whole app now shares, so the affordance is defined once here instead
 *     of being re-implemented per page.
 *  3. **copies the system id** — the chip's contract, exercised live on the
 *     signed-in account. The account's readable handle is its `username` and
 *     its system id is the user UUID, which is the same uid-vs-id shape an
 *     artifact has, so the demonstration is the real behaviour and not a mock.
 *
 * Issue #1096 — persistence. This section is the *writer* for the account-scoped
 * endpoint `GET/PATCH /api/v1/users/me/display-preferences/`
 * (`api/display-preferences.ts`). Until #1096 the choice lived only in
 * `localStorage`; it now follows the user across devices. The server is the
 * source of truth:
 *
 *   - on mount the section GETs the effective flags and writes them into the
 *     shared store (which also refreshes the localStorage first-render cache);
 *   - a toggle flips the store optimistically so every chip reacts at once,
 *     PATCHes, then applies the server's returned value;
 *   - a rejected save rolls the store back to the previous value and surfaces
 *     the error — a failed save is never silently swallowed.
 *
 * States
 * ------
 *   - **loading** (`isLoading`): the checkbox is disabled and a `role="status"`
 *     line explains why, while the store shows the cached/default value so the
 *     section does not flash empty.
 *   - **error**: a `role="alert"` element carries the API message (or a
 *     localized fallback) for both a failed load and a failed save.
 *   - **signed out** (`user` not yet resolved): a `role="status"` line instead
 *     of a chip with an empty identifier, which would read as "this account has
 *     no ID" rather than "the session is not loaded".
 *   - **ready**: the chip, with its copy outcome announced through the chip's
 *     own `aria-live` region (success, the no-system-id fallback, and a refused
 *     clipboard are all reported by `<IdChip>` itself).
 */

import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { extractApiErrorMessage } from "../../api/client";
import { displayPreferencesApi } from "../../api/display-preferences";
import { useAuth } from "../../context/AuthContext";
import { useReadableIdsVisible } from "../../hooks/useReadableIdsVisible";
import { IdChip } from "../shared/IdChip";
import styles from "./IdentifiersSection.module.css";

export function IdentifiersSection(): JSX.Element {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [readableIdsVisible, setReadableIdsVisible] = useReadableIdsVisible();
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setError(null);
    displayPreferencesApi
      .get()
      .then((prefs) => {
        if (!cancelled) setReadableIdsVisible(prefs.show_readable_ids);
      })
      .catch((err: unknown) => {
        // A failed load is shown, not swallowed; the cached value stays usable.
        if (!cancelled) setError(extractApiErrorMessage(err) ?? "");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // Mount-only: `setReadableIdsVisible` is a module-level function (stable).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleToggle = useCallback(
    async (next: boolean): Promise<void> => {
      if (isSaving) return;
      const previous = readableIdsVisible;
      setError(null);
      setIsSaving(true);
      // Optimistic: the shared store flips once and every mounted chip follows.
      setReadableIdsVisible(next);
      try {
        // The server's returned flags win — never assume the click took effect.
        const prefs = await displayPreferencesApi.update({ show_readable_ids: next });
        setReadableIdsVisible(prefs.show_readable_ids);
      } catch (err: unknown) {
        // Roll back so the UI does not keep claiming a change the server rejected.
        setReadableIdsVisible(previous);
        setError(extractApiErrorMessage(err) ?? "");
      } finally {
        setIsSaving(false);
      }
    },
    [isSaving, readableIdsVisible, setReadableIdsVisible],
  );

  return (
    <section className={styles.section} data-testid="identifiers-section">
      <h2 className={styles.heading}>{t("identifiers.title")}</h2>
      <p className={styles.hint}>{t("identifiers.hint")}</p>

      <div className={styles.rows}>
        <div className={styles.row} data-testid="identifiers-row-visible">
          <label className={styles.label}>
            <input
              type="checkbox"
              className={styles.checkbox}
              checked={readableIdsVisible}
              disabled={isLoading || isSaving}
              onChange={(event) => void handleToggle(event.target.checked)}
              data-testid="identifiers-show-readable"
            />
            <span className={styles.labelText}>{t("identifiers.showReadable")}</span>
          </label>

          {isLoading ? (
            <p
              role="status"
              data-testid="identifiers-loading"
              className={styles.rowHint}
            >
              {t("identifiers.loading")}
            </p>
          ) : (
            <p className={styles.rowHint}>
              {readableIdsVisible
                ? t("identifiers.readableShown")
                : t("identifiers.readableHidden")}
            </p>
          )}

          {error !== null && (
            <p
              role="alert"
              data-testid="identifiers-error"
              className={styles.error}
            >
              {error || t("identifiers.syncFailed")}
            </p>
          )}

          <p className={styles.accountNote}>{t("identifiers.accountNote")}</p>
        </div>

        <div className={styles.row} data-testid="identifiers-row-account">
          {user ? (
            <>
              <span className={styles.rowLabel}>{t("identifiers.accountLabel")}</span>
              <IdChip
                uid={user.username}
                systemId={user.id}
                label={t("identifiers.accountLabel")}
                hideReadable={!readableIdsVisible}
                testId="identifiers-account-chip"
              />
            </>
          ) : (
            <p
              className={styles.rowHint}
              role="status"
              data-testid="identifiers-account-loading"
            >
              {t("identifiers.accountUnavailable")}
            </p>
          )}
        </div>
      </div>
    </section>
  );
}
