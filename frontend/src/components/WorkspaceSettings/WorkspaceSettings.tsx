/**
 * ARCH-L1-001 ReactFrontend — WorkspaceSettings (REQ-L2-RF-012).
 *
 * leaf_id: COMP-RF-001 (NavigationShell scope — Workspace-Konfigurations-UI)
 * req_id:  REQ-L2-RF-012 (Workspace-Konfigurations-UI),
 *          REQ-L2-RF-007 (Preset-Wechsel),
 *          REQ-L2-RF-008 (Terminologie-Profil)
 */

import React, { useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useWorkspace } from "../../context/WorkspaceContext";
import type { WorkspacePreset, TerminologyProfile } from "../../types";
import { workspacesApi } from "../../api/workspaces";
import { i18n } from "../../i18n/index";

const PRESET_FEATURES: Record<WorkspacePreset, { baselines: boolean; changeReason: string; workflow: string }> = {
  minimal:  { baselines: false, changeReason: "optional", workflow: "Basic (Draft/Approved)" },
  standard: { baselines: true,  changeReason: "optional", workflow: "Full (Draft/Approved/Deprecated)" },
  extended: { baselines: true,  changeReason: "required", workflow: "Full + Approval workflow" },
};

export default function WorkspaceSettings(): JSX.Element {
  const { t } = useTranslation();
  const { activeWorkspace, reloadWorkspaces, isFeatureVisible } = useWorkspace();
  const navigate = useNavigate();

  const [name, setName] = useState(activeWorkspace?.name ?? "");
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savedOk, setSavedOk] = useState(false);

  if (!activeWorkspace) {
    return <p style={{ padding: "var(--space-6)" }}>{t("errors.generic")}</p>;
  }

  const handlePresetChange = useCallback(async (preset: WorkspacePreset): Promise<void> => {
    if (preset === activeWorkspace.preset) return;
    setSaveError(null);
    setSavedOk(false);
    try {
      await workspacesApi.setPreset(activeWorkspace.id, preset);
      await reloadWorkspaces(activeWorkspace.id);
      setSavedOk(true);
    } catch (err: unknown) {
      setSaveError((err as { error?: { message?: string } })?.error?.message ?? String(err));
    }
  }, [activeWorkspace, reloadWorkspaces]);

  const handleProfileChange = useCallback(async (profile: TerminologyProfile): Promise<void> => {
    if (profile === activeWorkspace.terminology_profile) return;
    setSaveError(null);
    setSavedOk(false);
    try {
      await workspacesApi.update(activeWorkspace.id, { terminology_profile: profile });
      await reloadWorkspaces(activeWorkspace.id);
      setSavedOk(true);
    } catch (err: unknown) {
      setSaveError((err as { error?: { message?: string } })?.error?.message ?? String(err));
    }
  }, [activeWorkspace, reloadWorkspaces]);

  const handleLanguageChange = useCallback(async (lang: string): Promise<void> => {
    void i18n.changeLanguage(lang);
    document.documentElement.lang = lang;
    if (lang === activeWorkspace.language) return;
    setSaveError(null);
    setSavedOk(false);
    try {
      await workspacesApi.update(activeWorkspace.id, { language: lang });
      await reloadWorkspaces(activeWorkspace.id);
      setSavedOk(true);
    } catch (err: unknown) {
      setSaveError((err as { error?: { message?: string } })?.error?.message ?? String(err));
    }
  }, [activeWorkspace, reloadWorkspaces]);

  const handleSaveName = useCallback(async (): Promise<void> => {
    if (!name.trim() || name === activeWorkspace.name) return;
    setSaveError(null);
    setSavedOk(false);
    setIsSaving(true);
    try {
      await workspacesApi.update(activeWorkspace.id, { name: name.trim() });
      await reloadWorkspaces(activeWorkspace.id);
      setSavedOk(true);
    } catch (err: unknown) {
      setSaveError((err as { error?: { message?: string } })?.error?.message ?? String(err));
    } finally {
      setIsSaving(false);
    }
  }, [activeWorkspace, name, reloadWorkspaces]);

  const sectionStyle: React.CSSProperties = {
    background: "var(--color-surface)",
    border: "1px solid var(--color-border)",
    borderRadius: "var(--radius-lg)",
    padding: "var(--space-5)",
    marginBottom: "var(--space-5)",
    boxShadow: "var(--shadow-card)",
  };

  const labelStyle: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: "var(--space-3)",
    padding: "var(--space-2) 0",
    cursor: "pointer",
    fontSize: "var(--font-size-base)",
  };

  const headingStyle: React.CSSProperties = {
    fontSize: "var(--font-size-lg)",
    fontWeight: 600,
    color: "var(--color-text)",
    margin: "0 0 var(--space-4) 0",
  };

  const currentPreset = activeWorkspace.preset as WorkspacePreset;

  return (
    <div data-testid="workspace-settings" style={{ maxWidth: "640px" }}>
      <h2 style={{ fontSize: "var(--font-size-2xl)", fontWeight: 700, color: "var(--color-text)", marginBottom: "var(--space-6)" }}>
        {t("nav.settings")}
      </h2>

      {/* Workspace Name */}
      <section style={sectionStyle}>
        <h3 style={headingStyle}>Workspace Name</h3>
        <div style={{ display: "flex", gap: "var(--space-3)" }}>
          <input
            data-testid="workspace-name-input"
            value={name}
            onChange={(e) => { setName(e.target.value); setSavedOk(false); }}
            style={{
              flex: 1,
              background: "var(--color-bg)",
              border: "1px solid var(--color-border)",
              borderRadius: "var(--radius-md)",
              padding: "var(--space-2) var(--space-3)",
              color: "var(--color-text)",
              fontSize: "var(--font-size-base)",
            }}
          />
          <button
            data-testid="workspace-name-save"
            onClick={() => void handleSaveName()}
            disabled={isSaving || name === activeWorkspace.name}
            style={{
              background: "var(--color-primary)",
              color: "white",
              border: "none",
              borderRadius: "var(--radius-md)",
              padding: "var(--space-2) var(--space-4)",
              cursor: "pointer",
              opacity: (isSaving || name === activeWorkspace.name) ? 0.5 : 1,
            }}
          >
            {isSaving ? "…" : t("actions.save")}
          </button>
        </div>
      </section>

      {/* Preset */}
      <section style={sectionStyle}>
        <h3 style={headingStyle}>{t("settings.preset")}</h3>
        <div data-testid="preset-selector">
          {(["minimal", "standard", "extended"] as WorkspacePreset[]).map((preset) => {
            const features = PRESET_FEATURES[preset];
            const isActive = currentPreset === preset;
            return (
              <label
                key={preset}
                style={{
                  ...labelStyle,
                  background: isActive ? "rgba(var(--color-primary-rgb, 79,70,229), 0.08)" : "transparent",
                  borderRadius: "var(--radius-md)",
                  padding: "var(--space-3)",
                  border: isActive ? "1px solid var(--color-primary)" : "1px solid transparent",
                  marginBottom: "var(--space-2)",
                }}
              >
                <input
                  type="radio"
                  name="preset"
                  value={preset}
                  checked={isActive}
                  onChange={() => void handlePresetChange(preset)}
                  data-testid={`preset-option-${preset}`}
                />
                <div>
                  <div style={{ fontWeight: 600, textTransform: "capitalize" }}>{preset}</div>
                  <div style={{ fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)", marginTop: "2px" }}>
                    Baselines: {features.baselines ? "✓" : "✗"} &nbsp;|&nbsp;
                    change_reason: {features.changeReason} &nbsp;|&nbsp;
                    {features.workflow}
                  </div>
                </div>
              </label>
            );
          })}
        </div>
      </section>

      {/* Terminology Profile */}
      <section style={sectionStyle}>
        <h3 style={headingStyle}>{t("settings.terminologyProfile")}</h3>
        {(["dev_mode", "se_mode"] as TerminologyProfile[]).map((profile) => (
          <label key={profile} style={{ ...labelStyle, marginBottom: "var(--space-2)" }}>
            <input
              type="radio"
              name="profile"
              value={profile}
              checked={activeWorkspace.terminology_profile === profile}
              onChange={() => void handleProfileChange(profile)}
              data-testid={`profile-option-${profile}`}
            />
            <div>
              <div style={{ fontWeight: 600 }}>
                {profile === "dev_mode" ? t("settings.devMode") : t("settings.seMode")}
              </div>
              <div style={{ fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)" }}>
                {profile === "dev_mode" ? "Feature / Story / Task" : "System / Subsystem / Component"}
              </div>
            </div>
          </label>
        ))}
      </section>

      {/* Language */}
      <section style={sectionStyle}>
        <h3 style={headingStyle}>{t("settings.language")}</h3>
        {["de", "en"].map((lang) => (
          <label key={lang} style={{ ...labelStyle, marginBottom: "var(--space-2)" }}>
            <input
              type="radio"
              name="language"
              value={lang}
              checked={(activeWorkspace.language ?? "en") === lang}
              onChange={() => void handleLanguageChange(lang)}
              data-testid={`language-option-${lang}`}
            />
            {lang === "de" ? "Deutsch" : "English"}
          </label>
        ))}
      </section>

      {/* Data Management (REQ-L0-013, REQ-L2-RF-016) */}
      {isFeatureVisible("csv_import") && (
        <section style={sectionStyle}>
          <h3 style={headingStyle}>{t("settings.dataManagement", "Data Management")}</h3>
          <p style={{ fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)", marginBottom: "var(--space-3)" }}>
            {t("settings.dataManagementHint", "Import existing requirements from a CSV file.")}
          </p>
          <button
            type="button"
            data-testid="settings-csv-import-btn"
            onClick={() => navigate("/import")}
            style={{
              background: "var(--color-primary)",
              color: "white",
              border: "none",
              borderRadius: "var(--radius-md)",
              padding: "var(--space-2) var(--space-4)",
              fontSize: "var(--font-size-sm)",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            {t("import.title", "CSV Import")}
          </button>
        </section>
      )}

      {/* Status */}
      {saveError && (
        <div role="alert" style={{ color: "var(--color-danger)", padding: "var(--space-3)", background: "var(--color-surface)", borderRadius: "var(--radius-md)", border: "1px solid var(--color-danger)" }}>
          {saveError}
        </div>
      )}
      {savedOk && (
        <div data-testid="settings-saved-ok" style={{ color: "var(--color-success, #16a34a)", padding: "var(--space-3)" }}>
          {t("settings.saved")}
        </div>
      )}
    </div>
  );
}
