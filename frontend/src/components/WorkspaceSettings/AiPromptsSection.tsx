import React, { useState } from "react";
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

  const handlePromptChange = (level: string, value: string) => {
    setPrompts(prev => ({ ...prev, [level]: value }));
  };

  const handleSave = async () => {
    setIsSaving(true);
    await onSavePrompts(prompts);
    setIsSaving(false);
  };

  return (
    <section className="settings-section">
      <h3>{t("settings.aiPrompts", "AI Derivation Prompts")}</h3>
      <p className="text-muted">
        {t("settings.aiPromptsDesc", "Configure the specific LLM prompts used when deriving requirements automatically across different levels.")}
      </p>

      <div className="form-group" style={{ marginTop: "16px" }}>
        <label>
          <strong>{t("settings.prompt.l0_to_l1", "Level 0 (Needs) ➔ Level 1 (System Requirements)")}</strong>
        </label>
        <textarea 
          className="input" 
          rows={4}
          value={prompts["L0_L1"] || ""}
          onChange={(e) => handlePromptChange("L0_L1", e.target.value)}
          placeholder="e.g., Translate the following stakeholder need into verifiable system requirements..."
          style={{ width: "100%", marginTop: "8px" }}
        />
      </div>

      <div className="form-group" style={{ marginTop: "16px" }}>
        <label>
          <strong>{t("settings.prompt.l1_to_l2", "Level 1 (System Req) ➔ Level 2 (Architecture/Component)")}</strong>
        </label>
        <textarea 
          className="input" 
          rows={4}
          value={prompts["L1_L2"] || ""}
          onChange={(e) => handlePromptChange("L1_L2", e.target.value)}
          placeholder="e.g., Decompose this system requirement into software architecture components..."
          style={{ width: "100%", marginTop: "8px" }}
        />
      </div>

      <button className="btn-primary" onClick={handleSave} disabled={isSaving} style={{ marginTop: "16px" }}>
        {isSaving ? t("saving", "Saving...") : t("save", "Save Prompts")}
      </button>
    </section>
  );
}
