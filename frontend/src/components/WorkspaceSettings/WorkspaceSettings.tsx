/**
 * ARCH-L1-001 ReactFrontend — WorkspaceSettings (REQ-L2-RF-012).
 *
 * leaf_id: COMP-RF-001 (NavigationShell scope — Workspace-Konfigurations-UI)
 * req_id:  REQ-L2-RF-012 (Workspace-Konfigurations-UI),
 *          REQ-L2-RF-007 (Preset-Wechsel),
 *          REQ-L2-RF-008 (Terminologie-Profil)
 *
 * Allows admin user to change preset, terminology profile, and language.
 * Changes apply immediately without page reload (REQ-L2-RF-012 AC).
 * NOTE: PATCH /api/v1/workspaces/{id}/settings/ not yet in backend — see Escalation.
 */

import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import { useWorkspace } from "../../context/WorkspaceContext";
import type { WorkspacePreset, TerminologyProfile } from "../../types";
import { i18n } from "../../i18n/index";

export default function WorkspaceSettings(): JSX.Element {
  const { t } = useTranslation();
  const { activeWorkspace, setActiveWorkspace } = useWorkspace();
  const [saved, setSaved] = useState(false);

  if (!activeWorkspace) {
    return <p>{t("errors.generic")}</p>;
  }

  const handlePresetChange = (preset: WorkspacePreset): void => {
    setActiveWorkspace({ ...activeWorkspace, preset });
    setSaved(false);
  };

  const handleProfileChange = (profile: TerminologyProfile): void => {
    setActiveWorkspace({
      ...activeWorkspace,
      terminology_profile: profile,
    });
    setSaved(false);
  };

  const handleLanguageChange = (lang: string): void => {
    void i18n.changeLanguage(lang);
    document.documentElement.lang = lang;
    setActiveWorkspace({ ...activeWorkspace, language: lang });
    setSaved(false);
  };

  const handleSave = (): void => {
    // TODO: PATCH /api/v1/workspaces/{id}/settings/ when backend endpoint is available
    // See ESCALATION: /api/v1/workspaces/ not implemented in backend yet.
    setSaved(true);
  };

  return (
    <div style={{ maxWidth: "600px", fontFamily: "sans-serif" }}>
      <h2>{t("nav.settings")}</h2>

      <section style={{ marginBottom: "1.5rem" }}>
        <h3>{t("settings.preset")}</h3>
        {(["minimal", "standard", "extended"] as WorkspacePreset[]).map(
          (preset) => (
            <label
              key={preset}
              style={{ display: "block", marginBottom: "0.5rem" }}
            >
              <input
                type="radio"
                name="preset"
                value={preset}
                checked={activeWorkspace.preset === preset}
                onChange={() => handlePresetChange(preset)}
                style={{ marginRight: "0.5rem" }}
              />
              {preset.charAt(0).toUpperCase() + preset.slice(1)}
            </label>
          )
        )}
      </section>

      <section style={{ marginBottom: "1.5rem" }}>
        <h3>{t("settings.terminologyProfile")}</h3>
        {(["dev_mode", "se_mode"] as TerminologyProfile[]).map((profile) => (
          <label
            key={profile}
            style={{ display: "block", marginBottom: "0.5rem" }}
          >
            <input
              type="radio"
              name="profile"
              value={profile}
              checked={activeWorkspace.terminology_profile === profile}
              onChange={() => handleProfileChange(profile)}
              style={{ marginRight: "0.5rem" }}
            />
            {profile === "dev_mode" ? t("settings.devMode") : t("settings.seMode")}
          </label>
        ))}
      </section>

      <section style={{ marginBottom: "1.5rem" }}>
        <h3>{t("settings.language")}</h3>
        {["de", "en"].map((lang) => (
          <label
            key={lang}
            style={{ display: "block", marginBottom: "0.5rem" }}
          >
            <input
              type="radio"
              name="language"
              value={lang}
              checked={(activeWorkspace.language ?? "en") === lang}
              onChange={() => handleLanguageChange(lang)}
              style={{ marginRight: "0.5rem" }}
            />
            {lang === "de" ? "Deutsch" : "English"}
          </label>
        ))}
      </section>

      <button onClick={handleSave} style={{ padding: "0.5rem 1.5rem" }}>
        {t("actions.save")}
      </button>
      {saved && (
        <span style={{ marginLeft: "1rem", color: "green" }}>
          {t("settings.saved")}
        </span>
      )}
    </div>
  );
}
