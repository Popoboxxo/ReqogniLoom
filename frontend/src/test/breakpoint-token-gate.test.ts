/**
 * Breakpoint token gate (S3.2 WP-2 — UI-003 / R2S-006 remainder).
 *
 * `styles/tokens.css` is the single source of truth for the breakpoint
 * vocabulary. This test makes the JS↔CSS contract executable:
 *
 *  1. every JS breakpoint constant (the `BREAKPOINTS` map in
 *     `hooks/useBreakpoint.ts` and the inspector's `INSPECTOR_BREAKPOINTS`)
 *     resolves to the exact value of the CSS custom property it mirrors;
 *  2. every `@media (max-width: Npx)` literal in a CSS file under `src/` is
 *     either a token value or a *documented* exception with a named reason;
 *  3. the `inspectorRegionFor` R1–R5 boundaries are frozen at the ten values
 *     around 768 / 1024 / 1280 / 1440 / 1600 — the R2S-006 compat risk. A
 *     refactor must never flip a width state while the constants are moving.
 *
 * The scan mirrors `design-tokens.test.ts`: plain `node:fs` + regex, no new
 * dependency. The new hook module is read as source (not imported) so this
 * gate runs against an unfixed tree as well and reports the missing map as a
 * first-class failure rather than a module-resolution crash.
 */
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import { describe, expect, it } from "vitest";

import {
  INSPECTOR_BREAKPOINTS,
  inspectorDefaultsOpen,
  inspectorRegionFor,
} from "../components/shared/ArtifactInspector/inspectorContract";

const SRC_DIR = resolve(__dirname, "..");
const TOKENS_FILE = join(SRC_DIR, "styles", "tokens.css");
const BREAKPOINT_HOOK_FILE = join(SRC_DIR, "hooks", "useBreakpoint.ts");
const TRACE_SPINE_CSS_FILE = join(
  SRC_DIR,
  "components",
  "shared",
  "TraceSpine",
  "TraceSpine.module.css",
);
const SPLIT_VIEW_TSX_FILE = join(SRC_DIR, "components", "SplitView", "SplitView.tsx");

/** JS map key → CSS custom property. Deliberately duplicated here: a map that
 *  silently drifts from the hook is exactly what this gate must catch. */
const BREAKPOINT_TOKEN_BY_KEY: Readonly<Record<string, string>> = {
  sm: "--bp-sm",
  md: "--bp-md",
  lg: "--bp-lg",
  sheetOpen: "--bp-sheetOpen",
  default: "--bp-default",
  xl: "--bp-xl",
};

/** Inspector alias → CSS custom property it must resolve to. */
const INSPECTOR_TOKEN_BY_KEY: Readonly<Record<string, string>> = {
  rail: "--bp-md",
  sheet: "--bp-lg",
  sheetOpen: "--bp-sheetOpen",
  default: "--bp-default",
  wide: "--bp-xl",
};

/**
 * `Npx` values that are intentionally not a `--bp-*` token. Every entry must
 * also be named in the vocabulary comment in `tokens.css` (asserted below),
 * so the allow-list cannot become a graveyard of forgotten exceptions.
 */
const DOCUMENTED_MAX_WIDTH_EXCEPTIONS: ReadonlyMap<number, string> = new Map([
  [
    359,
    "InspectorShell R5 tab strip: --inspector-w-wide (360px, spec §4.2) minus 1 — the R5 boundary is the inspector width scale, not a --bp-* layout token.",
  ],
  [
    900,
    "CreateFormFieldsSection two-column collapse: registered form-density threshold (UI-003 exception) kept at its historical value to avoid a boundary change.",
  ],
  [
    1023,
    "InspectorShell R4 sheet: --bp-lg (1024px) minus 1 — one pixel below the sidebar/lg breakpoint.",
  ],
]);

/** Parse every `--bp-*: Npx;` declaration from tokens.css. */
function parseBreakpointTokens(tokensCss: string): Map<string, number> {
  const out = new Map<string, number>();
  const pattern = /^\s*(--bp-[a-zA-Z0-9-]+)\s*:\s*(\d+)px\s*;/gm;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(tokensCss)) !== null) {
    out.set(match[1], Number(match[2]));
  }
  return out;
}

/** Extract the numeric literal pairs of `export const BREAKPOINTS = { ... } as const;`. */
function extractBreakpointMap(source: string): Record<string, number> {
  const declaration =
    /export\s+const\s+BREAKPOINTS\s*(?::[^=]+)?=\s*\{([\s\S]*?)\n\}\s*as\s+const\s*;/.exec(
      source,
    );
  expect(
    declaration,
    "hooks/useBreakpoint.ts must export `BREAKPOINTS = { ... } as const;` with one `key: <number>,` per line",
  ).not.toBeNull();

  const out: Record<string, number> = {};
  const pairPattern = /^\s*([a-zA-Z][a-zA-Z0-9]*)\s*:\s*(\d+)\s*,/gm;
  let match: RegExpExecArray | null;
  while ((match = pairPattern.exec(declaration![1])) !== null) {
    out[match[1]] = Number(match[2]);
  }
  return out;
}

/** Recursively collect every `.css` file under `dir`. */
function collectCssFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) out.push(...collectCssFiles(full));
    else if (entry.endsWith(".css")) out.push(full);
  }
  return out;
}

interface MediaLiteral {
  value: number;
  file: string;
  line: number;
}

/** Collect all `@media … (max-width: Npx)` literals with their location. */
function collectMaxWidthLiterals(): MediaLiteral[] {
  const out: MediaLiteral[] = [];
  const pattern = /@media[^{}]*\(max-width:\s*(\d+)px\)/g;
  for (const file of collectCssFiles(SRC_DIR)) {
    const lines = readFileSync(file, "utf-8").split("\n");
    lines.forEach((line, index) => {
      pattern.lastIndex = 0;
      let match: RegExpExecArray | null;
      while ((match = pattern.exec(line)) !== null) {
        out.push({ value: Number(match[1]), file, line: index + 1 });
      }
    });
  }
  return out;
}

describe("breakpoint token gate (S3.2 WP-2 / UI-003 / R2S-006)", () => {
  const tokensCss = readFileSync(TOKENS_FILE, "utf-8");
  const tokens = parseBreakpointTokens(tokensCss);

  it("defines the six --bp-* tokens in styles/tokens.css", () => {
    for (const name of Object.values(BREAKPOINT_TOKEN_BY_KEY)) {
      expect(tokens.has(name), `missing custom property ${name} in tokens.css`).toBe(true);
    }
    // The four original layout tokens keep their exact value (issue #160).
    expect(tokens.get("--bp-sm")).toBe(640);
    expect(tokens.get("--bp-md")).toBe(768);
    expect(tokens.get("--bp-lg")).toBe(1024);
    expect(tokens.get("--bp-xl")).toBe(1600);
  });

  it("mirrors every JS breakpoint constant in the CSS custom property", () => {
    expect(
      existsSync(BREAKPOINT_HOOK_FILE),
      "hooks/useBreakpoint.ts must exist — the JS breakpoint vocabulary is the gate's second source",
    ).toBe(true);

    const jsMap = extractBreakpointMap(readFileSync(BREAKPOINT_HOOK_FILE, "utf-8"));
    for (const [key, token] of Object.entries(BREAKPOINT_TOKEN_BY_KEY)) {
      expect(jsMap[key], `useBreakpoint.ts is missing BREAKPOINTS.${key}`).toBeDefined();
      expect(
        jsMap[key],
        `BREAKPOINTS.${key} (${jsMap[key]}) must equal ${token} (${tokens.get(token)})`,
      ).toBe(tokens.get(token));
    }
    expect(Object.keys(jsMap).sort()).toEqual(Object.keys(BREAKPOINT_TOKEN_BY_KEY).sort());
  });

  it("derives INSPECTOR_BREAKPOINTS from tokens, with no unbacked literals", () => {
    for (const [key, token] of Object.entries(INSPECTOR_TOKEN_BY_KEY)) {
      expect(
        INSPECTOR_BREAKPOINTS[key as keyof typeof INSPECTOR_BREAKPOINTS],
        `INSPECTOR_BREAKPOINTS.${key} must equal ${token}`,
      ).toBe(tokens.get(token));
    }
  });

  it("uses a token value or a documented exception for every @media max-width literal", () => {
    const tokenValues = new Set(tokens.values());
    const offenders = collectMaxWidthLiterals().filter(
      ({ value }) => !tokenValues.has(value) && !DOCUMENTED_MAX_WIDTH_EXCEPTIONS.has(value),
    );
    const details = offenders
      .map(({ value, file, line }) => `  ${value}px at ${relative(SRC_DIR, file)}:${line}`)
      .join("\n");
    expect(
      offenders,
      `undocumented @media max-width literal(s):\n${details}`,
    ).toEqual([]);
  });

  it("keeps every documented exception explained in the tokens.css vocabulary", () => {
    for (const value of DOCUMENTED_MAX_WIDTH_EXCEPTIONS.keys()) {
      expect(
        tokensCss,
        `${value}px is allow-listed in the gate but not documented in tokens.css`,
      ).toContain(`${value}px`);
    }
  });

  it.each([
    [767, "R5"],
    [768, "R4"],
    [1023, "R4"],
    [1024, "R3"],
    [1279, "R3"],
    [1280, "R3"],
    [1439, "R3"],
    [1440, "R2"],
    [1599, "R2"],
    [1600, "R1"],
  ])("freezes inspectorRegionFor(%i) at %s", (width, region) => {
    expect(inspectorRegionFor(width)).toBe(region);
  });

  it("freezes the R3 sheet-open boundary at 1280px", () => {
    expect(inspectorDefaultsOpen("R3", 1279)).toBe(false);
    expect(inspectorDefaultsOpen("R3", 1280)).toBe(true);
  });
});

/**
 * Schnitt 2c (Task 6) — removal of the three obsolete spine-breakpoint
 * mechanisms. The footer component is always horizontal now, no host feeds
 * the SplitView `spine` slot any more, and `--bp-lg` belongs to the inspector
 * alone. These gates are intentionally source-level (jsdom has `css: false`).
 */
describe("trace-spine footer breakpoint cleanup (Schnitt 2c / Task 6)", () => {
  const traceSpineCss = readFileSync(TRACE_SPINE_CSS_FILE, "utf-8");
  const splitViewSrc = readFileSync(SPLIT_VIEW_TSX_FILE, "utf-8");
  const tokensCssForCleanup = readFileSync(TOKENS_FILE, "utf-8");
  const tokensForCleanup = parseBreakpointTokens(tokensCssForCleanup);

  it("drops the TraceSpine vertical-to-horizontal footer media query", () => {
    expect(
      traceSpineCss,
      "@media (max-width: 1024px) turned the rail horizontal — obsolete now that <TraceSpineFooter> is always horizontal",
    ).not.toMatch(/@media[^{}]*\(max-width:\s*1024px\)/);
    expect(traceSpineCss).not.toMatch(/\.rail\s*\{[^}]*overflow-x:\s*auto/);
    expect(traceSpineCss).not.toContain("flex-wrap: nowrap");
  });

  it("removes SplitView's spineIsHorizontal / NARROW_RATIO logic", () => {
    expect(splitViewSrc).not.toContain("spineIsHorizontal");
    expect(splitViewSrc).not.toContain("NARROW_RATIO");
  });

  it("removes the unoccupied spine slot from SplitView entirely", () => {
    const spineLines = splitViewSrc
      .split("\n")
      .filter((line) => /spine/i.test(line));
    expect(
      spineLines,
      "no host passes spine= since Schnitt 2b — the slot, its testid and its styles must be gone",
    ).toEqual([]);
  });

  it("keeps --bp-lg registered for the inspector, with no spine in its vocabulary", () => {
    expect(tokensForCleanup.get("--bp-lg")).toBe(1024);
    const vocabulary = tokensCssForCleanup.slice(
      tokensCssForCleanup.indexOf("Layout breakpoints"),
      tokensCssForCleanup.indexOf("--bp-sm: 640px;"),
    );
    expect(vocabulary).toMatch(/inspector/i);
    expect(
      vocabulary,
      "the --bp-lg vocabulary must no longer mention the trace spine",
    ).not.toMatch(/spine/i);
  });
});
