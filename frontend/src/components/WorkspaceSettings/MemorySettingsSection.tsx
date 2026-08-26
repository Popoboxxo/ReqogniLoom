/**
 * ARCH-L1-001 ReactFrontend — MemorySettingsSection (WorkspaceSettings,
 * general tab). Spec 2026-08-24, Task 11.
 *
 * Per-workspace enable/disable toggle for the AI Long-Term Memory feature.
 * Any workspace member sees the current state; the toggle itself is
 * server-enforced editor+ (``WorkspaceMemorySettingsView.put``) — a viewer
 * who clicks it gets the PUT's 403 surfaced via `error`.
 */

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { memorySettingsApi } from "../../api/memory-settings";
import { extractErrorMessage } from "../../api/client";
import type { UUID } from "../../types";
import styles from "./MemorySettingsSection.module.css";

interface Props {
  workspaceId: UUID;
}

export function MemorySettingsSection({ workspaceId }: Props): JSX.Element {
  const { t } = useTranslation();
  const [enabled, setEnabled] = useState(true);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedOk, setSavedOk] = useState(false);

  useEffect(() => {
    setIsLoading(true);
    memorySettingsApi
      .get(workspaceId)
      .then((settings) => setEnabled(settings.enabled))
      .catch((err) => setError(extractErrorMessage(err)))
      .finally(() => setIsLoading(false));
  }, [workspaceId]);

  const handleToggle = async (next: boolean): Promise<void> => {
    const previous = enabled;
    setEnabled(next);
    setIsSaving(true);
    setError(null);
    setSavedOk(false);
    try {
      const updated = await memorySettingsApi.update(workspaceId, next);
      setEnabled(updated.enabled);
      setSavedOk(true);
    } catch (err) {
      setEnabled(previous);
      setError(extractErrorMessage(err));
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading) {
    return (
      <section className={styles.section} data-testid="memory-settings-section">
        <h3 className={styles.heading}>{t("settings.memory.title", "AI Memory")}</h3>
        <p>{t("loading", "Loading...")}</p>
      </section>
    );
  }

  return (
    <section className={styles.section} data-testid="memory-settings-section">
      <h3 className={styles.heading}>{t("settings.memory.title", "AI Memory")}</h3>
      <p className={styles.description}>
        {t(
          "settings.memory.description",
          "Learns and recalls facts from interactions in this workspace to improve AI-assisted suggestions over time.",
        )}
      </p>

      <label className={styles.toggleLabel} data-disabled={isSaving}>
        <input
          type="checkbox"
          data-testid="memory-settings-toggle"
          checked={enabled}
          disabled={isSaving}
          onChange={(e) => void handleToggle(e.target.checked)}
        />
        {t("settings.memory.enabled", "Enabled")}
      </label>

      {error && (
        <p className={styles.error} data-testid="memory-settings-error">
          {error}
        </p>
      )}
      {savedOk && (
        <p className={styles.saved} data-testid="memory-settings-saved">
          {t("settings.saved", "Saved")}
        </p>
      )}
    </section>
  );
}
