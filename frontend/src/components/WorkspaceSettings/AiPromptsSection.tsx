import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Workspace } from "../../types";

interface Props {
  workspace: Workspace;
  onSavePrompts: (prompts: Record<string, string>) => Promise<void>;
}

export function AiPromptsSection({ workspace, onSavePrompts }: Props): JSX.Element {
  const { t } = useTranslation();
  const [prompts, setPrompts] = useState<Record<string, string>>(workspace.ai_prompts || {});
  const [isSaving, setIsSaving] = useState(false);
  const [activePrompt, setActivePrompt] = useState<string | null>(null);

  const handlePromptChange = (level: string, value: string) => {
    setPrompts((prev) => ({ ...prev, [level]: value }));
  };

  const handleSave = async () => {
    setIsSaving(true);
    await onSavePrompts(prompts);
    setIsSaving(false);
  };

  const cardStyle = (isActive: boolean): React.CSSProperties => ({
    background: isActive ? "rgba(255, 255, 255, 0.05)" : "rgba(255, 255, 255, 0.02)",
    border: `1px solid ${isActive ? "rgba(79, 110, 247, 0.5)" : "rgba(255, 255, 255, 0.1)"}`,
    borderRadius: "16px",
    padding: "24px",
    backdropFilter: "blur(12px)",
    WebkitBackdropFilter: "blur(12px)",
    boxShadow: isActive 
      ? "0 8px 32px rgba(79, 110, 247, 0.15)" 
      : "0 4px 16px rgba(0, 0, 0, 0.1)",
    transition: "all 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
    transform: isActive ? "translateY(-2px)" : "translateY(0)",
    marginBottom: "24px",
    position: "relative",
    overflow: "hidden",
  });

  const glowStyle = (isActive: boolean): React.CSSProperties => ({
    position: "absolute",
    top: 0,
    left: 0,
    width: "100%",
    height: "2px",
    background: "linear-gradient(90deg, transparent, var(--color-primary), transparent)",
    opacity: isActive ? 1 : 0,
    transition: "opacity 0.3s ease",
  });

  const textAreaStyle = (isActive: boolean): React.CSSProperties => ({
    width: "100%",
    background: "rgba(0, 0, 0, 0.2)",
    border: `1px solid ${isActive ? "rgba(79, 110, 247, 0.3)" : "rgba(255, 255, 255, 0.1)"}`,
    borderRadius: "12px",
    padding: "16px",
    color: "var(--color-text)",
    fontFamily: "var(--font-mono, monospace)",
    fontSize: "0.9rem",
    lineHeight: "1.6",
    outline: "none",
    resize: "vertical",
    transition: "all 0.3s ease",
    marginTop: "16px",
    boxShadow: isActive ? "inset 0 2px 4px rgba(0,0,0,0.2)" : "none",
  });

  const headerStyle: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: "12px",
    marginBottom: "8px",
  };

  const iconStyle: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    width: "32px",
    height: "32px",
    borderRadius: "8px",
    background: "linear-gradient(135deg, var(--color-primary), #8B5CF6)",
    color: "white",
    fontWeight: "bold",
    fontSize: "1rem",
    boxShadow: "0 2px 8px rgba(79, 110, 247, 0.3)",
  };

  return (
    <section style={{ animation: "fadeIn 0.5s ease" }}>
      <div style={{ marginBottom: "32px" }}>
        <h3 style={{ 
          fontSize: "1.5rem", 
          fontWeight: 700, 
          background: "linear-gradient(90deg, #ffffff, #a5b4fc)",
          WebkitBackgroundClip: "text",
          WebkitTextFillColor: "transparent",
          marginBottom: "8px",
        }}>
          {t("settings.aiPrompts", "AI Derivation Prompts")}
        </h3>
        <p style={{ color: "var(--color-text-muted)", fontSize: "0.95rem", lineHeight: 1.5 }}>
          {t("settings.aiPromptsDesc", "Design the intelligence of your workspace. Fine-tune how the AI derives requirements across different architectural levels using specialized prompts.")}
        </p>
      </div>

      <div style={{
        display: "grid",
        gridTemplateColumns: "1fr 1fr",
        gap: "var(--space-4)",
        marginBottom: "var(--space-6)",
      }}>
        <div style={{ background: "rgba(255, 255, 255, 0.02)", padding: "16px", borderRadius: "12px", border: "1px solid rgba(255, 255, 255, 0.1)" }}>
          <label style={{ display: "block", marginBottom: "8px", fontWeight: 600, color: "var(--color-text)" }}>
            {t("settings.aiLlmModel", "LLM Model")}
          </label>
          <select
            value={prompts["llm_model"] || "gpt-4"}
            onChange={(e) => handlePromptChange("llm_model", e.target.value)}
            style={{
              width: "100%", padding: "10px", background: "rgba(0, 0, 0, 0.2)",
              border: "1px solid rgba(255, 255, 255, 0.1)", borderRadius: "8px",
              color: "var(--color-text)", fontSize: "0.95rem"
            }}
          >
            <option value="gpt-4">GPT-4 (OpenAI)</option>
            <option value="gpt-4o">GPT-4o (OpenAI)</option>
            <option value="claude-3-opus">Claude 3 Opus (Anthropic)</option>
            <option value="claude-3-5-sonnet">Claude 3.5 Sonnet (Anthropic)</option>
            <option value="gemini-1-5-pro">Gemini 1.5 Pro (Google)</option>
            <option value="local-llama3">Llama 3 (Local)</option>
          </select>
          <p style={{ color: "var(--color-text-muted)", fontSize: "0.8rem", marginTop: "8px", marginBottom: 0 }}>
            {t("settings.aiLlmDesc", "Select the underlying LLM engine for processing derivations.")}
          </p>
        </div>

        <div style={{ background: "rgba(255, 255, 255, 0.02)", padding: "16px", borderRadius: "12px", border: "1px solid rgba(255, 255, 255, 0.1)" }}>
          <label style={{ display: "block", marginBottom: "8px", fontWeight: 600, color: "var(--color-text)" }}>
            {t("settings.aiTestMode", "Test Mode (Dry Run)")}
          </label>
          <select
            value={prompts["test_mode"] || "false"}
            onChange={(e) => handlePromptChange("test_mode", e.target.value)}
            style={{
              width: "100%", padding: "10px", background: "rgba(0, 0, 0, 0.2)",
              border: "1px solid rgba(255, 255, 255, 0.1)", borderRadius: "8px",
              color: "var(--color-text)", fontSize: "0.95rem"
            }}
          >
            <option value="false">{t("settings.aiTestModeOff", "Off (Execute normally)")}</option>
            <option value="true">{t("settings.aiTestModeOn", "On (Simulate output only)")}</option>
          </select>
          <p style={{ color: "var(--color-text-muted)", fontSize: "0.8rem", marginTop: "8px", marginBottom: 0 }}>
            {t("settings.aiTestDesc", "If enabled, AI Derivation will simulate creating artifacts instead of saving them to DB.")}
          </p>
        </div>
      </div>

      <div 
        style={cardStyle(activePrompt === "L0_L1")}
        onMouseEnter={() => setActivePrompt("L0_L1")}
        onMouseLeave={() => setActivePrompt(null)}
      >
        <div style={glowStyle(activePrompt === "L0_L1")} />
        <div style={headerStyle}>
          <div style={iconStyle}>L1</div>
          <label style={{ fontSize: "1.1rem", fontWeight: 600, color: "var(--color-text)" }}>
            {t("settings.prompt.l0_to_l1", "Needs ➔ System Requirements")}
          </label>
        </div>
        <p style={{ color: "var(--color-text-muted)", fontSize: "0.85rem", marginLeft: "44px" }}>
          Instruct the AI on how to translate high-level stakeholder needs into verifiable system requirements.
        </p>
        <textarea
          style={textAreaStyle(activePrompt === "L0_L1")}
          rows={5}
          value={prompts["L0_L1"] || ""}
          onChange={(e) => handlePromptChange("L0_L1", e.target.value)}
          onFocus={() => setActivePrompt("L0_L1")}
          onBlur={() => setActivePrompt(null)}
          placeholder="e.g., Translate the following stakeholder need into verifiable system requirements. Ensure they follow INCOSE guidelines..."
        />
      </div>

      <div 
        style={cardStyle(activePrompt === "L1_L2")}
        onMouseEnter={() => setActivePrompt("L1_L2")}
        onMouseLeave={() => setActivePrompt(null)}
      >
        <div style={glowStyle(activePrompt === "L1_L2")} />
        <div style={headerStyle}>
          <div style={iconStyle}>L2</div>
          <label style={{ fontSize: "1.1rem", fontWeight: 600, color: "var(--color-text)" }}>
            {t("settings.prompt.l1_to_l2", "System Req ➔ Architecture")}
          </label>
        </div>
        <p style={{ color: "var(--color-text-muted)", fontSize: "0.85rem", marginLeft: "44px" }}>
          Define the rules for decomposing system requirements into software and hardware architecture components.
        </p>
        <textarea
          style={textAreaStyle(activePrompt === "L1_L2")}
          rows={5}
          value={prompts["L1_L2"] || ""}
          onChange={(e) => handlePromptChange("L1_L2", e.target.value)}
          onFocus={() => setActivePrompt("L1_L2")}
          onBlur={() => setActivePrompt(null)}
          placeholder="e.g., Decompose this system requirement into software architecture components. Assign ASIL levels if relevant..."
        />
      </div>

      <div style={{ display: "flex", justifyContent: "flex-end", marginTop: "32px" }}>
        <button
          onClick={handleSave}
          data-testid="ai-prompts-save-btn"
          disabled={isSaving}
          style={{
            background: "linear-gradient(135deg, var(--color-primary), #4f46e5)",
            color: "white",
            border: "none",
            borderRadius: "12px",
            padding: "12px 32px",
            fontSize: "1rem",
            fontWeight: 600,
            cursor: isSaving ? "not-allowed" : "pointer",
            opacity: isSaving ? 0.7 : 1,
            boxShadow: "0 4px 14px rgba(79, 110, 247, 0.4)",
            transition: "all 0.3s ease",
            transform: isSaving ? "scale(0.98)" : "scale(1)",
          }}
          onMouseEnter={(e) => {
            if (!isSaving) {
              e.currentTarget.style.transform = "translateY(-2px)";
              e.currentTarget.style.boxShadow = "0 6px 20px rgba(79, 110, 247, 0.6)";
            }
          }}
          onMouseLeave={(e) => {
            if (!isSaving) {
              e.currentTarget.style.transform = "translateY(0)";
              e.currentTarget.style.boxShadow = "0 4px 14px rgba(79, 110, 247, 0.4)";
            }
          }}
        >
          {isSaving ? (
            <span style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <span className="spinner" style={{ width: "16px", height: "16px", border: "2px solid rgba(255,255,255,0.3)", borderTopColor: "white", borderRadius: "50%", animation: "spin 1s linear infinite" }} />
              {t("saving", "Saving...")}
            </span>
          ) : (
            t("save", "Save Intelligence Settings")
          )}
        </button>
      </div>
      <style>{`
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(10px); }
          to { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </section>
  );
}
