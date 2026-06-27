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
import { NavLink, useLocation } from "react-router-dom";
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

// Sidebar palette — dark professional theme.
// All design-system colors are sourced from var(--color-*) tokens in tokens.css.
const SIDEBAR_BG = "#1a1f2e";
const SIDEBAR_TEXT = "#ffffff";
const SIDEBAR_TEXT_MUTED = "rgba(255,255,255,0.65)";
const SIDEBAR_BORDER = "rgba(255,255,255,0.08)";
const ACTIVE_BG = "rgba(79,110,247,0.15)";
const HOVER_BG = "rgba(255,255,255,0.05)";

export function SidebarNavigation(): JSX.Element {
  const { t } = useTranslation();
  const {
    isFeatureVisible,
    activeWorkspace,
    workspaces,
    setActiveWorkspace,
    terminologyLabel,
  } = useWorkspace();
  const { logout } = useAuth();
  const location = useLocation();
  const [hoveredPath, setHoveredPath] = React.useState<string | null>(null);
  const [hoveredButton, setHoveredButton] = React.useState<string | null>(null);
  const [isSwitcherOpen, setIsSwitcherOpen] = React.useState<boolean>(false);
  const [hoveredOptionId, setHoveredOptionId] = React.useState<string | null>(
    null
  );
  const switcherRef = React.useRef<HTMLDivElement | null>(null);

  // Click-outside handler — close dropdown when clicking outside
  React.useEffect(() => {
    if (!isSwitcherOpen) return;
    const handler = (event: MouseEvent): void => {
      if (
        switcherRef.current &&
        !switcherRef.current.contains(event.target as Node)
      ) {
        setIsSwitcherOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [isSwitcherOpen]);

  const handleLanguageToggle = (): void => {
    const next = i18n.language.startsWith("de") ? "en" : "de";
    void i18n.changeLanguage(next);
    document.documentElement.lang = next;
  };

  const visibleItems = NAV_ITEMS.filter((item) =>
    isFeatureVisible(item.feature)
  );

  const isItemActive = (path: string): boolean => {
    if (path === "/") {
      return location.pathname === "/";
    }
    return location.pathname === path || location.pathname.startsWith(path + "/");
  };

  return (
    <nav
      aria-label="Main navigation"
      style={{
        width: "220px",
        minHeight: "100vh",
        background: SIDEBAR_BG,
        display: "flex",
        flexDirection: "column",
        padding: "var(--space-6) var(--space-4)",
        gap: "var(--space-2)",
        boxSizing: "border-box",
        fontFamily: "var(--font-sans)",
        color: SIDEBAR_TEXT,
      }}
    >
      {/* Logo */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "var(--space-2)",
          marginBottom: "var(--space-8)",
          padding: "0 var(--space-2)",
        }}
      >
        <span
          aria-hidden="true"
          style={{
            display: "inline-block",
            width: "10px",
            height: "10px",
            borderRadius: "var(--radius-full)",
            background: "var(--color-primary)",
            boxShadow: "0 0 0 3px rgba(79,110,247,0.20)",
          }}
        />
        <span
          style={{
            color: SIDEBAR_TEXT,
            fontWeight: 700,
            fontSize: "1.25rem",
            letterSpacing: "0.01em",
          }}
        >
          ReqFlow
        </span>
      </div>

      {/* Nav links */}
      <ul style={{ listStyle: "none", padding: 0, margin: 0, flex: 1 }}>
        {visibleItems.map((item) => {
          const active = isItemActive(item.path);
          const hovered = hoveredPath === item.path;

          return (
            <li key={item.path} style={{ marginBottom: "var(--space-1)" }}>
              <NavLink
                to={item.path}
                end={item.path === "/"}
                onMouseEnter={() => setHoveredPath(item.path)}
                onMouseLeave={() => setHoveredPath(null)}
                style={{
                  display: "block",
                  padding: "var(--space-2) var(--space-3)",
                  paddingLeft: active ? "calc(var(--space-3) - 3px)" : "var(--space-3)",
                  borderRadius: "var(--radius-md)",
                  borderLeft: active
                    ? "3px solid var(--color-primary)"
                    : "3px solid transparent",
                  textDecoration: "none",
                  color: SIDEBAR_TEXT,
                  background: active
                    ? ACTIVE_BG
                    : hovered
                    ? HOVER_BG
                    : "transparent",
                  fontSize: "var(--font-size-sm)",
                  fontWeight: active ? 600 : 500,
                  transition: "var(--transition-fast)",
                }}
              >
                {t(item.labelKey)}
              </NavLink>
            </li>
          );
        })}
      </ul>

      {/* Workspace switcher (REQ-L2-RF-012) */}
      {activeWorkspace && (
        <div
          ref={switcherRef}
          style={{
            position: "relative",
            borderTop: `1px solid ${SIDEBAR_BORDER}`,
            paddingTop: "var(--space-3)",
            marginTop: "var(--space-3)",
            marginBottom: "var(--space-2)",
            display: "flex",
            flexDirection: "column",
            gap: "var(--space-2)",
            padding: "var(--space-3) var(--space-2) 0",
          }}
        >
          <button
            type="button"
            data-testid="workspace-switcher"
            aria-haspopup="listbox"
            aria-expanded={isSwitcherOpen}
            onClick={() => setIsSwitcherOpen((open) => !open)}
            onMouseEnter={() => setHoveredButton("switcher")}
            onMouseLeave={() => setHoveredButton(null)}
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: "var(--space-2)",
              width: "100%",
              padding: "var(--space-2) var(--space-3)",
              borderRadius: "var(--radius-md)",
              border: `1px solid ${SIDEBAR_BORDER}`,
              background: hoveredButton === "switcher" ? HOVER_BG : "transparent",
              color: SIDEBAR_TEXT,
              fontSize: "var(--font-size-sm)",
              fontWeight: 500,
              fontFamily: "inherit",
              cursor: "pointer",
              transition: "var(--transition-fast)",
              textAlign: "left",
            }}
          >
            <span
              style={{
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
                flex: 1,
              }}
              title={activeWorkspace.name}
            >
              {activeWorkspace.name}
            </span>
            <span
              aria-hidden="true"
              style={{
                fontSize: "0.7rem",
                color: SIDEBAR_TEXT_MUTED,
                transform: isSwitcherOpen ? "rotate(180deg)" : "rotate(0deg)",
                transition: "var(--transition-fast)",
                display: "inline-block",
              }}
            >
              ▾
            </span>
          </button>

          {/* Preset + terminology meta line */}
          <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)", padding: "0 var(--space-1)" }}>
            <span
              style={{
                display: "inline-block",
                padding: "2px var(--space-2)",
                borderRadius: "var(--radius-sm)",
                background: "rgba(79,110,247,0.20)",
                color: "var(--color-primary)",
                fontSize: "0.7rem",
                fontWeight: 600,
                textTransform: "uppercase",
                letterSpacing: "0.05em",
              }}
            >
              {activeWorkspace.preset}
            </span>
            <span
              style={{
                color: SIDEBAR_TEXT_MUTED,
                fontSize: "0.7rem",
              }}
            >
              {terminologyLabel("requirement")}
            </span>
          </div>

          {/* Dropdown */}
          {isSwitcherOpen && workspaces.length > 0 && (
            <ul
              role="listbox"
              aria-label="Workspace switcher"
              style={{
                position: "absolute",
                bottom: "calc(100% + var(--space-2))",
                left: "var(--space-2)",
                right: "var(--space-2)",
                listStyle: "none",
                margin: 0,
                padding: "var(--space-1)",
                background: SIDEBAR_BG,
                border: `1px solid ${SIDEBAR_BORDER}`,
                borderRadius: "var(--radius-md)",
                boxShadow: "0 8px 24px rgba(0,0,0,0.35)",
                maxHeight: "240px",
                overflowY: "auto",
                zIndex: 100,
              }}
            >
              {workspaces.map((ws) => {
                const isActive = ws.id === activeWorkspace.id;
                const isHovered = hoveredOptionId === ws.id;
                return (
                  <li key={ws.id}>
                    <button
                      type="button"
                      role="option"
                      aria-selected={isActive}
                      data-testid="workspace-switcher-option"
                      onClick={() => {
                        setActiveWorkspace(ws);
                        setIsSwitcherOpen(false);
                      }}
                      onMouseEnter={() => setHoveredOptionId(ws.id)}
                      onMouseLeave={() => setHoveredOptionId(null)}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        gap: "var(--space-2)",
                        width: "100%",
                        padding: "var(--space-2) var(--space-3)",
                        borderRadius: "var(--radius-sm)",
                        border: "none",
                        background: isActive
                          ? ACTIVE_BG
                          : isHovered
                          ? HOVER_BG
                          : "transparent",
                        color: SIDEBAR_TEXT,
                        fontSize: "var(--font-size-sm)",
                        fontWeight: isActive ? 600 : 500,
                        fontFamily: "inherit",
                        cursor: "pointer",
                        textAlign: "left",
                        transition: "var(--transition-fast)",
                      }}
                    >
                      <span
                        style={{
                          whiteSpace: "nowrap",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          flex: 1,
                        }}
                        title={ws.name}
                      >
                        {ws.name}
                      </span>
                      {isActive && (
                        <span
                          aria-hidden="true"
                          style={{
                            color: "var(--color-primary)",
                            fontSize: "0.8rem",
                          }}
                        >
                          ✓
                        </span>
                      )}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}

      {/* Footer actions */}
      <div
        style={{
          borderTop: `1px solid ${SIDEBAR_BORDER}`,
          paddingTop: "var(--space-3)",
          display: "flex",
          flexDirection: "column",
          gap: "var(--space-2)",
        }}
      >
        <button
          onClick={handleLanguageToggle}
          onMouseEnter={() => setHoveredButton("lang")}
          onMouseLeave={() => setHoveredButton(null)}
          title="Toggle language DE/EN"
          style={{
            padding: "var(--space-2) var(--space-3)",
            borderRadius: "var(--radius-md)",
            border: `1px solid ${SIDEBAR_BORDER}`,
            background: hoveredButton === "lang" ? HOVER_BG : "transparent",
            color: SIDEBAR_TEXT,
            fontSize: "var(--font-size-sm)",
            fontWeight: 500,
            cursor: "pointer",
            transition: "var(--transition-fast)",
            textAlign: "left",
          }}
        >
          {i18n.language.startsWith("de") ? "EN" : "DE"}
        </button>
        <button
          onClick={logout}
          onMouseEnter={() => setHoveredButton("logout")}
          onMouseLeave={() => setHoveredButton(null)}
          style={{
            padding: "var(--space-2) var(--space-3)",
            borderRadius: "var(--radius-md)",
            border: `1px solid ${SIDEBAR_BORDER}`,
            background: hoveredButton === "logout" ? HOVER_BG : "transparent",
            color: SIDEBAR_TEXT,
            fontSize: "var(--font-size-sm)",
            fontWeight: 500,
            cursor: "pointer",
            transition: "var(--transition-fast)",
            textAlign: "left",
          }}
        >
          {t("nav.logout")}
        </button>
      </div>
    </nav>
  );
}
