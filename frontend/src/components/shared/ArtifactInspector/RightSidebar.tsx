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

const COLLAPSE_KEY = (kind: ArtifactKind): string => `reqflow_inspector_collapsed_${kind}`;
const PIN_KEY = (kind: ArtifactKind): string => `reqflow_inspector_pinned_${kind}`;
const WIDTH_KEY = (kind: ArtifactKind): string => `reqflow_inspector_width_${kind}`;

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

  const [collapsed, setCollapsed] = useState<boolean>(() => readBool(COLLAPSE_KEY(kind), false));
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
        <button
          type="button"
          className={styles.collapsedIconButton}
          aria-label={t("sidebar.version.title", "Version")}
          title={t("sidebar.version.title", "Version")}
        >
          ⏱
        </button>
        <button
          type="button"
          className={styles.collapsedIconButton}
          aria-label={t("sidebar.diff.title", "Diff")}
          title={t("sidebar.diff.title", "Diff")}
        >
          ≅
        </button>
        {!hideTraceLinks && (
          <button
            type="button"
            className={styles.collapsedIconButton}
            aria-label={t("sidebar.trace.title", "Trace Links")}
            title={t("sidebar.trace.title", "Trace Links")}
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
        onMouseDown={onResizeMouseDown}
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
