/**
 * ARCH-L1-001 ReactFrontend — useMediaQuery.
 *
 * Minimal React subscription to a CSS media query. It exists because the
 * sidebar's mobile drawer (SidebarNavigation) has to know whether it is
 * rendered as the off-canvas drawer or as the static desktop rail: only the
 * drawer is a modal dialog with a focus trap, the rail must stay non-modal.
 *
 * SSR-safe: without a `window` — or without `matchMedia`, which jsdom and some
 * non-browser renderers do not provide — the hook reports `false` instead of
 * throwing, so server rendering and unit tests degrade to the "query does not
 * match" state rather than crashing.
 */

import { useEffect, useState } from "react";

/** True when a `MediaQueryList` can actually be constructed here. */
function canQueryMedia(): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function";
}

/**
 * Tracks whether `query` currently matches.
 *
 * @param query A CSS media query string, e.g. `"(max-width: 1024px)"`.
 * @returns `true` while the query matches, `false` otherwise — and always
 *   `false` in environments without `window.matchMedia`.
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState<boolean>(() =>
    canQueryMedia() ? window.matchMedia(query).matches : false
  );

  useEffect(() => {
    if (!canQueryMedia()) return;
    const mediaQueryList = window.matchMedia(query);
    const handleChange = (event: MediaQueryListEvent): void => {
      setMatches(event.matches);
    };
    // Re-read on (re)subscribe: the query can change between the render that
    // produced the initial state and this effect, and the first value must not
    // lag behind a viewport that already crossed the breakpoint.
    setMatches(mediaQueryList.matches);
    mediaQueryList.addEventListener("change", handleChange);
    return () => mediaQueryList.removeEventListener("change", handleChange);
  }, [query]);

  return matches;
}
