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
import { ChevronDown } from "lucide-react";
import { APP_NAME } from "../../config/app-name";
import { useWorkspace, DEFAULT_WORKSPACE } from "../../context/WorkspaceContext";
import { useAuth } from "../../context/AuthContext";
import { useTheme } from "../../context/ThemeContext";
import { i18n } from "../../i18n/index";
import { searchApi, type SearchHit } from "../../api/search";
import { versionApi, type VersionInfo } from "../../api/version";
import { workspacesApi } from "../../api/workspaces";
import { CreateWorkspaceModal } from "./CreateWorkspaceModal";
import type { Workspace } from "../../types";
import styles from "./SidebarNavigation.module.css";

// ---------------------------------------------------------------------------
// Navigation items — preset-gated (REQ-L3-RF001-002)
// ---------------------------------------------------------------------------

// Nav-group ids (issue #317) — logical sections shown as headers above the
// flat item list so ~20 entries no longer force scrolling at normal window
// heights without any orientation. Order here defines render order.
type NavGroupId = "overview" | "requirements" | "architecture" | "test" | "admin";

const NAV_GROUP_ORDER: NavGroupId[] = [
  "overview",
  "requirements",
  "architecture",
  "test",
  "admin",
];

// Issues #654/#651: `.navGroupLabel` applies `text-transform: uppercase` to
// every one of these, so an all-caps group header ("ÜBERSICHT",
// "ARCHITEKTUR", ...) next to normal-case items is the intended, consistent
// pattern — not the capitalization outlier the UI audit read it as. The real
// defect the audit saw was that the `architecture` group header rendered the
// *same word* as the `/architecture` item nested directly beneath it
// ("ARCHITEKTUR" / "Architektur"), which reads as a duplicate rather than as
// a section. The group label now names what the section actually contains
// (architecture plus its trace/interface/diagram views), matching the
// existing "Test & Qualität" compound-label style.
const NAV_GROUP_LABEL_KEYS: Record<NavGroupId, string> = {
  overview: "nav.groupOverview",
  requirements: "nav.groupRequirements",
  architecture: "nav.groupArchitecture",
  test: "nav.groupTest",
  admin: "nav.groupAdmin",
};

interface NavItem {
  path: string;
  labelKey: string;
  feature: string; // key in PRESET_VISIBILITY
  group: NavGroupId; // issue #317 — section grouping
}

const NAV_ITEMS: NavItem[] = [
  { path: "/", labelKey: "nav.dashboard", feature: "dashboard", group: "overview" },
  // REQ-L2-TE-020: Goals/MainGoal — the preset-visibility system does not
  // gate this item; visibility instead depends on the workspace's own
  // `goals_enabled` toggle (see WorkspaceSettings). "dashboard" here just
  // means "not filtered by preset" — the actual gate is applied below in
  // `visibleItems` against `activeWorkspace.goals_enabled`.
  { path: "/goals", labelKey: "nav.goals", feature: "dashboard", group: "overview" },
  { path: "/metrics", labelKey: "nav.metrics", feature: "metrics", group: "overview" },
  // Always visible (like glossary/workflows/audit below) — the interview flow
  // itself is the entry point for brainstorming any artifact type, so it must
  // not disappear behind a preset that hides one of its target types.
  { path: "/interviews", labelKey: "nav.interviews", feature: "dashboard", group: "overview" },

  { path: "/needs", labelKey: "nav.needs", feature: "requirements", group: "requirements" },
  { path: "/requirements", labelKey: "nav.requirements", feature: "requirements", group: "requirements" },
  { path: "/adrs", labelKey: "nav.adrs", feature: "adr", group: "requirements" },
  { path: "/risks", labelKey: "nav.risks", feature: "risk", group: "requirements" },
  { path: "/issues", labelKey: "nav.issues", feature: "issue", group: "requirements" },
  { path: "/glossary", labelKey: "nav.glossary", feature: "dashboard", group: "requirements" },

  { path: "/architecture", labelKey: "nav.architecture", feature: "architecture", group: "architecture" },
  { path: "/traceability", labelKey: "nav.traceability", feature: "traceability", group: "architecture" },
  { path: "/impact", labelKey: "nav.impact", feature: "impact", group: "architecture" },
  { path: "/icds", labelKey: "nav.icds", feature: "icds", group: "architecture" },
  { path: "/diagrams", labelKey: "nav.diagrams", feature: "diagrams", group: "architecture" },

  { path: "/testcases", labelKey: "nav.testCases", feature: "testCases", group: "test" },
  { path: "/test-runs", labelKey: "nav.testRuns", feature: "testRuns", group: "test" },
  { path: "/baselines", labelKey: "nav.baselines", feature: "baselines", group: "test" },
  // REQ-144: reuses the pre-existing (previously unused) `approver_ui`
  // preset-visibility flag — true only for the extended preset.
  { path: "/reviews", labelKey: "nav.reviews", feature: "approver_ui", group: "test" },

  { path: "/import", labelKey: "nav.import", feature: "csv_import", group: "admin" },
  // REQ-176: Visual Workflow Editor — always visible (like glossary/settings).
  { path: "/workflows", labelKey: "nav.workflows", feature: "dashboard", group: "admin" },
  // SysEng 2.0 Phase 3 (Auditor UI) — always visible, like glossary/workflows/
  // settings; the RuleEngine already filters findings by the workspace's
  // active rigor tier so there is no separate preset-visibility gate here.
  { path: "/audit", labelKey: "nav.audit", feature: "dashboard", group: "admin" },
  { path: "/settings", labelKey: "nav.settings", feature: "dashboard", group: "admin" },
  // REQ-184: System Settings — tenant-wide config. Link always visible (like
  // /settings); the page itself gates on the admin role.
  { path: "/system-settings", labelKey: "nav.systemSettings", feature: "dashboard", group: "admin" },
  // Multi-user management design spec (Task 12): tenant-admin is a NEW,
  // tenant-wide concept distinct from the workspace `admin` role that gates
  // /settings and /system-settings — a tenant-admin need not be a workspace
  // admin of the currently active workspace (and vice versa), so this link
  // cannot simply live inside either of those pages' existing role gate.
  // Link always visible (like every other admin-group item); the page
  // itself gates on `useAuth().isTenantAdmin` (UX-only — real enforcement
  // is server-side, see UserManagement.tsx's module docstring).
  { path: "/user-management", labelKey: "nav.userManagement", feature: "dashboard", group: "admin" },
];

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
    markLanguageOverrideActive,
    clearLanguageOverride,
  } = useWorkspace();
  const { logout, roles } = useAuth();
  // F-02 (code review, High): the equivalent language radios on the
  // Workspace Settings page are admin-only (`WorkspaceSettings.tsx`'s
  // `isAdmin` gate). `workspace.language` is a workspace-wide field shared
  // by every member, so this quick toggle must respect the same boundary —
  // a non-admin flipping it here must not silently change the language for
  // the whole workspace.
  const isAdmin = roles.includes("admin");
  // Theme Presets: mode-only quick toggle — keeps the current palette and
  // flips dark <-> light (the highest-frequency action). Full palette
  // switching lives in WorkspaceSettings.
  const { mode, paletteKey, setPreference } = useTheme();
  const location = useLocation();
  const navigate = useNavigate();
  const [isSwitcherOpen, setIsSwitcherOpen] = React.useState<boolean>(false);
  // Off-canvas drawer state, only relevant below the --breakpoint-tablet
  // (1024px) media query defined in SidebarNavigation.module.css (issue #160).
  const [isMobileNavOpen, setIsMobileNavOpen] = React.useState<boolean>(false);
  const switcherRef = React.useRef<HTMLDivElement | null>(null);

  // ---- Global search state (REQ-L1-020) -----------------------------------
  const [searchQuery, setSearchQuery] = React.useState<string>("");
  const [searchResults, setSearchResults] = React.useState<SearchHit[]>([]);
  const [isSearching, setIsSearching] = React.useState<boolean>(false);
  const [isSearchOpen, setIsSearchOpen] = React.useState<boolean>(false);
  const searchRef = React.useRef<HTMLDivElement | null>(null);
  const debounceRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);

  // ---- Workspace create modal (REQ-D25: moved out of the nav tree) -------
  const [showCreateWorkspace, setShowCreateWorkspace] = React.useState<boolean>(false);

  // ---- Scroll affordance for the nav list (issue #168) --------------------
  // The nav list can overflow (many workspaces/items) with only
  // `overflowY: auto` and no visual cue that content is cut off below the
  // fold. Track scroll position so a fade-out gradient can be shown only
  // while there is more content to scroll to.
  const navScrollRef = React.useRef<HTMLDivElement | null>(null);
  const [showScrollHint, setShowScrollHint] = React.useState<boolean>(false);

  const updateScrollHint = React.useCallback((): void => {
    const el = navScrollRef.current;
    if (!el) return;
    const distanceToBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    setShowScrollHint(distanceToBottom > 1);
  }, []);

  React.useEffect(() => {
    updateScrollHint();
    const el = navScrollRef.current;
    if (!el) return;
    el.addEventListener("scroll", updateScrollHint);
    window.addEventListener("resize", updateScrollHint);
    return () => {
      el.removeEventListener("scroll", updateScrollHint);
      window.removeEventListener("resize", updateScrollHint);
    };
  });

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
        : hit.artifact_type === "TestCase"
        ? `/testcases/${hit.id}`
        : hit.artifact_type === "StakeholderNeed"
        ? `/needs/${hit.id}`
        : `/requirements/${hit.id}`;
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

  // BUG-01 (SYSTEMAUDIT_2026-08-18 §4): this used to only flip the
  // in-memory i18next instance, never persisting the choice to the
  // workspace — unlike the language radios on the Workspace Settings page.
  // Any real navigation/reload (i18n/index.ts re-seeds `lng` purely from
  // the browser locale) silently reverted the UI to the browser default.
  //
  // F-02/F-04 (code review): persistence is admin-only (mirrors
  // `WorkspaceSettings.handleLanguageChange`'s `isAdmin` gate) and a save
  // failure is surfaced, not swallowed — a silent catch here would recreate
  // BUG-01 the moment any later `reloadWorkspaces()` call (workspace switch,
  // preset change, ...) re-applies the still-unsaved old value from the
  // WorkspaceContext restore effect.
  const [langNotice, setLangNotice] = React.useState<
    { kind: "info" | "error"; text: string } | null
  >(null);

  const handleLanguageToggle = (): void => {
    const next = i18n.language.startsWith("de") ? "en" : "de";
    void i18n.changeLanguage(next);
    document.documentElement.lang = next;
    // Code-review F-04-Residual: mark this as a not-yet-(or-never-)persisted
    // local choice *before* any PATCH is attempted — WorkspaceContext's
    // restore effect fires on every `reloadWorkspaces()` call, not just ones
    // caused by this toggle (preset change, name save, per-user visibility
    // toggle, ... — see `WorkspaceSettings.tsx`/`WorkspaceAdminSection.tsx`),
    // and would otherwise silently snap the language back to the still-old
    // `activeWorkspace.language` if one of those fires while this toggle's
    // own PATCH is in flight, has failed, or (non-admin) was never sent at
    // all. Covers: the non-admin path (never persisted), the
    // DEFAULT_WORKSPACE-placeholder path (nothing to persist against yet)
    // and the in-flight window of an admin's own PATCH.
    markLanguageOverrideActive();

    if (!isAdmin) {
      // Session-local only — never PATCHes the shared workspace setting.
      // Explicit, visible notice so this limitation is never silent.
      setLangNotice({ kind: "info", text: t("nav.languageSessionOnly") });
      return;
    }
    // The DEFAULT_WORKSPACE placeholder's id is a fake UUID (or an E2E
    // override) — PATCHing it would 404. Skip persistence until a real
    // workspace has loaded; the local language switch above still applies.
    if (!activeWorkspace || activeWorkspace === DEFAULT_WORKSPACE) return;
    setLangNotice(null);
    void workspacesApi
      .update(activeWorkspace.id, { language: next })
      // Code-review R-01: clear the override AFTER the reload lands, not
      // before. `reloadWorkspaces` synchronously sets `isLoadingWorkspace`
      // and only resolves `activeWorkspace.language === next` once its own
      // `GET /workspaces/` completes; clearing the override first left a
      // window where `hasLocalLanguageOverride` was already `false` but
      // `activeWorkspace.language` was still the pre-toggle value — the
      // restore effect could fire in that window and flash the UI back to
      // the old language before flipping forward again once the reload
      // finished. Clearing only after `reloadWorkspaces` resolves means the
      // restore effect is a no-op the one time it's allowed to run again
      // (`activeWorkspace.language` already equals `next` by then).
      .then(() => reloadWorkspaces(activeWorkspace.id))
      .then(() => {
        clearLanguageOverride();
      })
      .catch(() => {
        setLangNotice({ kind: "error", text: t("nav.languageSaveFailed") });
      });
  };

  const visibleItems = NAV_ITEMS.filter((item) =>
    isFeatureVisible(item.feature)
  ).filter(
    (item) => item.path !== "/goals" || !!activeWorkspace?.goals_enabled
  );

  // Group the flat visible-item list into logical sections (issue #317) so
  // ~20 entries no longer read as one undifferentiated scrolling list.
  const groupedVisibleItems: Array<{ id: NavGroupId; items: NavItem[] }> =
    NAV_GROUP_ORDER.map((id) => ({
      id,
      items: visibleItems.filter((item) => item.group === id),
    })).filter((group) => group.items.length > 0);

  // ---- Optional-artifacts master toggle (REQ-L1-027) -------------------
  const handleHideAllToggle = (): void => {
    void setHideAllOptional(!hideAllOptional);
  };

  // Close the mobile drawer whenever the route changes (issue #160) so it
  // never stays open covering the newly navigated page.
  React.useEffect(() => {
    setIsMobileNavOpen(false);
  }, [location.pathname]);

  // UI-27 (systemaudit 2026-08-27): the mobile drawer's backdrop only closed
  // on click, leaving no keyboard-operable way to dismiss it (WCAG 2.1.1
  // Keyboard). Escape is the conventional dismiss key for this kind of
  // non-modal overlay (same convention as the shared Dialog component).
  React.useEffect(() => {
    if (!isMobileNavOpen) return;
    const handleKeyDown = (e: KeyboardEvent): void => {
      if (e.key === "Escape") setIsMobileNavOpen(false);
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isMobileNavOpen]);

  const isItemActive = (path: string): boolean => {
    if (path === "/") {
      return location.pathname === "/";
    }
    return location.pathname === path || location.pathname.startsWith(path + "/");
  };

  return (
    <>
    {/* Burger toggle — only rendered visibly below --breakpoint-tablet
        (1024px, see SidebarNavigation.module.css). Opens the off-canvas
        drawer (issue #160). */}
    <button
      type="button"
      className={styles.burgerButton}
      data-testid="sidebar-burger"
      aria-label={isMobileNavOpen ? t("nav.closeMenu") : t("nav.openMenu")}
      aria-expanded={isMobileNavOpen}
      onClick={() => setIsMobileNavOpen((open) => !open)}
    >
      {isMobileNavOpen ? "✕" : "☰"}
    </button>
    {isMobileNavOpen && (
      // Backdrop only — deliberately not focusable/role="button": a
      // full-viewport overlay in the tab order would be a keyboard trap of
      // its own. Keyboard dismissal is handled by the document-level Escape
      // listener above (WCAG 2.1.1), not a handler on this element.
      // eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-static-element-interactions
      <div
        className={styles.overlay}
        data-testid="sidebar-overlay"
        onClick={() => setIsMobileNavOpen(false)}
      />
    )}
    <nav
      aria-label={t("nav.mainNavigation")}
      className={`${styles.sidebarNav} ${styles.navRoot} ${isMobileNavOpen ? styles.open : ""}`}
    >
      {/* Wraps the scrollable nav content so the fade-out scroll affordance
          (issue #168) can be positioned against its bottom edge, not the
          nav's own bottom (which is the pinned footer below). */}
      <div className={styles.scrollWrapper}>
      {/* Scrollable nav content — keeps the footer (below) pinned to the
          viewport bottom regardless of how many nav items are rendered
          (issue #47: footer must not scroll away with a long sidebar). */}
      <div ref={navScrollRef} className={styles.scrollContent} data-testid="sidebar-nav-scroll-content">
      {/* Logo */}
      <div className={styles.logoRow}>
        <span aria-hidden="true" className={styles.logoDot} />
        <span className={styles.logoText}>{APP_NAME}</span>
      </div>

      {/* Global search (REQ-L1-020) */}
      <div ref={searchRef} className={styles.searchWrapper}>
        <input
          type="search"
          placeholder={t("nav.searchPlaceholder", "Suchen...")}
          aria-label={t("nav.searchPlaceholder", "Suchen...")}
          data-testid="global-search"
          value={searchQuery}
          onChange={handleSearchChange}
          onKeyDown={handleSearchKeyDown}
          onFocus={() => {
            if (searchResults.length > 0) setIsSearchOpen(true);
          }}
          className={styles.searchInput}
        />
        {isSearchOpen && (searchResults.length > 0 || isSearching) && (
          <ul role="listbox" aria-label={t("nav.searchResults")} className={styles.dropdownList}>
            {isSearching && (
              <li className={styles.dropdownLoadingItem}>
                {t("nav.searching", "Suche läuft...")}
              </li>
            )}
            {!isSearching &&
              searchResults.map((hit) => (
                <li key={hit.id}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={false}
                    data-testid="global-search-result"
                    onClick={() => handleHitClick(hit)}
                    className={styles.searchResultButton}
                  >
                    <span className={styles.searchResultTitle} title={hit.title}>
                      {hit.title}
                    </span>
                    <span className={styles.searchResultType}>{hit.artifact_type}</span>
                  </button>
                </li>
              ))}
          </ul>
        )}
      </div>

      {/* Nav links — grouped into logical sections (issue #317) so ~20
          entries no longer read as one flat, unoriented scrolling list. */}
      <div className={styles.navGroupsWrapper}>
        {groupedVisibleItems.map((group) => (
          <div key={group.id} className={styles.navGroup}>
            <div data-testid={`nav-group-${group.id}`} className={styles.navGroupLabel}>
              {t(NAV_GROUP_LABEL_KEYS[group.id])}
            </div>
            <ul className={styles.navList}>
              {group.items.map((item) => {
                const active = isItemActive(item.path);

                return (
                  <li key={item.path} className={styles.navListItem}>
                    <NavLink
                      to={item.path}
                      end={item.path === "/"}
                      className={active ? styles.navLinkActive : styles.navLink}
                    >
                      {t(item.labelKey)}
                    </NavLink>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </div>

      {/* Optional-artifacts master toggle (REQ-L1-027) — sits above the
          workspace switcher so it acts as a navigation filter. */}
      <button
        type="button"
        role="switch"
        aria-checked={!hideAllOptional}
        onClick={handleHideAllToggle}
        data-testid="optional-toggle"
        title={
          hideAllOptional
            ? t("nav.showOptionalArtifacts", "Optionale Artefakte einblenden")
            : t("nav.hideOptionalArtifacts", "Optionale Artefakte ausblenden")
        }
        className={styles.optionalToggleBtn}
      >
        <span>{t("nav.optionalArtifacts", "Optional-Artefakte")}</span>
        <span
          aria-hidden="true"
          className={`${styles.switchTrack} ${!hideAllOptional ? styles.switchTrackOn : ""}`}
        >
          <span
            className={`${styles.switchKnob} ${!hideAllOptional ? styles.switchKnobOn : ""}`}
          />
        </span>
      </button>

      {/* Workspace switcher (REQ-L2-RF-012). Hidden while workspaces are
          still loading so the DEFAULT_WORKSPACE placeholder name never
          flashes as if it were the real active workspace (issue #24). */}
      {activeWorkspace && !isLoadingWorkspace && (
        <div ref={switcherRef} className={styles.workspaceSwitcherWrapper}>
          <button
            type="button"
            data-testid="workspace-switcher"
            aria-haspopup="listbox"
            aria-expanded={isSwitcherOpen}
            onClick={() => setIsSwitcherOpen((open) => !open)}
            className={styles.switcherToggleBtn}
          >
            <span className={styles.switcherLabel} title={activeWorkspace.name}>
              {activeWorkspace.name}
            </span>
            <span
              aria-hidden="true"
              className={`${styles.chevron} ${isSwitcherOpen ? styles.chevronOpen : ""}`}
            >
              ▾
            </span>
          </button>

          {/* Preset + terminology meta line */}
          <div className={styles.switcherMetaRow}>
            <span className={styles.presetBadge}>{activeWorkspace.preset}</span>
            <span className={styles.terminologyLabel}>{terminologyLabel("requirement")}</span>
          </div>

          {/* Create workspace button — opens CreateWorkspaceModal (REQ-D25) */}
          <button
            type="button"
            data-testid="create-workspace-btn"
            onClick={() => setShowCreateWorkspace(true)}
            className={styles.createWorkspaceBtn}
          >
            {t("workspaceCreate.button")}
          </button>

          {/* Dropdown — show empty state if no other workspaces available */}
          {isSwitcherOpen && (
            workspaces.length > 0 ? (
              <ul
                data-testid="workspace-list"
                role="listbox"
                aria-label={t("nav.workspaceSwitcher")}
                className={styles.workspaceList}
              >
                {workspaces.map((ws) => {
                  const isActive = ws.id === activeWorkspace.id;
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
                        className={isActive ? styles.workspaceOptionActive : styles.workspaceOption}
                      >
                        <span className={styles.workspaceOptionLabel} title={ws.name}>
                          {ws.name}
                        </span>
                        {isActive && (
                          <span aria-hidden="true" className={styles.workspaceOptionCheck}>
                            ✓
                          </span>
                        )}
                      </button>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <div data-testid="workspace-empty-state" className={styles.workspaceEmptyState}>
                {/* Issues #654/#651: the old key was `workspace.noOthers`, a
                    namespace that does not exist in either locale file, so
                    i18next always fell through to the English literal
                    fallback — visible English text in an otherwise German
                    sidebar. Moved under the `nav` namespace this file
                    already uses for every other label. */}
                {t("nav.noOtherWorkspaces")}
              </div>
            )
          )}
        </div>
      )}
      </div>

      {/* Fade-out scroll affordance (issue #168). GESAMTTEST_BERICHT_2026-08-21.md
          §6 "Sidebar navigation: no scroll indicator": at common laptop
          resolutions (1366×900) the plain fade-to-background gradient was
          nearly indistinguishable from the boundary between the scroll
          region and the pinned footer below it (both share the same nav
          background color), so it read as "end of list", not "scroll for
          more" — live-verified: the last item (e.g. "Architektur") fades
          out with no unambiguous cue. Adding a small centered chevron on
          top of the same gradient makes the affordance legible without
          changing the underlying scroll-detection logic. Still purely
          decorative/non-interactive. */}
      {showScrollHint && (
        <div aria-hidden="true" data-testid="sidebar-nav-scroll-hint" className={styles.scrollHint}>
          <ChevronDown size={14} className={styles.scrollHintChevron} />
        </div>
      )}
      </div>

      {/* Footer actions — sibling of the scrollable content above, so it
          always stays pinned to the bottom of the (viewport-height) nav
          (issue #47). */}
      <div className={styles.footer}>
        <button
          data-testid="lang-switch"
          onClick={handleLanguageToggle}
          title={
            isAdmin
              ? t("nav.languageToggleTitleAdmin")
              : t("nav.languageToggleTitleMember")
          }
          className={styles.footerBtn}
        >
          {i18n.language.startsWith("de") ? "EN" : "DE"}
        </button>
        {langNotice && (
          <p
            data-testid="lang-switch-notice"
            role={langNotice.kind === "error" ? "alert" : "status"}
            className={
              langNotice.kind === "error"
                ? `${styles.langNotice} ${styles.langNoticeError}`
                : styles.langNotice
            }
          >
            {langNotice.text}
          </p>
        )}
        <button
          data-testid="sidebar-theme-mode-toggle"
          onClick={() => setPreference(paletteKey, mode === "dark" ? "light" : "dark")}
          title={t("nav.toggleTheme")}
          className={styles.footerBtn}
        >
          {mode === "dark" ? t("nav.lightMode") : t("nav.darkMode")}
        </button>
        {/* Personal Access Tokens — workspace-independent, always reachable (REQ-L2-RF-027) */}
        <button
          data-testid="nav-profile"
          onClick={() => navigate("/profile")}
          className={location.pathname === "/profile" ? `${styles.footerBtn} ${styles.footerBtnActive}` : styles.footerBtn}
        >
          {t("nav.profile")}
        </button>
        <button data-testid="nav-logout" onClick={logout} className={styles.footerBtn}>
          {t("nav.logout")}
        </button>
        {versionInfo && (
          <span data-testid="build-version-indicator" className={styles.buildVersion}>
            {versionInfo.app_version && versionInfo.app_version !== "unknown"
              ? `${t("nav.appVersion", { version: versionInfo.app_version, defaultValue: `v${versionInfo.app_version}` })} · `
              : ""}
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
