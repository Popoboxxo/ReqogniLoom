/**
 * REQ-184 — SystemSettings shell (SCR-203/204/205/206).
 *
 * leaf_id: COMP-RF-001 (NavigationShell scope)
 *
 * Tenant/system-wide configuration, split out of the workspace-bound
 * ``WorkspaceSettings`` (IA split, not a redesign — the tab shell is a
 * structural clone of that surface, reusing the same underline-active tab
 * pattern and card styling). Tabs:
 *   - administration    → relocated System Health / Backup / Lifecycle (SCR-204)
 *   - workflow-defaults  → global per-preset Workflow Editor (SCR-205)
 *   - attribute-defaults → global attribute visibility/required/layout defaults
 *   - permission-defaults → global matrix + enforcement + mismatches (SCR-206)
 *   - display            → tree/create-form/preference tenant defaults
 *   - memory             → memory backend, workspace overview, visualization
 *   - vector-store       → artifact vector backend + Qdrant settings (ADR-020)
 *
 * Admin-gated with the same page-level early-return pattern as WorkspaceSettings
 * (the nav link is visible to all authenticated users; the page gates on the
 * admin role). Active tab is a ``?tab=`` query param (no deeper routing).
 */

import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../context/AuthContext";
import { WorkflowEditorPage } from "../WorkflowEditor/WorkflowEditorPage";
import { AttributeEditorPage } from "../AttributeEditor";
import { WorkspaceAdminSection } from "./WorkspaceAdminSection";
import { BannerSection } from "./BannerSection";
import { ThemeManagementSection } from "./ThemeManagementSection";
import { PermissionDefaultsTab } from "./PermissionDefaultsTab";
import { MemoryManagementSection } from "./MemoryManagementSection";
import { MemorySystemSettingsSection } from "./MemorySystemSettingsSection";
import { ArtifactVectorSettingsSection } from "./ArtifactVectorSettingsSection";
import { MemoryVisualizationSection } from "./MemoryVisualizationSection";
import { TreeDisplaySection } from "./TreeDisplaySection";
import { CreateFormSection } from "./CreateFormSection";
import { PreferenceLevelSection } from "../shared/PreferenceLevelSection/PreferenceLevelSection";
import { PageHeader } from "../shared/PageHeader";
import { ConfirmDialog } from "../shared/ConfirmDialog";
import { handleTablistKeyDown, tabRovingTabIndex } from "../shared/tablistKeyboardNav";
import styles from "./SystemSettings.module.css";

type SystemTabId =
  | "administration"
  | "workflow-defaults"
  | "attribute-defaults"
  | "permission-defaults"
  | "display"
  | "memory"
  | "vector-store";

const TAB_IDS: SystemTabId[] = [
  "administration",
  "workflow-defaults",
  "attribute-defaults",
  "permission-defaults",
  "display",
  "memory",
  "vector-store",
];

function isSystemTab(value: string | null): value is SystemTabId {
  return value != null && (TAB_IDS as string[]).includes(value);
}

export default function SystemSettings(): JSX.Element {
  const { t } = useTranslation();
  const { roles } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();

  const isAdmin = roles.includes("admin");
  const [isDirty, setIsDirty] = useState(false);
  const [pendingTab, setPendingTab] = useState<SystemTabId | null>(null);
  const tabParam = searchParams.get("tab");
  const activeTab: SystemTabId = isSystemTab(tabParam) ? tabParam : "administration";

  if (!isAdmin) {
    return (
      <div className={styles.adminOnly}>
        <PageHeader title={t("nav.systemSettings", "System Settings")} />
        <p className={styles.adminOnlyText}>
          {t("systemSettings.adminOnly")}
        </p>
      </div>
    );
  }

  const setTab = (tab: SystemTabId): void => {
    const next = new URLSearchParams(searchParams);
    next.set("tab", tab);
    setSearchParams(next, { replace: true });
    setIsDirty(false);
  };

  /**
   * A tab switch unmounts the active section, discarding staged edits. Ask
   * before doing that instead of losing a half-edited settings form silently.
   */
  const requestTab = (tab: SystemTabId): void => {
    if (tab === activeTab) return;
    if (isDirty) {
      setPendingTab(tab);
      return;
    }
    setTab(tab);
  };

  const TABS: { id: SystemTabId; label: string }[] = [
    { id: "administration", label: t("systemSettings.tabs.administration", "Administration") },
    { id: "workflow-defaults", label: t("systemSettings.tabs.workflowDefaults", "Workflow Defaults") },
    { id: "attribute-defaults", label: t("systemSettings.tabs.attributeDefaults", "Attribute Defaults") },
    { id: "permission-defaults", label: t("systemSettings.tabs.permissionDefaults", "Permission Defaults") },
    { id: "display", label: t("systemSettings.tabs.display") },
    { id: "memory", label: t("systemSettings.tabs.memory", "Memory") },
    { id: "vector-store", label: t("systemSettings.tabs.vectorStore") },
  ];

  const isEditorTab = activeTab === "workflow-defaults";

  return (
    <div
      data-testid="system-settings"
      className={
        styles.root +
        " " +
        (isEditorTab ? styles.rootEditor : styles.rootCentered)
      }
    >
      <PageHeader
        title={t("nav.systemSettings", "System Settings")}
        summary={t(
          "systemSettings.pageSummary",
          "Tenant-weite Konfiguration: Administration, Workflow-Vorgaben und Berechtigungs-Standards.",
        )}
      />

      <div
        role="tablist"
        aria-label={t("nav.systemSettings", "System Settings")}
        data-testid="system-settings-tablist"
        onKeyDown={(e) => handleTablistKeyDown(e, TAB_IDS, activeTab, requestTab)}
        className={styles.tablist}
      >
        {TABS.map((tab) => {
          const isTabActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              role="tab"
              id={`system-settings-tab-${tab.id}`}
              data-testid={`system-settings-tab-${tab.id}`}
              aria-selected={isTabActive}
              // Only the active tab has a rendered panel; pointing the other
              // five at an ID that does not exist is an axe aria-valid-attr-value
              // violation and makes the tab/panel relation unresolvable.
              aria-controls={
                isTabActive ? `system-settings-panel-${tab.id}` : undefined
              }
              tabIndex={tabRovingTabIndex(tab.id, activeTab)}
              onClick={() => requestTab(tab.id)}
              className="btn-tab"
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      <div
        role="tabpanel"
        id={`system-settings-panel-${activeTab}`}
        data-testid={`system-settings-panel-${activeTab}`}
        aria-labelledby={`system-settings-tab-${activeTab}`}
      >
        {activeTab === "administration" && (
          <>
            <WorkspaceAdminSection />
            <BannerSection />
            <ThemeManagementSection />
          </>
        )}
        {activeTab === "workflow-defaults" && (
          <div data-testid="system-workflow-defaults" className={styles.editorHost}>
            <WorkflowEditorPage scope="global" />
          </div>
        )}
        {activeTab === "attribute-defaults" && (
          <div data-testid="system-attribute-defaults">
            <AttributeEditorPage scope="global" />
          </div>
        )}
        {activeTab === "permission-defaults" && <PermissionDefaultsTab />}
        {activeTab === "display" && (
          <div data-testid="system-tree-display">
            {/* Issue #1257: the tenant-wide default for the navigation tree's
                fields; every workspace inherits it unless it overrides it. */}
            <TreeDisplaySection />
            {/* Issue #1263: the tenant-wide default for the "new artifact"
                dialog's fields (visible / order / required / default). */}
            <CreateFormSection />
            {/* Plan C / T-C2-5: the tenant-wide default for the generic Q1
                preference values; every workspace inherits it unless it
                overrides it. */}
            <PreferenceLevelSection scope="global" />
          </div>
        )}
        {activeTab === "memory" && (
          <>
            <MemorySystemSettingsSection onDirtyChange={setIsDirty} />
            <MemoryManagementSection />
            <MemoryVisualizationSection />
          </>
        )}
        {activeTab === "vector-store" && (
          <div data-testid="system-vector-store">
            <ArtifactVectorSettingsSection onDirtyChange={setIsDirty} />
          </div>
        )}
      </div>

      {pendingTab && (
        <ConfirmDialog
          title={t("systemSettings.unsaved.title")}
          message={t("systemSettings.unsaved.message")}
          confirmLabel={t("systemSettings.unsaved.confirm")}
          onConfirm={() => {
            const target = pendingTab;
            setPendingTab(null);
            setTab(target);
          }}
          onCancel={() => setPendingTab(null)}
          testId="system-settings-unsaved-confirm"
        />
      )}
    </div>
  );
}
