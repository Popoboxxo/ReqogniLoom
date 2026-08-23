/**
 * ARCH-L1-001 ReactFrontend — WorkspaceBannerSection (WorkspaceSettings, general tab).
 *
 * leaf_id: COMP-RF-001 (NavigationShell scope — Workspace-Konfigurations-UI)
 *
 * Workspace-Admin (or System-Admin) editor for this workspace's single
 * banner. Page-level access mirrors PermissionsSection's precedent (parent
 * gates on the admin role, UX-only — real enforcement is server-side via
 * WorkspaceBannerView's ctx.has_role("admin") / is_tenant_admin check).
 * No `show_on_login_page` field — the login page has no workspace context
 * (spec: that flag only exists on the global banner).
 */

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { bannersApi, type Banner, type BannerLevel } from "../../api/banners";
import { extractErrorMessage } from "../../api/client";
import type { UUID } from "../../types";
import styles from "./WorkspaceBannerSection.module.css";

const LEVELS: BannerLevel[] = ["neutral", "info", "warning", "critical"];

interface Props {
  workspaceId: UUID;
}

export function WorkspaceBannerSection({ workspaceId }: Props): JSX.Element {
  const { t } = useTranslation();
  const [banner, setBanner] = useState<Banner | null>(null);
  const [level, setLevel] = useState<BannerLevel>("neutral");
  const [message, setMessage] = useState("");
  const [enabled, setEnabled] = useState(false);
  const [dismissible, setDismissible] = useState(true);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedOk, setSavedOk] = useState(false);

  useEffect(() => {
    setIsLoading(true);
    bannersApi
      .getWorkspace(workspaceId)
      .then((existing) => {
        if (!existing) return;
        setBanner(existing);
        setLevel(existing.level);
        setMessage(existing.message);
        setEnabled(existing.enabled);
        setDismissible(existing.dismissible);
      })
      .catch((err) => setError(extractErrorMessage(err)))
      .finally(() => setIsLoading(false));
  }, [workspaceId]);

  const handleLevelChange = (next: BannerLevel): void => {
    setLevel(next);
    setSavedOk(false);
    if (next === "critical" && !banner) setDismissible(false);
  };

  const handleSave = async (): Promise<void> => {
    setIsSaving(true);
    setError(null);
    setSavedOk(false);
    try {
      const updated = await bannersApi.putWorkspace(workspaceId, {
        level,
        message,
        enabled,
        dismissible,
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
      <section className={styles.section} data-testid="workspace-banner-section">
        <h3 className={styles.heading}>{t("banners.workspaceTitle", "Workspace Banner")}</h3>
        <p>{t("loading", "Loading...")}</p>
      </section>
    );
  }

  return (
    <section className={styles.section} data-testid="workspace-banner-section">
      <h3 className={styles.heading}>{t("banners.workspaceTitle", "Workspace Banner")}</h3>

      {error && <p className={styles.error}>{error}</p>}
      {savedOk && <p className={styles.saved}>{t("actions.saved", "Saved.")}</p>}

      <label className={styles.checkboxLabel}>
        <input
          type="checkbox"
          data-testid="workspace-banner-enabled-toggle"
          checked={enabled}
          onChange={(e) => { setEnabled(e.target.checked); setSavedOk(false); }}
        />
        {t("banners.enabled", "Enabled")}
      </label>

      <div className={styles.field}>
        <span className={styles.label}>{t("banners.levelLabel", "Level")}</span>
        <div className={styles.levelGroup} data-testid="workspace-banner-level-group">
          {LEVELS.map((lvl) => (
            <label key={lvl} className={styles.checkboxLabel}>
              <input
                type="radio"
                name="workspace-banner-level"
                data-testid={`workspace-banner-level-${lvl}`}
                checked={level === lvl}
                onChange={() => handleLevelChange(lvl)}
              />
              {t(`banners.level.${lvl}`, lvl)}
            </label>
          ))}
        </div>
      </div>

      <div className={styles.field}>
        <label className={styles.label} htmlFor="workspace-banner-message-input">
          {t("banners.messageLabel", "Message (Markdown)")}
        </label>
        <textarea
          id="workspace-banner-message-input"
          data-testid="workspace-banner-message-input"
          className={styles.textarea}
          value={message}
          onChange={(e) => { setMessage(e.target.value); setSavedOk(false); }}
          placeholder={t("banners.messagePlaceholder", "Markdown text...")}
        />
      </div>

      <label className={styles.checkboxLabel}>
        <input
          type="checkbox"
          data-testid="workspace-banner-dismissible-toggle"
          checked={dismissible}
          onChange={(e) => { setDismissible(e.target.checked); setSavedOk(false); }}
        />
        {t("banners.dismissibleField", "Dismissible by end users")}
      </label>

      <div>
        <button
          type="button"
          data-testid="workspace-banner-save-button"
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
