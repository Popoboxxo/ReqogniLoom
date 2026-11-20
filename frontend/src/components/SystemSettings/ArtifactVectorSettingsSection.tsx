/**
 * Artifact vector store settings (ADR-020 extension).
 *
 * Admin surface for the store that serves artifact ANN search. Qdrant was
 * previously configurable only through `ARTIFACT_VECTOR_BACKEND` / `QDRANT_*`
 * environment variables; this section makes the selector, the per-backend
 * schema and the effective-vs-requested diagnostic visible and editable.
 *
 * The fields are rendered generically from the server-declared schema
 * (`backends.<name>.schema`), so a new registered backend appears without a
 * frontend change — same contract as the memory settings surface.
 */
import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  artifactVectorSettingsApi,
  type ArtifactVectorSettings,
} from "../../api/system-artifact-vector-settings";
import { BackendOptionsFieldset } from "./BackendOptionsFieldset";
import { ConfirmDialog } from "../shared/ConfirmDialog";
import styles from "./MemorySystemSettingsSection.module.css";

type OptionMap = Record<string, unknown>;
type SecretMap = Record<string, string>;

const EMPTY_OPTIONS: Record<string, OptionMap> = {};
const EMPTY_SECRETS: Record<string, SecretMap> = {};

export function ArtifactVectorSettingsSection(): JSX.Element {
  const { t } = useTranslation();
  const [settings, setSettings] = useState<ArtifactVectorSettings | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savedNotice, setSavedNotice] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [backend, setBackend] = useState<string>("");
  const [stagedOptions, setStagedOptions] = useState<Record<string, OptionMap>>(EMPTY_OPTIONS);
  const [stagedSecrets, setStagedSecrets] = useState<Record<string, SecretMap>>(EMPTY_SECRETS);
  const [pendingReset, setPendingReset] = useState(false);

  const reload = useCallback(async (): Promise<void> => {
    setLoadError(null);
    try {
      const result = await artifactVectorSettingsApi.get();
      setSettings(result);
      setBackend(result.vector_backend ?? "");
      setStagedOptions(EMPTY_OPTIONS);
      setStagedSecrets(EMPTY_SECRETS);
    } catch (err) {
      console.error("ArtifactVectorSettingsSection: failed to load settings", err);
      setLoadError(t("systemSettings.artifactVectorSettings.loadError"));
    }
  }, [t]);

  useEffect(() => {
    void reload();
  }, [reload]);

  // When no explicit override is selected, edit the backend the environment
  // currently resolves to — otherwise an env-configured Qdrant deployment
  // would show a backend choice but no fields to configure.
  const displayBackend = backend || settings?.effective_vector_backend || "";
  const activeBlock = displayBackend ? settings?.backends[displayBackend] : undefined;

  const onOptionChange = (field: string, value: unknown): void => {
    if (!displayBackend) return;
    setStagedOptions((prev) => ({
      ...prev,
      [displayBackend]: { ...(prev[displayBackend] ?? {}), [field]: value },
    }));
    setSavedNotice(null);
  };

  const onSecretChange = (field: string, value: string): void => {
    if (!displayBackend) return;
    setStagedSecrets((prev) => ({
      ...prev,
      [displayBackend]: { ...(prev[displayBackend] ?? {}), [field]: value },
    }));
    setSavedNotice(null);
  };

  const doSave = useCallback(async (): Promise<void> => {
    setIsSaving(true);
    setSaveError(null);
    setSavedNotice(null);
    try {
      const result = await artifactVectorSettingsApi.update({
        vector_backend: backend === "" ? null : backend,
        backend_options: stagedOptions,
        backend_secrets: stagedSecrets,
      });
      setSettings(result);
      setBackend(result.vector_backend ?? "");
      setStagedOptions(EMPTY_OPTIONS);
      setStagedSecrets(EMPTY_SECRETS);
      setSavedNotice(t("actions.saved"));
    } catch (err) {
      console.error("ArtifactVectorSettingsSection: failed to save settings", err);
      setSaveError(t("systemSettings.artifactVectorSettings.saveError"));
    } finally {
      setIsSaving(false);
    }
  }, [backend, stagedOptions, stagedSecrets, t]);

  const doReset = useCallback(async (): Promise<void> => {
    setIsSaving(true);
    setSaveError(null);
    setSavedNotice(null);
    try {
      const result = await artifactVectorSettingsApi.reset();
      setSettings(result);
      setBackend(result.vector_backend ?? "");
      setStagedOptions(EMPTY_OPTIONS);
      setStagedSecrets(EMPTY_SECRETS);
      setPendingReset(false);
      setSavedNotice(t("actions.saved"));
    } catch (err) {
      console.error("ArtifactVectorSettingsSection: failed to reset settings", err);
      setSaveError(t("systemSettings.artifactVectorSettings.saveError"));
    } finally {
      setIsSaving(false);
    }
  }, [t]);

  if (loadError) {
    return (
      <section className={styles.section} data-testid="artifact-vector-settings-section">
        <h2>{t("systemSettings.artifactVectorSettings.heading")}</h2>
        <p role="alert" className={styles.error} data-testid="artifact-vector-settings-error">
          {loadError}
        </p>
        <button
          type="button"
          className="btn-secondary"
          data-testid="artifact-vector-settings-retry"
          onClick={() => void reload()}
        >
          {t("actions.retry")}
        </button>
      </section>
    );
  }

  if (!settings) {
    return (
      <section className={styles.section} data-testid="artifact-vector-settings-section">
        <p role="status" className={styles.hint}>
          {t("loading")}
        </p>
      </section>
    );
  }

  const diagnostic = settings.diagnostic;
  const fallbackActive = diagnostic.reason !== "";

  return (
    <section className={styles.section} data-testid="artifact-vector-settings-section">
      <h2>{t("systemSettings.artifactVectorSettings.heading")}</h2>
      <p className={styles.hint}>{t("systemSettings.artifactVectorSettings.hint")}</p>

      <p
        className={fallbackActive ? styles.warning : styles.hint}
        data-testid="artifact-vector-settings-diagnostic"
        role="status"
      >
        {t("systemSettings.artifactVectorSettings.diagnostic", {
          requested: diagnostic.requested,
          active: diagnostic.active,
        })}
        {fallbackActive
          ? ` ${t(
              `systemSettings.artifactVectorSettings.reason.${diagnostic.reason}`,
              { defaultValue: diagnostic.reason }
            )}`
          : ""}
      </p>

      <label className={styles.field}>
        {t("systemSettings.artifactVectorSettings.backend")}
        <select
          data-testid="artifact-vector-settings-backend"
          value={backend}
          disabled={isSaving}
          onChange={(e) => {
            setBackend(e.target.value);
            setSavedNotice(null);
          }}
        >
          <option value="">
            {t("systemSettings.artifactVectorSettings.backendEnvDefault")}
          </option>
          {settings.available_backends.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
      </label>

      {activeBlock && (
        <BackendOptionsFieldset
          backend={displayBackend}
          testIdPrefix="artifact-vector-settings"
          fields={activeBlock.schema}
          values={activeBlock.values}
          isOverride={activeBlock.is_override}
          secretsSet={activeBlock.secrets_set}
          stagedOptions={stagedOptions[displayBackend] ?? {}}
          stagedSecrets={stagedSecrets[displayBackend] ?? {}}
          onOptionChange={onOptionChange}
          onSecretChange={onSecretChange}
        />
      )}

      {saveError && (
        <p role="alert" className={styles.error} data-testid="artifact-vector-settings-save-error">
          {saveError}
        </p>
      )}
      {savedNotice && !saveError && (
        <p role="status" className={styles.hint} data-testid="artifact-vector-settings-saved">
          {savedNotice}
        </p>
      )}

      <div className={styles.actions}>
        <button
          type="button"
          className="btn-primary"
          data-testid="artifact-vector-settings-save"
          disabled={isSaving}
          onClick={() => void doSave()}
        >
          {isSaving ? "…" : t("actions.save")}
        </button>
        <button
          type="button"
          className="btn-secondary"
          data-testid="artifact-vector-settings-reset"
          disabled={isSaving}
          onClick={() => setPendingReset(true)}
        >
          {t("systemSettings.artifactVectorSettings.reset")}
        </button>
      </div>

      {pendingReset && (
        <ConfirmDialog
          title={t("systemSettings.artifactVectorSettings.resetConfirmTitle")}
          message={t("systemSettings.artifactVectorSettings.resetConfirmBody")}
          confirmLabel={t("systemSettings.artifactVectorSettings.reset")}
          onConfirm={() => void doReset()}
          onCancel={() => setPendingReset(false)}
          testId="artifact-vector-settings-reset-confirm"
        />
      )}
    </section>
  );
}
