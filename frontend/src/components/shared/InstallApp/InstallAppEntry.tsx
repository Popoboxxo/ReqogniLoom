/**
 * Single in-app installation entry point (plan M3, REQ-213).
 *
 * Android/Chromium gets the real `beforeinstallprompt` flow; iOS gets an
 * honest instruction sheet (the platform has no install API). Dismissal is
 * persisted as a user preference. Rendered in the sidebar footer and on the
 * profile page from this one component so the two cannot drift apart.
 */
import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useInstallPrompt } from "../../../hooks/useInstallPrompt";
import { preferenceValuesApi } from "../../../api/preference-values";
import { Dialog } from "../Dialog/Dialog";
import styles from "./InstallAppEntry.module.css";

const DISMISS_KEY = "ui.pwa.install_dismissed";

export function InstallAppEntry(): JSX.Element | null {
  const { t } = useTranslation();
  const { canInstall, platform, standalone, promptInstall } = useInstallPrompt();
  const [hintOpen, setHintOpen] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    // A dismissal must survive reloads; the key is a user-level preference.
    void preferenceValuesApi
      .getLevel("user")
      .then((level) => setDismissed(level.values[DISMISS_KEY] === true))
      .catch(() => undefined);
  }, []);

  const dismiss = useCallback((): void => {
    setDismissed(true);
    void preferenceValuesApi
      .patchLevel("user", { values: { [DISMISS_KEY]: true } })
      .catch(() => undefined);
  }, []);

  if (standalone || dismissed) return null;

  const onInstall = async (): Promise<void> => {
    if (platform !== "android" || !canInstall) {
      setHintOpen(true);
      return;
    }
    const outcome = await promptInstall();
    if (outcome === "dismissed") dismiss();
  };

  return (
    <>
      <button
        type="button"
        className={`btn-ghost ${styles.installButton}`}
        data-testid="install-app"
        onClick={() => void onInstall()}
      >
        {t("pwa.install", "Install app")}
      </button>
      {hintOpen && (
        <Dialog
          onClose={() => setHintOpen(false)}
          title={t("pwa.installTitle", "Install ReqogniLoom")}
        >
          <p data-testid="install-hint">{t("pwa.installHint", "Use “Add to Home Screen” from the share menu")}</p>
          <button type="button" className="btn-primary" data-testid="install-hint-dismiss" onClick={dismiss}>
            {t("pwa.installDismiss", "Don't ask again")}
          </button>
        </Dialog>
      )}
    </>
  );
}
