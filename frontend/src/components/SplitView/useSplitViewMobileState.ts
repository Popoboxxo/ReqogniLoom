/**
 * useSplitViewMobileState — the single mobile pane state machine for SplitView.
 *
 * Before UI-001/S3.2 this machine was copy-pasted twice inside SplitView:
 * once in the deleted legacy `leftPanel`/`rightPanel` branch and once in the
 * concept `list`/`detail` branch. With the legacy branch gone this hook is the
 * one owner of the three-resize-zone model (UI_KONZEPT.md ch. 6.3) and of the
 * "phone enters on the list, a row opens the detail, one back step returns"
 * rule (ch. 6.2 / REQ-209, PR #1888).
 *
 * The parent keeps its selection — `detail` is a controlled prop, so "back"
 * only flips this local pane choice. The list stays mounted at all times
 * (hidden via `display: none` on a phone) so its native scrollTop survives an
 * open/close cycle; when the detail closes we additionally scroll the
 * currently selected row into view.
 *
 * Breakpoints are read from the same `--bp-*` tokens as before via
 * `window.innerWidth` (JS cannot read a custom property from a `@media`
 * condition). `useBreakpoint` from hooks/ is media-query based and therefore
 * not interchangeable here: the mobile unit tests drive the viewport through
 * `window.innerWidth`, and the E2E shards resize the real window.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import type React from 'react';

/** Responsive bands from UI_KONZEPT.md ch. 6.3 (token-backed breakpoints). */
export type ResponsiveZone = 'desktop' | 'narrow' | 'mobile';

/** Which pane is visible when the mobile layout replaces the list with the detail. */
export type MobilePane = 'list' | 'detail';

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

function computeZone(bpMd: number, bpLg: number): ResponsiveZone {
  if (typeof window === 'undefined') return 'desktop';
  if (window.innerWidth < bpMd) return 'mobile';
  if (window.innerWidth < bpLg) return 'narrow';
  return 'desktop';
}

function currentZone(): ResponsiveZone {
  return computeZone(
    readBreakpointToken('--bp-md', FALLBACK_BP_MD),
    readBreakpointToken('--bp-lg', FALLBACK_BP_LG),
  );
}

export interface UseSplitViewMobileStateResult {
  /** Active responsive band, recomputed on window resize. */
  zone: ResponsiveZone;
  /** Which pane the phone is currently showing. */
  mobilePane: MobilePane;
  /** True when the detail replaces the list (phone + open detail). Drives
   *  the back header and the hidden/visible pane styles. */
  isMobileReplace: boolean;
  /** Attach to the list pane — owns the delegated row click and scroll memory. */
  listContainerRef: React.RefObject<HTMLDivElement | null>;
  /** Attach to the single back control — receives focus on detail open. */
  backButtonRef: React.RefObject<HTMLButtonElement | null>;
  /** The single back step: return to the list, keep the parent's selection. */
  goBack: () => void;
}

/**
 * Own the mobile pane state for one SplitView instance.
 *
 * @param detail The controlled detail node; `null`/`undefined` means "no
 *   selection" and always leaves the phone in the list pane.
 */
export function useSplitViewMobileState(
  detail: React.ReactNode | null,
): UseSplitViewMobileStateResult {
  const hasDetail = detail !== null && detail !== undefined;

  // PR #1888: a phone ALWAYS enters on the list — even for a deep link or a
  // route-selected artifact that already provides `detail` at mount.
  const [mobilePane, setMobilePane] = useState<MobilePane>('list');
  const listContainerRef = useRef<HTMLDivElement>(null);
  const backButtonRef = useRef<HTMLButtonElement>(null);
  const lastClickedRowRef = useRef<HTMLElement | null>(null);
  const lastDetailRef = useRef<React.ReactNode>(detail);

  const [zone, setZone] = useState<ResponsiveZone>(currentZone);

  useEffect(() => {
    const handleResize = (): void => setZone(currentZone());
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // Position memory (ch. 7.3): the list container stays mounted while a
  // detail is open, so scrollIntoView on the current row is all that is left.
  // Covers both current-row conventions: `aria-selected="true"` (treeitems)
  // and `aria-pressed="true"` (selectable `role="button"` rows, ArtifactRow).
  const wasDetailOpenRef = useRef(hasDetail);

  useEffect(() => {
    if (wasDetailOpenRef.current && !hasDetail) {
      const selected = listContainerRef.current?.querySelector(
        '[aria-selected="true"], [aria-pressed="true"]',
      );
      selected?.scrollIntoView({ block: 'nearest' });
    }
    wasDetailOpenRef.current = hasDetail;
  }, [hasDetail]);

  // Only a genuine detail -> null transition returns to the list. A new
  // inline <Detail/> identity on every parent render must not pop the detail
  // back open after the user pressed back.
  useEffect(() => {
    if (lastDetailRef.current === detail) return;
    lastDetailRef.current = detail;
    if (!hasDetail) setMobilePane('list');
  }, [detail, hasDetail]);

  const isMobileReplace = zone === 'mobile' && hasDetail && mobilePane === 'detail';

  // Delegated via a native listener rather than a JSX `onClick` on the list
  // pane: that pane is a clickable *region*, not a button, so a `btn-*` chrome
  // class would be wrong. A ref listener also covers rows mounted after the
  // first paint.
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

  // Focus follows the visible pane (spec §7.2): opening a detail focuses the
  // single back control; returning to the list restores focus to the row that
  // opened it, so keyboard and screen-reader users keep their position.
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

  const goBack = useCallback((): void => setMobilePane('list'), []);

  return {
    zone,
    mobilePane,
    isMobileReplace,
    listContainerRef,
    backButtonRef,
    goBack,
  };
}
