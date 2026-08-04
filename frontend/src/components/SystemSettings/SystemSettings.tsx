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
import { WorkspaceAdminSection } from "./WorkspaceAdminSection";
import { PermissionDefaultsTab } from "./PermissionDefaultsTab";
import { PageHeader } from "../shared/PageHeader";

type SystemTabId = "administration" | "workflow-defaults" | "permission-defaults";

const TAB_IDS: SystemTabId[] = [
  "administration",
  "workflow-defaults",
  "permission-defaults",
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
      <div style={{ padding: "var(--space-6)", maxWidth: "640px" }}>
        <PageHeader title={t("nav.systemSettings", "System Settings")} />
        <p style={{ color: "var(--color-warning)" }}>
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
    { id: "permission-defaults", label: t("systemSettings.tabs.permissionDefaults", "Permission Defaults") },
  ];

  const isEditorTab = activeTab === "workflow-defaults";

  return (
    <div
      data-testid="system-settings"
      style={{
        maxWidth: isEditorTab ? "none" : "860px",
        margin: isEditorTab ? undefined : "0 auto",
        padding: "var(--space-6)",
      }}
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
              id={`system-settings-tab-${tab.id}`}
              data-testid={`system-settings-tab-${tab.id}`}
              aria-selected={isTabActive}
              aria-controls={`system-settings-panel-${tab.id}`}
              onClick={() => setTab(tab.id)}
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
        id={`system-settings-panel-${activeTab}`}
        data-testid={`system-settings-panel-${activeTab}`}
        aria-labelledby={`system-settings-tab-${activeTab}`}
      >
        {activeTab === "administration" && <WorkspaceAdminSection />}
        {activeTab === "workflow-defaults" && (
          <div
            data-testid="system-workflow-defaults"
            style={{ height: "calc(100vh - 220px)", position: "relative" }}
          >
            <WorkflowEditorPage scope="global" />
          </div>
        )}
        {activeTab === "permission-defaults" && <PermissionDefaultsTab />}
      </div>
    </div>
  );
}
