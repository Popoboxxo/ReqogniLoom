/**
 * ARCH-L1-001 ReactFrontend — useViewportWidth.
 *
 * The single numeric viewport subscription. Before S3.2 WP-2 this resize
 * machine was duplicated inside `useInspectorLayout` (and, in the UI-001
 * follow-up, in SplitView); the inspector now consumes this hook so there is
 * one `window.innerWidth` + `resize` listener pair for the whole front end.
 *
 * Companion of `useMediaQuery` / `useBreakpoint`: all three read the same
 * `BREAKPOINTS` vocabulary from `useBreakpoint.ts`. `useMediaQuery` answers
 * boolean media questions, `useBreakpoint` derives the active token band from
 * it, and `useViewportWidth` supplies the exact pixel width for consumers
 * whose region table (inspector R1–R5) needs it. A media query cannot report a
 * numeric width, so this is the only hook that legitimately reads `innerWidth`.
 */

import { useEffect, useState } from "react";

import { BREAKPOINTS } from "./useBreakpoint";

/**
 * Width used when there is no `window` (SSR, unit tests). Kept equal to the
 * `--bp-default` token so a server render lands in the same inspector region
 * as the common desktop case — the value the old hook hardcoded inline.
 */
export const SSR_VIEWPORT_WIDTH: number = BREAKPOINTS.default;

/** Current viewport width, with the token-backed SSR fallback. */
export function currentViewportWidth(): number {
  if (typeof window === "undefined") return SSR_VIEWPORT_WIDTH;
  return window.innerWidth;
}

/** Subscribe to the exact viewport width in pixels (mobile-first resize). */
export function useViewportWidth(): number {
  const [width, setWidth] = useState<number>(currentViewportWidth);

  useEffect(() => {
    function onResize(): void {
      setWidth(currentViewportWidth());
    }
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  return width;
}
