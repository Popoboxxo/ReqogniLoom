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
import { ConfirmDialog } from "../shared/ConfirmDialog";
import styles from "./MemorySystemSettingsSection.module.css";

// "openai" is a registered, documented backend provider (1536-dim); a
// deployment configured that way must be able to see/keep it selected.
const EMBEDDING_PROVIDERS: EmbeddingProviderName[] = [
  "sentence-transformers",
  "ollama",
  "openai",
  "mock",
];
// "honcho" routes memory to an external Honcho service; it also needs the
// Honcho base URL field below to be filled in, which System Health surfaces.
// Keep in sync with SystemMemorySettingsWriteSerializer.memory_backend.
const MEMORY_BACKENDS: MemoryBackendName[] = ["pgvector", "honcho"];

/**
 * Display value for an optional text field: a staged `null` (user cleared the
 * input) must render as empty, NOT fall back to the loaded effective value —
 * `??` alone would redraw the old value under the user's cursor.
 */
function textFieldValue(staged: string | null | undefined, loaded: string | null): string {
  return staged !== undefined ? (staged ?? "") : (loaded ?? "");
}

/** Same staged-vs-loaded distinction as {@link textFieldValue}, for the one numeric field. */
function numberFieldValue(staged: number | null | undefined, loaded: number | null): number | string {
  return staged !== undefined ? (staged ?? "") : (loaded ?? "");
}

export function MemorySystemSettingsSection(): JSX.Element {
  const { t } = useTranslation();
  const [settings, setSettings] = useState<SystemMemorySettings | null>(null);
  const [form, setForm] = useState<SystemMemorySettingsUpdate>({});
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [pendingWarningConfirm, setPendingWarningConfirm] = useState(false);
  // UI-20: unified on the shared ConfirmDialog instead of window.confirm.
  const [pendingResetConfirm, setPendingResetConfirm] = useState(false);

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
        {t("systemSettings.memorySettings.embeddingModelName")}
        <input
          type="text"
          data-testid="memory-settings-embedding-model-name"
          value={textFieldValue(form.embedding_model_name, settings.embedding_model_name)}
          onChange={(e) =>
            // Empty input -> send `null` (clear the override), never `""`:
            // the runtime overlay ignores an empty string, so storing one
            // would report an active override that does not actually apply.
            setForm((f) => ({ ...f, embedding_model_name: e.target.value || null }))
          }
        />
        {settings.embedding_model_name_is_override && (
          <span data-testid="embedding-model-name-override-badge" className={styles.overrideBadge}>
            {t("systemSettings.memorySettings.overrideBadge")}
          </span>
        )}
      </label>

      <label className={styles.field}>
        {t("systemSettings.memorySettings.ollamaBaseUrl")}
        <input
          type="text"
          data-testid="memory-settings-ollama-base-url"
          value={textFieldValue(form.ollama_base_url, settings.ollama_base_url)}
          onChange={(e) => setForm((f) => ({ ...f, ollama_base_url: e.target.value || null }))}
        />
        {settings.ollama_base_url_is_override && (
          <span data-testid="ollama-base-url-override-badge" className={styles.overrideBadge}>
            {t("systemSettings.memorySettings.overrideBadge")}
          </span>
        )}
      </label>

      <label className={styles.field}>
        {t("systemSettings.memorySettings.embeddingTimeout")}
        <input
          type="number"
          data-testid="memory-settings-embedding-timeout"
          value={numberFieldValue(form.embedding_timeout, settings.embedding_timeout)}
          onChange={(e) =>
            setForm((f) => ({
              ...f,
              embedding_timeout: e.target.value === "" ? null : Number(e.target.value),
            }))
          }
        />
        {settings.embedding_timeout_is_override && (
          <span data-testid="embedding-timeout-override-badge" className={styles.overrideBadge}>
            {t("systemSettings.memorySettings.overrideBadge")}
          </span>
        )}
      </label>

      <label className={styles.field}>
        {t("systemSettings.memorySettings.honchoBaseUrl")}
        <input
          type="text"
          data-testid="memory-settings-honcho-base-url"
          value={textFieldValue(form.honcho_base_url, settings.honcho_base_url)}
          onChange={(e) => setForm((f) => ({ ...f, honcho_base_url: e.target.value || null }))}
        />
        {settings.honcho_base_url_is_override && (
          <span data-testid="honcho-base-url-override-badge" className={styles.overrideBadge}>
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
          onChange={(e) =>
            setForm((f) => {
              const { honcho_api_key: _honchoApiKey, ...rest } = f;
              return e.target.value ? { ...rest, honcho_api_key: e.target.value } : rest;
            })
          }
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
        <button type="button" data-testid="memory-settings-reset-btn" disabled={isSaving} onClick={() => setPendingResetConfirm(true)}>
          {t("systemSettings.memorySettings.resetButton")}
        </button>
      </div>

      {pendingResetConfirm && (
        <ConfirmDialog
          title={t("systemSettings.memorySettings.resetButton")}
          message={t("systemSettings.memorySettings.resetConfirm")}
          confirmLabel={t("systemSettings.memorySettings.resetButton")}
          onConfirm={() => {
            setPendingResetConfirm(false);
            void handleReset();
          }}
          onCancel={() => setPendingResetConfirm(false)}
          testId="memory-settings-reset-confirm"
        />
      )}

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
          {saveError && (
            <p role="alert" data-testid="memory-settings-confirm-dialog-error" className={styles.error}>
              {saveError}
            </p>
          )}
        </Dialog>
      )}
    </section>
  );
}
