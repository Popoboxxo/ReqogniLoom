/**
 * ARCH-L1-001 ReactFrontend — useBreakpoint / BREAKPOINTS.
 *
 * The single JS mirror of the `--bp-*` vocabulary declared in
 * `styles/tokens.css`. JS cannot read a custom property from a `@media`
 * condition, so the numeric values have to exist on both sides; this module
 * is the ONLY place on the JS side where they are written as literals.
 * `src/test/breakpoint-token-gate.test.ts` parses both files and fails the
 * build if either side drifts.
 *
 * `useBreakpoint()` composes the canonical `useMediaQuery` subscription — one
 * `(min-width: Npx)` query per token — rather than opening a second viewport
 * machine. `useViewportWidth()` in the sibling hook is the numeric companion
 * for consumers (the inspector R1–R5 table) that need the exact pixel width.
 */

import { useMediaQuery } from "./useMediaQuery";

/**
 * JS mirror of the CSS breakpoint vocabulary. Values are literals by
 * necessity (see module doc); keys map 1:1 to `BREAKPOINT_TOKEN_NAMES`.
 */
export const BREAKPOINTS = {
  sm: 640,
  md: 768,
  lg: 1024,
  sheetOpen: 1280,
  default: 1440,
  xl: 1600,
} as const;

export type BreakpointName = keyof typeof BREAKPOINTS;

/** CSS custom property backing each JS key — the gate's naming contract. */
export const BREAKPOINT_TOKEN_NAMES: Readonly<Record<BreakpointName, string>> = {
  sm: "--bp-sm",
  md: "--bp-md",
  lg: "--bp-lg",
  sheetOpen: "--bp-sheetOpen",
  default: "--bp-default",
  xl: "--bp-xl",
};

/** Build the token-backed `min-width` query for one breakpoint. */
export function minWidthQuery(breakpoint: BreakpointName): string {
  return `(min-width: ${BREAKPOINTS[breakpoint]}px)`;
}

/** Build the token-backed `max-width` query for one breakpoint. */
export function maxWidthQuery(breakpoint: BreakpointName): string {
  return `(max-width: ${BREAKPOINTS[breakpoint]}px)`;
}

/**
 * The active breakpoint at the current viewport width, or `null` below the
 * smallest token. Queries are tested largest-first; the first match wins, so
 * a 1600px viewport is `xl`, not `sm`.
 *
 * SSR / no-`matchMedia` degrades to `null` — the same "query does not match"
 * behaviour `useMediaQuery` provides — never a guessed width.
 */
export function useBreakpoint(): BreakpointName | null {
  // Fixed, unconditional hook order — a dynamic `map()` would violate the
  // rules of hooks even though the list itself is constant.
  const xl = useMediaQuery(minWidthQuery("xl"));
  const defaultWidth = useMediaQuery(minWidthQuery("default"));
  const sheetOpen = useMediaQuery(minWidthQuery("sheetOpen"));
  const lg = useMediaQuery(minWidthQuery("lg"));
  const md = useMediaQuery(minWidthQuery("md"));
  const sm = useMediaQuery(minWidthQuery("sm"));

  if (xl) return "xl";
  if (defaultWidth) return "default";
  if (sheetOpen) return "sheetOpen";
  if (lg) return "lg";
  if (md) return "md";
  if (sm) return "sm";
  return null;
}
