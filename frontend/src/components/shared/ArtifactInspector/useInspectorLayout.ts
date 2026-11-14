/**
 * ArtifactInspector — layout hook of the tabbed shell (issue #1762, M1).
 *
 * leaf_id: COMP-RF-014 (ArtifactInspector)
 * req_id:  REQ-L1-089 (unified inspector shell), REQ-L1-093
 *
 * Owns the two pieces of state that depend on the viewport, not on the data:
 *
 *  - the **width state** R1…R5 and the rendered form (panel / rail / sheet /
 *    fullscreen) derived from it (spec §4.2), and
 *  - the **panel width** the user dragged, persisted per kind (spec §4.2).
 *
 * The mapping itself lives in `inspectorContract.ts` so the test can pin it
 * without mounting anything; this hook only wires that mapping to `resize`
 * events, storage and React state.
 *
 * The open/closed decision is deliberately **not** persisted: the region
 * default is the answer every time a route mounts, so a collapsed inspector on
 * a wide viewport cannot silence every later visit (spec §4.2 defines the
 * default per region, not a remembered choice).
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  clampInspectorWidth,
  inspectorDefaultWidth,
  inspectorDefaultsOpen,
  inspectorFormFor,
  inspectorRegionFor,
  inspectorWidthStorageKey,
  type InspectorForm,
  type InspectorRegion,
} from "./inspectorContract";
import { safeLocalStorage, safeSessionStorage } from "../../../utils/safeStorage";
import type { ArtifactKind } from "./types";

export interface InspectorLayout {
  /** Width state R1…R5 of the current viewport (spec §4.2). */
  region: InspectorRegion;
  /** Rendered form: rail / panel / sheet / fullscreen. */
  form: InspectorForm;
  /** Whether the inspector is expanded (panel open or sheet visible). */
  open: boolean;
  setOpen: (open: boolean) => void;
  toggleOpen: () => void;
  /** Panel width in px — clamped to `--inspector-w-min`/`-max`. */
  widthPx: number;
  setWidthPx: (width: number) => void;
  /** True while the splitter may be shown (panel form only, spec §5.1 #5). */
  canResize: boolean;
}

function currentViewportWidth(): number {
  if (typeof window === "undefined") return 1440;
  return window.innerWidth;
}

function readStoredWidth(kind: ArtifactKind, fallback: number): number {
  const raw = safeLocalStorage.getItem(inspectorWidthStorageKey(kind));
  if (raw === null) return clampInspectorWidth(fallback);
  const parsed = Number.parseInt(raw, 10);
  return clampInspectorWidth(Number.isFinite(parsed) ? parsed : fallback);
}

export function useInspectorLayout(kind: ArtifactKind): InspectorLayout {
  const [viewportWidth, setViewportWidth] = useState<number>(currentViewportWidth);

  const region = useMemo<InspectorRegion>(
    () => inspectorRegionFor(viewportWidth),
    [viewportWidth],
  );

  // The open state is seeded from the region's default and follows the
  // region while the viewport moves — but only until the user decides for
  // this session. `userSetOpen` records that decision.
  const [userSetOpen, setUserSetOpen] = useState<boolean | null>(null);
  const defaultOpen = inspectorDefaultsOpen(region, viewportWidth);
  const open = userSetOpen === null ? defaultOpen : userSetOpen;

  const setOpen = useCallback((next: boolean): void => setUserSetOpen(next), []);
  const toggleOpen = useCallback(
    (): void => setUserSetOpen((prev) => !(prev === null ? defaultOpen : prev)),
    [defaultOpen],
  );

  const [widthPx, setWidthState] = useState<number>(() =>
    readStoredWidth(kind, inspectorDefaultWidth(inspectorRegionFor(currentViewportWidth()))),
  );

  // A region change moves the *default* width with it (360 in R1, 320 in R2)
  // unless the user dragged a width of their own. Storing the width per kind
  // is the only remembered preference here (spec §4.2).
  useEffect(() => {
    setWidthState(() => {
      const stored = safeLocalStorage.getItem(inspectorWidthStorageKey(kind));
      if (stored !== null) {
        const parsed = Number.parseInt(stored, 10);
        if (Number.isFinite(parsed)) return clampInspectorWidth(parsed);
      }
      return clampInspectorWidth(inspectorDefaultWidth(region));
    });
  }, [kind, region]);

  const setWidthPx = useCallback(
    (next: number): void => {
      const clamped = clampInspectorWidth(next);
      setWidthState(clamped);
      safeLocalStorage.setItem(inspectorWidthStorageKey(kind), String(clamped));
    },
    [kind],
  );

  useEffect(() => {
    function onResize(): void {
      setViewportWidth(currentViewportWidth());
    }
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  const form = inspectorFormFor(region, open);

  return {
    region,
    form,
    open,
    setOpen,
    toggleOpen,
    widthPx,
    setWidthPx,
    // §5.1 #5: the splitter only exists where the inspector is an inline
    // panel — a sheet at 100 % of the detail width has nothing to split.
    canResize: form === "panel",
  };
}

// ---------------------------------------------------------------------------
// Tab persistence — sessionStorage per kind + artifact, `?inspector=` in the URL
// ---------------------------------------------------------------------------

/**
 * Remembered tab for this artifact (spec §5.4).
 *
 * sessionStorage, not localStorage: the tab is view state of one session, and
 * a tab restored from weeks ago is the "why am I on comments?" surprise.
 */
export function readStoredTab<T extends string>(
  storageKey: string,
  available: readonly T[],
): T | null {
  const raw = safeSessionStorage.getItem(storageKey);
  if (raw === null) return null;
  return (available as readonly string[]).includes(raw) ? (raw as T) : null;
}

export function writeStoredTab(storageKey: string, value: string): void {
  safeSessionStorage.setItem(storageKey, value);
}

/**
 * `?inspector=<key>` — the reproducible deep link into one tab (spec §5.4).
 * Returns `null` for a missing or unknown value so the caller can fall back to
 * storage, then to the default tab.
 */
export function readTabFromUrl<T extends string>(available: readonly T[]): T | null {
  if (typeof window === "undefined") return null;
  const raw = new URLSearchParams(window.location.search).get("inspector");
  if (raw === null) return null;
  return (available as readonly string[]).includes(raw) ? (raw as T) : null;
}

/**
 * Rewrites `?inspector=` without navigating: the tab switch must not push a
 * history entry, and `location.pathname` has to stay untouched (M1-8 asserts
 * exactly that).
 */
export function writeTabToUrl(value: string): void {
  if (typeof window === "undefined") return;
  const url = new URL(window.location.href);
  url.searchParams.set("inspector", value);
  window.history.replaceState(window.history.state, "", url);
}
