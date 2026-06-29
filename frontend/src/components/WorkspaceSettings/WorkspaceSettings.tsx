/**
 * ARCH-L1-001 ReactFrontend — WorkspaceSettings (REQ-L2-RF-012).
 *
 * leaf_id: COMP-RF-001 (NavigationShell scope — Workspace-Konfigurations-UI)
 * req_id:  REQ-L2-RF-012 (Workspace-Konfigurations-UI),
 *          REQ-L2-RF-007 (Preset-Wechsel),
 *          REQ-L2-RF-008 (Terminologie-Profil),
 *          REQ-L1-042 (Workspace Lifecycle Management),
 *          REQ-L1-027 (Per-user visibility overrides — Sichtbarkeit section)
 */

import React, { useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useWorkspace } from "../../context/WorkspaceContext";
import { useAuth } from "../../context/AuthContext";
import type { WorkspacePreset, TerminologyProfile } from "../../types";
import { workspacesApi } from "../../api/workspaces";
import { i18n } from "../../i18n/index";
import { OPTIONAL_FEATURES, type OptionalArtifactFeature } from "../../api/preferences";

const PRESET_FEATURES: Record<WorkspacePreset, { baselines: boolean; changeReason: string; workflow: string }> = {
  minimal:  { baselines: false, changeReason: "optional", workflow: "Basic (Draft/Approved)" },
  standard: { baselines: true,  changeReason: "optional", workflow: "Full (Draft/Approved/Deprecated)" },
  extended: { baselines: true,  changeReason: "required", workflow: "Full + Approval workflow" },
};

const VISIBILITY_LABELS: Record<OptionalArtifactFeature, string> = {
  adr: "ADR (Architecture Decision Records)",
  risk: "Risks",
  issue: "Issues",
  diagrams: "Diagrams",
  icds: "ICDs (Interface Control Documents)",
  metrics: "Metrics",
};

export default function WorkspaceSettings(): JSX.Element {
  const { t } = useTranslation();
  const {
    activeWorkspace,
    reloadWorkspaces,
    isFeatureVisible,
    setFeatureVisible,
    resetFeatureOverride,
    isFeatureOverridden,
  } = useWorkspace();
  const { roles } = useAuth();
  const navigate = useNavigate();

  const [name, setName] = useState(activeWorkspace?.name ?? "");
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savedOk, setSavedOk] = useState(false);

  // Per-feature saving state for the Sichtbarkeit section (REQ-L1-027).
  const [pendingFeature, setPendingFeature] = useState<OptionalArtifactFeature | null>(null);

  // Lifecycle state (REQ-L1-042)
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleteConfirmation, setDeleteConfirmation] = useState("");
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isClosing, setIsClosing] = useState(false);

  const isAdmin = roles.includes("admin");

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

  // ---- Lifecycle handlers (REQ-L1-042) ----

  const handleCloseWorkspace = useCallback(async (): Promise<void> => {
    if (!window.confirm(t("settings.closeConfirm"))) return;
    setSaveError(null);
    setIsClosing(true);
    try {
      await workspacesApi.closeWorkspace(activeWorkspace.id);
      await reloadWorkspaces(activeWorkspace.id);
      setSavedOk(true);
    } catch (err: unknown) {
      setSaveError((err as { error?: { message?: string } })?.error?.message ?? String(err));
    } finally {
      setIsClosing(false);
    }
  }, [activeWorkspace, reloadWorkspaces, t]);

  const handleReactivateWorkspace = useCallback(async (): Promise<void> => {
    setSaveError(null);
    try {
      await workspacesApi.reactivateWorkspace(activeWorkspace.id);
      await reloadWorkspaces(activeWorkspace.id);
      setSavedOk(true);
    } catch (err: unknown) {
      setSaveError((err as { error?: { message?: string } })?.error?.message ?? String(err));
    }
  }, [activeWorkspace, reloadWorkspaces]);

  const handleDeleteWorkspace = useCallback(async (): Promise<void> => {
    if (deleteConfirmation !== activeWorkspace.name) {
      setDeleteError(t("settings.deleteConfirmationMismatch"));
      return;
    }
    setDeleteError(null);
    setIsDeleting(true);
    try {
      await workspacesApi.deleteWorkspace(activeWorkspace.id, deleteConfirmation);
      setShowDeleteModal(false);
      setDeleteConfirmation("");
      // Navigate to dashboard since workspace no longer exists
      navigate("/");
    } catch (err: unknown) {
      setDeleteError((err as { error?: { message?: string } })?.error?.message ?? String(err));
    } finally {
      setIsDeleting(false);
    }
  }, [activeWorkspace, deleteConfirmation, navigate, t]);

  // ---- Per-feature visibility handlers (REQ-L1-027) ----

  const handleFeatureToggle = useCallback(
    async (feature: OptionalArtifactFeature, value: boolean): Promise<void> => {
      setSaveError(null);
      setSavedOk(false);
      setPendingFeature(feature);
      try {
        await setFeatureVisible(feature, value);
        setSavedOk(true);
      } catch (err: unknown) {
        setSaveError((err as { error?: { message?: string } })?.error?.message ?? String(err));
      } finally {
        setPendingFeature(null);
      }
    },
    [setFeatureVisible]
  );

  const handleResetFeature = useCallback(
    async (feature: OptionalArtifactFeature): Promise<void> => {
      setSaveError(null);
      setSavedOk(false);
      setPendingFeature(feature);
      try {
        await resetFeatureOverride(feature);
        setSavedOk(true);
      } catch (err: unknown) {
        setSaveError((err as { error?: { message?: string } })?.error?.message ?? String(err));
      } finally {
        setPendingFeature(null);
      }
    },
    [resetFeatureOverride]
  );

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

      {/* Sichtbarkeit — per-user visibility overrides (REQ-L1-027) */}
      <section style={sectionStyle} data-testid="visibility-section">
        <h3 style={headingStyle}>{t("settings.visibility", "Sichtbarkeit")}</h3>
        <p
          style={{
            fontSize: "var(--font-size-sm)",
            color: "var(--color-text-muted)",
            marginBottom: "var(--space-3)",
          }}
        >
          {t(
            "settings.visibilityHint",
            "Blendet einzelne optionale Artefakttypen in der Navigation und den Editoren ein oder aus. Overrides wirken nur für dich in diesem Workspace und überschreiben die Preset-Vorgabe."
          )}
        </p>
        {OPTIONAL_FEATURES.map((feature) => {
          const effective = isFeatureVisible(feature);
          const overridden = isFeatureOverridden(feature);
          const isPending = pendingFeature === feature;
          return (
            <div
              key={feature}
              style={{
                ...labelStyle,
                justifyContent: "space-between",
                padding: "var(--space-2) 0",
                borderTop: "1px solid var(--color-border)",
              }}
              data-testid={`visibility-row-${feature}`}
            >
              <label
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "var(--space-3)",
                  cursor: isPending ? "wait" : "pointer",
                  flex: 1,
                }}
              >
                <input
                  type="checkbox"
                  checked={effective}
                  disabled={isPending}
                  onChange={(e) => void handleFeatureToggle(feature, e.target.checked)}
                  data-testid={`visibility-checkbox-${feature}`}
                />
                <span>
                  <span style={{ fontWeight: 500 }}>{VISIBILITY_LABELS[feature]}</span>
                  <span
                    style={{
                      fontSize: "var(--font-size-sm)",
                      color: "var(--color-text-muted)",
                      marginLeft: "var(--space-2)",
                    }}
                  >
                    {overridden
                      ? t("settings.visibilityOverridden", "(überschrieben)")
                      : t("settings.visibilityFromPreset", "(aus Preset)")}
                  </span>
                </span>
              </label>
              {overridden && (
                <button
                  type="button"
                  data-testid={`visibility-reset-${feature}`}
                  onClick={() => void handleResetFeature(feature)}
                  disabled={isPending}
                  style={{
                    background: "transparent",
                    color: "var(--color-text-muted)",
                    border: "1px solid var(--color-border)",
                    borderRadius: "var(--radius-sm)",
                    padding: "var(--space-1) var(--space-3)",
                    fontSize: "var(--font-size-sm)",
                    cursor: isPending ? "not-allowed" : "pointer",
                  }}
                >
                  {t("settings.visibilityReset", "Auf Preset zurücksetzen")}
                </button>
              )}
            </div>
          );
        })}
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

      {/* Workspace Administration (REQ-L1-042) — admin only */}
      {isAdmin && (
        <section style={sectionStyle} data-testid="lifecycle-section">
          <h3 style={headingStyle}>{t("settings.lifecycleSection", "Workspace Administration")}</h3>

          {/* Close button — visible when workspace is active */}
          {activeWorkspace.is_active !== false && (
            <button
              type="button"
              data-testid="close-workspace-btn"
              onClick={() => void handleCloseWorkspace()}
              disabled={isClosing}
              style={{
                background: "var(--color-warning, #f59e0b)",
                color: "white",
                border: "none",
                borderRadius: "var(--radius-md)",
                padding: "var(--space-2) var(--space-4)",
                fontSize: "var(--font-size-sm)",
                fontWeight: 600,
                cursor: "pointer",
                marginRight: "var(--space-2)",
                opacity: isClosing ? 0.5 : 1,
              }}
            >
              {isClosing ? "…" : t("settings.closeWorkspace", "Close Workspace")}
            </button>
          )}

          {/* Reactivate button — visible when workspace is closed */}
          {activeWorkspace.is_active === false && (
            <button
              type="button"
              data-testid="reactivate-workspace-btn"
              onClick={() => void handleReactivateWorkspace()}
              style={{
                background: "var(--color-success, #16a34a)",
                color: "white",
                border: "none",
                borderRadius: "var(--radius-md)",
                padding: "var(--space-2) var(--space-4)",
                fontSize: "var(--font-size-sm)",
                fontWeight: 600,
                cursor: "pointer",
                marginRight: "var(--space-2)",
              }}
            >
              {t("settings.reactivateWorkspace", "Reactivate Workspace")}
            </button>
          )}

          {/* Delete button — always visible for admin */}
          <button
            type="button"
            data-testid="delete-workspace-btn"
            onClick={() => { setShowDeleteModal(true); setDeleteError(null); setDeleteConfirmation(""); }}
            style={{
              background: "var(--color-danger, #dc2626)",
              color: "white",
              border: "none",
              borderRadius: "var(--radius-md)",
              padding: "var(--space-2) var(--space-4)",
              fontSize: "var(--font-size-sm)",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            {t("settings.deleteWorkspace", "Delete Workspace")}
          </button>

          {/* Delete confirmation modal */}
          {showDeleteModal && (
            <div
              data-testid="delete-modal"
              role="dialog"
              style={{
                marginTop: "var(--space-4)",
                padding: "var(--space-4)",
                background: "var(--color-bg, #f9fafb)",
                border: "1px solid var(--color-danger, #dc2626)",
                borderRadius: "var(--radius-md)",
              }}
            >
              <p style={{ fontWeight: 600, marginBottom: "var(--space-2)" }}>
                {t("settings.deleteConfirmTitle", "Delete Workspace")}
              </p>
              <p style={{ fontSize: "var(--font-size-sm)", marginBottom: "var(--space-3)" }}>
                {t("settings.deleteCaptchaPrompt", { name: activeWorkspace.name })}
              </p>
              <input
                data-testid="delete-confirmation-input"
                type="text"
                value={deleteConfirmation}
                onChange={(e) => { setDeleteConfirmation(e.target.value); setDeleteError(null); }}
                placeholder={activeWorkspace.name}
                style={{
                  width: "100%",
                  background: "var(--color-surface)",
                  border: "1px solid var(--color-border)",
                  borderRadius: "var(--radius-md)",
                  padding: "var(--space-2) var(--space-3)",
                  color: "var(--color-text)",
                  fontSize: "var(--font-size-base)",
                  marginBottom: "var(--space-2)",
                }}
              />
              {deleteError && (
                <div role="alert" data-testid="delete-error" style={{ color: "var(--color-danger, #dc2626)", fontSize: "var(--font-size-sm)", marginBottom: "var(--space-2)" }}>
                  {deleteError}
                </div>
              )}
              <div style={{ display: "flex", gap: "var(--space-2)" }}>
                <button
                  type="button"
                  data-testid="delete-confirm-btn"
                  onClick={() => void handleDeleteWorkspace()}
                  disabled={isDeleting || deleteConfirmation !== activeWorkspace.name}
                  style={{
                    background: "var(--color-danger, #dc2626)",
                    color: "white",
                    border: "none",
                    borderRadius: "var(--radius-md)",
                    padding: "var(--space-2) var(--space-4)",
                    fontSize: "var(--font-size-sm)",
                    fontWeight: 600,
                    cursor: "pointer",
                    opacity: (isDeleting || deleteConfirmation !== activeWorkspace.name) ? 0.5 : 1,
                  }}
                >
                  {isDeleting ? "…" : t("settings.deleteConfirmButton", "Permanently Delete")}
                </button>
                <button
                  type="button"
                  data-testid="delete-cancel-btn"
                  onClick={() => { setShowDeleteModal(false); setDeleteConfirmation(""); setDeleteError(null); }}
                  style={{
                    background: "transparent",
                    color: "var(--color-text-muted)",
                    border: "1px solid var(--color-border)",
                    borderRadius: "var(--radius-md)",
                    padding: "var(--space-2) var(--space-4)",
                    fontSize: "var(--font-size-sm)",
                    cursor: "pointer",
                  }}
                >
                  {t("actions.cancel", "Cancel")}
                </button>
              </div>
            </div>
          )}
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
