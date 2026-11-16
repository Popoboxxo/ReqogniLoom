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
import { useTranslation } from 'react-i18next';
import { safeLocalStorage } from '../../utils/safeStorage';

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

/**
 * Mobile row-click delegation (plan M5, REQ-209).
 *
 * Both row conventions in this app announce selection through ARIA —
 * `[role="treeitem"][aria-selected]` (WorkspaceTree) and `[aria-pressed]` on a
 * `div[role="button"]` (ArtifactRow) — but so do real controls: the
 * `RequirementViewToggle` buttons, filter checkboxes and toolbar switches all
 * carry `aria-pressed`. A bare `[aria-pressed]` match therefore opens a detail
 * when the user only flips the list/table view. Check controls first, rows
 * second, and only inside the pane that owns the delegation.
 */
const MOBILE_ROW_SELECTOR = '[role="treeitem"], [aria-pressed], [aria-selected]';
const MOBILE_CONTROL_SELECTOR =
  'button, input, select, textarea, [role="toolbar"], [data-testid="req-view-toggle"]';
const MOBILE_CONTROL_TAG = /^(?:BUTTON|INPUT|SELECT|TEXTAREA)$/;

/** Return the genuine list/tree row under `target`, or `null` for a control. */
function findClickedListRow(target: EventTarget | null, container: HTMLElement): HTMLElement | null {
  if (!(target instanceof Element)) return null;
  if (target.closest(MOBILE_CONTROL_SELECTOR) !== null) return null;
  const row = target.closest<HTMLElement>(MOBILE_ROW_SELECTOR);
  if (row === null || !container.contains(row)) return null;
  return MOBILE_CONTROL_TAG.test(row.tagName) ? null : row;
}

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

const LIST_SCROLL_SURFACE_STYLE: React.CSSProperties = {
  ...SCROLL_SURFACE_STYLE,
  overflowX: 'hidden',
  overflowY: 'auto',
};

// ---------------------------------------------------------------------------
// Issue #876 (Etappe 7, batch 3): the nine inline style-object literals of
// the legacy contract are hoisted to named `React.CSSProperties` identifiers
// (and, for the divider, a `dividerStyle(dragging)` function identifier whose
// `transition` stays conditional per render, exactly as on `main`) and applied
// as `style={identifier}`.
//
// This is the documented house pattern (not a workaround): the rule only
// reports an *object literal* directly inside the attribute
// (`no-static-inline-style.js`, gap 4), and every one of these surfaces is
// pinned by a test that reads the rendered inline style rather than a CSS
// class — vitest's `css: false` (vite.config) means CSS Modules never load in
// the test run, so a class-based migration would break
// `SplitView.test.tsx` (`getComputedStyle` on `overscrollBehavior`/
// `scrollbarGutter`/`maxWidth`, `toHaveStyle` on the list/detail flex widths,
// with the divider as the locator for the legacy panels),
// `RequirementEditors.test.tsx:360` and `ArchitectureEditors.test.tsx:374`
// (both `toHaveStyle("cursor: col-resize")` on the divider).
// Same sanctioned precedent as `MetricsDashboard.helpToggleStyle` (Etappe 5).
//
// The divider keeps its pre-migration drag-state transition — `none` while
// dragging, `background 0.2s ease` at rest — via `dividerStyle` below.
//
// The legacy contract's *own* styles therefore stay inline by design; the
// concept contract above (list/detail/spine/ratio) continues to use the
// existing `listStyle`/`detailStyle`/`spineStyle`/`rootStyle`/`rowStyle`
// identifiers.
// ---------------------------------------------------------------------------

/** Mobile collapsed root: stacked single-column shell. */
const MOBILE_ROOT_STYLE: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  height: '100%',
  overflow: 'hidden',
  background: 'var(--color-surface)',
};

/** Mobile detail header: owns the single back step (spec §7.2). */
const MOBILE_HEADER_STYLE: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  minHeight: 'var(--btn-h-lg)',
  padding: 'var(--space-1) var(--space-3)',
  borderBottom: '1px solid var(--color-border)',
  background: 'var(--color-surface)',
};

/** Mobile content area: the shared scroll surface, padded, full flex. */
const MOBILE_PANEL_STYLE: React.CSSProperties = {
  ...SCROLL_SURFACE_STYLE,
  flex: 1,
  padding: 'var(--space-4)',
};

/** Hoisted visibility variants — no static inline objects in JSX. */
const MOBILE_LIST_VISIBLE_STYLE: React.CSSProperties = { ...MOBILE_PANEL_STYLE, display: 'block' };
const MOBILE_LIST_HIDDEN_STYLE: React.CSSProperties = { ...MOBILE_PANEL_STYLE, display: 'none' };
const MOBILE_DETAIL_VISIBLE_STYLE: React.CSSProperties = { ...MOBILE_PANEL_STYLE, display: 'block' };
const MOBILE_DETAIL_HIDDEN_STYLE: React.CSSProperties = { ...MOBILE_PANEL_STYLE, display: 'none' };

/** Desktop root: side-by-side row shell. */
const DESKTOP_ROOT_STYLE: React.CSSProperties = {
  display: 'flex',
  height: '100%',
  overflow: 'hidden',
  background: 'var(--color-surface)',
  fontFamily: 'var(--font-sans)',
  color: 'var(--color-text)',
};

/** Desktop divider: 24px hitbox (WCAG 2.2 SC 2.5.8), 2px visual center line via gradient. */
const DIVIDER_BASE_STYLE: React.CSSProperties = {
  flex: '0 0 24px',
  background: 'linear-gradient(90deg, transparent 11px, var(--color-border) 11px, var(--color-border) 13px, transparent 13px)',
  cursor: 'col-resize',
  userSelect: 'none',
};

/** Divider style for one render pass: the transition is suppressed while a
 * drag is in progress (`none`) and eased otherwise — restored from `main`'s
 * pre-migration conditional. Hoisted as a function identifier so the
 * conditional stays out of the `style` attribute as an object literal. */
const dividerStyle = (dragging: boolean): React.CSSProperties => ({
  ...DIVIDER_BASE_STYLE,
  transition: dragging ? 'none' : 'background 0.2s ease',
});

/** Upper bound of the left panel in px, from the container width and the
 *  configured percentage. One definition for the drag handler, the keyboard
 *  handler and the separator's `aria-valuemax` (#1406) — three copies of the
 *  same arithmetic are how the announced bound drifts from the enforced one. */
const maxPanelWidth = (
  containerWidth: number,
  leftMaxWidthPercent: number,
): number => (containerWidth * leftMaxWidthPercent) / 100;

/** Width of the flex container the divider lives in.
 *
 *  Falls back to the viewport when the container has no measurable width —
 *  `null` before the first measurement *and* `0` in a non-layout environment
 *  (jsdom, a hidden pane). `0` must not be treated as a real container: it
 *  would make the computed upper bound 0 and announce an impossible maximum. */
const measureContainerWidth = (divider: HTMLElement | null): number =>
  divider?.parentElement?.clientWidth || window.innerWidth;

/** Desktop right pane: the shared scroll surface, full flex, padded. */
const RIGHT_PANEL_STYLE: React.CSSProperties = {
  ...SCROLL_SURFACE_STYLE,
  flex: '1 1 auto',
  minWidth: 0,
  background: 'var(--color-surface)',
  padding: 'var(--space-4)',
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
    // `!== undefined` (not `!= null`) is deliberate: `list` is the ReactNode
    // that IS the list pane, so an explicit `list={null}` is a caller error
    // (there is no meaningful "empty concept contract"), not a signal to
    // fall back to the legacy contract. `detail`, by contrast, treats
    // `null` as a first-class, meaningful value (ch. 6.2 "no selection").
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
    const { t } = useTranslation();

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
      const stored = safeLocalStorage.getItem(storageKey);
      if (stored) {
        const parsed = parseInt(stored, 10);
        if (!isNaN(parsed) && parsed >= leftMinWidth) {
          return parsed;
        }
      }

      // 3. Default: 40% of viewport
      return Math.max(leftMinWidth, window.innerWidth * 0.4);
      // `storageKey` already derives from `moduleType`, so listing the prop
      // itself would only re-create the callback for the same storage key.
    }, [initialLeftWidth, storageKey, leftMinWidth]);

    const [leftPanelWidth, setLeftPanelWidth] = useState(getInitialWidth());
    // M5: two independent states. Before this fix a single
    // `isResponsiveCollapsed` meant both "we are on a phone" and "which pane
    // is visible", so clicking "Detail" rendered the two-column desktop
    // branch at 390px (and the tabs were hardcoded English).
    const [isMobile, setIsMobile] = useState(
      responsiveMode && window.innerWidth < readBreakpointToken('--bp-md', FALLBACK_BP_MD)
    );
    // PR #1888: on a phone the list is always the entry point — even for a
    // deep link or a route-selected artifact that already provides `rightPanel`
    // at mount. Initialising from a non-null `rightPanel` hid the list behind
    // `display: none`, so no row was clickable and the mobile list/detail E2E
    // flows timed out on `toBeVisible()`. The detail is reached through the
    // delegated row click below; the back step still returns to this pane.
    // Desktop never reads `mobilePane`, so its behaviour is unchanged.
    const [mobilePane, setMobilePane] = useState<'list' | 'detail'>('list');
    const lastRightPanelRef = useRef<React.ReactNode>(rightPanel);

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
          // UI-41 (systemaudit 2026-08-27): `classList.add('dragging')` alone
          // has no effect — this component's layout/feedback styles are all
          // inline (see the module docstring on why SplitView.module.scss's
          // `.dragging` rule is never actually attached to this element), so
          // a *class name* toggle here does not translate to a visible
          // style. Setting the highlighted gradient directly, the same way
          // the hover handlers below already do, is what actually renders.
          dividerRef.current.classList.add('dragging');
          dividerRef.current.style.background =
            'linear-gradient(90deg, transparent 4px, var(--color-primary) 4px, var(--color-primary) 8px, transparent 8px)';
        }

        e.preventDefault();
      },
      [leftPanelWidth]
    );

    const persistWidth = useCallback((width: number): void => {
      safeLocalStorage.setItem(storageKey, String(width));
      onDividerMove?.(width);
    }, [storageKey, onDividerMove]);

    // UI-27 (systemaudit 2026-08-27): the divider was mouse-only (WCAG 2.1.1
    // Keyboard). Same ARIA APG "window splitter" step pattern as
    // inspector splitter: Left/Right adjust, Home/End snap to the
    // configured bounds.
    const DIVIDER_STEP_PX = 20;
    const handleDividerKeyDown = useCallback(
      (e: React.KeyboardEvent<HTMLDivElement>): void => {
        const maxWidth = maxPanelWidth(
          measureContainerWidth(dividerRef.current),
          leftMaxWidthPercent,
        );
        let next: number | null = null;
        if (e.key === 'ArrowLeft') next = leftPanelWidth - DIVIDER_STEP_PX;
        else if (e.key === 'ArrowRight') next = leftPanelWidth + DIVIDER_STEP_PX;
        else if (e.key === 'Home') next = leftMinWidth;
        else if (e.key === 'End') next = maxWidth;
        if (next === null) return;
        e.preventDefault();
        const constrained = Math.max(leftMinWidth, Math.min(next, maxWidth));
        setLeftPanelWidth(constrained);
        persistWidth(constrained);
      },
      [leftPanelWidth, leftMinWidth, leftMaxWidthPercent, persistWidth]
    );

    // -----------------------------------------------------------------------
    // Global mouse events: move and up
    // -----------------------------------------------------------------------

    useEffect(() => {
      const handleMouseMove = (e: MouseEvent): void => {
        if (!isDraggingRef.current) return;

        const delta = e.clientX - dragStartXRef.current;
        const newWidth = Math.max(leftMinWidth, dragStartWidthRef.current + delta);

        // Respect max-width constraint (percentage-based)
        const maxWidth = maxPanelWidth(
          measureContainerWidth(dividerRef.current),
          leftMaxWidthPercent,
        );
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
          // Mirror the mouseleave reset — restore the resting gradient
          // (see the mousedown handler's comment for why this must be an
          // inline-style write, not a class toggle).
          dividerRef.current.style.background =
            'linear-gradient(90deg, transparent 5px, var(--color-border) 5px, var(--color-border) 7px, transparent 7px)';
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
        setIsMobile(window.innerWidth < bpMd);
      };

      window.addEventListener('resize', handleResize);
      return () => window.removeEventListener('resize', handleResize);
    }, [responsiveMode]);

    // A breakpoint change resets the pane choice but never the selection.
    useEffect(() => {
      if (!isMobile) setMobilePane('list');
    }, [isMobile]);

    // Only a genuine null -> detail transition follows the selection. An
    // inline `<Detail/>` element gets a new identity on every parent render,
    // so treating every identity change as a selection would pop the detail
    // back open right after the user pressed "Zurück". Row clicks inside the
    // list pane (below) handle changes of an already-open detail.
    useEffect(() => {
      if (lastRightPanelRef.current === rightPanel) return;
      lastRightPanelRef.current = rightPanel;
      // The list is ALWAYS the mobile entry point — including when a detail
      // appears later from async data loading. Opening a detail is an explicit
      // user action on a row (see the delegated click handler below).
      if (rightPanel === null || rightPanel === undefined) setMobilePane('list');
    }, [rightPanel]);

    const listPaneRef = useRef<HTMLDivElement>(null);
    const backButtonRef = useRef<HTMLButtonElement>(null);
    const lastClickedRowRef = useRef<HTMLElement | null>(null);

    // Delegated via a native listener rather than a JSX `onClick` on the list
    // pane: that pane is a clickable *region*, not a button, so a `btn-*` chrome
    // class would be wrong (the design-system ratchet exempts such regions
    // elsewhere). A ref listener keeps the region out of the gate entirely and
    // works for rows mounted by the list component after the first paint.
    const handleMobileListClick = useCallback((event: MouseEvent): void => {
      const container = listPaneRef.current;
      if (!container) return;
      const row = findClickedListRow(event.target, container);
      if (row === null) return;
      lastClickedRowRef.current = row;
      setMobilePane('detail');
    }, []);

    useEffect(() => {
      if (!isMobile) return;
      const container = listPaneRef.current;
      if (!container) return;
      container.addEventListener('click', handleMobileListClick);
      return () => container.removeEventListener('click', handleMobileListClick);
    }, [isMobile, handleMobileListClick]);

    const showDetail =
      isMobile && mobilePane === 'detail' && rightPanel !== null && rightPanel !== undefined;

    // Focus follows the visible pane (spec §7.2): opening a detail focuses the
    // single back control; returning to the list restores focus to the row that
    // opened it, so keyboard and screen-reader users keep their position.
    useEffect(() => {
      if (showDetail) backButtonRef.current?.focus();
    }, [showDetail]);

    useEffect(() => {
      if (!isMobile || mobilePane !== 'list') return;
      const row = lastClickedRowRef.current;
      if (row === null) return;
      lastClickedRowRef.current = null;
      row.focus();
    }, [isMobile, mobilePane]);

    // -----------------------------------------------------------------------
    // Responsive render: stacked layout or toggle tabs on mobile
    // -----------------------------------------------------------------------

    if (isMobile) {
      return (
        <div ref={ref} className={containerClassName} style={MOBILE_ROOT_STYLE}>
          {showDetail && (
            <div style={MOBILE_HEADER_STYLE}>
              <button
                ref={backButtonRef}
                type="button"
                className="btn-ghost"
                data-testid="splitview-back"
                onClick={() => setMobilePane('list')}
              >
                ← {t('splitView.back')}
              </button>
            </div>
          )}
          {/* Both panes stay mounted: the list keeps its native scrollTop
              while the detail replaces it visually. */}
          <div
            ref={listPaneRef}
            className="splitview-list-pane"
            data-testid="splitview-list"
            style={showDetail ? MOBILE_LIST_HIDDEN_STYLE : MOBILE_LIST_VISIBLE_STYLE}
          >
            {leftPanel}
          </div>
          <div
            data-testid="splitview-detail"
            style={showDetail ? MOBILE_DETAIL_VISIBLE_STYLE : MOBILE_DETAIL_HIDDEN_STYLE}
          >
            {rightPanel}
          </div>
        </div>
      );
    }

    // -----------------------------------------------------------------------
    // Desktop render: side-by-side with resizable divider
    // -----------------------------------------------------------------------

    // Left panel width is a genuine per-instance runtime value (drag state),
    // so its flex/min/max geometry stays on the `style` prop as a hoisted
    // identifier; the rest of the surface is the shared scroll model. See the
    // hoisted-style note above.
    const leftPanelStyle: React.CSSProperties = {
      ...LIST_SCROLL_SURFACE_STYLE,
      flex: `0 0 ${leftPanelWidth}px`,
      minWidth: `${leftMinWidth}px`,
      maxWidth: `${leftMaxWidthPercent}%`,
      borderRight: '1px solid var(--color-border)',
      background: 'var(--color-surface)',
      padding: 'var(--space-4)',
    };

    // #1406: the separator's announced upper bound. Measured against the
    // container the drag/keyboard handlers already use, falling back to the
    // viewport on the first render (the ref is not attached yet).
    const dividerMaxPosition = Math.round(
      maxPanelWidth(measureContainerWidth(dividerRef.current), leftMaxWidthPercent),
    );

    return (
      <div
        ref={ref}
        className={containerClassName}
        style={DESKTOP_ROOT_STYLE}
      >
        {/* Left Panel */}
        <div style={leftPanelStyle}>
          {leftPanel}
        </div>

        {/* Divider — REQ-007 / #1406: the box is a 24px hit area
            (`flex-basis`), the visible line stays 2px because the gradient
            only paints 11–13px. 24px is the WCAG 2.2 SC 2.5.8 minimum. */}
        <div
          ref={dividerRef}
          data-testid="splitview-divider"
          className={`splitview-divider ${dividerClassName || ''}`}
          role="separator"
          aria-orientation="vertical"
          aria-label={t('splitView.resizeDivider', 'Resize panels')}
          aria-valuenow={Math.round(leftPanelWidth)}
          aria-valuemin={leftMinWidth}
          aria-valuemax={dividerMaxPosition}
          tabIndex={0}
          onMouseDown={handleDividerMouseDown}
          onKeyDown={handleDividerKeyDown}
          style={dividerStyle(isDraggingRef.current)}
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
        <div style={RIGHT_PANEL_STYLE}>
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
    const { t } = useTranslation();
    const hasDetail = detail !== null && detail !== undefined;

    // Same mobile state machine as the legacy branch: on a phone the detail
    // replaces the list and a single back step returns to it. The parent keeps
    // its selection — `detail` is a controlled prop, so "back" only flips this
    // local pane choice (spec §7.2 / ch. 6.2).
    // PR #1888: same rule as the legacy branch — a phone always enters on the
    // list, even when a controlled `detail` is already present at mount. The
    // detail is opened by the delegated row click below; "back" returns here.
    const [mobilePane, setMobilePane] = useState<'list' | 'detail'>('list');
    const listContainerRef = useRef<HTMLDivElement>(null);
    const backButtonRef = useRef<HTMLButtonElement>(null);
    const lastClickedRowRef = useRef<HTMLElement | null>(null);
    const lastDetailRef = useRef<React.ReactNode>(detail);

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
    // scroll the currently-selected row into view. The selector below covers
    // both current-row conventions of this concept `list`/`detail` contract —
    // `aria-selected="true"` (treeitems, e.g. WorkspaceTree) and
    // `aria-pressed="true"` (selectable `role="button"` rows, ArtifactRow
    // since #1421). No production view mounts this contract yet (they all use
    // the legacy `leftPanel`/`rightPanel` panels instead), so the union is
    // forward-compat hygiene, not a user-visible fix today.
    // ---------------------------------------------------------------------

    const wasDetailOpenRef = useRef(hasDetail);

    useEffect(() => {
      if (wasDetailOpenRef.current && !hasDetail) {
        const selected = listContainerRef.current?.querySelector(
          '[aria-selected="true"], [aria-pressed="true"]'
        );
        selected?.scrollIntoView({ block: 'nearest' });
      }
      wasDetailOpenRef.current = hasDetail;
    }, [hasDetail]);

    // Only a genuine null -> detail transition follows the controlled prop;
    // a new inline <Detail/> identity on every parent render must not pop the
    // detail back open after the user pressed back (same rule as legacy).
    useEffect(() => {
      if (lastDetailRef.current === detail) return;
      lastDetailRef.current = detail;
      // Same rule as the legacy branch: never auto-hide the list on mobile.
      if (!hasDetail) setMobilePane('list');
    }, [detail, hasDetail]);

    const isMobileReplace = zone === 'mobile' && hasDetail && mobilePane === 'detail';

    // Same delegated row click as the legacy branch — see the selector note at
    // the top of this module. Toolbar / view-toggle controls never open detail.
    const handleMobileListClick = useCallback((event: MouseEvent): void => {
      const container = listContainerRef.current;
      if (!container) return;
      const row = findClickedListRow(event.target, container);
      if (row === null) return;
      lastClickedRowRef.current = row;
      setMobilePane('detail');
    }, []);

    useEffect(() => {
      if (zone !== 'mobile') return;
      const container = listContainerRef.current;
      if (!container) return;
      container.addEventListener('click', handleMobileListClick);
      return () => container.removeEventListener('click', handleMobileListClick);
    }, [zone, handleMobileListClick]);

    // Focus follows the visible pane; back returns it to the originating row.
    useEffect(() => {
      if (isMobileReplace) backButtonRef.current?.focus();
    }, [isMobileReplace]);

    useEffect(() => {
      if (zone !== 'mobile' || mobilePane !== 'list') return;
      const row = lastClickedRowRef.current;
      if (row === null) return;
      lastClickedRowRef.current = null;
      row.focus();
    }, [zone, mobilePane]);

    const listStyle: React.CSSProperties = hasDetail
      ? {
          ...LIST_SCROLL_SURFACE_STYLE,
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
          ...LIST_SCROLL_SURFACE_STYLE,
          flex: '1 1 100%',
          maxWidth: '100%',
          background: 'var(--color-surface)',
          padding: 'var(--space-4)',
        };

    const detailStyle: React.CSSProperties = {
      ...SCROLL_SURFACE_STYLE,
      // The detail stays mounted after "back" (the controlled `detail` prop
      // still holds the selection), so hide it explicitly on a phone — the
      // legacy branch does the same with MOBILE_DETAIL_HIDDEN_STYLE.
      display: zone === 'mobile' && !isMobileReplace ? 'none' : 'block',
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
      // The mobile back header is a full-width sibling above the panes; a
      // horizontal spine request cannot keep the root on the row axis.
      flexDirection: isMobileReplace || spineIsHorizontal ? 'column' : 'row',
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
        {isMobileReplace && (
          <div style={MOBILE_HEADER_STYLE} data-testid="splitview-mobile-header">
            <button
              ref={backButtonRef}
              type="button"
              className="btn-ghost"
              data-testid="splitview-back"
              onClick={() => setMobilePane('list')}
            >
              ← {t('splitView.back')}
            </button>
          </div>
        )}
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
