/**
 * ArtifactInspector — RightSidebar shell (REQ-L2-RF-034).
 *
 * leaf_id: COMP-RF-014 (ArtifactInspector)
 * req_id:  REQ-L2-RF-034 (RightSidebar shell),
 *          REQ-L1-089 (Unified ArtifactInspector shell),
 *          REQ-L0-062 (Unified Artifact Inspector Sidebar),
 *          REQ-L1-093 (Accessibility baseline),
 *          REQ-L1-094 (i18n key naming),
 *          REQ-L1-095 (Adoption on 10 artifact types)
 *
 * Composes VersionPanel → DiffPanel → TracePanel inside a
 * `<aside role="complementary">` with:
 *   - collapse/pin controls (localStorage per kind, UI standards §6.1)
 *   - resizable width 280..520 px (localStorage per kind, §7.2)
 *   - collapsed-state icon strip (§3.1)
 *   - live region announcements (REQ-L1-093)
 *
 * Per panel loading/empty/error states are owned by the individual
 * panels; the shell just lays them out.
 */
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from "react";
import { useTranslation } from "react-i18next";
import { VersionPanel } from "./VersionPanel";
import { DiffPanel } from "./DiffPanel";
import { TracePanel } from "./TracePanel";
import type { ArtifactKind, VersionRef } from "./types";
import styles from "./RightSidebar.module.css";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface RightSidebarProps {
  kind: ArtifactKind;
  artifactId: string | number;
  currentVersion?: VersionRef;
  /**
   * Hides the TracePanel section (REQ-L2-RF-037 / Task 3.3). Trace-link
   * display now lives in `<TraceSpine>` on every route that has one — the
   * shell must not show the same links twice (UI concept ch. 3.4 "Eine
   * Fläche, eine Aufgabe"). Pages without a Spine yet (Glossary, ICD) keep
   * the default `false` so they don't lose their only trace-link view.
   */
  hideTraceLinks?: boolean;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const DEFAULT_WIDTH_PX = 360;
const MIN_WIDTH_PX = 280;
const MAX_WIDTH_PX = 520;
const COLLAPSED_WIDTH_PX = 40;
/**
 * Upper bound on the share of the surrounding detail pane the expanded
 * inspector may occupy (see `asideStyle`). Keeps the editor column itself
 * usable on narrow viewports, where the pane is only about half the window.
 */
const MAX_WIDTH_SHARE_PERCENT = 45;

const COLLAPSE_KEY = (kind: ArtifactKind): string => `reqflow_inspector_collapsed_${kind}`;
const PIN_KEY = (kind: ArtifactKind): string => `reqflow_inspector_pinned_${kind}`;
const WIDTH_KEY = (kind: ArtifactKind): string => `reqflow_inspector_width_${kind}`;

/**
 * #419: below this viewport width, the expanded inspector (plus its
 * surrounding detail pane) leaves too little room for the editor — at
 * 1366px the Save button and every "Classification & Properties" field
 * became unreachable. Collapsing the aside by default on first load below
 * this threshold restores a usable editor without removing the option to
 * expand it again (collapsing the earlier 45%-width cap does not by itself
 * fix this — the editor's *remaining* share still has to stay usable).
 */
const DEFAULT_COLLAPSE_BREAKPOINT_PX = 1600;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function readBool(key: string, fallback: boolean): boolean {
  if (typeof window === "undefined") return fallback;
  try {
    const raw = window.localStorage.getItem(key);
    if (raw === "true") return true;
    if (raw === "false") return false;
  } catch {
    /* localStorage may be disabled (private mode, etc.) */
  }
  return fallback;
}

/**
 * #419: like `readBool`, but when there is no stored preference yet, the
 * fallback is viewport-aware instead of a fixed constant — collapsed on
 * narrow viewports, expanded otherwise. An explicit prior choice (any
 * stored "true"/"false") always wins over this heuristic.
 */
function readCollapsedDefault(key: string): boolean {
  if (typeof window === "undefined") return false;
  try {
    const raw = window.localStorage.getItem(key);
    if (raw === "true") return true;
    if (raw === "false") return false;
  } catch {
    /* localStorage may be disabled (private mode, etc.) */
  }
  return window.innerWidth < DEFAULT_COLLAPSE_BREAKPOINT_PX;
}

function writeBool(key: string, value: boolean): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(key, value ? "true" : "false");
  } catch {
    /* ignore */
  }
}

function readNumber(key: string, fallback: number): number {
  if (typeof window === "undefined") return fallback;
  try {
    const raw = window.localStorage.getItem(key);
    if (raw === null) return fallback;
    const n = parseInt(raw, 10);
    if (Number.isFinite(n)) return n;
  } catch {
    /* ignore */
  }
  return fallback;
}

function writeNumber(key: string, value: number): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(key, String(value));
  } catch {
    /* ignore */
  }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function RightSidebar({
  kind,
  artifactId,
  currentVersion,
  hideTraceLinks = false,
}: RightSidebarProps): JSX.Element {
  const { t } = useTranslation();

  // -------------------------------------------------------------------------
  // State — collapsed / pinned / width (all per-kind, persisted)
  // -------------------------------------------------------------------------

  const [collapsed, setCollapsed] = useState<boolean>(() => readCollapsedDefault(COLLAPSE_KEY(kind)));
  const [pinned, setPinned] = useState<boolean>(() => readBool(PIN_KEY(kind), false));
  const [width, setWidth] = useState<number>(() =>
    readNumber(WIDTH_KEY(kind), DEFAULT_WIDTH_PX)
  );

  // Persist on change
  useEffect(() => writeBool(COLLAPSE_KEY(kind), collapsed), [collapsed, kind]);
  useEffect(() => writeBool(PIN_KEY(kind), pinned), [pinned, kind]);
  useEffect(() => writeNumber(WIDTH_KEY(kind), width), [width, kind]);

  // -------------------------------------------------------------------------
  // Diff state — left/right version selection owned by the shell
  // -------------------------------------------------------------------------

  // M-04: `diffLeft` starts equal to `diffRight` — an empty range that names
  // no comparison at all. That is deliberate and means "no explicit choice
  // yet": DiffPanel forwards it as a *request*, and ArtifactDiff discards any
  // value that is not a real version below the right-hand side, falling back
  // to its own seeding. It only becomes a real selection once the user picks
  // "Compare to current" on a version row (handleCompareVersions below).
  // What must never happen again is a caller *describing* this placeholder
  // range to the user as though it were the comparison on screen.
  const [diffLeft, setDiffLeft] = useState<number>(() => currentVersion?.version ?? 1);
  const [diffRight, setDiffRight] = useState<number>(() => currentVersion?.version ?? 1);

  // Keep diffRight in sync with the current version when it changes
  // externally (e.g. onSwitch emitted by VersionPanel).
  useEffect(() => {
    if (currentVersion) {
      setDiffRight((prev) => (prev === currentVersion.version ? prev : currentVersion.version));
    }
  }, [currentVersion]);

  const handleSwitchVersion = useCallback((version: number): void => {
    if (currentVersion) {
      setDiffLeft(currentVersion.version);
    }
    setDiffRight(version);
  }, [currentVersion]);

  const handleCompareVersions = useCallback((a: number, b: number): void => {
    // 'a' is the version the user clicked, 'b' is the current version
    setDiffLeft(a);
    setDiffRight(b);
  }, []);

  // -------------------------------------------------------------------------
  // Width resize — simple drag handle on the right edge
  // -------------------------------------------------------------------------

  const isResizingRef = useRef(false);
  const resizeStartXRef = useRef(0);
  const resizeStartWidthRef = useRef(0);

  const onResizeMouseDown = useCallback(
    (e: React.MouseEvent<HTMLDivElement>): void => {
      isResizingRef.current = true;
      resizeStartXRef.current = e.clientX;
      resizeStartWidthRef.current = width;
      document.body.style.userSelect = "none";
      document.body.style.cursor = "col-resize";
      e.preventDefault();
    },
    [width]
  );

  // UI-27 (systemaudit 2026-08-27): the handle was mouse-only (WCAG 2.1.1
  // Keyboard). ARIA APG "window splitter" pattern: Left/Right adjust in
  // fixed steps (mirroring the mouse's "dragging left widens" direction —
  // the handle sits on the sidebar's left edge), Home/End snap to the
  // configured bounds.
  const RESIZE_STEP_PX = 20;
  const onResizeKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLDivElement>): void => {
      let next: number | null = null;
      if (e.key === "ArrowLeft") next = width + RESIZE_STEP_PX;
      else if (e.key === "ArrowRight") next = width - RESIZE_STEP_PX;
      else if (e.key === "Home") next = MIN_WIDTH_PX;
      else if (e.key === "End") next = MAX_WIDTH_PX;
      if (next === null) return;
      e.preventDefault();
      setWidth(Math.max(MIN_WIDTH_PX, Math.min(MAX_WIDTH_PX, next)));
    },
    [width]
  );

  useEffect(() => {
    function onMove(e: MouseEvent): void {
      if (!isResizingRef.current) return;
      const delta = resizeStartXRef.current - e.clientX; // dragging left widens
      const next = Math.max(MIN_WIDTH_PX, Math.min(MAX_WIDTH_PX, resizeStartWidthRef.current + delta));
      setWidth(next);
    }
    function onUp(): void {
      if (!isResizingRef.current) return;
      isResizingRef.current = false;
      document.body.style.userSelect = "";
      document.body.style.cursor = "";
    }
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, []);

  // -------------------------------------------------------------------------
  // Computed
  // -------------------------------------------------------------------------

  const effectiveWidth = useMemo<number>(
    () => (collapsed ? COLLAPSED_WIDTH_PX : width),
    [collapsed, width]
  );

  const asideStyle: CSSProperties = {
    width: `${effectiveWidth}px`,
    flex: `0 0 ${effectiveWidth}px`,
    // The inspector is nested *inside* the detail pane of a SplitView, so the
    // width it may claim is not the viewport's but whatever the split leaves
    // over — roughly half of it. `flex: 0 0 <w>px` alone is rigid: on a 1280px
    // viewport the 360px default ate the entire ~440px detail pane and left
    // the editor column ~69px wide, at which point the forms inside it
    // overflow their container to the left (they are `justify-content:
    // flex-end`) and end up underneath the SplitView divider, which then
    // swallows every click on them.
    //
    // Clamping to a share of the *available* width caps the sidebar without
    // touching the user's stored preference: the flex base size is clamped by
    // max-width, so the used width is min(storedWidth, 45% of the pane). Wide
    // viewports leave the pane well above 800px and therefore keep the full
    // preferred width — nothing changes there.
    //
    // H-03: the bare `45%` had no floor, so on a narrow pane the cap won
    // outright and the *expanded* inspector rendered far below its own
    // MIN_WIDTH_PX — measured live at 237px on a 1425px viewport (version
    // timestamps overlapping the row's overflow button) and 91px at 1100px,
    // where every panel degenerated to a one-character-wide sliver.
    //
    // Read outside-in: `max(MIN, 45%)` keeps the 45% cap wherever it is the
    // wider of the two and otherwise holds the panel at the width its
    // contents are designed for; the outer `min(…, 100%)` then stops that
    // floor from pushing the panel out past the pane it lives in, which
    // would only trade a clipped panel for a clipped page. On a pane too
    // narrow for even the minimum, the panel takes the whole pane and its
    // contents wrap (see VersionPanel.module.css) instead of overflowing.
    //
    // Narrow viewports still default to *collapsed* (see
    // DEFAULT_COLLAPSE_BREAKPOINT_PX / #419), so this only affects a user
    // who deliberately expanded the inspector — for whom an unreadable
    // sliver was never the more useful outcome.
    maxWidth: collapsed
      ? undefined
      : `min(max(${MIN_WIDTH_PX}px, ${MAX_WIDTH_SHARE_PERCENT}%), 100%)`,
  };

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  function renderCollapsedStrip(): JSX.Element {
    return (
      <div className={styles.collapsed} data-testid="artifact-inspector-collapsed">
        <button
          type="button"
          className={styles.collapsedButton}
          aria-label={t("sidebar.inspector.expand", "Open sidebar")}
          title={t("sidebar.inspector.expand", "Open sidebar")}
          onClick={(): void => setCollapsed(false)}
          data-testid="artifact-inspector-expand"
        >
          «
        </button>
        {/* UI-27 (systemaudit 2026-08-27): these three icons had no onClick
            at all — dead buttons, unreachable by mouse or keyboard alike.
            The panels below have no per-section tab/anchor concept (they are
            simply stacked — VersionPanel/DiffPanel/TracePanel render in a
            fixed order, see the expanded return below), so "jump to this
            section" cannot be wired without inventing that concept. Restoring
            the one behavior that *is* well-defined — open the sidebar, same
            as the "«" expand button — is the minimal, non-speculative fix;
            a real deep-link-to-section affordance is a UX decision for
            ui-ux-designer, not an a11y-only pass. */}
        <button
          type="button"
          className={styles.collapsedIconButton}
          aria-label={t("sidebar.version.title", "Version")}
          title={t("sidebar.version.title", "Version")}
          onClick={(): void => setCollapsed(false)}
        >
          ⏱
        </button>
        <button
          type="button"
          className={styles.collapsedIconButton}
          aria-label={t("sidebar.diff.title", "Diff")}
          title={t("sidebar.diff.title", "Diff")}
          onClick={(): void => setCollapsed(false)}
        >
          ≅
        </button>
        {!hideTraceLinks && (
          <button
            type="button"
            className={styles.collapsedIconButton}
            aria-label={t("sidebar.trace.title", "Trace Links")}
            title={t("sidebar.trace.title", "Trace Links")}
            onClick={(): void => setCollapsed(false)}
          >
            🔗
          </button>
        )}
      </div>
    );
  }

  function renderHeader(): JSX.Element {
    return (
      <header className={styles.header}>
        <span className={styles.headerTitle}>
          {t("sidebar.inspector.title", "Inspector")}
        </span>
        <div className={styles.headerActions}>
          <button
            type="button"
            className={styles.headerButton}
            aria-label={
              pinned
                ? t("sidebar.inspector.unpin", "Unpin sidebar")
                : t("sidebar.inspector.pin", "Pin sidebar")
            }
            aria-pressed={pinned}
            title={
              pinned
                ? t("sidebar.inspector.unpin", "Unpin sidebar")
                : t("sidebar.inspector.pin", "Pin sidebar")
            }
            onClick={(): void => setPinned((v) => !v)}
            data-testid="artifact-inspector-pin"
          >
            📌
          </button>
          <button
            type="button"
            className={styles.headerButton}
            aria-label={t("sidebar.inspector.collapse", "Collapse sidebar")}
            title={t("sidebar.inspector.collapse", "Collapse sidebar")}
            onClick={(): void => setCollapsed(true)}
            data-testid="artifact-inspector-collapse"
          >
            «
          </button>
        </div>
      </header>
    );
  }

  function renderResizeHandle(): JSX.Element {
    return (
      <div
        className={styles.resizeHandle}
        role="separator"
        aria-orientation="vertical"
        aria-label={t("sidebar.inspector.resize", "Resize inspector")}
        aria-valuenow={width}
        aria-valuemin={MIN_WIDTH_PX}
        aria-valuemax={MAX_WIDTH_PX}
        tabIndex={0}
        onMouseDown={onResizeMouseDown}
        onKeyDown={onResizeKeyDown}
        data-testid="artifact-inspector-resize"
      />
    );
  }

  return (
    <aside
      className={`${styles.aside} ${collapsed ? styles.asideCollapsed : ""}`}
      style={asideStyle}
      role="complementary"
      aria-label={t("sidebar.inspector.ariaLabel", { kind })}
      data-testid="artifact-inspector"
      data-artifact-kind={kind}
    >
      {collapsed ? (
        renderCollapsedStrip()
      ) : (
        <>
          {renderHeader()}
          <div className={styles.panels}>
            <VersionPanel
              kind={kind}
              artifactId={artifactId}
              currentVersion={currentVersion}
              onSwitch={handleSwitchVersion}
              onCompare={handleCompareVersions}
            />
            <DiffPanel
              kind={kind}
              artifactId={artifactId}
              leftVersion={diffLeft}
              rightVersion={diffRight}
            />
            {!hideTraceLinks && <TracePanel kind={kind} artifactId={artifactId} />}
          </div>
          {renderResizeHandle()}
        </>
      )}
    </aside>
  );
}
