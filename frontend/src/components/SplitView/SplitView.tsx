/**
 * REQ-L1-084 / ADR-030: Generic SplitView Container (UI_KONZEPT.md ch. 12.6)
 *
 * One contract, one implementation:
 *
 *   <SplitView
 *     list={<RequirementList />}
 *     detail={selected ? <RequirementDetail /> : null}
 *     ratio={[40, 60]}
 *     minWidths={[380, 520]}
 *     moduleType="requirements"
 *   />
 *
 * `detail === null` collapses the layout to a full-width `list` — no empty
 * panel, no width constraint (ch. 6.2). The derivation chain is rendered by a
 * dedicated footer component, which each host mounts as a sibling of this
 * container; it is always horizontal, so this component owns no chain slot and
 * no breakpoint-specific chain layout. The three-zone responsive model (ch. 6.3)
 * and the mobile list/detail/back state machine live in
 * `useSplitViewMobileState`.
 *
 * Tree width (ADR-030): after the first resize the pixel width is
 * authoritative. `ratio` is only the INITIAL value (used while no width is
 * stored), `minWidths` are the CLAMP bounds in px. The clamp is
 * `minWidths[0] … effMax` with
 * `effMax = min(70% × contentWidth, contentWidth − minWidths[1] − dividerWidth)`
 * measured at runtime from the content box (no new width media query). The
 * optional `moduleType` selects a per-module default. Persistence is supplied
 * by Task 9 through the controlled `treeWidth` / `onTreeWidthChange` seam;
 * until then the component keeps a local fallback so the divider is fully
 * usable on its own.
 *
 * The legacy `leftPanel`/`rightPanel` contract was removed in UI-001 / S3.2.
 * All former callers were migrated; there is no adapter, no second render
 * path. The scroll model (`overscroll-behavior: contain`,
 * `scrollbar-gutter: stable`) applies to every scroll surface.
 *
 * Shared testids `splitview-list` / `splitview-detail` / `splitview-back` are
 * part of the E2E contract and must stay byte-identical.
 *
 * leaf_id: COMP-RF-005-SplitView
 * interfaces: treeWidth seam (Task 9)
 */

import React from 'react';
import { useTranslation } from 'react-i18next';

import { useSplitViewMobileState } from './useSplitViewMobileState';
import { computeTreeWidthEffMax } from '../../hooks/useTreeWidth';

/** Props for the generic SplitView component. */
export interface SplitViewProps {
  /** List/tree content. */
  list: React.ReactNode;

  /** Detail content. `null`/`undefined` collapses the layout to a
   *  full-width `list` — no empty panel, no width constraint (ch. 6.2). */
  detail?: React.ReactNode | null;

  /** [list%, detail%] INITIAL ratio, used only while there is no stored
   *  width. Default `[40, 60]` (ch. 6.1). Clamp always wins over this value. */
  ratio?: [number, number];

  /** [listPx, detailPx] CLAMP bounds. Default `[380, 520]`, matching
   *  `--list-min` / `--detail-min` in tokens.css. `minWidths[0]` is the lower
   *  clamp (Home); `minWidths[1]` feeds the upper `effMax` formula. */
  minWidths?: [number, number];

  /** Classname for root container */
  containerClassName?: string;

  /** Module identifier for the per-module default tree width. */
  moduleType?: string;

  /**
   * Task 9 seam — controlled tree width in px. When a number is supplied it
   * is authoritative (clamped to the current bounds). When omitted, this
   * component keeps a local fallback width. `undefined` = uncontrolled.
   */
  treeWidth?: number;

  /**
   * Task 9 seam — called with the clamped px value whenever the user resizes
   * the tree via the divider (keyboard, pointer drag or reset). Wire this to
   * `useTreeWidth` persistence in Task 9.
   */
  onTreeWidthChange?: (widthPx: number) => void;

  /**
   * Task 9 seam — optional per-module default override for the reset action
   * (Enter / double-click). Falls back to the module default map, then to the
   * ratio-derived initial width.
   */
  defaultTreeWidth?: number;
}

const DEFAULT_RATIO: [number, number] = [40, 60];
const DEFAULT_MIN_WIDTHS: [number, number] = [380, 520];

/** ADR-030 divider geometry and keyboard steps. */
const DIVIDER_TARGET_PX = 24;
const TREE_WIDTH_STEP_PX = 16;
const TREE_WIDTH_SHIFT_STEP_PX = 64;

/**
 * Task 8 fallback defaults; Task 9 replaces these with the persisted
 * `useTreeWidth` defaults per module. Out-of-range values are clamped.
 */
const DEFAULT_TREE_WIDTH_BY_MODULE: Readonly<Record<string, number>> = {
  adr: 350,
  adrs: 350,
  requirement: 424,
  requirements: 424,
};

/** Scroll model shared by every scroll surface in SplitView: ch. 7.1
 * (`overscroll-behavior: contain`) and ch. 7.3 (`scrollbar-gutter: stable`).
 * Applied inline so it is observable via `getComputedStyle` regardless of
 * whether CSS Modules are processed by the current build/test pipeline. */
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

/** Mobile detail header: owns the single back step (spec §7.2). */
const MOBILE_HEADER_STYLE: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  minHeight: 'var(--btn-h-lg)',
  padding: 'var(--space-1) var(--space-3)',
  borderBottom: '1px solid var(--color-border)',
  background: 'var(--color-surface)',
};

/**
 * ADR-030 divider: a 24px grab strip (the visible hairline is its right
 * border). Hoisted to a named constant per the documented house pattern —
 * ESLint's static-inline-style rule and the `ui-ratchet` count only flag an
 * object literal directly inside the `style` attribute. No new width media
 * query: the runtime clamp is computed in JS from the measured content box.
 */
const DIVIDER_STYLE: React.CSSProperties = {
  flex: `0 0 ${DIVIDER_TARGET_PX}px`,
  width: `${DIVIDER_TARGET_PX}px`,
  minHeight: `${DIVIDER_TARGET_PX}px`,
  alignSelf: 'stretch',
  borderRight: '1px solid var(--color-border)',
  background: 'var(--color-surface)',
  cursor: 'col-resize',
  userSelect: 'none',
  transition: 'background var(--transition-fast)',
  outlineOffset: '-2px',
};

// ---------------------------------------------------------------------------
// Issue #876 (Etappe 7, batch 3): the remaining static inline style objects
// are hoisted to named `React.CSSProperties` identifiers. This is the
// documented house pattern, not a workaround: lint/ratchet only report an
// object literal directly inside the `style` attribute, and these surfaces are
// pinned by tests reading the rendered inline style (`getComputedStyle` /
// `toHaveStyle`; vitest's `css: false` means CSS Modules never load).
// ---------------------------------------------------------------------------

/** Clamp helper — clamp always wins over a ratio initial value or a stored width. */
function clampWidth(width: number, lower: number, upper: number): number {
  if (!Number.isFinite(width)) return lower;
  return Math.round(Math.min(Math.max(width, lower), Math.max(lower, upper)));
}

/**
 * Generic SplitView Component — implements REQ-L1-084 / ADR-030
 *
 * @param props - SplitViewProps configuration
 * @returns JSX.Element rendering the split-view container
 */
export const SplitView = React.forwardRef<HTMLDivElement, SplitViewProps>(
  (
    {
      list,
      detail = null,
      ratio = DEFAULT_RATIO,
      minWidths = DEFAULT_MIN_WIDTHS,
      containerClassName,
      moduleType,
      treeWidth,
      onTreeWidthChange,
      defaultTreeWidth,
    },
    ref
  ) => {
    const { t } = useTranslation();
    const hasDetail = detail !== null && detail !== undefined;
    const {
      zone,
      isMobileReplace,
      listContainerRef,
      backButtonRef,
      goBack,
    } = useSplitViewMobileState(detail);

    // Runtime content width (ADR-030): ResizeObserver when available,
    // window resize + initial measurement as the jsdom/test fallback. The
    // initializer avoids a one-frame 380px clamp before the first measurement.
    const [contentWidth, setContentWidth] = React.useState(() =>
      typeof window === 'undefined' ? 0 : window.innerWidth,
    );
    React.useEffect(() => {
      const root = listContainerRef.current?.parentElement;
      if (!root) return;
      const measure = (): void => {
        const next = root.getBoundingClientRect().width;
        setContentWidth((prev) => (prev === next ? prev : next));
      };
      measure();
      window.addEventListener('resize', measure);
      let observer: ResizeObserver | undefined;
      if (typeof ResizeObserver !== 'undefined') {
        observer = new ResizeObserver((entries) => {
          const width = entries[0]?.contentRect.width ?? 0;
          if (width > 0) setContentWidth((prev) => (prev === width ? prev : width));
        });
        observer.observe(root);
      }
      return () => {
        window.removeEventListener('resize', measure);
        observer?.disconnect();
      };
    }, [listContainerRef]);

    const lower = minWidths[0];
    const detailMin = minWidths[1];
    const effMax = computeTreeWidthEffMax(contentWidth, lower, detailMin);
    const ratioInitial = clampWidth((ratio[0] / 100) * contentWidth, lower, effMax);

    const moduleDefault = moduleType
      ? DEFAULT_TREE_WIDTH_BY_MODULE[moduleType]
      : undefined;
    const defaultRaw = defaultTreeWidth ?? moduleDefault ?? (ratio[0] / 100) * contentWidth;
    const defaultWidth = clampWidth(defaultRaw, lower, effMax);

    const isControlled = treeWidth !== undefined;
    const [localWidth, setLocalWidth] = React.useState<number | null>(null);
    const currentWidth = clampWidth(
      isControlled ? (treeWidth as number) : (localWidth ?? ratioInitial),
      lower,
      effMax,
    );

    const commitWidth = React.useCallback(
      (raw: number): void => {
        const next = clampWidth(raw, lower, effMax);
        if (!isControlled) setLocalWidth(next);
        onTreeWidthChange?.(next);
      },
      [lower, effMax, isControlled, onTreeWidthChange],
    );

    const handleDividerKeyDown = React.useCallback(
      (event: React.KeyboardEvent<HTMLDivElement>): void => {
        const step = event.shiftKey ? TREE_WIDTH_SHIFT_STEP_PX : TREE_WIDTH_STEP_PX;
        let next: number;
        switch (event.key) {
          case 'ArrowLeft':
            next = currentWidth - step;
            break;
          case 'ArrowRight':
            next = currentWidth + step;
            break;
          case 'Home':
            next = lower;
            break;
          case 'End':
            next = effMax;
            break;
          case 'Enter':
            next = defaultWidth;
            break;
          default:
            return;
        }
        event.preventDefault();
        commitWidth(next);
      },
      [currentWidth, lower, effMax, defaultWidth, commitWidth],
    );

    const dividerRef = React.useRef<HTMLDivElement>(null);
    const dividerVisible = hasDetail && zone !== 'mobile';

    // Double-click resets to the module default. Native listener keeps the
    // JSX free of click-handler attributes (separator semantics, not a button).
    React.useEffect(() => {
      const element = dividerRef.current;
      if (!element || !dividerVisible) return;
      const onDoubleClick = (): void => commitWidth(defaultWidth);
      element.addEventListener('dblclick', onDoubleClick);
      return () => element.removeEventListener('dblclick', onDoubleClick);
    }, [dividerVisible, commitWidth, defaultWidth]);

    // Pointer drag (REQ-L3-RF009-001): the pointer starts on the divider, the
    // move/up listeners live on window so the gesture survives leaving it.
    React.useEffect(() => {
      const element = dividerRef.current;
      if (!element || !dividerVisible) return;
      let dragging = false;
      const onPointerDown = (event: PointerEvent): void => {
        if (event.button !== 0) return;
        event.preventDefault();
        dragging = true;
      };
      const onPointerMove = (event: PointerEvent): void => {
        if (!dragging) return;
        const root = listContainerRef.current?.parentElement;
        if (!root) return;
        commitWidth(event.clientX - root.getBoundingClientRect().left);
      };
      const onPointerUp = (): void => {
        dragging = false;
      };
      element.addEventListener('pointerdown', onPointerDown);
      window.addEventListener('pointermove', onPointerMove);
      window.addEventListener('pointerup', onPointerUp);
      window.addEventListener('pointercancel', onPointerUp);
      return () => {
        element.removeEventListener('pointerdown', onPointerDown);
        window.removeEventListener('pointermove', onPointerMove);
        window.removeEventListener('pointerup', onPointerUp);
        window.removeEventListener('pointercancel', onPointerUp);
      };
    }, [dividerVisible, commitWidth, listContainerRef]);

    const listStyle: React.CSSProperties = hasDetail
      ? {
          ...LIST_SCROLL_SURFACE_STYLE,
          display: isMobileReplace ? 'none' : 'block',
          // Mobile stacks the panes — the tree width is not applied there.
          flex: zone === 'mobile' ? '1 1 100%' : `0 0 ${currentWidth}px`,
          minWidth: zone === 'mobile' ? undefined : `${lower}px`,
          borderRight: 'none',
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
      // still holds the selection), so hide it explicitly on a phone.
      display: zone === 'mobile' && !isMobileReplace ? 'none' : 'block',
      flex: zone === 'mobile' ? '1 1 100%' : '1 1 auto',
      minWidth: zone === 'mobile' ? undefined : `${detailMin}px`,
      background: 'var(--color-surface)',
      padding: 'var(--space-4)',
    };

    const rootStyle: React.CSSProperties = {
      display: 'flex',
      // The mobile back header is a full-width sibling above the panes, so
      // the root stacks into a column whenever the phone shows the detail.
      // Every other zone keeps the list/detail row on the horizontal axis.
      flexDirection: isMobileReplace ? 'column' : 'row',
      height: '100%',
      overflow: 'hidden',
      background: 'var(--color-surface)',
      fontFamily: 'var(--font-sans)',
      color: 'var(--color-text)',
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
              onClick={goBack}
            >
              ← {t('splitView.back')}
            </button>
          </div>
        )}
        <div ref={listContainerRef} data-testid="splitview-list" style={listStyle}>
          {list}
        </div>
        {dividerVisible && (
          <div
            ref={dividerRef}
            role="separator"
            tabIndex={0}
            aria-orientation="vertical"
            aria-label={t('splitView.resizeDivider')}
            aria-valuemin={lower}
            aria-valuemax={effMax}
            aria-valuenow={currentWidth}
            aria-valuetext={`${currentWidth} px`}
            aria-controls="splitview-list"
            data-testid="tree-width-separator"
            style={DIVIDER_STYLE}
            onKeyDown={handleDividerKeyDown}
          />
        )}
        {hasDetail && (
          <div data-testid="splitview-detail" style={detailStyle}>
            {detail}
          </div>
        )}
      </div>
    );
  }
);

SplitView.displayName = 'SplitView';
