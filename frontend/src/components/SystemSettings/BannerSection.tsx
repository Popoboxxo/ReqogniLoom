/**
 * ARCH-L1-001 ReactFrontend — BannerSection (SystemSettings, administration tab).
 *
 * leaf_id: COMP-RF-001 (NavigationShell scope — System Settings)
 *
 * System-Admin-only editor for the tenant's single global banner. Page-level
 * access is gated by SystemSettings.tsx's existing `roles.includes("admin")`
 * check (loose, UX-only — matches WorkspaceAdminSection's precedent); real
 * enforcement is server-side via `AuthorizationService.is_tenant_admin`
 * (GlobalBannerView), so a workspace-admin who is not a System-Admin will
 * see this form but get a 403 on save, surfaced as the `error` state below.
 */

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { bannersApi, type Banner, type BannerLevel } from "../../api/banners";
import { extractErrorMessage } from "../../api/client";
import styles from "./BannerSection.module.css";

const LEVELS: BannerLevel[] = ["neutral", "info", "warning", "critical"];

export function BannerSection(): JSX.Element {
  const { t } = useTranslation();
  const [banner, setBanner] = useState<Banner | null>(null);
  const [level, setLevel] = useState<BannerLevel>("neutral");
  const [message, setMessage] = useState("");
  const [enabled, setEnabled] = useState(false);
  const [dismissible, setDismissible] = useState(true);
  const [showOnLoginPage, setShowOnLoginPage] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedOk, setSavedOk] = useState(false);

  useEffect(() => {
    setIsLoading(true);
    bannersApi
      .getGlobal()
      .then((existing) => {
        if (!existing) return;
        setBanner(existing);
        setLevel(existing.level);
        setMessage(existing.message);
        setEnabled(existing.enabled);
        setDismissible(existing.dismissible);
        setShowOnLoginPage(existing.show_on_login_page);
      })
      .catch((err) => setError(extractErrorMessage(err)))
      .finally(() => setIsLoading(false));
  }, []);

  const handleLevelChange = (next: BannerLevel): void => {
    setLevel(next);
    setSavedOk(false);
    // UI-level pre-fill only (spec: "modularer" — always overridable):
    // switching to critical suggests non-dismissible, but never forces it
    // once the admin has touched dismissible for this row.
    if (next === "critical" && !banner) setDismissible(false);
  };

  const handleSave = async (): Promise<void> => {
    setIsSaving(true);
    setError(null);
    setSavedOk(false);
    try {
      const updated = await bannersApi.putGlobal({
        level,
        message,
        enabled,
        dismissible,
        show_on_login_page: showOnLoginPage,
      });
      setBanner(updated);
      setSavedOk(true);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading) {
    return (
      <section className={styles.section} data-testid="banner-section">
        <h3 className={styles.heading}>{t("banners.globalTitle", "Global Banner")}</h3>
        <p>{t("loading", "Loading...")}</p>
      </section>
    );
  }

  return (
    <section className={styles.section} data-testid="banner-section">
      <h3 className={styles.heading}>{t("banners.globalTitle", "Global Banner")}</h3>

      {error && (
        <p role="alert" className={styles.error}>
          {error}
        </p>
      )}
      {savedOk && <p className={styles.saved}>{t("actions.saved", "Saved.")}</p>}

      <label className={styles.checkboxLabel}>
        <input
          type="checkbox"
          data-testid="banner-enabled-toggle"
          checked={enabled}
          onChange={(e) => { setEnabled(e.target.checked); setSavedOk(false); }}
        />
        {t("banners.enabled", "Enabled")}
      </label>

      <div className={styles.field}>
        <span className={styles.label}>{t("banners.levelLabel", "Level")}</span>
        <div className={styles.levelGroup} data-testid="banner-level-group">
          {LEVELS.map((lvl) => (
            <label key={lvl} className={styles.checkboxLabel}>
              <input
                type="radio"
                name="banner-level"
                data-testid={`banner-level-${lvl}`}
                checked={level === lvl}
                onChange={() => handleLevelChange(lvl)}
              />
              {t(`banners.level.${lvl}`, lvl)}
            </label>
          ))}
        </div>
      </div>

      <div className={styles.field}>
        <label className={styles.label} htmlFor="banner-message-input">
          {t("banners.messageLabel", "Message (Markdown)")}
        </label>
        <textarea
          id="banner-message-input"
          data-testid="banner-message-input"
          className={styles.textarea}
          value={message}
          onChange={(e) => { setMessage(e.target.value); setSavedOk(false); }}
          placeholder={t("banners.messagePlaceholder", "Markdown text...")}
        />
      </div>

      <label className={styles.checkboxLabel}>
        <input
          type="checkbox"
          data-testid="banner-dismissible-toggle"
          checked={dismissible}
          onChange={(e) => { setDismissible(e.target.checked); setSavedOk(false); }}
        />
        {t("banners.dismissibleField", "Dismissible by end users")}
      </label>

      <label className={styles.checkboxLabel}>
        <input
          type="checkbox"
          data-testid="banner-show-on-login-toggle"
          checked={showOnLoginPage}
          onChange={(e) => { setShowOnLoginPage(e.target.checked); setSavedOk(false); }}
        />
        {t("banners.showOnLoginPage", "Also show on the login page")}
      </label>

      <div>
        <button
          type="button"
          data-testid="banner-save-button"
          className={styles.saveButton}
          disabled={isSaving}
          onClick={() => void handleSave()}
        >
          {isSaving ? "…" : t("actions.save")}
        </button>
      </div>
    </section>
  );
}
