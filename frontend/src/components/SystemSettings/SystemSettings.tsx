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
 *   - permission-defaults → global matrix + enforcement + mismatches (SCR-206)
 *
 * Admin-gated with the same page-level early-return pattern as WorkspaceSettings
 * (the nav link is visible to all authenticated users; the page gates on the
 * admin role). Active tab is a ``?tab=`` query param (no deeper routing).
 */

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
import { MemoryVisualizationSection } from "./MemoryVisualizationSection";
import { PageHeader } from "../shared/PageHeader";
import { handleTablistKeyDown, tabRovingTabIndex } from "../shared/tablistKeyboardNav";
import styles from "./SystemSettings.module.css";

type SystemTabId =
  | "administration"
  | "workflow-defaults"
  | "attribute-defaults"
  | "permission-defaults"
  | "memory";

const TAB_IDS: SystemTabId[] = [
  "administration",
  "workflow-defaults",
  "attribute-defaults",
  "permission-defaults",
  "memory",
];

function isSystemTab(value: string | null): value is SystemTabId {
  return value != null && (TAB_IDS as string[]).includes(value);
}

export default function SystemSettings(): JSX.Element {
  const { t } = useTranslation();
  const { roles } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();

  const isAdmin = roles.includes("admin");
  const tabParam = searchParams.get("tab");
  const activeTab: SystemTabId = isSystemTab(tabParam) ? tabParam : "administration";

  if (!isAdmin) {
    return (
      <div className={styles.adminOnly}>
        <PageHeader title={t("nav.systemSettings", "System Settings")} />
        <p className={styles.adminOnlyText}>
          {t(
            "systemSettings.adminOnly",
            "You must be an admin to view or edit System Settings."
          )}
        </p>
      </div>
    );
  }

  const setTab = (tab: SystemTabId): void => {
    const next = new URLSearchParams(searchParams);
    next.set("tab", tab);
    setSearchParams(next, { replace: true });
  };

  const TABS: { id: SystemTabId; label: string }[] = [
    { id: "administration", label: t("systemSettings.tabs.administration", "Administration") },
    { id: "workflow-defaults", label: t("systemSettings.tabs.workflowDefaults", "Workflow Defaults") },
    { id: "attribute-defaults", label: t("systemSettings.tabs.attributeDefaults", "Attribute Defaults") },
    { id: "permission-defaults", label: t("systemSettings.tabs.permissionDefaults", "Permission Defaults") },
    { id: "memory", label: t("systemSettings.tabs.memory", "Memory") },
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
        onKeyDown={(e) => handleTablistKeyDown(e, TAB_IDS, activeTab, setTab)}
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
              aria-controls={`system-settings-panel-${tab.id}`}
              tabIndex={tabRovingTabIndex(tab.id, activeTab)}
              onClick={() => setTab(tab.id)}
              className={
                styles.tab +
                " " +
                (isTabActive ? styles.tabActive : styles.tabInactive)
              }
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
        {activeTab === "memory" && (
          <>
            <MemorySystemSettingsSection />
            <MemoryManagementSection />
            <MemoryVisualizationSection />
          </>
        )}
      </div>
    </div>
  );
}
