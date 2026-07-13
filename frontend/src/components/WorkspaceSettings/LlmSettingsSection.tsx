/**
 * ARCH-L1-001 ReactFrontend — LLM settings admin section (REQ-L2-LLM-001).
 *
 * Renders the tenant-scoped LLM provider configuration form:
 *   - provider dropdown (anthropic / openai / ollama / mock)
 *   - base_url input (Ollama only)
 *   - api_key password input (write-only; placeholder reflects api_key_is_set)
 *   - model_name text input
 *   - Save button
 *
 * The api_key is never returned by the backend; an empty submission keeps the
 * stored key unchanged.
 */

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  llmSettingsApi,
  LLM_PROVIDERS,
  type LlmProvider,
} from "../../api/llm-settings";
import { extractErrorMessage } from "../../api/client";

const sectionStyle: React.CSSProperties = {
  background: "var(--color-surface)",
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-lg)",
  padding: "var(--space-5)",
  marginBottom: "var(--space-5)",
  boxShadow: "var(--shadow-card)",
};

const headingStyle: React.CSSProperties = {
  fontSize: "var(--font-size-lg)",
  fontWeight: 600,
  color: "var(--color-text)",
  margin: "0 0 var(--space-4) 0",
};

const fieldLabelStyle: React.CSSProperties = {
  display: "block",
  marginBottom: "var(--space-2)",
  fontWeight: 600,
  color: "var(--color-text)",
  fontSize: "var(--font-size-sm)",
};

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "var(--space-2) var(--space-3)",
  background: "var(--color-background)",
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-md)",
  color: "var(--color-text)",
  fontSize: "var(--font-size-sm)",
  marginBottom: "var(--space-4)",
};

export function LlmSettingsSection(): JSX.Element {
  const { t } = useTranslation();
  const [provider, setProvider] = useState<LlmProvider>("mock");
  const [baseUrl, setBaseUrl] = useState("");
  const [modelName, setModelName] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [apiKeyIsSet, setApiKeyIsSet] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedOk, setSavedOk] = useState(false);

  useEffect(() => {
    let active = true;
    llmSettingsApi
      .get()
      .then((s) => {
        if (!active) return;
        setProvider(s.provider);
        setBaseUrl(s.base_url);
        setModelName(s.model_name);
        setApiKeyIsSet(s.api_key_is_set);
      })
      .catch((err) => {
        if (active) setError(extractErrorMessage(err));
      })
      .finally(() => {
        if (active) setIsLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const handleSave = async (): Promise<void> => {
    setIsSaving(true);
    setError(null);
    setSavedOk(false);
    try {
      const payload: {
        provider: LlmProvider;
        base_url: string;
        model_name: string;
        api_key?: string;
      } = { provider, base_url: baseUrl, model_name: modelName };
      // Only send api_key when the user typed a new one (write-only field).
      if (apiKey) payload.api_key = apiKey;
      const updated = await llmSettingsApi.update(payload);
      setApiKeyIsSet(updated.api_key_is_set);
      setApiKey("");
      setSavedOk(true);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading) {
    return (
      <section style={sectionStyle} data-testid="llm-settings-section">
        <h3 style={headingStyle}>{t("settings.llm.title", "LLM Provider")}</h3>
        <p>{t("loading", "Loading...")}</p>
      </section>
    );
  }

  return (
    <section style={sectionStyle} data-testid="llm-settings-section">
      <h3 style={headingStyle}>{t("settings.llm.title", "LLM Provider")}</h3>
      <p
        style={{
          fontSize: "var(--font-size-sm)",
          color: "var(--color-text-muted)",
          marginBottom: "var(--space-4)",
        }}
      >
        {t(
          "settings.llm.description",
          "Configure the LLM provider used for AI-assisted derivation. Credentials are stored per tenant and never returned by the API."
        )}
      </p>

      <label style={fieldLabelStyle} htmlFor="llm-provider">
        {t("settings.llm.provider", "Provider")}
      </label>
      <select
        id="llm-provider"
        data-testid="llm-provider-select"
        value={provider}
        onChange={(e) => setProvider(e.target.value as LlmProvider)}
        style={inputStyle}
      >
        {LLM_PROVIDERS.map((p) => (
          <option key={p} value={p}>
            {p}
          </option>
        ))}
      </select>

      {provider === "ollama" && (
        <>
          <label style={fieldLabelStyle} htmlFor="llm-base-url">
            {t("settings.llm.baseUrl", "Base URL")}
          </label>
          <input
            id="llm-base-url"
            data-testid="llm-base-url-input"
            type="url"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder="http://localhost:11434"
            style={inputStyle}
          />
        </>
      )}

      <label style={fieldLabelStyle} htmlFor="llm-api-key">
        {t("settings.llm.apiKey", "API Key")}
      </label>
      <input
        id="llm-api-key"
        data-testid="llm-api-key-input"
        type="password"
        value={apiKey}
        onChange={(e) => setApiKey(e.target.value)}
        placeholder={
          apiKeyIsSet
            ? "••••••••"
            : t("settings.llm.apiKeyNotSet", "Not set")
        }
        style={inputStyle}
      />

      <label style={fieldLabelStyle} htmlFor="llm-model-name">
        {t("settings.llm.modelName", "Model Name")}
      </label>
      <input
        id="llm-model-name"
        data-testid="llm-model-name-input"
        type="text"
        value={modelName}
        onChange={(e) => setModelName(e.target.value)}
        placeholder="claude-3-opus-20240229"
        style={inputStyle}
      />

      {error && (
        <p
          data-testid="llm-settings-error"
          style={{ color: "var(--color-error)", marginBottom: "var(--space-3)" }}
        >
          {error}
        </p>
      )}
      {savedOk && (
        <p
          data-testid="llm-settings-saved"
          style={{ color: "var(--color-success)", marginBottom: "var(--space-3)" }}
        >
          {t("settings.saved", "Saved")}
        </p>
      )}

      <button
        type="button"
        data-testid="llm-settings-save"
        onClick={handleSave}
        disabled={isSaving}
        style={{
          background: "var(--color-primary)",
          color: "white",
          border: "none",
          borderRadius: "var(--radius-md)",
          padding: "var(--space-2) var(--space-4)",
          fontSize: "var(--font-size-sm)",
          fontWeight: 600,
          cursor: isSaving ? "not-allowed" : "pointer",
          opacity: isSaving ? 0.7 : 1,
        }}
      >
        {isSaving ? t("saving", "Saving...") : t("save", "Save")}
      </button>
    </section>
  );
}
