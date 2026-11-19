/**
 * Task 9 (Schnitt 3b) — per-module tree-width persistence (ADR-030).
 *
 * A device-local, cosmetic layout preference. It deliberately does NOT revive
 * the old underscore-separated SplitView key family removed in UI-001/S3.2:
 * the only storage key is `reqflow.splitview.treeWidth.v2.<moduleType>`. Each module
 * owns its own key, its own default and its own value — an ADR resize can never
 * move the Requirements tree.
 *
 * Authority (ADR-030): <SplitView> remains authoritative for the *runtime*
 * clamp because it measures the content box. This module is the synchronous
 * read/write surface around localStorage:
 *
 *   - on READ, a missing / corrupt / out-of-range value falls back to the
 *     module default (never throws, never jitters);
 *   - on WRITE, the incoming px value is clamped to [min, effMax] before it is
 *     stored, mirroring SplitView's own `computeEffMax` formula;
 *   - writing the module default deletes the key — that is how the divider's
 *     Enter / double-click reset reaches "delete + default" without SplitView
 *     needing a second callback.
 *
 * The `min` option exists so each host can pass its own `minWidths[0]`
 * (Requirements 320, Architecture 250, Goals 350, …). It defaults to 380
 * (`--list-min` / SplitView's default `minWidths[0]`) per ADR-030.
 *
 * No server call, no tenant data: see ADR-030 §Abgrenzung zu ADR-029.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';

import { safeLocalStorage } from '../utils/safeStorage';

/** Sole storage key prefix. The removed UI-001 key family is never touched. */
export const TREE_WIDTH_STORAGE_KEY = 'reqflow.splitview.treeWidth.v2.';

/** Lower clamp — `minWidths[0]` / `--list-min` (ADR-030 F1). */
export const TREE_WIDTH_MIN = 380;

/** Detail-side minimum from SplitView's default `minWidths[1]` (`--detail-min`). */
export const TREE_WIDTH_DETAIL_MIN = 520;

/** Divider target width used by SplitView's runtime clamp. */
export const TREE_WIDTH_DIVIDER_PX = 24;

/** Upper clamp ratio from ADR-030 (`effMax = min(70% × contentWidth, …)`). */
export const TREE_WIDTH_MAX_RATIO = 0.7;

/** Fallback for module types without an explicit default. */
export const DEFAULT_TREE_WIDTH = TREE_WIDTH_MIN;

/** Optimal per-module defaults (ADR 350 px / Requirements 424 px / …). */
export const DEFAULT_TREE_WIDTH_BY_MODULE: Readonly<Record<string, number>> = Object.freeze({
  adr: 350,
  adrs: 350,
  requirement: 424,
  requirements: 424,
  need: 380,
  needs: 380,
  risk: 380,
  risks: 380,
  architecture: 424,
  architectures: 424,
  issue: 380,
  issues: 380,
  testcase: 380,
  testcases: 380,
  test_case: 380,
  test_cases: 380,
  goal: 380,
  goals: 380,
});

/** Optional clamp overrides. Primitives so effects can depend on them safely. */
export interface TreeWidthBounds {
  /** Lower clamp in px. Defaults to `TREE_WIDTH_MIN` (380). */
  min?: number;
  /** Explicit upper clamp. Defaults to the ADR-030 `effMax` runtime formula. */
  max?: number;
  /** Measured content width feeding the formula. Defaults to `window.innerWidth`. */
  contentWidth?: number;
}

/** Public surface returned by `useTreeWidth`. */
export interface UseTreeWidthResult {
  /** Persisted width, or the module default when nothing valid is stored. */
  treeWidth: number;
  /** Clamped default of this module (the divider's Enter / dblclick target). */
  defaultTreeWidth: number;
  /** Persist a clamped width. Writing the default deletes the key. */
  setTreeWidth: (widthPx: number) => void;
  /** Delete the key and return to the module default. */
  resetTreeWidth: () => void;
}

interface ResolvedBounds {
  min: number;
  max: number;
}

/** Storage key for one module. */
export function treeWidthStorageKey(moduleType: string): string {
  return `${TREE_WIDTH_STORAGE_KEY}${moduleType}`;
}

/**
 * ADR-030 upper clamp, identical to SplitView's `computeEffMax`:
 * `min(70% × contentWidth, contentWidth − detailMin − dividerWidth)`, floored
 * at `min`. A non-positive/unavailable measurement collapses to `min`.
 */
export function computeTreeWidthEffMax(
  contentWidth: number,
  min: number = TREE_WIDTH_MIN,
  detailMin: number = TREE_WIDTH_DETAIL_MIN,
): number {
  if (!Number.isFinite(contentWidth) || contentWidth <= 0) return min;
  const byRatio = TREE_WIDTH_MAX_RATIO * contentWidth;
  const byDetailMin = contentWidth - detailMin - TREE_WIDTH_DIVIDER_PX;
  return Math.round(Math.max(min, Math.min(byRatio, byDetailMin)));
}

/** Clamp a px width to `[min, max]`, with non-finite input mapped to `min`. */
export function clampTreeWidth(width: number, min: number, max: number): number {
  if (!Number.isFinite(width)) return min;
  return Math.round(Math.min(Math.max(width, min), Math.max(min, max)));
}

function resolveBounds(bounds: TreeWidthBounds = {}): ResolvedBounds {
  const min = Number.isFinite(bounds.min) ? (bounds.min as number) : TREE_WIDTH_MIN;
  const contentWidth =
    bounds.contentWidth ?? (typeof window === 'undefined' ? 0 : window.innerWidth);
  const max = Number.isFinite(bounds.max)
    ? (bounds.max as number)
    : computeTreeWidthEffMax(contentWidth, min);
  return { min, max: Math.max(min, max) };
}

/** Clamped module default — the reset target on every host. */
export function defaultTreeWidthFor(moduleType: string, bounds: TreeWidthBounds = {}): number {
  const { min, max } = resolveBounds(bounds);
  const raw = DEFAULT_TREE_WIDTH_BY_MODULE[moduleType] ?? DEFAULT_TREE_WIDTH;
  return clampTreeWidth(raw, min, max);
}

/** Read one module's persisted width; fall back to its default on any anomaly. */
export function readTreeWidth(moduleType: string, bounds: TreeWidthBounds = {}): number {
  const fallback = defaultTreeWidthFor(moduleType, bounds);
  const raw = safeLocalStorage.getItem(treeWidthStorageKey(moduleType));
  if (raw === null || raw.trim() === '') return fallback;

  const parsed = Number(raw);
  const { min, max } = resolveBounds(bounds);
  if (!Number.isFinite(parsed) || parsed < min || parsed > max) return fallback;
  return clampTreeWidth(parsed, min, max);
}

/**
 * Persist a clamped width. Passing the module default (SplitView's reset path)
 * deletes the key instead — so reset and "never dragged" are the same state.
 */
export function writeTreeWidth(
  moduleType: string,
  widthPx: number,
  bounds: TreeWidthBounds = {}
): void {
  const key = treeWidthStorageKey(moduleType);
  if (!Number.isFinite(widthPx)) {
    safeLocalStorage.removeItem(key);
    return;
  }
  const { min, max } = resolveBounds(bounds);
  const next = clampTreeWidth(widthPx, min, max);
  if (next === defaultTreeWidthFor(moduleType, bounds)) {
    safeLocalStorage.removeItem(key);
  } else {
    safeLocalStorage.setItem(key, String(next));
  }
}

/** Delete one module's stored width. Other modules are untouched. */
export function resetStoredTreeWidth(moduleType: string): void {
  safeLocalStorage.removeItem(treeWidthStorageKey(moduleType));
}

/**
 * `[treeWidth, defaultTreeWidth, setTreeWidth, resetTreeWidth]` for one module.
 * A `storage` listener keeps multiple mounted editors consistent; no global
 * snapshot is kept, so module state cannot leak between test runs.
 */
export function useTreeWidth(moduleType: string, bounds: TreeWidthBounds = {}): UseTreeWidthResult {
  const resolved = resolveBounds(bounds);
  const contentWidth = bounds.contentWidth;
  // Stable object identity: an inline `bounds` literal from a host must not
  // re-subscribe the storage listener on every render.
  const effectiveBounds: TreeWidthBounds = useMemo(
    () => ({ min: resolved.min, max: resolved.max, contentWidth }),
    [resolved.min, resolved.max, contentWidth]
  );
  const key = treeWidthStorageKey(moduleType);

  const [treeWidth, setWidth] = useState<number>(() => readTreeWidth(moduleType, effectiveBounds));

  useEffect(() => {
    setWidth(readTreeWidth(moduleType, effectiveBounds));
    const onStorage = (event: StorageEvent): void => {
      if (event.key === key || event.key === null) {
        setWidth(readTreeWidth(moduleType, effectiveBounds));
      }
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, [moduleType, key, effectiveBounds]);

  const setTreeWidth = useCallback(
    (widthPx: number): void => {
      writeTreeWidth(moduleType, widthPx, effectiveBounds);
      setWidth(readTreeWidth(moduleType, effectiveBounds));
    },
    [moduleType, effectiveBounds]
  );

  const resetTreeWidth = useCallback((): void => {
    resetStoredTreeWidth(moduleType);
    setWidth(defaultTreeWidthFor(moduleType, effectiveBounds));
  }, [moduleType, effectiveBounds]);

  return {
    treeWidth,
    defaultTreeWidth: defaultTreeWidthFor(moduleType, effectiveBounds),
    setTreeWidth,
    resetTreeWidth,
  };
}
