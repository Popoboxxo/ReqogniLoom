/**
 * Offline notice + update banner (plan M2, REQ-214).
 *
 * Both are context-free primitives rendered next to the app shell: an offline
 * banner tells the user why writes fail, the update banner asks before a new
 * service worker takes over. `data-testid` on both for E2E.
 */
import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  onPwaUpdateAvailable,
  pwaApplyUpdate,
  pwaNeedsRefresh,
} from "../../../pwa/register";
import styles from "./PwaNotices.module.css";

export function PwaNotices(): JSX.Element | null {
  const { t } = useTranslation();
  const [online, setOnline] = useState(() =>
    typeof navigator === "undefined" ? true : navigator.onLine
  );
  const [updateAvailable, setUpdateAvailable] = useState(() => pwaNeedsRefresh());

  useEffect(() => {
    const onOnline = (): void => setOnline(true);
    const onOffline = (): void => setOnline(false);
    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOffline);
    const unsubscribe = onPwaUpdateAvailable(() => setUpdateAvailable(pwaNeedsRefresh()));
    return () => {
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOffline);
      unsubscribe();
    };
  }, []);

  const applyUpdate = useCallback((): void => {
    void pwaApplyUpdate();
  }, []);

  if (online && !updateAvailable) return null;

  return (
    <div className={styles.pwaNotices} role="status" aria-live="polite">
      {!online && (
        <div className={`${styles.pwaNotice} ${styles.offline}`} data-testid="offline-notice">
          {t("pwa.offlineNotice", "Offline — Änderungen können nicht gespeichert werden.")}
        </div>
      )}
      {updateAvailable && (
        <div className={`${styles.pwaNotice} ${styles.update}`} data-testid="pwa-update-banner">
          <span>{t("pwa.updateAvailable", "Neue Version verfügbar.")}</span>
          <button type="button" className="btn-primary" onClick={applyUpdate} data-testid="pwa-update-apply">
            {t("pwa.updateApply", "Jetzt neu laden")}
          </button>
        </div>
      )}
    </div>
  );
}
