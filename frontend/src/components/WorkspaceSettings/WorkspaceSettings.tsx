/**
 * ARCH-L1-001 ReactFrontend — WorkspaceSettings (REQ-L2-RF-012).
 *
 * leaf_id: COMP-RF-001 (NavigationShell scope — Workspace-Konfigurations-UI)
 * req_id:  REQ-L2-RF-012 (Workspace-Konfigurations-UI),
 *          REQ-L2-RF-007 (Preset-Wechsel),
 *          REQ-L2-RF-008 (Terminologie-Profil),
 *          REQ-L1-042 (Workspace Lifecycle Management),
 *          REQ-L1-027 (Per-user visibility overrides — Sichtbarkeit section),
 *          REQ-015   (Redesign: konsistente Sektions-/Tab-Struktur)
 *
 * REQ-015: the settings surface is organised into tabs. All settings groups
 * share a single card/heading style (aligned with ApiKeysSection) instead of
 * the previous per-block inline card styles. The child sections
 * (Llm/PromptTemplate/Workflows/Permissions/BackupRestore) already render their
 * own consistently-styled <section> cards, so they are embedded unchanged.
 *
 * Issue #119 resolved the former overlap between the (unused, `ai_prompts`-blob
 * based) `AiPromptsSection` and `PromptTemplateSection`: there is now a single
 * `AiPromptsSection` backed by the `/prompt-templates/slots/` API, covering
 * every prompt slot at both the global and the per-workspace scope.
 */

import { useState, useCallback } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useWorkspace } from "../../context/WorkspaceContext";
import { useAuth } from "../../context/AuthContext";
import { useTheme } from "../../context/ThemeContext";
import type { WorkspacePreset, TerminologyProfile } from "../../types";
import { workspacesApi } from "../../api/workspaces";
import { i18n } from "../../i18n/index";
import { WorkflowPermissionsSection } from "./WorkflowPermissionsSection";
import { PermissionsSection } from "./PermissionsSection";
import { AttributeVisibilityAdmin } from "../AdminDialog/AttributeVisibilityAdmin";
import { LlmSettingsSection } from "./LlmSettingsSection";
import { AiPromptsSection } from "./AiPromptsSection";
import { PromptVariablesSection } from "./PromptVariablesSection";
import { CustomFieldsSection } from "./CustomFieldsSection";
import { McpConnectionSection } from "./McpConnectionSection";
import { ContextGraphSettingsSection } from "./ContextGraphSettingsSection";
import { WorkspaceBannerSection } from "./WorkspaceBannerSection";
import { ALL_LINK_TYPES, getLinkTypeLabel } from "../../constants/traceLinkLabels";
import { PageHeader } from "../shared/PageHeader";

const PRESET_FEATURES: Record<WorkspacePreset, { baselines: boolean; changeReason: string; workflow: string }> = {
  minimal:  { baselines: false, changeReason: "optional", workflow: "Basic (Draft/Approved)" },
  standard: { baselines: true,  changeReason: "optional", workflow: "Full (Draft/Approved/Deprecated)" },
  extended: { baselines: true,  changeReason: "required", workflow: "Full + Approval workflow" },
};

/**
 * Tab identifiers for the settings surface (REQ-015; REQ-184/185 IA split).
 * The former ``governance`` tab is rebuilt as ``workflows-permissions``; the
 * former ``admin`` tab relocated to System Settings (SCR-204).
 */
type SettingsTabId =
  | "general"
  | "traceability"
  | "visibility"
  | "llm"
  | "workflows-permissions";

const SETTINGS_TAB_IDS: SettingsTabId[] = [
  "general",
  "traceability",
  "visibility",
  "llm",
  "workflows-permissions",
];

function isSettingsTabId(value: string | null): value is SettingsTabId {
  return value !== null && (SETTINGS_TAB_IDS as string[]).includes(value);
}

export default function WorkspaceSettings(): JSX.Element {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const {
    activeWorkspace,
    reloadWorkspaces,
  } = useWorkspace();
  const { roles } = useAuth();

  const [name, setName] = useState(activeWorkspace?.name ?? "");
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savedOk, setSavedOk] = useState(false);
  // #609: allow deep-linking a tab via ?tab=llm (e.g. the /prompts redirect)
  // instead of always landing on "general".
  const [searchParams] = useSearchParams();
  const [activeTab, setActiveTab] = useState<SettingsTabId>(() => {
    const requested = searchParams.get("tab");
    return isSettingsTabId(requested) ? requested : "general";
  });

  const isAdmin = roles.includes("admin");

  const handlePresetChange = useCallback(async (preset: WorkspacePreset): Promise<void> => {
    if (!activeWorkspace || preset === activeWorkspace.preset) return;
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
    if (!activeWorkspace || profile === activeWorkspace.terminology_profile) return;
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
    if (!activeWorkspace || lang === activeWorkspace.language) return;
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

  // Theme Presets: two independent axes (palette x mode), resolved and
  // persisted by ThemeContext — no longer a workspace-owned `theme` field.
  const { paletteKey, mode, palettes, setPreference } = useTheme();

  const handleSaveName = useCallback(async (): Promise<void> => {
    if (!activeWorkspace || !name.trim() || name === activeWorkspace.name) return;
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

  // ---- Shared styles (REQ-015: single card/heading system) ----

  const cardStyle: React.CSSProperties = {
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

  const hintStyle: React.CSSProperties = {
    fontSize: "var(--font-size-sm)",
    color: "var(--color-text-muted)",
    margin: "0 0 var(--space-4) 0",
  };

  const labelStyle: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: "var(--space-3)",
    padding: "var(--space-2) 0",
    cursor: "pointer",
    fontSize: "var(--font-size-base)",
  };

  const fieldLabelStyle: React.CSSProperties = {
    display: "block",
    marginBottom: "var(--space-2)",
    fontWeight: 600,
    fontSize: "var(--font-size-sm)",
    color: "var(--color-text)",
  };

  const selectStyle: React.CSSProperties = {
    width: "100%",
    padding: "var(--space-2) var(--space-3)",
    borderRadius: "var(--radius-md)",
    border: "1px solid var(--color-border)",
    background: "var(--color-surface-raised)",
    color: "var(--color-text)",
    fontSize: "var(--font-size-sm)",
  };

  const primaryButtonStyle: React.CSSProperties = {
    background: "var(--color-primary)",
    color: "white",
    border: "none",
    borderRadius: "var(--radius-md)",
    padding: "var(--space-2) var(--space-4)",
    fontSize: "var(--font-size-sm)",
    fontWeight: 600,
    cursor: "pointer",
  };

  // Early returns AFTER hooks to keep hook order stable across renders.
  if (!activeWorkspace) {
    return <p style={{ padding: "var(--space-6)" }}>{t("errors.generic")}</p>;
  }

  if (!isAdmin) {
    return (
      <div style={{ padding: "var(--space-6)", maxWidth: "640px" }}>
        <PageHeader title={t("nav.settings")} />
        <p style={{ color: "var(--color-warning)" }}>
          {t("settings.adminOnly", "You must be an admin to view or edit Workspace Settings. Please visit the Profile dialog for personal preferences.")}
        </p>
      </div>
    );
  }

  const currentPreset = activeWorkspace.preset as WorkspacePreset;

  const TABS: { id: SettingsTabId; label: string }[] = [
    { id: "general", label: t("settings.tabs.general", "Allgemein") },
    { id: "traceability", label: t("settings.tabs.traceability", "Traceability") },
    { id: "visibility", label: t("settings.tabs.visibility", "Sichtbarkeit") },
    { id: "llm", label: t("settings.tabs.llm", "LLM & Prompts") },
    { id: "workflows-permissions", label: t("settings.tabs.governanceReplacement", "Workflows & Permissions") },
  ];

  return (
    <div data-testid="workspace-settings" style={{ maxWidth: "860px", margin: "0 auto", padding: "var(--space-6)" }}>
      <PageHeader
        title={t("nav.settings")}
        summary={t(
          "settings.pageSummary",
          "Workspace-Konfiguration: Preset, Traceability, Sichtbarkeit, LLM-Einstellungen und Workflows.",
        )}
      />

      {/* Tab navigation (REQ-015) */}
      <div
        role="tablist"
        aria-label={t("nav.settings")}
        data-testid="settings-tablist"
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "var(--space-1)",
          borderBottom: "1px solid var(--color-border)",
          marginBottom: "var(--space-5)",
        }}
      >
        {TABS.map((tab) => {
          const isTabActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              role="tab"
              id={`settings-tab-${tab.id}`}
              data-testid={`settings-tab-${tab.id}`}
              aria-selected={isTabActive}
              aria-controls={`settings-panel-${tab.id}`}
              onClick={() => setActiveTab(tab.id)}
              style={{
                appearance: "none",
                background: "transparent",
                border: "none",
                borderBottom: isTabActive
                  ? "2px solid var(--color-primary)"
                  : "2px solid transparent",
                color: isTabActive ? "var(--color-text)" : "var(--color-text-muted)",
                fontWeight: isTabActive ? 600 : 500,
                fontSize: "var(--font-size-sm)",
                padding: "var(--space-3) var(--space-4)",
                marginBottom: "-1px",
                cursor: "pointer",
                whiteSpace: "nowrap",
              }}
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      <div
        role="tabpanel"
        id={`settings-panel-${activeTab}`}
        data-testid={`settings-panel-${activeTab}`}
        aria-labelledby={`settings-tab-${activeTab}`}
      >
        {/* ---------------- General ---------------- */}
        {activeTab === "general" && (
          <>
            {/* Workspace Name */}
            <section style={cardStyle}>
              <h3 id="workspace-name-heading" style={headingStyle}>{t("settings.workspaceName", "Workspace Name")}</h3>
              <div style={{ display: "flex", gap: "var(--space-2)" }}>
                <input
                  data-testid="workspace-name-input"
                  aria-labelledby="workspace-name-heading"
                  value={name}
                  onChange={(e) => { setName(e.target.value); setSavedOk(false); }}
                  style={{
                    flex: 1,
                    background: "var(--color-surface-raised)",
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
                  disabled={isSaving || !name.trim() || name === activeWorkspace.name}
                  style={{
                    ...primaryButtonStyle,
                    opacity: (isSaving || !name.trim() || name === activeWorkspace.name) ? 0.5 : 1,
                  }}
                >
                  {isSaving ? "…" : t("actions.save")}
                </button>
              </div>
            </section>

            {/* Preset */}
            <section style={cardStyle}>
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
                        background: isActive ? "rgba(var(--color-primary-rgb), 0.08)" : "transparent",
                        borderRadius: "var(--radius-md)",
                        padding: "var(--space-3)",
                        border: isActive ? "1px solid var(--color-primary)" : "1px solid var(--color-border)",
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
                        <div
                          data-testid={`preset-features-${preset}`}
                          style={{ fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)", marginTop: "2px" }}
                        >
                          <div>{features.baselines ? "✓" : "✗"} {t("settings.presets.baselines", "Baselines")}</div>
                          <div>
                            {features.changeReason === "required" ? "✓" : "✗"}{" "}
                            {t("settings.presets.changeReason", "Change Reason")}{" "}
                            ({features.changeReason === "required" ? t("settings.presets.required", "required") : t("settings.presets.optional", "optional")})
                          </div>
                          <div>✓ {t("settings.presets.workflow", "Workflow")}: {features.workflow}</div>
                        </div>
                      </div>
                    </label>
                  );
                })}
              </div>
            </section>

            {/* Terminology Profile */}
            <section style={cardStyle}>
              <h3 style={headingStyle}>{t("settings.terminologyProfile")}</h3>
              {(["dev_mode", "se_mode"] as TerminologyProfile[]).map((profile) => (
                <label
                  key={profile}
                  style={{
                    ...labelStyle,
                    padding: "var(--space-3)",
                    borderRadius: "var(--radius-md)",
                    border: activeWorkspace.terminology_profile === profile
                      ? "1px solid var(--color-primary)"
                      : "1px solid var(--color-border)",
                    marginBottom: "var(--space-2)",
                  }}
                >
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
                      {profile === "dev_mode" ? t("settings.devModeHint", "Feature / Story / Task") : t("settings.seModeHint", "System / Subsystem / Component")}
                    </div>
                  </div>
                </label>
              ))}
            </section>

            {/* Language */}
            <section style={cardStyle}>
              <h3 style={headingStyle}>{t("settings.language")}</h3>
              {["de", "en"].map((lang) => (
                <label key={lang} style={{ ...labelStyle, marginBottom: "var(--space-1)" }}>
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

            {/* Theme (Theme Presets): independent palette + mode pickers */}
            <section style={cardStyle}>
              <h3 style={headingStyle}>{t("settings.theme")}</h3>
              <div data-testid="theme-palette-picker" style={{ display: "flex", flexDirection: "column", gap: "var(--space-1)" }}>
                {palettes.map((p) => (
                  <button
                    key={p.key}
                    type="button"
                    data-testid={`theme-palette-option-${p.key}`}
                    aria-pressed={p.key === paletteKey}
                    onClick={() => setPreference(p.key, mode)}
                    style={labelStyle}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
              <div data-testid="theme-mode-picker" style={{ display: "flex", gap: "var(--space-2)", marginTop: "var(--space-2)" }}>
                <button
                  type="button"
                  data-testid="theme-mode-dark"
                  aria-pressed={mode === "dark"}
                  onClick={() => setPreference(paletteKey, "dark")}
                >
                  {t("nav.darkMode")}
                </button>
                <button
                  type="button"
                  data-testid="theme-mode-light"
                  aria-pressed={mode === "light"}
                  onClick={() => setPreference(paletteKey, "light")}
                >
                  {t("nav.lightMode")}
                </button>
              </div>
            </section>

            {/* Ziele (Goal/MainGoal, REQ-L2-TE-020) — feature + AI-generation toggle */}
            <section style={cardStyle}>
              <h3 style={headingStyle}>{t("settings.goals", "Ziele")}</h3>
              <label style={labelStyle}>
                <input
                  type="checkbox"
                  data-testid="goals-enabled-checkbox"
                  checked={!!activeWorkspace.goals_enabled}
                  onChange={(e) => {
                    const val = e.target.checked;
                    setSaveError(null);
                    setSavedOk(false);
                    workspacesApi.update(activeWorkspace.id, { goals_enabled: val })
                      .then(() => reloadWorkspaces(activeWorkspace.id))
                      .then(() => setSavedOk(true))
                      .catch((err) => setSaveError(err?.error?.message ?? String(err)));
                  }}
                />
                {t("settings.goalsEnabled", "Ziele-Feature aktivieren")}
              </label>
              <label style={labelStyle}>
                <input
                  type="checkbox"
                  data-testid="goals-ai-enabled-checkbox"
                  checked={!!activeWorkspace.goals_ai_enabled}
                  disabled={!activeWorkspace.goals_enabled}
                  onChange={(e) => {
                    const val = e.target.checked;
                    setSaveError(null);
                    setSavedOk(false);
                    workspacesApi.update(activeWorkspace.id, { goals_ai_enabled: val })
                      .then(() => reloadWorkspaces(activeWorkspace.id))
                      .then(() => setSavedOk(true))
                      .catch((err) => setSaveError(err?.error?.message ?? String(err)));
                  }}
                />
                {t("settings.goalsAiEnabled", "KI-Generierung für Haupt-Ziel aktivieren")}
              </label>
            </section>

            {/* Custom Fields (REQ-016) — workspace-wide field definitions, admin-managed */}
            {isAdmin && <CustomFieldsSection workspaceId={activeWorkspace.id} />}

            {/* Data Management — link to the CSV import page (REQ-L0-013) */}
            <section style={cardStyle}>
              <h3 style={headingStyle}>{t("settings.dataManagement", "Datenmanagement")}</h3>
              <button
                type="button"
                data-testid="settings-csv-import-btn"
                onClick={() => navigate("/import")}
                style={{
                  appearance: "none",
                  border: "1px solid var(--color-border)",
                  background: "var(--color-surface)",
                  borderRadius: "var(--radius-md)",
                  padding: "var(--space-2) var(--space-4)",
                  cursor: "pointer",
                }}
              >
                {t("settings.csvImport", "CSV-Import")}
              </button>
            </section>

            {/* MCP connection info — read-only, everything an MCP client needs
                to address this workspace (endpoints, workspace_id, auth). */}
            <McpConnectionSection
              workspaceId={activeWorkspace.id}
              workspaceName={activeWorkspace.name}
            />

            <WorkspaceBannerSection workspaceId={activeWorkspace.id} />
          </>
        )}

        {/* ---------------- Traceability ---------------- */}
        {activeTab === "traceability" && (
          <section style={cardStyle}>
            <h3 style={headingStyle}>{t("settings.traceability", "Traceability")}</h3>
            <p style={hintStyle}>
              {t("settings.traceabilityHint", "Konfiguriere, welcher Trace Link Typ standardmäßig beim Herunterbruch (Ableiten) von Requirements verwendet werden soll.")}
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
              <label style={fieldLabelStyle}>
                {t("settings.decompositionLinkType", "Decomposition Link Typ")}
              </label>
              <select
                value={activeWorkspace.decomposition_link_type || "parent-child"}
                onChange={(e) => {
                  const val = e.target.value;
                  setSaveError(null);
                  setSavedOk(false);
                  workspacesApi.update(activeWorkspace.id, { decomposition_link_type: val })
                    .then(() => reloadWorkspaces(activeWorkspace.id))
                    .then(() => setSavedOk(true))
                    .catch(err => setSaveError(err?.error?.message ?? String(err)));
                }}
                style={selectStyle}
                data-testid="decomposition-link-type-select"
              >
                <option value="parent-child">parent-child (Strukturell)</option>
                <option value="derives-from">derives-from (Ableitung)</option>
              </select>
            </div>

            {/* Standard Trace Link Type — REQ-006 */}
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)", marginTop: "var(--space-4)" }}>
              <label style={fieldLabelStyle}>
                {t("settings.defaultLinkType", "Standard-Linktyp")}
              </label>
              <select
                value={activeWorkspace.default_link_type || "derives-from"}
                onChange={(e) => {
                  const val = e.target.value;
                  setSaveError(null);
                  setSavedOk(false);
                  workspacesApi.update(activeWorkspace.id, { default_link_type: val })
                    .then(() => reloadWorkspaces(activeWorkspace.id))
                    .then(() => setSavedOk(true))
                    .catch(err => setSaveError(err?.error?.message ?? String(err)));
                }}
                style={selectStyle}
                data-testid="default-link-type-select"
              >
                {ALL_LINK_TYPES.map((lt) => (
                  <option key={lt} value={lt}>{getLinkTypeLabel(lt)}</option>
                ))}
              </select>
            </div>
          </section>
        )}
        {activeTab === "traceability" && (
          <ContextGraphSettingsSection workspaceId={activeWorkspace.id} />
        )}

        {/* ---------------- Visibility ---------------- */}
        {activeTab === "visibility" && (
          <section style={cardStyle}>
            <h3 style={headingStyle}>{t("settings.attributeVisibility", "Attribut-Sichtbarkeit")}</h3>
            <p style={hintStyle}>
              {t("settings.attributeVisibilityHint", "Konfiguriere, welche Attribute für die jeweiligen Elementtypen im Workspace sichtbar sind.")}
            </p>
            <AttributeVisibilityAdmin />
          </section>
        )}

        {/* ---------------- LLM & Prompts ---------------- */}
        {activeTab === "llm" && (
          <>
            {/* LLM Provider configuration (REQ-L2-LLM-001) */}
            <LlmSettingsSection />
            {/* AI Prompt Templates (REQ-L2-PT-001, issue #119) — every slot,
                global default + per-workspace override. */}
            <AiPromptsSection workspaceId={activeWorkspace.id} />
            {/* Prompt variable catalog (spec §5): the central place every
                {placeholder} value is managed, across all prompt slots. */}
            <PromptVariablesSection workspaceId={activeWorkspace.id} />
          </>
        )}

        {/* ---------------- Workflows & Permissions (REQ-185, SCR-202) ---------------- */}
        {activeTab === "workflows-permissions" && (
          <>
            {/* On-default/customized status + reset for workflows and the
                permission matrix (REQ-180/183). */}
            <WorkflowPermissionsSection workspaceId={activeWorkspace.id} />
            {/* Item Permissions (REQ-L1-039) — unchanged, relocated verbatim. */}
            <PermissionsSection workspaceId={activeWorkspace.id} />
          </>
        )}
      </div>

      {/* Status (shared across tabs) */}
      {saveError && (
        <div role="alert" style={{ color: "var(--color-danger)", padding: "var(--space-3)", background: "var(--color-surface)", borderRadius: "var(--radius-md)", border: "1px solid var(--color-danger)" }}>
          {saveError}
        </div>
      )}
      {savedOk && (
        <div data-testid="settings-saved-ok" style={{ color: "var(--color-success)", padding: "var(--space-3)" }}>
          {t("settings.saved")}
        </div>
      )}
    </div>
  );
}
