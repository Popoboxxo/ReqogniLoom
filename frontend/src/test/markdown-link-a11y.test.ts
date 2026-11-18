/**
 * A11Y-003 / WCAG 2.1 SC 1.4.1 (Use of Color, Level A) — link underline gate.
 *
 * A link must be distinguishable from surrounding text by more than colour
 * alone. `global.css` suppresses `text-decoration` on every anchor, so the
 * react-markdown links rendered in the preview and read-only document views
 * relied on `--color-primary` vs `--color-text` as the sole signal — axe
 * stays green (contrast passes) while the SC is still violated. This gate
 * makes the non-colour signal executable source: both markdown surfaces must
 * underline their anchors, and the global hover/focus states must add an
 * underline too (the focus ring is a later state, not a resting-state signal).
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = join(__dirname, "..");
const css = (path: string): string => readFileSync(join(SRC, path), "utf-8");

/** Declaration blocks whose selector list contains `selector` exactly.
 *  A combined rule (`.previewBox a, .readOnlyBody a { ... }`) counts for both. */
function declarationBlocksFor(cssText: string, selector: string): string[] {
  const blocks: string[] = [];
  const rulePattern = /([^{}]+)\{([^{}]*)\}/g;
  let match: RegExpExecArray | null;
  while ((match = rulePattern.exec(cssText)) !== null) {
    // A leading doc comment lands in the selector capture; strip it so the
    // first selector of a comma list still matches literally.
    const selectors = match[1]
      .replace(/\/\*[\s\S]*?\*\//g, " ")
      .split(",")
      .map((part) => part.trim())
      .filter(Boolean);
    if (selectors.includes(selector)) {
      blocks.push(match[2]);
    }
  }
  return blocks;
}

function expectUnderline(cssText: string, selector: string, label: string): void {
  const blocks = declarationBlocksFor(cssText, selector);
  expect(blocks.length, `${label}: no CSS rule found for "${selector}"`).toBeGreaterThan(0);
  expect(
    blocks.some((block) => /text-decoration\s*:\s*underline\b/.test(block)),
    `${label}: "${selector}" has no text-decoration: underline declaration`,
  ).toBe(true);
}

describe("SC 1.4.1 — links are not identified by colour alone", () => {
  const preview = css("components/RequirementEditors/MarkdownPreview.module.css");

  it.each([".previewBox a", ".readOnlyBody a"])(
    "%s underlines rendered markdown links",
    (selector) => {
      expectUnderline(preview, selector, "MarkdownPreview.module.css");
    },
  );

  it("underlines anchors on hover and keyboard focus globally", () => {
    const globalStyles = css("styles/global.css");
    expectUnderline(globalStyles, "a:hover", "global.css");
    expectUnderline(globalStyles, "a:focus-visible", "global.css");
  });
});
