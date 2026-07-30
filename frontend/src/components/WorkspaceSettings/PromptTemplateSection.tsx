/**
 * ARCH-L1-001 ReactFrontend — prompt template admin section (REQ-L2-PT-001).
 *
 * Renders the tenant-scoped LLM prompt templates as three labelled textareas:
 *   - need_to_sysreq            (stakeholder need -> system requirements)
 *   - sysreq_to_arch_assign     (system requirement -> architecture assignment)
 *   - sysreq_decompose_next_level (decompose to the next architecture level)
 *
 * Each slot has a "Reset to default" button (per-slot reset endpoint). A single
 * global Save button PATCHes all three slots at once.
 */

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  promptTemplatesApi,
  PROMPT_SLOTS,
  type PromptSlot,
  type PromptTemplate,
} from "../../api/prompt-templates";
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

const textareaStyle: React.CSSProperties = {
  width: "100%",
  minHeight: "120px",
  padding: "var(--space-2) var(--space-3)",
  background: "var(--color-background)",
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-md)",
  color: "var(--color-text)",
  fontSize: "var(--font-size-sm)",
  fontFamily: "var(--font-mono, monospace)",
  resize: "vertical",
};

/** Human-readable label fallbacks for each slot. */
const SLOT_LABELS: Record<PromptSlot, string> = {
  need_to_sysreq: "Stakeholder Need → System Requirements",
  sysreq_to_arch_assign: "System Requirement → Architecture Assignment",
  sysreq_decompose_next_level: "Decompose to Next Architecture Level",
  goal_aggregate: "Ziel-Aggregation",
};

type SlotValues = Record<PromptSlot, string>;

const EMPTY_VALUES: SlotValues = {
  need_to_sysreq: "",
  sysreq_to_arch_assign: "",
  sysreq_decompose_next_level: "",
  goal_aggregate: "",
};

function extractValues(tpl: PromptTemplate): SlotValues {
  return {
    need_to_sysreq: tpl.need_to_sysreq,
    sysreq_to_arch_assign: tpl.sysreq_to_arch_assign,
    sysreq_decompose_next_level: tpl.sysreq_decompose_next_level,
    goal_aggregate: tpl.goal_aggregate,
  };
}

export function PromptTemplateSection(): JSX.Element {
  const { t } = useTranslation();
  const [values, setValues] = useState<SlotValues>(EMPTY_VALUES);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedOk, setSavedOk] = useState(false);

  useEffect(() => {
    let active = true;
    promptTemplatesApi
      .get()
      .then((tpl) => {
        if (active) setValues(extractValues(tpl));
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

  const handleChange = (slot: PromptSlot, next: string): void => {
    setValues((prev) => ({ ...prev, [slot]: next }));
    setSavedOk(false);
  };

  const handleSave = async (): Promise<void> => {
    setIsSaving(true);
    setError(null);
    setSavedOk(false);
    try {
      const updated = await promptTemplatesApi.update(values);
      setValues(extractValues(updated));
      setSavedOk(true);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setIsSaving(false);
    }
  };

  const handleReset = async (slot: PromptSlot): Promise<void> => {
    setError(null);
    setSavedOk(false);
    try {
      const updated = await promptTemplatesApi.reset(slot);
      setValues(extractValues(updated));
    } catch (err) {
      setError(extractErrorMessage(err));
    }
  };

  if (isLoading) {
    return (
      <section style={sectionStyle} data-testid="prompt-template-section">
        <h3 style={headingStyle}>
          {t("settings.promptTemplates.title", "AI Prompt Templates")}
        </h3>
        <p>{t("loading", "Loading...")}</p>
      </section>
    );
  }

  return (
    <section style={sectionStyle} data-testid="prompt-template-section">
      <h3 style={headingStyle}>
        {t("settings.promptTemplates.title", "AI Prompt Templates")}
      </h3>
      <p
        style={{
          fontSize: "var(--font-size-sm)",
          color: "var(--color-text-muted)",
          marginBottom: "var(--space-4)",
        }}
      >
        {t(
          "settings.promptTemplates.description",
          "Customise the prompts used for AI-assisted derivation. Available placeholders: " +
            "{n} (number of drafts requested), {need_title} and {need_description} " +
            "(stakeholder need), {req_title} and {req_description} (requirement), and " +
            "{arch_elements_json} (candidate architecture elements). Unknown or omitted " +
            "placeholders are left as-is, so existing templates keep working (REQ-046)."
        )}
      </p>

      {PROMPT_SLOTS.map((slot) => (
        <div key={slot} style={{ marginBottom: "var(--space-4)" }}>
          <label style={fieldLabelStyle} htmlFor={`prompt-${slot}`}>
            {t(`settings.promptTemplates.slot.${slot}`, SLOT_LABELS[slot])}
          </label>
          <textarea
            id={`prompt-${slot}`}
            data-testid={`prompt-${slot}-input`}
            value={values[slot]}
            onChange={(e) => handleChange(slot, e.target.value)}
            style={textareaStyle}
          />
          <button
            type="button"
            data-testid={`prompt-${slot}-reset`}
            onClick={() => void handleReset(slot)}
            style={{
              marginTop: "var(--space-2)",
              background: "transparent",
              color: "var(--color-text-muted)",
              border: "1px solid var(--color-border)",
              borderRadius: "var(--radius-md)",
              padding: "var(--space-1) var(--space-3)",
              fontSize: "var(--font-size-sm)",
              cursor: "pointer",
            }}
          >
            {t("settings.promptTemplates.reset", "Reset to default")}
          </button>
        </div>
      ))}

      {error && (
        <p
          data-testid="prompt-template-error"
          style={{ color: "var(--color-error)", marginBottom: "var(--space-3)" }}
        >
          {error}
        </p>
      )}
      {savedOk && (
        <p
          data-testid="prompt-template-saved"
          style={{ color: "var(--color-success)", marginBottom: "var(--space-3)" }}
        >
          {t("settings.saved", "Saved")}
        </p>
      )}

      <button
        type="button"
        data-testid="prompt-template-save"
        onClick={() => void handleSave()}
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
