/**
 * Interactive hit-target contract (issue #1395, WCAG 2.2 AA SC 2.5.8).
 *
 * jsdom has no layout engine, so a rendered box cannot be asserted here. Like
 * `theme-contrast.test.ts` (its `rulesFor()` helper) and
 * `responsive-card-grids.test.ts`, this suite asserts the *stylesheet
 * declarations* that decide the box instead, and resolves the referenced
 * custom property to real pixels so "uses a token" cannot silently mean
 * "uses a 20px token".
 *
 * Why exactly these controls:
 * - `<IdChip>`'s copy button and the Requirement list's per-row delete trigger
 *   were the two measured failures (24x20 and 22x22). Both capped their own
 *   box below the inherited `.btn-*` geometry, so the floor has to live in
 *   their own rule — a descendant/global rule cannot win against it.
 * - The Requirement detail's section toggles and the TraceSpine verification
 *   badge carry no geometry of their own; they are >=24px because they keep
 *   the `btn-ghost` chrome (`min-height: --btn-h-md` in global.css). That
 *   composition is pinned so a later rewrite cannot strip the class and
 *   silently reintroduce the 20/23.6px boxes without a red test.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const SRC_DIR = join(__dirname, "..");
const TOKENS_CSS = readFileSync(join(SRC_DIR, "styles", "tokens.css"), "utf-8");
const GLOBAL_CSS = readFileSync(join(SRC_DIR, "styles", "global.css"), "utf-8");

/** WCAG 2.2 SC 2.5.8 minimum target size, in CSS px. */
const HIT_TARGET_MIN_PX = 24;

function readSource(relativePath: string): string {
  return readFileSync(join(SRC_DIR, relativePath), "utf-8");
}

/** First declaration block of the given selector (same shape as theme-contrast's `rulesFor`). */
function rulesFor(css: string, selector: string): string {
  const match = new RegExp(`${selector.replace(/\./g, "\\.")}\\s*\\{([^}]*)\\}`).exec(css);
  if (match === null) throw new Error(`no rule for ${selector}`);
  return match[1];
}

/** The `--name: <value>` declaration of a token, or null when undefined. */
function tokenValue(css: string, name: string): string | null {
  const match = new RegExp(`^\\s*${name}\\s*:\\s*([^;]+);`, "m").exec(css);
  return match === null ? null : match[1].trim();
}

/**
 * Resolve a spacing/size token to CSS px. Only the two units the token file
 * actually uses are supported (`rem` against the 16px default root the app
 * never overrides, and `px`); anything else fails loudly so a unit change is
 * not silently read as 0.
 */
function tokenPx(css: string, name: string): number {
  const raw = tokenValue(css, name);
  if (raw === null) throw new Error(`token ${name} is not defined`);
  const value = /^(\d*\.?\d+)(rem|px)$/.exec(raw);
  if (value === null) throw new Error(`token ${name} has unsupported value '${raw}'`);
  return Number(value[1]) * (value[2] === "rem" ? 16 : 1);
}

/** `min-height`/`min-width` of a rule, resolved through its token. */
function declaredFloor(ruleBody: string, property: "min-height" | "min-width"): number {
  const match = new RegExp(`${property}\\s*:\\s*var\\((--[a-z0-9-]+)\\)`).exec(ruleBody);
  if (match === null) throw new Error(`no token-based ${property} in rule`);
  return tokenPx(TOKENS_CSS, match[1]);
}

describe("interactive hit targets meet WCAG 2.2 SC 2.5.8 (issue #1395)", () => {
  it("builds every floored control on a token that is at least 24px", () => {
    // The fix reuses the existing spacing scale instead of introducing a new
    // size token: --space-6 is the first step at or above the WCAG minimum.
    expect(tokenPx(TOKENS_CSS, "--space-6")).toBeGreaterThanOrEqual(HIT_TARGET_MIN_PX);
    // The button scale starts above the minimum too, which is why a control
    // that keeps the shared `.btn-*` chrome needs no floor of its own.
    expect(tokenPx(TOKENS_CSS, "--btn-h-sm")).toBeGreaterThanOrEqual(HIT_TARGET_MIN_PX);
  });

  it("floors the IdChip copy control at 24x24 (was 24x20)", () => {
    const rule = rulesFor(readSource("components/shared/IdChip/IdChip.module.css"), ".copyButton");

    expect(declaredFloor(rule, "min-height")).toBeGreaterThanOrEqual(HIT_TARGET_MIN_PX);
    expect(declaredFloor(rule, "min-width")).toBeGreaterThanOrEqual(HIT_TARGET_MIN_PX);
    // The 20px (--space-5) cap this control used to carry must not come back:
    // it beat the inherited `.btn-sm` min-height by cascade order.
    expect(rule).not.toMatch(/min-height\s*:\s*var\(--space-5\)/);
  });

  it("floors the Requirement list delete control at 24x24 (was 22x22)", () => {
    const rule = rulesFor(
      readSource("components/RequirementEditors/RequirementList.module.css"),
      ".deleteButton",
    );

    expect(declaredFloor(rule, "min-height")).toBeGreaterThanOrEqual(HIT_TARGET_MIN_PX);
    expect(declaredFloor(rule, "min-width")).toBeGreaterThanOrEqual(HIT_TARGET_MIN_PX);
    // A fixed pixel box was what made it 22x22; only the token floors remain.
    expect(rule).not.toMatch(/(^|[^-])(width|height)\s*:\s*\d+px/);
    // The 14px glyph must stay legible and centred, not be shrunk to fit.
    expect(rule).toMatch(/justify-content\s*:\s*center/);
  });

  it("keeps the shared btn-ghost chrome on the detail-route disclosure controls", () => {
    // These two controls declare no height of their own: their >=24px box
    // comes entirely from `.btn-ghost`'s `min-height: var(--btn-h-md)`. Pin
    // both halves of that composition.
    const base = rulesFor(GLOBAL_CSS, ".btn-ghost");
    expect(base).toMatch(/min-height\s*:\s*var\(--btn-h-md\)/);
    expect(tokenPx(TOKENS_CSS, "--btn-h-md")).toBeGreaterThanOrEqual(HIT_TARGET_MIN_PX);

    const sections = readSource("components/shared/ArtifactForm/ArtifactSections.tsx");
    expect(sections).toContain("`btn-ghost ${styles.sectionHeader}`");

    const traceSpine = readSource("components/shared/TraceSpine/TraceSpine.tsx");
    expect(traceSpine).toMatch(/className=\{`btn-ghost \$\{/);
  });
});
