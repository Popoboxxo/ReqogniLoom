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
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useWorkspace } from "../../context/WorkspaceContext";
import { useAuth } from "../../context/AuthContext";
import { useTheme } from "../../context/ThemeContext";
import { i18n } from "../../i18n/index";
import { searchApi, type SearchHit } from "../../api/search";
import { versionApi, type VersionInfo } from "../../api/version";
import { CreateWorkspaceModal } from "./CreateWorkspaceModal";
import type { Workspace } from "../../types";

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
  { path: "/needs", labelKey: "nav.needs", feature: "requirements" },
  { path: "/requirements", labelKey: "nav.requirements", feature: "requirements" },
  { path: "/architecture", labelKey: "nav.architecture", feature: "architecture" },
  { path: "/traceability", labelKey: "nav.traceability", feature: "traceability" },
  { path: "/impact", labelKey: "nav.impact", feature: "impact" },
  { path: "/adrs", labelKey: "nav.adrs", feature: "adr" },
  { path: "/risks", labelKey: "nav.risks", feature: "risk" },
  { path: "/issues", labelKey: "nav.issues", feature: "issue" },
  { path: "/testcases", labelKey: "nav.testCases", feature: "testCases" },
  { path: "/test-runs", labelKey: "nav.testRuns", feature: "testRuns" },
  { path: "/baselines", labelKey: "nav.baselines", feature: "baselines" },
  // REQ-144: reuses the pre-existing (previously unused) `approver_ui`
  // preset-visibility flag — true only for the extended preset.
  { path: "/reviews", labelKey: "nav.reviews", feature: "approver_ui" },
  { path: "/import", labelKey: "nav.import", feature: "csv_import" },
  { path: "/icds", labelKey: "nav.icds", feature: "icds" },
  { path: "/diagrams", labelKey: "nav.diagrams", feature: "diagrams" },
  { path: "/glossary", labelKey: "nav.glossary", feature: "dashboard" },
  { path: "/metrics", labelKey: "nav.metrics", feature: "metrics" },
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
    isLoadingWorkspace,
    setActiveWorkspace,
    terminologyLabel,
    reloadWorkspaces,
    hideAllOptional,
    setHideAllOptional,
  } = useWorkspace();
  const { logout } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const location = useLocation();
  const navigate = useNavigate();
  const [hoveredPath, setHoveredPath] = React.useState<string | null>(null);
  const [hoveredButton, setHoveredButton] = React.useState<string | null>(null);
  const [isSwitcherOpen, setIsSwitcherOpen] = React.useState<boolean>(false);
  const [hoveredOptionId, setHoveredOptionId] = React.useState<string | null>(
    null
  );
  const switcherRef = React.useRef<HTMLDivElement | null>(null);

  // ---- Global search state (REQ-L1-020) -----------------------------------
  const [searchQuery, setSearchQuery] = React.useState<string>("");
  const [searchResults, setSearchResults] = React.useState<SearchHit[]>([]);
  const [isSearching, setIsSearching] = React.useState<boolean>(false);
  const [isSearchOpen, setIsSearchOpen] = React.useState<boolean>(false);
  const [hoveredHitId, setHoveredHitId] = React.useState<string | null>(null);
  const searchRef = React.useRef<HTMLDivElement | null>(null);
  const debounceRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);

  // ---- Workspace create modal (REQ-D25: moved out of the nav tree) -------
  const [showCreateWorkspace, setShowCreateWorkspace] = React.useState<boolean>(false);

  const handleWorkspaceCreated = async (ws: Workspace): Promise<void> => {
    await reloadWorkspaces(ws.id);
    navigate("/");
  };

  // ---- Build/version indicator (deployed commit, fetched once on mount) --
  const [versionInfo, setVersionInfo] = React.useState<VersionInfo | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    void versionApi
      .getVersion()
      .then((info) => {
        if (!cancelled) setVersionInfo(info);
      })
      .catch(() => {
        // Non-critical, non-blocking build indicator — silently omit on failure.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Click-outside handler for search dropdown
  React.useEffect(() => {
    if (!isSearchOpen) return;
    const handler = (event: MouseEvent): void => {
      if (
        searchRef.current &&
        !searchRef.current.contains(event.target as Node)
      ) {
        setIsSearchOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [isSearchOpen]);

  // Debounced search execution
  const runSearch = React.useCallback(
    (query: string): void => {
      if (!activeWorkspace || !query.trim()) {
        setSearchResults([]);
        setIsSearching(false);
        return;
      }
      setIsSearching(true);
      searchApi
        .search(query.trim(), activeWorkspace.id, { limit: 10 })
        .then((resp) => {
          setSearchResults(resp.results);
          setIsSearchOpen(true);
        })
        .catch(() => {
          setSearchResults([]);
        })
        .finally(() => {
          setIsSearching(false);
        });
    },
    [activeWorkspace]
  );

  const handleSearchChange = (
    event: React.ChangeEvent<HTMLInputElement>
  ): void => {
    const value = event.target.value;
    setSearchQuery(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!value.trim()) {
      setSearchResults([]);
      setIsSearchOpen(false);
      return;
    }
    debounceRef.current = setTimeout(() => runSearch(value), 300);
  };

  const handleSearchKeyDown = (
    event: React.KeyboardEvent<HTMLInputElement>
  ): void => {
    if (event.key === "Enter") {
      event.preventDefault();
      if (debounceRef.current) clearTimeout(debounceRef.current);
      runSearch(searchQuery);
    } else if (event.key === "Escape") {
      setIsSearchOpen(false);
    }
  };

  const handleHitClick = (hit: SearchHit): void => {
    setIsSearchOpen(false);
    setSearchQuery("");
    setSearchResults([]);
    const route =
      hit.artifact_type === "Requirement"
        ? `/requirements/${hit.id}`
        : hit.artifact_type === "ArchitectureElement"
        ? `/architecture/${hit.id}`
        : hit.artifact_type === "Adr"
        ? `/adrs/${hit.id}`
        : hit.artifact_type === "Risk"
        ? `/risks/${hit.id}`
        : hit.artifact_type === "Issue"
        ? `/issues/${hit.id}`
        : `/tests/${hit.id}`;
    navigate(route);
  };

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

  // ---- Optional-artifacts master toggle (REQ-L1-027) -------------------
  const handleHideAllToggle = (): void => {
    void setHideAllOptional(!hideAllOptional);
  };

  const isItemActive = (path: string): boolean => {
    if (path === "/") {
      return location.pathname === "/";
    }
    return location.pathname === path || location.pathname.startsWith(path + "/");
  };

  return (
    <>
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

      {/* Global search (REQ-L1-020) */}
      <div
        ref={searchRef}
        style={{
          position: "relative",
          marginBottom: "var(--space-4)",
        }}
      >
        <input
          type="search"
          placeholder={t("nav.searchPlaceholder", "Suchen...")}
          data-testid="global-search"
          value={searchQuery}
          onChange={handleSearchChange}
          onKeyDown={handleSearchKeyDown}
          onFocus={() => {
            if (searchResults.length > 0) setIsSearchOpen(true);
          }}
          style={{
            width: "100%",
            padding: "var(--space-2) var(--space-3)",
            background: "rgba(255,255,255,0.1)",
            border: "1px solid rgba(255,255,255,0.2)",
            borderRadius: "var(--radius-md)",
            color: "white",
            fontSize: "var(--font-size-sm)",
            boxSizing: "border-box" as const,
            fontFamily: "inherit",
            outline: "none",
          }}
        />
        {isSearchOpen && (searchResults.length > 0 || isSearching) && (
          <ul
            role="listbox"
            aria-label="Search results"
            style={{
              position: "absolute",
              top: "calc(100% + var(--space-1))",
              left: 0,
              right: 0,
              listStyle: "none",
              margin: 0,
              padding: "var(--space-1)",
              background: SIDEBAR_BG,
              border: `1px solid ${SIDEBAR_BORDER}`,
              borderRadius: "var(--radius-md)",
              boxShadow: "0 8px 24px rgba(0,0,0,0.35)",
              maxHeight: "320px",
              overflowY: "auto",
              zIndex: 100,
            }}
          >
            {isSearching && (
              <li
                style={{
                  padding: "var(--space-2) var(--space-3)",
                  color: SIDEBAR_TEXT_MUTED,
                  fontSize: "var(--font-size-sm)",
                }}
              >
                {t("nav.searching", "Suche läuft...")}
              </li>
            )}
            {!isSearching &&
              searchResults.map((hit) => {
                const isHovered = hoveredHitId === hit.id;
                return (
                  <li key={hit.id}>
                    <button
                      type="button"
                      role="option"
                      data-testid="global-search-result"
                      onClick={() => handleHitClick(hit)}
                      onMouseEnter={() => setHoveredHitId(hit.id)}
                      onMouseLeave={() => setHoveredHitId(null)}
                      style={{
                        display: "flex",
                        flexDirection: "column",
                        alignItems: "flex-start",
                        gap: "2px",
                        width: "100%",
                        padding: "var(--space-2) var(--space-3)",
                        borderRadius: "var(--radius-sm)",
                        border: "none",
                        background: isHovered ? HOVER_BG : "transparent",
                        color: SIDEBAR_TEXT,
                        fontSize: "var(--font-size-sm)",
                        fontWeight: 500,
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
                          maxWidth: "100%",
                        }}
                        title={hit.title}
                      >
                        {hit.title}
                      </span>
                      <span
                        style={{
                          fontSize: "0.7rem",
                          color: SIDEBAR_TEXT_MUTED,
                          textTransform: "uppercase",
                          letterSpacing: "0.05em",
                        }}
                      >
                        {hit.artifact_type}
                      </span>
                    </button>
                  </li>
                );
              })}
          </ul>
        )}
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

      {/* Optional-artifacts master toggle (REQ-L1-027) — sits above the
          workspace switcher so it acts as a navigation filter. */}
      <button
        type="button"
        role="switch"
        aria-checked={!hideAllOptional}
        onClick={handleHideAllToggle}
        onMouseEnter={() => setHoveredButton("optional-toggle")}
        onMouseLeave={() => setHoveredButton(null)}
        data-testid="optional-toggle"
        title={
          hideAllOptional
            ? t("nav.showOptionalArtifacts", "Optionale Artefakte einblenden")
            : t("nav.hideOptionalArtifacts", "Optionale Artefakte ausblenden")
        }
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "var(--space-2)",
          width: "100%",
          padding: "var(--space-2) var(--space-3)",
          marginTop: "var(--space-3)",
          borderRadius: "var(--radius-md)",
          border: `1px solid ${SIDEBAR_BORDER}`,
          background: hoveredButton === "optional-toggle" ? HOVER_BG : "transparent",
          color: SIDEBAR_TEXT,
          fontSize: "var(--font-size-sm)",
          fontWeight: 500,
          fontFamily: "inherit",
          cursor: "pointer",
          transition: "var(--transition-fast)",
          textAlign: "left",
        }}
      >
        <span>{t("nav.optionalArtifacts", "Optional-Artefakte")}</span>
        <span
          aria-hidden="true"
          style={{
            display: "inline-block",
            width: "28px",
            height: "16px",
            borderRadius: "999px",
            background: hideAllOptional
              ? "rgba(255,255,255,0.15)"
              : "var(--color-primary)",
            position: "relative",
            transition: "var(--transition-fast)",
            flexShrink: 0,
          }}
        >
          <span
            style={{
              position: "absolute",
              top: "2px",
              left: hideAllOptional ? "2px" : "14px",
              width: "12px",
              height: "12px",
              borderRadius: "999px",
              background: "white",
              transition: "var(--transition-fast)",
            }}
          />
        </span>
      </button>

      {/* Workspace switcher (REQ-L2-RF-012). Hidden while workspaces are
          still loading so the DEFAULT_WORKSPACE placeholder name never
          flashes as if it were the real active workspace (issue #24). */}
      {activeWorkspace && !isLoadingWorkspace && (
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

          {/* Create workspace button — opens CreateWorkspaceModal (REQ-D25) */}
          <button
            type="button"
            data-testid="create-workspace-btn"
            onClick={() => setShowCreateWorkspace(true)}
            style={{
              marginTop: "var(--space-2)",
              width: "100%",
              background: "var(--color-primary)",
              color: "white",
              border: "none",
              borderRadius: "var(--radius-md)",
              padding: "var(--space-2)",
              cursor: "pointer",
              fontSize: "var(--font-size-sm)",
              fontWeight: 600,
              fontFamily: "inherit",
              transition: "var(--transition-fast)",
            }}
          >
            + Workspace
          </button>

          {/* Dropdown */}
          {isSwitcherOpen && workspaces.length > 0 && (
            <ul
              data-testid="workspace-list"
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
          data-testid="lang-switch"
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
          data-testid="theme-toggle"
          onClick={toggleTheme}
          onMouseEnter={() => setHoveredButton("theme")}
          onMouseLeave={() => setHoveredButton(null)}
          title={t("nav.toggleTheme")}
          style={{
            padding: "var(--space-2) var(--space-3)",
            borderRadius: "var(--radius-md)",
            border: `1px solid ${SIDEBAR_BORDER}`,
            background: hoveredButton === "theme" ? HOVER_BG : "transparent",
            color: SIDEBAR_TEXT,
            fontSize: "var(--font-size-sm)",
            fontWeight: 500,
            cursor: "pointer",
            transition: "var(--transition-fast)",
            textAlign: "left",
          }}
        >
          {theme === "dark" ? t("nav.lightMode") : t("nav.darkMode")}
        </button>
        {/* Personal Access Tokens — workspace-independent, always reachable (REQ-L2-RF-027) */}
        <button
          data-testid="nav-profile"
          onClick={() => navigate("/profile")}
          onMouseEnter={() => setHoveredButton("profile")}
          onMouseLeave={() => setHoveredButton(null)}
          style={{
            padding: "var(--space-2) var(--space-3)",
            borderRadius: "var(--radius-md)",
            border: `1px solid ${SIDEBAR_BORDER}`,
            background:
              hoveredButton === "profile" || location.pathname === "/profile"
                ? HOVER_BG
                : "transparent",
            color: SIDEBAR_TEXT,
            fontSize: "var(--font-size-sm)",
            fontWeight: 500,
            cursor: "pointer",
            transition: "var(--transition-fast)",
            textAlign: "left",
          }}
        >
          {t("nav.profile")}
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
        {versionInfo && (
          <span
            data-testid="build-version-indicator"
            title={
              versionInfo.build_time
                ? `${versionInfo.commit} (${versionInfo.build_time})`
                : versionInfo.commit
            }
            style={{
              padding: "var(--space-1) var(--space-3)",
              fontSize: "var(--font-size-xs)",
              color: "var(--color-text-muted)",
              opacity: 0.7,
            }}
          >
            {t("nav.buildVersion", { sha: versionInfo.commit_short, defaultValue: `Build ${versionInfo.commit_short}` })}
          </span>
        )}
      </div>
    </nav>
    <CreateWorkspaceModal
      isOpen={showCreateWorkspace}
      onClose={() => setShowCreateWorkspace(false)}
      onCreated={handleWorkspaceCreated}
    />
    </>
  );
}
