/**
 * Memory Admin UI Phase 3 (spec 2026-08-26) — System-Admin override form for
 * the memory feature's embedding provider / memory backend configuration.
 * Mounted in the "memory" tab of SystemSettings, above MemoryManagementSection.
 */

import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  systemMemorySettingsApi,
  type EmbeddingProviderName,
  type MemoryBackendName,
  type SystemMemorySettings,
  type SystemMemorySettingsUpdate,
} from "../../api/system-memory-settings";
import { Dialog } from "../shared/Dialog";
import styles from "./MemorySystemSettingsSection.module.css";

const EMBEDDING_PROVIDERS: EmbeddingProviderName[] = ["sentence-transformers", "ollama", "mock"];
const MEMORY_BACKENDS: MemoryBackendName[] = ["pgvector", "honcho"];

export function MemorySystemSettingsSection(): JSX.Element {
  const { t } = useTranslation();
  const [settings, setSettings] = useState<SystemMemorySettings | null>(null);
  const [form, setForm] = useState<SystemMemorySettingsUpdate>({});
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [pendingWarningConfirm, setPendingWarningConfirm] = useState(false);

  const reload = useCallback((): void => {
    systemMemorySettingsApi
      .get()
      .then((s) => {
        setSettings(s);
        setForm({});
        setLoadError(null);
      })
      .catch((err: unknown) => {
        console.error("MemorySystemSettingsSection: failed to load settings", err);
        setLoadError(t("systemSettings.memorySettings.loadError"));
      });
  }, [t]);

  useEffect(() => {
    reload();
  }, [reload]);

  const isRiskyChange = useCallback((): boolean => {
    if (!settings) return false;
    const providerChanged =
      form.embedding_provider !== undefined && form.embedding_provider !== settings.embedding_provider;
    const backendChanged =
      form.memory_backend !== undefined && form.memory_backend !== settings.memory_backend;
    return providerChanged || backendChanged;
  }, [form, settings]);

  const doSave = useCallback(async (): Promise<void> => {
    setIsSaving(true);
    setSaveError(null);
    try {
      const result = await systemMemorySettingsApi.update(form);
      setSettings(result);
      setForm({});
      setPendingWarningConfirm(false);
    } catch (err) {
      console.error("MemorySystemSettingsSection: failed to save settings", err);
      setSaveError(t("systemSettings.memorySettings.saveError"));
    } finally {
      setIsSaving(false);
    }
  }, [form, t]);

  const handleSaveClick = useCallback((): void => {
    if (isRiskyChange()) {
      setPendingWarningConfirm(true);
      return;
    }
    void doSave();
  }, [isRiskyChange, doSave]);

  const handleReset = useCallback(async (): Promise<void> => {
    if (!window.confirm(t("systemSettings.memorySettings.resetConfirm"))) return;
    setIsSaving(true);
    setSaveError(null);
    try {
      const result = await systemMemorySettingsApi.reset();
      setSettings(result);
      setForm({});
    } catch (err) {
      console.error("MemorySystemSettingsSection: failed to reset settings", err);
      setSaveError(t("systemSettings.memorySettings.saveError"));
    } finally {
      setIsSaving(false);
    }
  }, [t]);

  if (loadError) {
    return (
      <p role="alert" data-testid="memory-system-settings-error" className={styles.error}>
        {loadError}
      </p>
    );
  }
  if (!settings) {
    return <p data-testid="memory-system-settings-loading">{t("loading", "Loading...")}</p>;
  }

  return (
    <section className={styles.section} data-testid="memory-system-settings-section">
      <h3>{t("systemSettings.memorySettings.heading")}</h3>
      <p className={styles.hint}>{t("systemSettings.memorySettings.hint")}</p>

      <label className={styles.field}>
        {t("systemSettings.memorySettings.embeddingProvider")}
        <select
          data-testid="memory-settings-embedding-provider"
          value={form.embedding_provider ?? settings.embedding_provider}
          onChange={(e) =>
            setForm((f) => ({ ...f, embedding_provider: e.target.value as EmbeddingProviderName }))
          }
        >
          {EMBEDDING_PROVIDERS.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
        {settings.embedding_provider_is_override && (
          <span data-testid="embedding-provider-override-badge" className={styles.overrideBadge}>
            {t("systemSettings.memorySettings.overrideBadge")}
          </span>
        )}
      </label>

      <label className={styles.field}>
        {t("systemSettings.memorySettings.memoryBackend")}
        <select
          data-testid="memory-settings-backend"
          value={form.memory_backend ?? settings.memory_backend}
          onChange={(e) => setForm((f) => ({ ...f, memory_backend: e.target.value as MemoryBackendName }))}
        >
          {MEMORY_BACKENDS.map((b) => (
            <option key={b} value={b}>
              {b}
            </option>
          ))}
        </select>
        {settings.memory_backend_is_override && (
          <span data-testid="memory-backend-override-badge" className={styles.overrideBadge}>
            {t("systemSettings.memorySettings.overrideBadge")}
          </span>
        )}
      </label>

      <label className={styles.field}>
        {t("systemSettings.memorySettings.honchoApiKey")}
        <input
          type="password"
          data-testid="memory-settings-honcho-api-key"
          placeholder={
            settings.honcho_api_key_is_set
              ? t("systemSettings.memorySettings.secretSetPlaceholder")
              : t("systemSettings.memorySettings.secretUnsetPlaceholder")
          }
          value={form.honcho_api_key ?? ""}
          onChange={(e) => setForm((f) => ({ ...f, honcho_api_key: e.target.value }))}
        />
      </label>

      {saveError && (
        <p role="alert" data-testid="memory-system-settings-save-error" className={styles.error}>
          {saveError}
        </p>
      )}
      {settings.warning && (
        <p role="alert" data-testid="memory-system-settings-warning" className={styles.warning}>
          {settings.warning}
        </p>
      )}

      <div className={styles.actions}>
        <button
          type="button"
          data-testid="memory-settings-save-btn"
          disabled={isSaving || Object.keys(form).length === 0}
          onClick={handleSaveClick}
        >
          {isSaving ? "…" : t("actions.save", "Save")}
        </button>
        <button type="button" data-testid="memory-settings-reset-btn" disabled={isSaving} onClick={() => void handleReset()}>
          {t("systemSettings.memorySettings.resetButton")}
        </button>
      </div>

      {pendingWarningConfirm && (
        <Dialog
          title={t("systemSettings.memorySettings.confirmTitle")}
          onClose={() => setPendingWarningConfirm(false)}
          size="sm"
          testId="memory-settings-confirm-dialog"
          footer={
            <div className={styles.dialogFooter}>
              <button type="button" onClick={() => setPendingWarningConfirm(false)}>
                {t("actions.cancel", "Cancel")}
              </button>
              <button type="button" data-testid="memory-settings-confirm-btn" disabled={isSaving} onClick={() => void doSave()}>
                {isSaving ? "…" : t("systemSettings.memorySettings.confirmButton")}
              </button>
            </div>
          }
        >
          <p>{t("systemSettings.memorySettings.confirmBody")}</p>
        </Dialog>
      )}
    </section>
  );
}
