/**
 * Memory Admin UI Phase 3 (spec 2026-08-26) — System-Admin override form for
 * the memory feature's embedding provider / memory backend configuration.
 * Mounted in the "memory" tab of SystemSettings, above MemoryManagementSection.
 *
 * #1286: beyond `honcho_api_key` + `honcho_base_url` the form now exposes the
 * remaining Honcho knobs (`honcho_dialectic_level`, `honcho_peer_name`,
 * `honcho_workspace_id`, `honcho_app_id`, `honcho_session_ttl`) plus a
 * read-only `honcho_version`.
 *
 * FOLLOW-UP (stream boundary, no backend change here): the backend's
 * `SystemMemorySettingsWriteSerializer` (backend/memory/memory_rest.py) does
 * not yet declare these keys, so a PUT carrying them is silently dropped and
 * the GET response omits them. The frontend contract in
 * `api/system-memory-settings.ts` already models them; the backend serializer
 * + `_with_env_fallback` still need to add the matching fields (and expose
 * `honcho_version` from Honcho's `/health`). Until then the fields render
 * their loaded/default value and a save is a server-side no-op.
 */

import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  HONCHO_DIALECTIC_LEVELS,
  systemMemorySettingsApi,
  type EmbeddingProviderName,
  type BackendSettingField,
  type MemoryBackendName,
  type SystemMemorySettings,
  type SystemMemorySettingsUpdate,
} from "../../api/system-memory-settings";
import { BackendOptionsFieldset } from "./BackendOptionsFieldset";
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
const MEMORY_BACKENDS: MemoryBackendName[] = ["pgvector", "honcho", "qdrant"];

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

/**
 * T-A0b-5 fallback: an older server (or a test double) predating the additive
 * `backends` block still exposes the flat Honcho fields. This local descriptor
 * renders the same controls and keeps the flat payload until the contract
 * migration removes those columns; the server-declared schema always wins when
 * present.
 */
const FALLBACK_HONCHO_FIELDS: BackendSettingField[] = [
  {
    name: "base_url",
    type: "str",
    env_var: "HONCHO_BASE_URL",
    label_key: "systemSettings.memorySettings.honchoBaseUrl",
    choices: [],
    min_value: null,
    max_length: 255,
    default: null,
  },
  {
    name: "api_key",
    type: "secret",
    env_var: "HONCHO_API_KEY",
    label_key: "systemSettings.memorySettings.honchoApiKey",
    choices: [],
    min_value: null,
    max_length: 512,
    default: null,
  },
  {
    name: "dialectic_level",
    type: "choice",
    env_var: "HONCHO_DIALECTIC_LEVEL",
    label_key: "systemSettings.memorySettings.honchoDialecticLevel",
    choices: [...HONCHO_DIALECTIC_LEVELS],
    min_value: null,
    max_length: null,
    default: null,
  },
  {
    name: "session_ttl",
    type: "int",
    env_var: "HONCHO_SESSION_TTL",
    label_key: "systemSettings.memorySettings.honchoSessionTtl",
    choices: [],
    min_value: 0,
    max_length: null,
    default: null,
  },
];

interface BackendBlock {
  backend: string;
  fields: BackendSettingField[];
  values: Record<string, unknown>;
  isOverride: Record<string, boolean>;
  secretsSet: Record<string, boolean>;
  nested: boolean;
}

/** Staged flat Honcho values for the compatibility renderer (older servers). */
function buildFlatStaged(form: SystemMemorySettingsUpdate): Record<string, unknown> {
  const staged: Record<string, unknown> = {};
  if (form.honcho_base_url !== undefined) staged.base_url = form.honcho_base_url;
  if (form.honcho_dialectic_level !== undefined) {
    staged.dialectic_level = form.honcho_dialectic_level;
  }
  if (form.honcho_session_ttl !== undefined) staged.session_ttl = form.honcho_session_ttl;
  return staged;
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

  const setNestedOption = useCallback(
    (backend: string, field: string, value: unknown): void => {
      setForm((f) => {
        const options = { ...(f.backend_options ?? {}) };
        options[backend] = { ...(options[backend] ?? {}), [field]: value };
        return { ...f, backend_options: options };
      });
    },
    []
  );

  const setNestedSecret = useCallback(
    (backend: string, field: string, value: string): void => {
      setForm((f) => {
        const secrets = { ...(f.backend_secrets ?? {}) };
        const current = { ...(secrets[backend] ?? {}) };
        if (value) current[field] = value;
        else delete current[field];
        if (Object.keys(current).length > 0) secrets[backend] = current;
        else delete secrets[backend];
        const next = { ...f };
        if (Object.keys(secrets).length > 0) next.backend_secrets = secrets;
        else delete next.backend_secrets;
        return next;
      });
    },
    []
  );

  const setFlatOption = useCallback((field: string, value: unknown): void => {
    setForm((f) => {
      const next: SystemMemorySettingsUpdate = { ...f };
      (next as Record<string, unknown>)[`honcho_${field}`] = value;
      return next;
    });
  }, []);

  const setFlatSecret = useCallback((field: string, value: string): void => {
    setForm((f) => {
      const next: SystemMemorySettingsUpdate = { ...f };
      const key = `honcho_${field}`;
      if (value) (next as Record<string, unknown>)[key] = value;
      else delete (next as Record<string, unknown>)[key];
      return next;
    });
  }, []);

  // The server-declared schema wins; without `backends` (older server / test
  // double) the flat Honcho fields remain editable.
  const backendBlocks: BackendBlock[] =
    settings?.backends && Object.keys(settings.backends).length > 0
      ? Object.entries(settings.backends)
          .filter(([, block]) => block.schema.length > 0)
          .map(([backend, block]) => ({
            backend,
            fields: block.schema,
            values: block.values,
            isOverride: block.is_override,
            secretsSet: block.secrets_set,
            nested: true,
          }))
      : [
          {
            backend: "honcho",
            fields: FALLBACK_HONCHO_FIELDS,
            values: {
              base_url: settings?.honcho_base_url ?? null,
              dialectic_level: settings?.honcho_dialectic_level ?? null,
              session_ttl: settings?.honcho_session_ttl ?? null,
            },
            isOverride: {
              base_url: settings?.honcho_base_url_is_override ?? false,
              dialectic_level: settings?.honcho_dialectic_level_is_override ?? false,
              session_ttl: settings?.honcho_session_ttl_is_override ?? false,
            },
            secretsSet: { api_key: settings?.honcho_api_key_is_set ?? false },
            nested: false,
          },
        ];

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

      {backendBlocks.map((block) => {
        const stagedOptions = block.nested
          ? ((form.backend_options?.[block.backend] ?? {}) as Record<string, unknown>)
          : buildFlatStaged(form);
        const stagedSecrets = block.nested
          ? ((form.backend_secrets?.[block.backend] ?? {}) as Record<string, string>)
          : form.honcho_api_key
            ? { api_key: form.honcho_api_key }
            : {};
        return (
          <fieldset key={block.backend} data-testid={`memory-settings-${block.backend}-fields`}>
            <legend>
              {t(`systemSettings.memorySettings.backendHeading.${block.backend}`, {
                defaultValue: block.backend,
              })}
            </legend>
            <BackendOptionsFieldset
              backend={block.backend}
              fields={block.fields}
              values={block.values}
              isOverride={block.isOverride}
              secretsSet={block.secretsSet}
              stagedOptions={stagedOptions}
              stagedSecrets={stagedSecrets}
              onOptionChange={(field, value) =>
                block.nested
                  ? setNestedOption(block.backend, field, value)
                  : setFlatOption(field, value)
              }
              onSecretChange={(field, value) =>
                block.nested
                  ? setNestedSecret(block.backend, field, value)
                  : setFlatSecret(field, value)
              }
            />
          </fieldset>
        );
      })}

      <p className={styles.hint} data-testid="memory-settings-honcho-legacy-fields-hint">
        {t("systemSettings.memorySettings.honchoLegacyFieldsHint")}
      </p>

      <label className={styles.field}>
        {t("systemSettings.memorySettings.honchoPeerName")}
        <input
          type="text"
          data-testid="memory-settings-honcho-peer-name"
          value={textFieldValue(form.honcho_peer_name, settings.honcho_peer_name)}
          onChange={(e) => setForm((f) => ({ ...f, honcho_peer_name: e.target.value || null }))}
        />
        {settings.honcho_peer_name_is_override && (
          <span data-testid="honcho-peer-name-override-badge" className={styles.overrideBadge}>
            {t("systemSettings.memorySettings.overrideBadge")}
          </span>
        )}
      </label>

      <label className={styles.field}>
        {t("systemSettings.memorySettings.honchoWorkspaceId")}
        <input
          type="text"
          data-testid="memory-settings-honcho-workspace-id"
          value={textFieldValue(form.honcho_workspace_id, settings.honcho_workspace_id)}
          onChange={(e) => setForm((f) => ({ ...f, honcho_workspace_id: e.target.value || null }))}
        />
        {settings.honcho_workspace_id_is_override && (
          <span data-testid="honcho-workspace-id-override-badge" className={styles.overrideBadge}>
            {t("systemSettings.memorySettings.overrideBadge")}
          </span>
        )}
      </label>

      <label className={styles.field}>
        {t("systemSettings.memorySettings.honchoAppId")}
        <input
          type="text"
          data-testid="memory-settings-honcho-app-id"
          value={textFieldValue(form.honcho_app_id, settings.honcho_app_id)}
          onChange={(e) => setForm((f) => ({ ...f, honcho_app_id: e.target.value || null }))}
        />
        {settings.honcho_app_id_is_override && (
          <span data-testid="honcho-app-id-override-badge" className={styles.overrideBadge}>
            {t("systemSettings.memorySettings.overrideBadge")}
          </span>
        )}
      </label>

      <label className={styles.field}>
        {t("systemSettings.memorySettings.honchoVersion")}
        <input
          type="text"
          readOnly
          data-testid="memory-settings-honcho-version"
          value={settings.honcho_version ?? ""}
          placeholder={t("systemSettings.memorySettings.honchoVersionUnavailable")}
        />
      </label>

      <label className={styles.field}>
        {t("systemSettings.memorySettings.writeRateLimit")}
        <input
          type="number"
          min={0}
          data-testid="memory-settings-write-rate-limit"
          value={numberFieldValue(
            form.memory_write_rate_limit_per_hour,
            settings.memory_write_rate_limit_per_hour
          )}
          onChange={(e) =>
            setForm((f) => ({
              ...f,
              memory_write_rate_limit_per_hour:
                e.target.value === "" ? null : Number(e.target.value),
            }))
          }
        />
        {settings.memory_write_rate_limit_per_hour_is_override ? (
          <span
            data-testid="write-rate-limit-override-badge"
            className={styles.overrideBadge}
          >
            {t("systemSettings.memorySettings.overrideBadge")}
          </span>
        ) : (
          <span
            data-testid="write-rate-limit-default-hint"
            className={styles.hint}
          >
            {t("systemSettings.memorySettings.usingDefault", "Standardwert aktiv")}
          </span>
        )}
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
          className="btn-primary"
          data-testid="memory-settings-save-btn"
          disabled={isSaving || Object.keys(form).length === 0}
          onClick={handleSaveClick}
        >
          {isSaving ? "…" : t("actions.save", "Save")}
        </button>
        <button type="button" className="btn-secondary" data-testid="memory-settings-reset-btn" disabled={isSaving} onClick={() => setPendingResetConfirm(true)}>
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
              <button type="button" className="btn-secondary" onClick={() => setPendingWarningConfirm(false)}>
                {t("actions.cancel", "Cancel")}
              </button>
              <button type="button" className="btn-primary" data-testid="memory-settings-confirm-btn" disabled={isSaving} onClick={() => void doSave()}>
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
