/**
 * ARCH-L1-001 ReactFrontend — Sidebar Navigation.
 *
 * leaf_id: COMP-RF-001 (NavigationShell)
 * req_id:  REQ-L2-RF-005 (Artefakt-Navigation / Baumstruktur),
 *          REQ-L3-RF001-002 (Preset-gesteuertes Routing),
 *          REQ-L2-RF-007 (Preset-basierte Sichtbarkeit)
 *
 * Renders: top-level nav links (preset-filtered) + workspace info + i18n toggle.
 * Artifact-tree lazy loading is done inside RequirementEditors/ArchitectureEditors
 * per their own data loaders; sidebar links only navigate to section routes.
 */

import React from "react";
import { NavLink } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useWorkspace } from "../../context/WorkspaceContext";
import { useAuth } from "../../context/AuthContext";
import { i18n } from "../../i18n/index";

// ---------------------------------------------------------------------------
// Navigation items — preset-gated (REQ-L3-RF001-002)
// ---------------------------------------------------------------------------

interface NavItem {
  path: string;
  labelKey: string;
  feature: string; // key in PRESET_VISIBILITY
}

const NAV_ITEMS: NavItem[] = [
  { path: "/", labelKey: "nav.dashboard", feature: "dashboard" },
  { path: "/requirements", labelKey: "nav.requirements", feature: "requirements" },
  { path: "/architecture", labelKey: "nav.architecture", feature: "architecture" },
  { path: "/traceability", labelKey: "nav.traceability", feature: "traceability" },
  { path: "/baselines", labelKey: "nav.baselines", feature: "baselines" },
  { path: "/settings", labelKey: "nav.settings", feature: "dashboard" },
];

const activeStyle = { fontWeight: "bold", color: "#0055aa" };

export function SidebarNavigation(): JSX.Element {
  const { t } = useTranslation();
  const { isFeatureVisible, activeWorkspace, terminologyLabel } = useWorkspace();
  const { logout } = useAuth();

  const handleLanguageToggle = (): void => {
    const next = i18n.language.startsWith("de") ? "en" : "de";
    void i18n.changeLanguage(next);
    document.documentElement.lang = next;
  };

  const visibleItems = NAV_ITEMS.filter((item) =>
    isFeatureVisible(item.feature)
  );

  return (
    <nav
      aria-label="Main navigation"
      style={{
        width: "220px",
        minHeight: "100vh",
        background: "#f5f5f5",
        borderRight: "1px solid #ddd",
        display: "flex",
        flexDirection: "column",
        padding: "1rem",
        gap: "0.5rem",
        boxSizing: "border-box",
      }}
    >
      <div style={{ marginBottom: "1rem", fontWeight: "bold", fontSize: "1.1rem" }}>
        ReqFlow
      </div>

      {activeWorkspace && (
        <div
          style={{
            fontSize: "0.8rem",
            color: "#666",
            marginBottom: "1rem",
            borderBottom: "1px solid #ddd",
            paddingBottom: "0.5rem",
          }}
        >
          <div title="Active workspace">{activeWorkspace.name}</div>
          <div style={{ fontStyle: "italic" }}>
            {terminologyLabel("requirement")} / {activeWorkspace.preset}
          </div>
        </div>
      )}

      <ul style={{ listStyle: "none", padding: 0, margin: 0, flex: 1 }}>
        {visibleItems.map((item) => (
          <li key={item.path} style={{ marginBottom: "0.25rem" }}>
            <NavLink
              to={item.path}
              end={item.path === "/"}
              style={({ isActive }) => ({
                display: "block",
                padding: "0.4rem 0.5rem",
                borderRadius: "4px",
                textDecoration: "none",
                color: isActive ? "#0055aa" : "#333",
                background: "transparent",
                ...(isActive ? activeStyle : {}),
              })}
            >
              {t(item.labelKey)}
            </NavLink>
          </li>
        ))}
      </ul>

      <div
        style={{
          borderTop: "1px solid #ddd",
          paddingTop: "0.75rem",
          display: "flex",
          flexDirection: "column",
          gap: "0.5rem",
        }}
      >
        <button
          onClick={handleLanguageToggle}
          style={{ fontSize: "0.8rem", cursor: "pointer" }}
          title="Toggle language DE/EN"
        >
          {i18n.language.startsWith("de") ? "EN" : "DE"}
        </button>
        <button
          onClick={logout}
          style={{ fontSize: "0.8rem", cursor: "pointer" }}
        >
          {t("nav.logout")}
        </button>
      </div>
    </nav>
  );
}
