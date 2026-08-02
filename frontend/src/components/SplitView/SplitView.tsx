/**
 * REQ-L1-084: Generic SplitView Container Component
 *
 * Provides a reusable two-column layout (List | Divider | Detail) with:
 * - Resizable divider via drag-and-drop
 * - localStorage persistence of left panel width
 * - Responsive collapse on mobile (<--bp-md)
 * - Full type safety and accessibility
 *
 * Two contracts co-exist on this component (see UI_KONZEPT.md ch. 12.6):
 *
 * 1. Legacy contract — `leftPanel` / `rightPanel` / `initialLeftWidth` /
 *    `moduleType`. Drag-resizable divider, localStorage-persisted width.
 *    Used by all pre-existing call sites; unchanged behavior.
 *
 * 2. Concept contract — `list` / `detail` / `spine` / `ratio` / `minWidths`.
 *    Fixed ratio (no drag), collapses to full-width list when `detail` is
 *    `null`, carries an optional trace-spine slot between list and detail,
 *    and owns the three-breakpoint responsive model from ch. 6.3.
 *
 * The two contracts are mutually exclusive per instance: passing `list`
 * (even `undefined` vs. explicitly passed) selects the concept contract and
 * `leftPanel`/`rightPanel` are ignored. This keeps existing call sites
 * working unmodified while new call sites (Phase 2+) opt into the new
 * contract explicitly. The scroll model (`overscroll-behavior: contain`,
 * `scrollbar-gutter: stable`) applies to both contracts unconditionally —
 * it is a CSS fix, not an API change.
 *
 * Usage (legacy):
 * ```tsx
 * <SplitView
 *   leftPanel={<RequirementsList />}
 *   rightPanel={<RequirementForm />}
 *   onDividerMove={(widthPercent) => console.log(widthPercent)}
 * />
 * ```
 *
 * Usage (concept, ch. 12.6):
 * ```tsx
 * <SplitView
 *   list={<RequirementList />}
 *   detail={selected ? <RequirementDetail /> : null}
 *   spine={selected ? <TraceSpine artifact={selected} /> : null}
 *   ratio={[40, 60]}
 *   minWidths={[380, 520]}
 * />
 * ```
 *
 * leaf_id: COMP-RF-005-SplitView
 * interfaces: none (internal UI container)
 */

import React, { useState, useCallback, useEffect, useRef } from 'react';

/**
 * Props for the generic SplitView component.
 *
 * Two contracts, selected by presence of `list` (see module docstring).
 */
export interface SplitViewProps {
  // ---------------------------------------------------------------------
  // Legacy contract
  // ---------------------------------------------------------------------

  /** Left panel content (typically a list/tree component) */
  leftPanel?: React.ReactNode;

  /** Right panel content (typically a form/detail component) */
  rightPanel?: React.ReactNode;

  /** Minimum width for left panel in pixels (default: 200) */
  leftMinWidth?: number;

  /** Maximum width for left panel as percentage of total (default: 70) */
  leftMaxWidthPercent?: number;

  /** Initial left panel width in pixels (optional; uses localStorage or default if not provided) */
  initialLeftWidth?: number;

  /** Module identifier for localStorage key (e.g., "requirements", "architecture") */
  moduleType?: string;

  /** Custom CSS class for the divider */
  dividerClassName?: string;

  /** Callback when divider is moved; receives pixel width of left panel */
  onDividerMove?: (widthPixels: number) => void;

  /** Enable responsive collapse on mobile (<--bp-md) */
  responsiveMode?: boolean;

  /** Classname for root container */
  containerClassName?: string;

  // ---------------------------------------------------------------------
  // Concept contract (UI_KONZEPT.md ch. 12.6) — additive, opt-in
  // ---------------------------------------------------------------------

  /** List/tree content. Presence of this prop (even `undefined`-typed but
   *  explicitly passed) selects the concept contract over the legacy one. */
  list?: React.ReactNode;

  /** Detail content. `null`/`undefined` collapses the layout to a
   *  full-width `list` — no empty panel, no width constraint (ch. 6.2). */
  detail?: React.ReactNode | null;

  /** Optional trace-spine slot rendered between `list` and `detail`. Does
   *  not scroll with the detail content (own scroll container). */
  spine?: React.ReactNode | null;

  /** [list%, detail%] at desktop width. Default `[40, 60]` (ch. 6.1). */
  ratio?: [number, number];

  /** [listPx, detailPx] minimum widths. Default `[380, 520]`, matching
   *  `--list-min` / `--detail-min` in tokens.css. */
  minWidths?: [number, number];
}

const DEFAULT_RATIO: [number, number] = [40, 60];
const DEFAULT_MIN_WIDTHS: [number, number] = [380, 520];

/** Fallback pixel values if the CSS custom properties are unavailable
 * (e.g. non-browser test environments without a stylesheet). Mirrors
 * tokens.css `--bp-md` / `--bp-lg` (ch. 6.3) — the single source of truth
 * for these breakpoints remains tokens.css; this is only a safety net. */
const FALLBACK_BP_MD = 768;
const FALLBACK_BP_LG = 1024;

function readBreakpointToken(varName: string, fallback: number): number {
  if (typeof window === 'undefined' || typeof document === 'undefined') {
    return fallback;
  }
  const raw = window
    .getComputedStyle(document.documentElement)
    .getPropertyValue(varName);
  const parsed = parseInt(raw, 10);
  return Number.isNaN(parsed) ? fallback : parsed;
}

/** Scroll model shared by every scroll surface in SplitView (both
 * contracts): ch. 7.1 (`overscroll-behavior: contain`) and ch. 7.3
 * (`scrollbar-gutter: stable`). Applied inline so it is observable via
 * `getComputedStyle` regardless of whether CSS Modules are processed by
 * the current build/test pipeline. */
const SCROLL_SURFACE_STYLE: React.CSSProperties = {
  overflow: 'auto',
  overscrollBehavior: 'contain',
  scrollbarGutter: 'stable',
};

type ResponsiveZone = 'desktop' | 'narrow' | 'mobile';

/**
 * Generic SplitView Component — implements REQ-L1-084
 *
 * @param props - SplitViewProps configuration
 * @returns JSX.Element rendering the split-view container
 */
export const SplitView = React.forwardRef<HTMLDivElement, SplitViewProps>(
  (
    {
      leftPanel,
      rightPanel,
      leftMinWidth = 200,
      leftMaxWidthPercent = 70,
      initialLeftWidth,
      moduleType = 'default',
      dividerClassName,
      onDividerMove,
      responsiveMode = true,
      containerClassName,
      list,
      detail,
      spine,
      ratio = DEFAULT_RATIO,
      minWidths = DEFAULT_MIN_WIDTHS,
    },
    ref
  ) => {
    // The concept contract is selected by the presence of `list`. This
    // keeps every legacy call site (`leftPanel`/`rightPanel`) on the old
    // render path untouched.
    const isConceptContract = list !== undefined;

    if (isConceptContract) {
      return (
        <ConceptSplitView
          ref={ref}
          list={list}
          detail={detail ?? null}
          spine={spine ?? null}
          ratio={ratio}
          minWidths={minWidths}
          containerClassName={containerClassName}
        />
      );
    }

    return (
      <LegacySplitView
        ref={ref}
        leftPanel={leftPanel}
        rightPanel={rightPanel}
        leftMinWidth={leftMinWidth}
        leftMaxWidthPercent={leftMaxWidthPercent}
        initialLeftWidth={initialLeftWidth}
        moduleType={moduleType}
        dividerClassName={dividerClassName}
        onDividerMove={onDividerMove}
        responsiveMode={responsiveMode}
        containerClassName={containerClassName}
      />
    );
  }
);

SplitView.displayName = 'SplitView';

// ===========================================================================
// Legacy contract — `leftPanel` / `rightPanel`, unchanged behavior plus the
// shared scroll model (ch. 7) and the tokens.css-driven breakpoint (ch. 6.3).
// ===========================================================================

interface LegacySplitViewProps {
  leftPanel: React.ReactNode;
  rightPanel: React.ReactNode;
  leftMinWidth: number;
  leftMaxWidthPercent: number;
  initialLeftWidth?: number;
  moduleType: string;
  dividerClassName?: string;
  onDividerMove?: (widthPixels: number) => void;
  responsiveMode: boolean;
  containerClassName?: string;
}

const LegacySplitView = React.forwardRef<HTMLDivElement, LegacySplitViewProps>(
  (
    {
      leftPanel,
      rightPanel,
      leftMinWidth,
      leftMaxWidthPercent,
      initialLeftWidth,
      moduleType,
      dividerClassName,
      onDividerMove,
      responsiveMode,
      containerClassName,
    },
    ref
  ) => {
    // -----------------------------------------------------------------------
    // State: left panel width (pixels), drag state
    // -----------------------------------------------------------------------

    const storageKey = `reqflow_splitview_${moduleType}`;

    const getInitialWidth = useCallback((): number => {
      // 1. Explicit initialLeftWidth prop
      if (initialLeftWidth !== undefined) {
        return initialLeftWidth;
      }

      // 2. localStorage (persisted from previous session)
      const stored =
        typeof window !== "undefined" && window.localStorage
          ? window.localStorage.getItem(storageKey)
          : null;
      if (stored) {
        const parsed = parseInt(stored, 10);
        if (!isNaN(parsed) && parsed >= leftMinWidth) {
          return parsed;
        }
      }

      // 3. Default: 40% of viewport
      return Math.max(leftMinWidth, window.innerWidth * 0.4);
    }, [initialLeftWidth, moduleType, storageKey, leftMinWidth]);

    const [leftPanelWidth, setLeftPanelWidth] = useState(getInitialWidth());
    const [isResponsiveCollapsed, setIsResponsiveCollapsed] = useState(
      responsiveMode && window.innerWidth < readBreakpointToken('--bp-md', FALLBACK_BP_MD)
    );

    // Drag state
    const isDraggingRef = useRef(false);
    const dragStartXRef = useRef(0);
    const dragStartWidthRef = useRef(0);
    const dividerRef = useRef<HTMLDivElement>(null);

    // -----------------------------------------------------------------------
    // Handlers: divider mouse events, persistence
    // -----------------------------------------------------------------------

    const handleDividerMouseDown = useCallback(
      (e: React.MouseEvent<HTMLDivElement>): void => {
        isDraggingRef.current = true;
        dragStartXRef.current = e.clientX;
        dragStartWidthRef.current = leftPanelWidth;

        // Visual feedback
        document.body.style.userSelect = 'none';
        document.body.style.cursor = 'col-resize';

        if (dividerRef.current) {
          dividerRef.current.classList.add('dragging');
        }

        e.preventDefault();
      },
      [leftPanelWidth]
    );

    const persistWidth = useCallback((width: number): void => {
      localStorage.setItem(storageKey, String(width));
      onDividerMove?.(width);
    }, [storageKey, onDividerMove]);

    // -----------------------------------------------------------------------
    // Global mouse events: move and up
    // -----------------------------------------------------------------------

    useEffect(() => {
      const handleMouseMove = (e: MouseEvent): void => {
        if (!isDraggingRef.current) return;

        const delta = e.clientX - dragStartXRef.current;
        const newWidth = Math.max(leftMinWidth, dragStartWidthRef.current + delta);

        // Respect max-width constraint (percentage-based)
        const containerWidth = dividerRef.current?.parentElement?.clientWidth ?? window.innerWidth;
        const maxWidth = (containerWidth * leftMaxWidthPercent) / 100;
        const constrainedWidth = Math.min(newWidth, maxWidth);

        setLeftPanelWidth(constrainedWidth);
      };

      const handleMouseUp = (): void => {
        if (!isDraggingRef.current) return;

        isDraggingRef.current = false;
        document.body.style.userSelect = '';
        document.body.style.cursor = '';

        if (dividerRef.current) {
          dividerRef.current.classList.remove('dragging');
        }

        // Persist the final width
        persistWidth(leftPanelWidth);
      };

      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);

      return () => {
        document.removeEventListener('mousemove', handleMouseMove);
        document.removeEventListener('mouseup', handleMouseUp);
      };
    }, [leftPanelWidth, leftMinWidth, leftMaxWidthPercent, persistWidth]);

    // -----------------------------------------------------------------------
    // Responsive behavior: listen for window resize
    // -----------------------------------------------------------------------

    useEffect(() => {
      if (!responsiveMode) return;

      const handleResize = (): void => {
        const bpMd = readBreakpointToken('--bp-md', FALLBACK_BP_MD);
        setIsResponsiveCollapsed(window.innerWidth < bpMd);
      };

      window.addEventListener('resize', handleResize);
      return () => window.removeEventListener('resize', handleResize);
    }, [responsiveMode]);

    // -----------------------------------------------------------------------
    // Responsive render: stacked layout or toggle tabs on mobile
    // -----------------------------------------------------------------------

    if (isResponsiveCollapsed) {
      return (
        <div
          ref={ref}
          className={containerClassName}
          style={{
            display: 'flex',
            flexDirection: 'column',
            height: '100%',
            overflow: 'hidden',
            background: 'var(--color-surface)',
          }}
        >
          {/* Mobile: tab-like toggle between left and right panels */}
          <div
            style={{
              display: 'flex',
              gap: '1px',
              borderBottom: '1px solid var(--color-border)',
              background: 'var(--color-surface)',
              padding: 0,
            }}
          >
            <button
              onClick={() => setIsResponsiveCollapsed(true)}
              style={{
                flex: 1,
                padding: 'var(--space-3)',
                border: 'none',
                background: 'transparent',
                cursor: 'pointer',
                fontSize: 'var(--font-size-sm)',
                fontWeight: 600,
                color: 'var(--color-text)',
                borderBottom: '2px solid var(--color-primary)',
              }}
            >
              List
            </button>
            <button
              onClick={() => setIsResponsiveCollapsed(false)}
              style={{
                flex: 1,
                padding: 'var(--space-3)',
                border: 'none',
                background: 'transparent',
                cursor: 'pointer',
                fontSize: 'var(--font-size-sm)',
                fontWeight: 600,
                color: 'var(--color-text-muted)',
              }}
            >
              Detail
            </button>
          </div>

          {/* Show only left panel on mobile (collapsed state) */}
          <div
            style={{
              ...SCROLL_SURFACE_STYLE,
              flex: 1,
              padding: 'var(--space-4)',
            }}
          >
            {leftPanel}
          </div>
        </div>
      );
    }

    // -----------------------------------------------------------------------
    // Desktop render: side-by-side with resizable divider
    // -----------------------------------------------------------------------

    return (
      <div
        ref={ref}
        className={containerClassName}
        style={{
          display: 'flex',
          height: '100%',
          overflow: 'hidden',
          background: 'var(--color-surface)',
          fontFamily: 'var(--font-sans)',
          color: 'var(--color-text)',
        }}
      >
        {/* Left Panel */}
        <div
          style={{
            ...SCROLL_SURFACE_STYLE,
            flex: `0 0 ${leftPanelWidth}px`,
            minWidth: `${leftMinWidth}px`,
            maxWidth: `${leftMaxWidthPercent}%`,
            overflowX: 'hidden',
            borderRight: '1px solid var(--color-border)',
            background: 'var(--color-surface)',
            padding: 'var(--space-4)',
          }}
        >
          {leftPanel}
        </div>

        {/* Divider — REQ-007: 12px hitbox, 2px visual center line via gradient */}
        <div
          ref={dividerRef}
          data-testid="splitview-divider"
          className={`splitview-divider ${dividerClassName || ''}`}
          onMouseDown={handleDividerMouseDown}
          style={{
            flex: '0 0 12px',
            background: 'linear-gradient(90deg, transparent 5px, var(--color-border) 5px, var(--color-border) 7px, transparent 7px)',
            cursor: 'col-resize',
            transition: isDraggingRef.current ? 'none' : 'background 0.2s ease',
            userSelect: 'none',
          }}
          onMouseEnter={(e) => {
            if (!isDraggingRef.current) {
              e.currentTarget.style.background = 'linear-gradient(90deg, transparent 4px, var(--color-primary) 4px, var(--color-primary) 8px, transparent 8px)';
            }
          }}
          onMouseLeave={(e) => {
            if (!isDraggingRef.current) {
              e.currentTarget.style.background = 'linear-gradient(90deg, transparent 5px, var(--color-border) 5px, var(--color-border) 7px, transparent 7px)';
            }
          }}
        />

        {/* Right Panel */}
        <div
          style={{
            ...SCROLL_SURFACE_STYLE,
            flex: '1 1 auto',
            overflowX: 'hidden',
            background: 'var(--color-surface)',
            padding: 'var(--space-4)',
          }}
        >
          {rightPanel}
        </div>
      </div>
    );
  }
);

LegacySplitView.displayName = 'LegacySplitView';

// ===========================================================================
// Concept contract (UI_KONZEPT.md ch. 12.6) — `list` / `detail` / `spine` /
// `ratio` / `minWidths`. Owns the responsive model from ch. 6.3:
//
//   >= --bp-lg (desktop) : list/detail side by side at `ratio`
//   <  --bp-lg, >= --bp-md (narrow) : list/detail side by side at 45:55,
//        spine wanders under the artifact header (rendered as a horizontal
//        bar above the row instead of a vertical column between the panes)
//   <  --bp-md (mobile) : single column; an open `detail` replaces `list`
//        entirely (list stays mounted but hidden — no scroll-position loss)
// ===========================================================================

interface ConceptSplitViewProps {
  list: React.ReactNode;
  detail: React.ReactNode | null;
  spine: React.ReactNode | null;
  ratio: [number, number];
  minWidths: [number, number];
  containerClassName?: string;
}

/** Narrow-viewport ratio fixed by ch. 6.3 ("< 1024px: Verhältnis 45 : 55"). */
const NARROW_RATIO: [number, number] = [45, 55];

function computeZone(bpMd: number, bpLg: number): ResponsiveZone {
  if (typeof window === 'undefined') return 'desktop';
  if (window.innerWidth < bpMd) return 'mobile';
  if (window.innerWidth < bpLg) return 'narrow';
  return 'desktop';
}

const ConceptSplitView = React.forwardRef<HTMLDivElement, ConceptSplitViewProps>(
  ({ list, detail, spine, ratio, minWidths, containerClassName }, ref) => {
    const hasDetail = detail !== null && detail !== undefined;

    const [zone, setZone] = useState<ResponsiveZone>(() =>
      computeZone(
        readBreakpointToken('--bp-md', FALLBACK_BP_MD),
        readBreakpointToken('--bp-lg', FALLBACK_BP_LG)
      )
    );

    useEffect(() => {
      const handleResize = (): void => {
        setZone(
          computeZone(
            readBreakpointToken('--bp-md', FALLBACK_BP_MD),
            readBreakpointToken('--bp-lg', FALLBACK_BP_LG)
          )
        );
      };
      window.addEventListener('resize', handleResize);
      return () => window.removeEventListener('resize', handleResize);
    }, []);

    const effectiveRatio = zone === 'narrow' ? NARROW_RATIO : ratio;

    // ---------------------------------------------------------------------
    // Position memory (ch. 7.3): the list container stays mounted at all
    // times (hidden via `display: none` on mobile instead of unmounted),
    // so its native scrollTop survives detail open/close for free. On top
    // of that, when the user navigates back to the list (detail -> null),
    // scroll the currently-selected row into view — list items follow the
    // `aria-selected="true"` convention already used across the app's list
    // primitives (e.g. WorkspaceTree).
    // ---------------------------------------------------------------------

    const listContainerRef = useRef<HTMLDivElement>(null);
    const wasDetailOpenRef = useRef(hasDetail);

    useEffect(() => {
      if (wasDetailOpenRef.current && !hasDetail) {
        const selected = listContainerRef.current?.querySelector(
          '[aria-selected="true"]'
        );
        selected?.scrollIntoView({ block: 'nearest' });
      }
      wasDetailOpenRef.current = hasDetail;
    }, [hasDetail]);

    const isMobileReplace = zone === 'mobile' && hasDetail;

    const listStyle: React.CSSProperties = hasDetail
      ? {
          ...SCROLL_SURFACE_STYLE,
          display: isMobileReplace ? 'none' : 'block',
          flex: zone === 'mobile' ? '1 1 100%' : `0 0 ${effectiveRatio[0]}%`,
          minWidth: zone === 'mobile' ? undefined : `${minWidths[0]}px`,
          borderRight: zone === 'mobile' ? 'none' : '1px solid var(--color-border)',
          background: 'var(--color-surface)',
          padding: 'var(--space-4)',
        }
      : {
          // Ch. 6.2: without a selected detail, the list runs full width —
          // no leftover panel, no width constraint.
          ...SCROLL_SURFACE_STYLE,
          flex: '1 1 100%',
          maxWidth: '100%',
          background: 'var(--color-surface)',
          padding: 'var(--space-4)',
        };

    const detailStyle: React.CSSProperties = {
      ...SCROLL_SURFACE_STYLE,
      flex: zone === 'mobile' ? '1 1 100%' : `1 1 ${effectiveRatio[1]}%`,
      minWidth: zone === 'mobile' ? undefined : `${minWidths[1]}px`,
      background: 'var(--color-surface)',
      padding: 'var(--space-4)',
    };

    // Spine sits between list and detail as its own scroll-independent
    // flex sibling — never nested inside the detail scroll container, so
    // scrolling the detail content cannot move it. At the narrow (--bp-lg)
    // breakpoint it wanders horizontal, above the row, per ch. 6.3.
    const spineStyle: React.CSSProperties =
      zone === 'narrow' || zone === 'mobile'
        ? {
            flex: '0 0 auto',
            width: '100%',
            overflow: 'visible',
            borderBottom: '1px solid var(--color-border)',
          }
        : {
            flex: '0 0 auto',
            overflow: 'visible',
            borderRight: '1px solid var(--color-border)',
          };

    const spineNode =
      hasDetail && spine ? (
        <div data-testid="splitview-spine" style={spineStyle}>
          {spine}
        </div>
      ) : null;

    // The narrow/mobile zones render the spine as a horizontal bar above
    // the list/detail row (ch. 6.3), so the root stacks into a column;
    // desktop keeps the spine as a vertical slot inside the row.
    const spineIsHorizontal =
      (zone === 'narrow' || zone === 'mobile') && !!spineNode && !isMobileReplace;

    const rootStyle: React.CSSProperties = {
      display: 'flex',
      flexDirection: spineIsHorizontal ? 'column' : 'row',
      height: '100%',
      overflow: 'hidden',
      background: 'var(--color-surface)',
      fontFamily: 'var(--font-sans)',
      color: 'var(--color-text)',
    };

    const rowStyle: React.CSSProperties = {
      display: 'flex',
      flex: '1 1 auto',
      overflow: 'hidden',
    };

    return (
      <div ref={ref} className={containerClassName} style={rootStyle}>
        {spineIsHorizontal ? (
          <>
            {spineNode}
            <div style={rowStyle}>
              <div ref={listContainerRef} data-testid="splitview-list" style={listStyle}>
                {list}
              </div>
              {hasDetail && (
                <div data-testid="splitview-detail" style={detailStyle}>
                  {detail}
                </div>
              )}
            </div>
          </>
        ) : (
          <>
            <div ref={listContainerRef} data-testid="splitview-list" style={listStyle}>
              {list}
            </div>
            {!isMobileReplace && spineNode}
            {hasDetail && (
              <div data-testid="splitview-detail" style={detailStyle}>
                {detail}
              </div>
            )}
          </>
        )}
      </div>
    );
  }
);

ConceptSplitView.displayName = 'ConceptSplitView';
