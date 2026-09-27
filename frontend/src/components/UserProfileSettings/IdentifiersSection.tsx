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
 * States
 * ------
 * This section performs **no fetch**: the preference is read synchronously from
 * `localStorage` (see the hook for why there is no server round trip — the
 * repo's two `/users/me/*` preference endpoints have closed vocabularies and
 * neither is a display-preference resource), and the identity shown belongs to
 * the session `AuthContext` already resolved. So there is no loading and no
 * error state to render here, and pretending otherwise would be dead code. The
 * states that DO exist are handled explicitly:
 *
 *   - **signed out** (`user` not yet resolved): a `role="status"` line instead
 *     of a chip with an empty identifier, which would read as "this account has
 *     no ID" rather than "the session is not loaded".
 *   - **ready**: the chip, with its copy outcome announced through the chip's
 *     own `aria-live` region (success, the no-system-id fallback, and a refused
 *     clipboard are all reported by `<IdChip>` itself).
 *
 * The persistence gap is stated to the user in the hint rather than hidden: the
 * choice currently applies to this browser only, and a display-preference
 * endpoint is needed to carry it across devices.
 */

import { useTranslation } from "react-i18next";

import { useAuth } from "../../context/AuthContext";
import { useReadableIdsVisible } from "../../hooks/useReadableIdsVisible";
import { IdChip } from "../shared/IdChip";
import styles from "./IdentifiersSection.module.css";

export function IdentifiersSection(): JSX.Element {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [readableIdsVisible, setReadableIdsVisible] = useReadableIdsVisible();

  return (
    <section className={styles.section} data-testid="identifiers-section">
      <h2 className={styles.heading}>{t("identifiers.title", "Kennungen")}</h2>
      <p className={styles.hint}>
        {t(
          "identifiers.hint",
          "Artefakte tragen zwei Kennungen: eine lesbare, im Workspace hochgezählte (z. B. REQ-001) und eine System-ID (UUID). Kopiert wird immer die System-ID, weil nur sie außerhalb dieses Workspaces gilt.",
        )}
      </p>

      <div className={styles.rows}>
        <div className={styles.row} data-testid="identifiers-row-visible">
          <label className={styles.label}>
            <input
              type="checkbox"
              className={styles.checkbox}
              checked={readableIdsVisible}
              onChange={(event) => setReadableIdsVisible(event.target.checked)}
              data-testid="identifiers-show-readable"
            />
            <span className={styles.labelText}>
              {t(
                "identifiers.showReadable",
                "Lesbare IDs anzeigen (z. B. REQ-001)",
              )}
            </span>
          </label>
          <p className={styles.rowHint}>
            {readableIdsVisible
              ? t(
                  "identifiers.readableShown",
                  "Lesbare IDs werden angezeigt. Die System-ID bleibt zusätzlich kopierbar.",
                )
              : t(
                  "identifiers.readableHidden",
                  "Lesbare IDs sind ausgeblendet. Die System-ID bleibt kopierbar.",
                )}
          </p>
          <p className={styles.persistenceNote}>
            {t(
              "identifiers.persistenceNote",
              "Hinweis: Diese Einstellung wird nur in diesem Browser gespeichert. Für einen server-seitigen Benutzer-Vorzug wird noch ein eigener Endpunkt benötigt.",
            )}
          </p>
        </div>

        <div className={styles.row} data-testid="identifiers-row-account">
          {user ? (
            <>
              <span className={styles.rowLabel}>
                {t("identifiers.accountLabel", "Ihr Konto")}
              </span>
              <IdChip
                uid={user.username}
                systemId={user.id}
                label={t("identifiers.accountLabel", "Ihr Konto")}
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
              {t("identifiers.accountUnavailable", "Konto wird geladen…")}
            </p>
          )}
        </div>
      </div>
    </section>
  );
}
