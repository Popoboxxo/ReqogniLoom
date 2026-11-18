/**
 * REQ-L1-084: Generic SplitView Container Component (UI_KONZEPT.md ch. 12.6)
 *
 * One contract, one implementation:
 *
 *   <SplitView
 *     list={<RequirementList />}
 *     detail={selected ? <RequirementDetail /> : null}
 *     spine={selected ? <TraceSpine artifact={selected} /> : null}
 *     ratio={[40, 60]}
 *     minWidths={[380, 520]}
 *   />
 *
 * `detail === null` collapses the layout to a full-width `list` — no empty
 * panel, no width constraint (ch. 6.2). The optional `spine` slot sits between
 * list and detail as its own scroll-independent sibling. The three-zone
 * responsive model (ch. 6.3) and the mobile list/detail/back state machine
 * live in `useSplitViewMobileState`.
 *
 * The legacy `leftPanel`/`rightPanel` contract (drag divider, persisted width,
 * `moduleType`) was removed in UI-001 / S3.2 WP-1. All former callers were
 * migrated to the concept contract; there is no adapter and no second render
 * path. Drag-persistence is intentionally gone — the concept uses a fixed
 * ratio. The scroll model (`overscroll-behavior: contain`,
 * `scrollbar-gutter: stable`) applies to every scroll surface.
 *
 * Shared testids `splitview-list` / `splitview-detail` / `splitview-back` are
 * part of the E2E contract and must stay byte-identical.
 *
 * leaf_id: COMP-RF-005-SplitView
 * interfaces: none (internal UI container)
 */

import React from 'react';
import { useTranslation } from 'react-i18next';

import { useSplitViewMobileState } from './useSplitViewMobileState';

/** Props for the generic SplitView component (concept contract only). */
export interface SplitViewProps {
  /** List/tree content. */
  list: React.ReactNode;

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

  /** Classname for root container */
  containerClassName?: string;
}

const DEFAULT_RATIO: [number, number] = [40, 60];
const DEFAULT_MIN_WIDTHS: [number, number] = [380, 520];

/** Narrow-viewport ratio fixed by ch. 6.3 ("< 1024px: Verhältnis 45 : 55"). */
const NARROW_RATIO: [number, number] = [45, 55];

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

// ---------------------------------------------------------------------------
// Issue #876 (Etappe 7, batch 3): the remaining inline style-object literals
// are hoisted to named `React.CSSProperties` identifiers (and the render-time
// geometry below stays in `listStyle`/`detailStyle`/`spineStyle`/`rootStyle`/
// `rowStyle` variables). This is the documented house pattern, not a
// workaround: the lint rule only reports an object literal directly inside
// the `style` attribute, and these surfaces are pinned by tests that read
// the rendered inline style (`SplitView.test.tsx` reads `getComputedStyle`
// for `overscrollBehavior`/`scrollbarGutter` and `toHaveStyle` for the flex
// widths; vitest's `css: false` means CSS Modules never load in the test
// run). Same sanctioned precedent as `MetricsDashboard.helpToggleStyle`.
// ---------------------------------------------------------------------------

/**
 * Generic SplitView Component — implements REQ-L1-084
 *
 * @param props - SplitViewProps configuration
 * @returns JSX.Element rendering the split-view container
 */
export const SplitView = React.forwardRef<HTMLDivElement, SplitViewProps>(
  (
    {
      list,
      detail = null,
      spine = null,
      ratio = DEFAULT_RATIO,
      minWidths = DEFAULT_MIN_WIDTHS,
      containerClassName,
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

    const effectiveRatio: [number, number] =
      zone === 'narrow' ? NARROW_RATIO : ratio;

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
      // still holds the selection), so hide it explicitly on a phone.
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
              onClick={goBack}
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

SplitView.displayName = 'SplitView';
