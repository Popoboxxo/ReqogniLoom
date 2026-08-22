/**
 * WCAG 2.1 AA contrast tests for every registered theme (multi-palette
 * theming Phase 3, Task 3, issue #568).
 *
 * `styles/tokens.css`'s own header promises that "every new theme runs the
 * same 4.5:1 contrast check as ch. 8.5 before it is released" — until this
 * file that check was a manual, undocumented step. Nothing verified it for
 * ANY theme, including the two pre-existing ones (`dark`/`light`), so this
 * test covers all five.
 *
 * What it does, end to end:
 *   1. reads the REAL `styles/tokens.css` (no fixture copy — a fixture would
 *      drift silently from the file the app actually ships),
 *   2. parses it into one `{token -> raw value}` map per theme, applying the
 *      same cascade a browser applies (`:root[data-theme="x"]` overlays the
 *      bare `:root` blocks, so a theme block inherits the shared primitive
 *      pool without redeclaring it),
 *   3. walks each var() reference chain down to a literal `#hex` / `rgba(...)`
 *      value (written without a concrete token name on purpose — the sibling
 *      `design-tokens.test.ts` scanner treats any literal var() reference in
 *      any source file, comments included, as a real token usage),
 *   4. alpha-composites translucent values over the SAME theme's own
 *      `--color-surface` (the dark-style badge fills are `rgba(..., 0.2)`;
 *      their effective rendered contrast is nothing like their full-opacity
 *      hex, so skipping this step would silently over-report every dark
 *      theme's badge contrast),
 *   5. computes the WCAG 2.1 relative luminance / contrast ratio and asserts
 *      >= 4.5:1 for the foreground/background token pairs below.
 *
 * No new dependency: the WCAG math is ~15 lines and fully specified in
 * https://www.w3.org/TR/WCAG21/#dfn-relative-luminance and #dfn-contrast-ratio.
 *
 * Pairs that do not clear AA today are pinned at their exact measured ratio
 * in `KNOWN_AA_SHORTFALLS` rather than excluded — see the comment there.
 *
 * Set `CONTRAST_TABLE=1` when running this file to print the full measured
 * ratio table (used for the Phase 3 task reports):
 *   cd frontend && CONTRAST_TABLE=1 npx vitest run src/test/theme-contrast.test.ts
 */
import { readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const TOKENS_FILE = join(resolve(__dirname, ".."), "styles", "tokens.css");

/** WCAG 2.1 AA minimum for normal-size text. */
const AA_MIN_RATIO = 4.5;

/** Every theme id the app ships (`dark` lives on the bare `:root` block). */
const THEME_IDS = ["dark", "light", "bauhaus", "nordic", "sepia"] as const;
type ThemeId = (typeof THEME_IDS)[number];

/**
 * Foreground/background token pairs that carry text and therefore must clear
 * AA. Deliberately NOT an exhaustive sweep of all 72 tokens: only pairs where
 * this codebase actually paints one token's color as text on the other's
 * background (see StatusBadge, the badge variants in `global.css`, and the
 * primary-button rule set).
 *
 * 3rd element: the backdrop token a translucent `bg` composites over —
 * `--color-surface` (the page background) for every pair above. Task 10
 * (contrast remediation, GESAMTTEST_BERICHT_2026-08-21 §5 findings 4-5)
 * added the sidebar/nav-chrome pairs below, which live on `--color-nav-bg`
 * instead — a permanently-dark chrome background that does NOT track
 * `--color-surface` (it is frozen to the same navy value in all 5 themes),
 * so those two explicitly override it. Always written out (rather than left
 * optional) — an optional tuple element made `it.each`'s inferred parameter
 * types collapse to `string | undefined` for every element, not just the
 * omitted one.
 */
const CONTRAST_PAIRS: ReadonlyArray<readonly [fg: string, bg: string, backdrop: string]> = [
  ["--color-text", "--color-surface", "--color-surface"],
  ["--color-on-primary", "--color-primary", "--color-surface"],
  ["--color-badge-success-text", "--color-badge-success-bg", "--color-surface"],
  ["--color-badge-danger-text", "--color-badge-danger-bg", "--color-surface"],
  ["--color-badge-warning-text", "--color-badge-warning-bg", "--color-surface"],
  ["--color-badge-neutral-text", "--color-badge-neutral-bg", "--color-surface"],
  ["--color-badge-info-text", "--color-badge-info-bg", "--color-surface"],
  // Task 10: --color-text-muted-on-surface (GESAMTTEST_BERICHT_2026-08-21
  // §10.1 — was failing in bauhaus/sepia specifically, 4.21:1/3.80:1).
  ["--color-text-muted", "--color-surface", "--color-surface"],
  // Task 10: SidebarNavigation.module.css's .buildVersion (was
  // --color-text-muted at 70% opacity — 1.69-3.85:1 in all 5 themes) now
  // uses --color-nav-text-muted, the token this file's own .terminologyLabel
  // sibling already used for the same role.
  ["--color-nav-text-muted", "--color-nav-bg", "--color-nav-bg"],
  // Task 10: .presetBadge (was --color-primary on a hardcoded translucent
  // royal-blue chip — 2.06:1 in 4 of 5 themes) now uses the dedicated,
  // frozen --color-nav-badge-* pair sized for the sidebar chrome.
  ["--color-nav-badge-text", "--color-nav-badge-bg", "--color-nav-bg"],
];

/* ==========================================================================
 * tokens.css parsing
 * ========================================================================== */

interface CssBlock {
  /** `null` for a bare `:root {}` block, else the `data-theme` value. */
  theme: string | null;
  body: string;
}

/**
 * Split `tokensCss` into its top-level `:root {...}` /
 * `:root[data-theme="id"] {...}` blocks.
 *
 * Comments are blanked of braces first: declaration values never contain a
 * literal `{`/`}`, but the file's doc comments occasionally do, and a naive
 * non-greedy match would stop at the first one. (Same approach as the sibling
 * scanner in `design-tokens.test.ts`; duplicated rather than shared so each
 * test file stays self-contained, matching this suite's existing style.)
 */
function collectCssBlocks(tokensCss: string): CssBlock[] {
  const withoutComments = tokensCss.replace(/\/\*[\s\S]*?\*\//g, (comment) =>
    comment.replace(/[{}]/g, " "),
  );

  const blocks: CssBlock[] = [];
  const selectorPattern = /:root(?:\[data-theme="([a-zA-Z0-9_-]+)"\])?\s*\{/g;
  let match: RegExpExecArray | null;
  while ((match = selectorPattern.exec(withoutComments)) !== null) {
    const bodyStart = selectorPattern.lastIndex;
    let depth = 1;
    let i = bodyStart;
    while (i < withoutComments.length && depth > 0) {
      if (withoutComments[i] === "{") depth++;
      else if (withoutComments[i] === "}") depth--;
      i++;
    }
    blocks.push({ theme: match[1] ?? null, body: withoutComments.slice(bodyStart, i - 1) });
    selectorPattern.lastIndex = i;
  }
  return blocks;
}

/** `--name: value` declarations of a block body, in source order. */
function collectDeclarations(body: string): Array<[string, string]> {
  const out: Array<[string, string]> = [];
  const pattern = /(--[a-zA-Z0-9-]+)\s*:\s*([^;]+);/g;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(body)) !== null) {
    out.push([match[1], match[2].trim()]);
  }
  return out;
}

/**
 * Build one `{token -> raw value}` map per theme, mirroring the browser
 * cascade: the bare `:root` blocks (primitive pool + `dark` semantics +
 * theme-independent tokens) form the base, and each
 * `:root[data-theme="id"]` block overlays it. So `nordic`'s map still sees
 * every `--palette-*` primitive, and `dark`'s map is simply the base itself.
 */
function buildThemeMaps(tokensCss: string): Record<ThemeId, Map<string, string>> {
  const blocks = collectCssBlocks(tokensCss);

  const base = new Map<string, string>();
  for (const block of blocks) {
    if (block.theme !== null) continue;
    for (const [name, value] of collectDeclarations(block.body)) base.set(name, value);
  }

  const maps = {} as Record<ThemeId, Map<string, string>>;
  for (const themeId of THEME_IDS) {
    const map = new Map(base);
    if (themeId !== "dark") {
      const block = blocks.find((b) => b.theme === themeId);
      if (!block) throw new Error(`tokens.css has no :root[data-theme="${themeId}"] block`);
      for (const [name, value] of collectDeclarations(block.body)) map.set(name, value);
    }
    maps[themeId] = map;
  }
  return maps;
}

/* ==========================================================================
 * var() chain resolution + color parsing
 * ========================================================================== */

interface Rgba {
  r: number;
  g: number;
  b: number;
  a: number;
}

const VAR_REFERENCE = /^var\(\s*(--[a-zA-Z0-9-]+)\s*\)$/;

/**
 * Follow a var() reference chain (e.g. `--color-badge-danger-bg` ->
 * `--palette-bauhaus-terracotta-100` -> `#f4eceb`) until a literal
 * value is reached. Throws on an unknown token or a reference cycle rather
 * than returning a silent fallback — either would be a real bug in
 * `tokens.css`, and a silent fallback is exactly what the sibling
 * `design-tokens.test.ts` exists to prevent.
 */
function resolveRawValue(map: Map<string, string>, token: string): string {
  const seen = new Set<string>();
  let current = token;
  for (;;) {
    if (seen.has(current)) {
      throw new Error(`var() reference cycle at ${current} (chain: ${[...seen].join(" -> ")})`);
    }
    seen.add(current);
    const value = map.get(current);
    if (value === undefined) throw new Error(`token ${current} is not defined in tokens.css`);
    const reference = VAR_REFERENCE.exec(value);
    if (!reference) return value;
    current = reference[1];
  }
}

/** Parse `#rgb`, `#rrggbb`, `rgb(r, g, b)` or `rgba(r, g, b, a)`. */
function parseColor(value: string): Rgba {
  const hex = /^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.exec(value.trim());
  if (hex) {
    const digits =
      hex[1].length === 3
        ? hex[1]
            .split("")
            .map((c) => c + c)
            .join("")
        : hex[1];
    return {
      r: parseInt(digits.slice(0, 2), 16),
      g: parseInt(digits.slice(2, 4), 16),
      b: parseInt(digits.slice(4, 6), 16),
      a: 1,
    };
  }

  const functional = /^rgba?\(([^)]+)\)$/.exec(value.trim());
  if (functional) {
    const parts = functional[1].split(",").map((p) => Number(p.trim()));
    if (parts.length >= 3 && parts.every((n) => Number.isFinite(n))) {
      return { r: parts[0], g: parts[1], b: parts[2], a: parts.length > 3 ? parts[3] : 1 };
    }
  }

  throw new Error(`cannot parse color value: ${value}`);
}

/**
 * Source-over composite of a translucent `top` onto an opaque `bottom` —
 * what the browser actually paints, and therefore what the eye actually
 * sees. Both the dark base theme and `nordic` build their badge fills from
 * `rgba(..., 0.2)` primitives over the page surface.
 */
function compositeOver(top: Rgba, bottom: Rgba): Rgba {
  return {
    r: top.r * top.a + bottom.r * (1 - top.a),
    g: top.g * top.a + bottom.g * (1 - top.a),
    b: top.b * top.a + bottom.b * (1 - top.a),
    a: 1,
  };
}

/**
 * Fully resolve `token` for `themeId` into the opaque color a browser paints:
 * walk the `var()` chain, then, if the result is translucent, composite it
 * over `backdrop` (the theme's own already-resolved `--color-surface`).
 */
function resolveRenderedColor(map: Map<string, string>, token: string, backdrop: Rgba): Rgba {
  const color = parseColor(resolveRawValue(map, token));
  return color.a >= 1 ? color : compositeOver(color, backdrop);
}

/** A theme's `--color-surface`, which must itself be opaque (it is the page). */
function resolveSurface(map: Map<string, string>): Rgba {
  return resolveBackdrop(map, "--color-surface");
}

/**
 * Resolve any token to use as a compositing backdrop — must itself be
 * opaque, since a translucent backdrop would need a backdrop of its own.
 * Generalizes `resolveSurface` (Task 10, contrast remediation) so
 * nav-chrome pairs can composite over `--color-nav-bg` instead of the page
 * `--color-surface`.
 */
function resolveBackdrop(map: Map<string, string>, token: string): Rgba {
  const color = parseColor(resolveRawValue(map, token));
  if (color.a < 1) throw new Error(`${token} must be an opaque color to use as a compositing backdrop`);
  return color;
}

/* ==========================================================================
 * WCAG 2.1 math (https://www.w3.org/TR/WCAG21/#dfn-relative-luminance)
 * ========================================================================== */

/** sRGB 8-bit channel -> linear-light value. */
function linearize(channel8Bit: number): number {
  const c = channel8Bit / 255;
  return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
}

/** WCAG relative luminance of an opaque color. */
function relativeLuminance({ r, g, b }: Rgba): number {
  return 0.2126 * linearize(r) + 0.7152 * linearize(g) + 0.0722 * linearize(b);
}

/** WCAG contrast ratio, 1:1 .. 21:1. Argument order does not matter. */
function contrastRatio(a: Rgba, b: Rgba): number {
  const [lighter, darker] = [relativeLuminance(a), relativeLuminance(b)].sort((x, y) => y - x);
  return (lighter + 0.05) / (darker + 0.05);
}

/**
 * Pairs that do NOT clear AA today, recorded with their exact measured ratio
 * instead of being silently excluded — this suite's established ratchet
 * philosophy (see `ui-ratchet.test.ts`): measure reality, pin it, make any
 * movement in either direction fail loudly.
 *
 * A recorded entry is a known defect, not a blessing. `themeContrastFloor`
 * below asserts the exact value, so the pair cannot quietly get worse, and
 * `known shortfalls are still shortfalls` asserts it is still below AA, so a
 * fixed pair fails until its entry is deleted here.
 */
const KNOWN_AA_SHORTFALLS: Record<string, { ratio: number; note: string }> = {
  // 2026-08-21 fix: `dark`'s --color-primary now points at indigo-600 (was
  // indigo-500), the same darkening `light` already used for this exact
  // reason. white-on-indigo-600 measures 6.29:1 — the "dark|on-primary|
  // primary" entry that used to live here is gone; see tokens.css's own
  // comment at --color-primary (dark block) for the fix's history.
};

/* ==========================================================================
 * Tests
 * ========================================================================== */

const themeMaps = buildThemeMaps(readFileSync(TOKENS_FILE, "utf-8"));

/**
 * Measured ratio for one token pair in one theme, rounded to 2 decimals.
 * `backdropToken` defaults to `--color-surface` (correct for every
 * page-level pair); pass an override for chrome that lives on a different,
 * non-`--color-surface`-tracking background (Task 10).
 */
function measure(
  themeId: ThemeId,
  fgToken: string,
  bgToken: string,
  backdropToken?: string,
): number {
  const map = themeMaps[themeId];
  const backdrop = resolveBackdrop(map, backdropToken ?? "--color-surface");
  const bg = resolveRenderedColor(map, bgToken, backdrop);
  const fg = resolveRenderedColor(map, fgToken, bg);
  return Math.round(contrastRatio(fg, bg) * 100) / 100;
}

describe("WCAG AA contrast per theme (theming phase 3, Task 3, #568)", () => {
  it("resolves a var() chain down to the literal primitive value", () => {
    // Sanity check on the resolver itself: a 3-link chain, an alpha
    // composite, and the theme cascade (nordic inherits --palette-white from
    // the bare :root primitive block it never redeclares).
    expect(resolveRawValue(themeMaps.bauhaus, "--color-badge-danger-bg")).toBe("#f4eceb");
    expect(resolveRawValue(themeMaps.nordic, "--color-on-primary")).toBe("#ffffff");
    expect(resolveRawValue(themeMaps.nordic, "--color-badge-success-bg")).toBe(
      "rgba(163, 190, 140, 0.2)",
    );
    // 20% #A3BE8C (163, 190, 140) over the #1B2430 (27, 36, 48) surface:
    // 0.2*163 + 0.8*27 = 54.2 / 0.2*190 + 0.8*36 = 66.8 / 0.2*140 + 0.8*48 = 66.4
    expect(
      resolveRenderedColor(
        themeMaps.nordic,
        "--color-badge-success-bg",
        resolveSurface(themeMaps.nordic),
      ),
    ).toEqual({ r: 54.2, g: 66.8, b: 66.4, a: 1 });
  });

  it("computes the WCAG reference ratios (black/white = 21:1, identical colors = 1:1)", () => {
    const black = { r: 0, g: 0, b: 0, a: 1 };
    const white = { r: 255, g: 255, b: 255, a: 1 };
    expect(contrastRatio(black, white)).toBeCloseTo(21, 5);
    expect(contrastRatio(white, black)).toBeCloseTo(21, 5);
    expect(contrastRatio(black, black)).toBeCloseTo(1, 5);
    // Independent spot check against a published value: #767676 on white is
    // the canonical "just passes AA" gray (4.54:1).
    expect(contrastRatio({ r: 118, g: 118, b: 118, a: 1 }, white)).toBeCloseTo(4.54, 2);
  });

  describe.each(THEME_IDS)("theme '%s'", (themeId) => {
    it.each(CONTRAST_PAIRS)("%s on %s meets its contrast floor", (fgToken, bgToken, backdropToken) => {
      const ratio = measure(themeId, fgToken, bgToken, backdropToken);
      const known = KNOWN_AA_SHORTFALLS[`${themeId}|${fgToken}|${bgToken}`];

      if (known) {
        expect(
          ratio,
          `theme '${themeId}': ${fgToken} on ${bgToken} is a recorded AA shortfall pinned at ${known.ratio}:1 (${known.note}) but now measures ${ratio}:1 — if this improved, delete the KNOWN_AA_SHORTFALLS entry; if it got worse, fix the palette`,
        ).toBe(known.ratio);
        return;
      }

      expect(
        ratio,
        `theme '${themeId}': ${fgToken} on ${bgToken} measures ${ratio}:1, below the WCAG AA minimum of ${AA_MIN_RATIO}:1`,
      ).toBeGreaterThanOrEqual(AA_MIN_RATIO);
    });
  });

  it("every recorded shortfall is still an actual shortfall", () => {
    for (const [key, known] of Object.entries(KNOWN_AA_SHORTFALLS)) {
      const [themeId, fgToken, bgToken] = key.split("|") as [ThemeId, string, string];
      expect(
        measure(themeId, fgToken, bgToken),
        `${key} is recorded as a known AA shortfall but now clears ${AA_MIN_RATIO}:1 — delete its KNOWN_AA_SHORTFALLS entry so the pair is held to the full AA bar again`,
      ).toBeLessThan(AA_MIN_RATIO);
      expect(known.note.length).toBeGreaterThan(0);
    }
  });

  // Opt-in reporting aid, not an assertion — prints the full measured matrix
  // so a palette change can be reviewed quantitatively, not just pass/fail.
  it("prints the full ratio matrix when CONTRAST_TABLE=1", () => {
    // Reached through `globalThis` rather than the bare `process` global:
    // this package's tsconfig deliberately ships no `@types/node`, so the
    // bare identifier would be an unresolved name here.
    const env = (globalThis as { process?: { env?: Record<string, string | undefined> } }).process
      ?.env;
    if (!env?.CONTRAST_TABLE) return;
    const rows = THEME_IDS.flatMap((themeId) =>
      CONTRAST_PAIRS.map(([fg, bg, backdrop]) => ({
        theme: themeId,
        pair: `${fg} / ${bg}`,
        ratio: measure(themeId, fg, bg, backdrop),
        pass: measure(themeId, fg, bg, backdrop) >= AA_MIN_RATIO,
      })),
    );
    console.table(rows);
    expect(rows).toHaveLength(THEME_IDS.length * CONTRAST_PAIRS.length);
  });
});
