/**
 * ARCH-L1-001 ReactFrontend — LLM settings admin section (REQ-L2-LLM-001).
 *
 * Renders the tenant-scoped LLM provider configuration form:
 *   - provider dropdown (see LLM_PROVIDERS)
 *   - base_url input (Ollama only)
 *   - api_key password input (write-only; placeholder reflects api_key_is_set)
 *   - model_name text input
 *   - Save button
 *
 * The api_key is never returned by the backend; an empty submission keeps the
 * stored key unchanged.
 *
 * Forward compatibility (issue #274): the backend enum may know provider
 * values that this frontend build does not. A `<select>` cannot render a
 * value that has no matching `<option>` — the browser silently falls back to
 * the FIRST option ("anthropic"), so a Save without any user edit used to
 * overwrite a working configuration with a different provider. Two guards
 * prevent that now:
 *   1. an unrecognized server value is rendered as its own (selected) option
 *      plus an explicit hint, so the UI never shows a wrong provider;
 *   2. `provider` is only part of the PATCH payload when the selected value
 *      is one this build actually knows — an untouched form can therefore
 *      never downgrade an unknown-but-working provider.
 */

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  llmSettingsApi,
  LLM_PROVIDERS,
  type LlmProvider,
  type LlmSettingsUpdate,
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
  background: "var(--color-surface-raised)",
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-md)",
  color: "var(--color-text)",
  fontSize: "var(--font-size-sm)",
  marginBottom: "var(--space-4)",
};

/** Warning shown when the server reports a provider this build cannot edit. */
const unsupportedProviderHintStyle: React.CSSProperties = {
  color: "var(--color-warning)",
  fontSize: "var(--font-size-sm)",
  marginTop: "calc(-1 * var(--space-3))",
  marginBottom: "var(--space-4)",
};

/**
 * Type guard: does this build know `value` as a selectable provider?
 *
 * Deliberately kept local (rather than exported from `api/llm-settings`)
 * because the test suite auto-mocks that module and re-supplies only the
 * `LLM_PROVIDERS` constant.
 */
function isKnownProvider(value: string): value is LlmProvider {
  return (LLM_PROVIDERS as readonly string[]).includes(value);
}

export function LlmSettingsSection(): JSX.Element {
  const { t } = useTranslation();
  // Typed as `string`, not `LlmProvider`: the server may legitimately return
  // an enum value this build predates (see the module docstring).
  const [provider, setProvider] = useState<string>("mock");
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
      const payload: LlmSettingsUpdate = {
        base_url: baseUrl,
        model_name: modelName,
      };
      // Only send provider when this build recognises the selected value.
      // An unrecognised value can only originate from the server, and echoing
      // a *different* one back would silently destroy a working config (#274).
      if (isKnownProvider(provider)) payload.provider = provider;
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
        onChange={(e) => setProvider(e.target.value)}
        style={inputStyle}
      >
        {/*
          Render the server value itself when it is unknown to this build, so
          the browser cannot fall back to the first option and display a
          provider that is not actually configured (#274).
        */}
        {!isKnownProvider(provider) && (
          <option value={provider}>
            {t(
              "settings.llm.providerUnsupportedOption",
              "{{provider}} (not supported by this UI version)",
              { provider }
            )}
          </option>
        )}
        {LLM_PROVIDERS.map((p) => (
          <option key={p} value={p}>
            {p}
          </option>
        ))}
      </select>
      {!isKnownProvider(provider) && (
        <p
          data-testid="llm-provider-unsupported-hint"
          style={unsupportedProviderHintStyle}
        >
          {t(
            "settings.llm.providerUnsupportedHint",
            "Provider \"{{provider}}\" is not supported by this UI version. It stays unchanged on save unless you pick a different provider.",
            { provider }
          )}
        </p>
      )}

      {(provider === "ollama" ||
        provider === "opencode_go" ||
        provider === "anthropic" ||
        provider === "openai") && (
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
          style={{ color: "var(--color-danger)", marginBottom: "var(--space-3)" }}
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
          color: "var(--color-on-primary)",
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
