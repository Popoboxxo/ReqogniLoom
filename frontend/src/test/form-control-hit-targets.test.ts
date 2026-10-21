/**
 * WCAG 2.2 AA SC 2.5.8 Target Size (Minimum) for radio/checkbox controls —
 * GitHub #1394.
 *
 * MEASURED DEFECT (issue #1394, `getBoundingClientRect`, dpr 1)
 * ------------------------------------------------------------
 * Every `<input type="radio">`/`<input type="checkbox">` on /settings,
 * /system-settings, /requirements and /architecture renders a 13x13 CSS-px box.
 * A visible `<label>` already wraps the input and is the real click target, but
 * the *net* control — what SC 2.5.8 measures — stays under 24x24 because the
 * wrapping label has no height floor of its own: it is a flex row whose height
 * is the 13px glyph plus its `gap`, i.e. ~13-15px.
 *
 * THE FIX keeps the native glyph at its default size and floors the CLICKABLE
 * label at 24x24 (`min-height`/`min-width` from the spacing scale). This suite
 * asserts the stylesheet declarations that decide that box — jsdom has no
 * layout engine, so this follows the same technique as
 * `interactive-hit-targets.test.ts` (#1395) and `theme-contrast.test.ts`:
 * read the rule, resolve the referenced token to real pixels so "uses a token"
 * cannot quietly mean "uses a 20px token".
 *
 * Why one assertion per module rather than one shared class: each of these
 * label rules lives in a different layout context (a full-width option card, a
 * padded settings row, a dense inline checkbox row, a dialog acknowledgement
 * row). A descendant/global rule cannot win against their own declarations, so
 * the floor has to live in each rule — exactly the conclusion #1395 reached for
 * its two capped controls.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const SRC_DIR = join(__dirname, "..");
const TOKENS_CSS = readFileSync(join(SRC_DIR, "styles", "tokens.css"), "utf-8");

/** WCAG 2.2 SC 2.5.8 minimum target size, in CSS px. */
const HIT_TARGET_MIN_PX = 24;

function readSource(relativePath: string): string {
  return readFileSync(join(SRC_DIR, relativePath), "utf-8");
}

export interface CssRule {
  selector: string;
  body: string;
  /** The enclosing `@media`/`@supports` prelude, or `null` for a top-level rule. */
  container: string | null;
}

/**
 * Index of the `}` that closes the `{` at `openIndex`, counting nesting.
 *
 * Declaration bodies contain no braces, but a container body (`@media`) does,
 * which is why a plain `indexOf("}")` cannot answer this.
 */
function matchingBrace(source: string, openIndex: number): number {
  let depth = 0;
  for (let index = openIndex; index < source.length; index += 1) {
    if (source[index] === "{") depth += 1;
    else if (source[index] === "}") {
      depth -= 1;
      if (depth === 0) return index;
    }
  }
  return -1;
}

/**
 * Every style rule of a CSS module, in source order, including rules nested in
 * `@media`/`@supports` containers (whose prelude is reported in `container`).
 *
 * A rule can be declared more than once (a later override, or a media-scoped
 * redefinition) and the FIRST match is not necessarily the one that applies —
 * see `rulesFor`. The earlier regex scan claimed to descend into `@media`, but
 * its `headerPattern.lastIndex = bodyStart` jumped past the container body, so
 * not a single nested rule was ever parsed: a media-scoped override that shrank
 * a floor below 24px was invisible to both `rulesFor`'s conflict check and the
 * "no rule sizes the glyph" invariant (N3). This walks braces instead, so
 * nesting is real and every nested rule carries its container.
 */
export function parseRules(css: string): CssRule[] {
  const source = css.replace(/\/\*[\s\S]*?\*\//g, "");
  const rules: CssRule[] = [];

  const walk = (start: number, end: number, container: string | null): void => {
    let index = start;
    while (index < end) {
      const brace = source.indexOf("{", index);
      if (brace === -1 || brace >= end) return;
      const selector = source.slice(index, brace).trim();
      const close = matchingBrace(source, brace);
      if (close === -1 || close > end) return;
      const body = source.slice(brace + 1, close);
      if (selector.startsWith("@media") || selector.startsWith("@supports")) {
        // Containers have no declarations of their own — recurse into the body.
        walk(brace + 1, close, container ?? selector);
      } else if (!selector.startsWith("@")) {
        rules.push({ selector, body, container });
      }
      // `@keyframes`/`@font-face` and friends are skipped whole: their inner
      // blocks are not selectors this suite reasons about.
      index = close + 1;
    }
  };

  walk(0, source.length, null);
  return rules;
}

/**
 * The declaration body that actually applies for `selector` — the LAST one, so
 * a later redefinition cannot neutralise the floor while an earlier one keeps
 * the assertion green (GitHub #1393 review, T2).
 *
 * A selector declared more than once with a *conflicting* `min-height` is a
 * hard failure: which one wins would depend on source order / media state, and
 * the assertion could not tell "floored" from "floored, then un-floored".
 */
export function rulesFor(css: string, selector: string): string {
  const all = parseRules(css);
  // A container-scoped redefinition could weaken the floor only in some
  // viewports (or neutralise it entirely) while a top-level rule keeps this
  // assertion green. The floor must be unconditional: fail on ANY `@media`
  // declaration of a target selector instead of trying to reason about which
  // media state applies (N3).
  const scoped = all.find((rule) => rule.selector === selector && rule.container !== null);
  if (scoped) {
    throw new Error(
      `${selector} is (re)declared inside ${scoped.container}; the 24px floor must live in a top-level rule`
    );
  }
  const blocks = all.filter((rule) => rule.selector === selector);
  if (blocks.length === 0) throw new Error(`no rule for ${selector}`);
  const floors = blocks
    .map((rule) => /min-height\s*:\s*([^;]+)/.exec(rule.body)?.[1]?.trim())
    .filter((value): value is string => value !== undefined);
  if (new Set(floors).size > 1) {
    throw new Error(
      `${selector} is declared with conflicting min-height values: ${[...new Set(floors)].join(", ")}`
    );
  }
  return blocks[blocks.length - 1].body;
}

function tokenValue(css: string, name: string): string | null {
  const match = new RegExp(`^\\s*${name}\\s*:\\s*([^;]+);`, "m").exec(css);
  return match === null ? null : match[1].trim();
}

/** Resolve a spacing token to CSS px (the token file only uses rem/px). */
function tokenPx(css: string, name: string): number {
  const raw = tokenValue(css, name);
  if (raw === null) throw new Error(`token ${name} is not defined`);
  const value = /^(\d*\.?\d+)(rem|px)$/.exec(raw);
  if (value === null) throw new Error(`token ${name} has unsupported value '${raw}'`);
  return Number(value[1]) * (value[2] === "rem" ? 16 : 1);
}

/** A `min-height`/`min-width` declaration resolved through its token, in px. */
function declaredFloor(ruleBody: string, property: "min-height" | "min-width"): number {
  const match = new RegExp(`${property}\\s*:\\s*var\\((--[a-z0-9-]+)\\)`).exec(ruleBody);
  if (match === null) throw new Error(`no token-based ${property} in rule`);
  return tokenPx(TOKENS_CSS, match[1]);
}

/**
 * One label rule that wraps a radio/checkbox. `route` and `selector` are named
 * per the issue's measurement so a future reader can map a red assertion back
 * to the route that failed.
 */
const WRAPPING_LABEL_RULES: ReadonlyArray<{
  route: string;
  file: string;
  selector: string;
  /** Test ids the rule is responsible for, for traceability. */
  controls: string;
}> = [
  {
    route: "/requirements, /architecture",
    file: "components/shared/IncludeDeletedToggle/IncludeDeletedToggle.module.css",
    selector: ".toggle",
    controls: "req-list-include-deleted, arch-list-include-deleted",
  },
  {
    route: "/settings",
    file: "components/WorkspaceSettings/WorkspaceSettings.module.css",
    selector: ".optionCard",
    controls: "preset-option-*, profile-option-*",
  },
  {
    route: "/settings",
    file: "components/WorkspaceSettings/WorkspaceSettings.module.css",
    selector: ".controlRow",
    controls: "goals-enabled-checkbox, goals-ai-enabled-checkbox",
  },
  {
    route: "/settings",
    file: "components/WorkspaceSettings/WorkspaceBannerSection.module.css",
    selector: ".checkboxLabel",
    controls: "workspace-banner-enabled-toggle, workspace-banner-level-*, workspace-banner-dismissible-toggle",
  },
  {
    route: "/system-settings",
    file: "components/SystemSettings/BannerSection.module.css",
    selector: ".checkboxLabel",
    controls: "banner-enabled-toggle, banner-level-*, banner-dismissible-toggle, banner-show-on-login-toggle",
  },
  {
    route: "/settings",
    file: "components/WorkspaceSettings/GlossaryReferenceSection.module.css",
    selector: ".optionRow",
    controls: "glossary-reference-mode-pinned, glossary-reference-mode-always_head",
  },
  {
    route: "/settings",
    file: "components/WorkspaceSettings/ContextGraphSettingsSection.module.css",
    selector: ".toggleLabel",
    controls: "context-graph-enabled-toggle",
  },
  {
    route: "/settings",
    file: "components/WorkspaceSettings/MemorySettingsSection.module.css",
    selector: ".toggleLabel",
    controls: "memory-settings-toggle",
  },
  // --- #1394 follow-up (GitHub #1393 review, B2): the remaining checkbox /
  // radio surfaces that still rendered 13-21px targets.
  {
    route: "/settings, /system-settings",
    file: "components/shared/CreateFormFields/CreateFormFieldsSection.module.css",
    selector: ".checkboxLabel",
    controls:
      "create-form-visible-*, create-form-required-* (Visibility/Required per field row)",
  },
  {
    route: "/requirements, /architecture",
    file: "components/shared/ArtifactForm/ArtifactForm.module.css",
    // Wrapping `<label>` around the lone checkbox (BooleanToggle) AND around
    // the per-criterion "fulfilled" checkbox (CriteriaList).
    selector: ".checkboxRow",
    controls: "artifact-field-<bool>, artifact-field-<criteria>-fulfilled-<n>",
  },
  {
    route: "/workflow (editor)",
    file: "components/WorkflowEditor/WorkflowEditor.module.css",
    selector: ".checkboxRow",
    controls: "workflow-transition-reason, workflow-transition-signature",
  },
  {
    route: "/attributes (catalog dialog)",
    file: "components/AttributeEditor/AttributeCatalogDialog.module.css",
    selector: ".checkboxLabel",
    controls: "attribute-catalog-include-deprecated",
  },
  {
    route: "/attributes (catalog dialog)",
    file: "components/AttributeEditor/AttributeCatalogDialog.module.css",
    selector: ".radioLabel",
    controls: "attribute-catalog-on-collision-*",
  },
  {
    route: "/attributes (import dialog)",
    file: "components/AttributeEditor/AttributeImportDialog.module.css",
    selector: ".radioLabel",
    controls: "attribute-import-dialog-on-collision-*",
  },
];

/** Modules whose label rule carries the floor (see the table above). */
const FLOORED_MODULES = [...new Set(WRAPPING_LABEL_RULES.map((rule) => rule.file))];

describe("radio/checkbox hit targets meet WCAG 2.2 SC 2.5.8 (issue #1394)", () => {
  it("builds the 24px floor on a token that is at least 24px", () => {
    expect(tokenPx(TOKENS_CSS, "--space-6")).toBeGreaterThanOrEqual(HIT_TARGET_MIN_PX);
  });

  it.each(WRAPPING_LABEL_RULES)(
    "floors the wrapping label at 24x24 on $route ($controls)",
    ({ file, selector }) => {
      const rule = rulesFor(readSource(file), selector);

      expect(declaredFloor(rule, "min-height")).toBeGreaterThanOrEqual(HIT_TARGET_MIN_PX);
      expect(declaredFloor(rule, "min-width")).toBeGreaterThanOrEqual(HIT_TARGET_MIN_PX);
    }
  );

  it("keeps the native glyph at its default size and clickable via the label", () => {
    // Inflating the glyph is not the fix — the label is and stays the click
    // target. Pin both halves so a later "just make the checkbox 24px" edit
    // does not silently pass this suite.
    //
    // T1 (GitHub #1393 review): this used to assert `not.toMatch(/width:\s*24px/)`
    // against the `.tsx` source, which can never contain a CSS declaration —
    // i.e. it passed even if the feature were reverted. The stylesheet is the
    // only place that can answer the question, so query THAT.
    const tsx = readSource(
      "components/shared/IncludeDeletedToggle/IncludeDeletedToggle.tsx"
    );
    expect(tsx).toMatch(/<label[\s\S]*<input[\s\S]*type="checkbox"[\s\S]*<\/label>/);

    const rules = parseRules(
      readSource("components/shared/IncludeDeletedToggle/IncludeDeletedToggle.module.css")
    );
    expect(rules.length).toBeGreaterThan(0);
    // No rule sizes the input at all: the floor is `min-height`/`min-width` on
    // the label class, never `width`/`height` (or `min-*`) on the glyph.
    for (const { selector, body } of rules) {
      if (!/(^|[\s>+~,(])input\b/.test(selector)) continue;
      expect(body, selector).not.toMatch(/(^|;)\s*(min-)?(width|height)\s*:/);
    }
    // And the floor lives on exactly one selector — the clickable label.
    const floored = rules
      .filter((rule) => /min-height\s*:/.test(rule.body))
      .map((rule) => rule.selector);
    expect(floored).toEqual([".toggle"]);
  });

  it("never sizes the checkbox/radio glyph in any floored module", () => {
    // Same invariant across every module in the table: the floor is on the
    // label, so no rule targeting the input may declare a size.
    for (const file of FLOORED_MODULES) {
      const rules = parseRules(readSource(file));
      expect(rules.length, file).toBeGreaterThan(0);
      for (const { selector, body } of rules) {
        if (!/(^|[\s>+~,(])input\b/.test(selector)) continue;
        expect(body, `${file} ${selector}`).not.toMatch(
          /(^|;)\s*(min-)?(width|height)\s*:/
        );
      }
    }
  });

  it("floors the RevealValue icon button at 24px (was --space-5 / 20px)", () => {
    const rule = rulesFor(
      readSource("components/shared/RevealValue.module.css"),
      ".iconButton"
    );

    expect(declaredFloor(rule, "min-height")).toBeGreaterThanOrEqual(HIT_TARGET_MIN_PX);
    expect(rule).not.toMatch(/var\(--space-5\)/);
  });
});

/**
 * N3 (GitHub #1393 review): the parser used to claim `@media` descent while
 * skipping the container body, so a media-scoped override could shrink a floor
 * below 24px (or size the glyph) without any assertion noticing. These cases
 * pin the parser and the guard that now make that impossible.
 */
describe("media-scoped rules are parsed and cannot hide a weaker floor (N3)", () => {
  it("descends into a @media body and records its container", () => {
    const rules = parseRules(`
      .label { min-height: var(--space-6); }
      @media (max-width: 600px) {
        .label { min-height: var(--space-3); }
        .label input { width: 40px; }
      }
    `);
    const nested = rules.filter((rule) => rule.container !== null);
    expect(nested.map((rule) => rule.selector)).toEqual([".label", ".label input"]);
    expect(nested[0].container).toMatch(/@media \(max-width: 600px\)/);
    // The top-level rule is still attributed to no container.
    expect(rules.find((rule) => rule.selector === ".label")?.container).toBeNull();
  });

  it("refuses a floored selector that is also declared inside @media", () => {
    const css = `
      .toggle { min-height: var(--space-6); min-width: var(--space-6); }
      @media (max-width: 600px) {
        .toggle { min-height: 12px; }
      }
    `;
    expect(() => rulesFor(css, ".toggle")).toThrow(/inside @media/);
  });
});
