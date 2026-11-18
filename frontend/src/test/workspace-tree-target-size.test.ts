/**
 * A11Y-005 / WCAG 2.2 SC 2.5.8 (Target Size Minimum, AA): the workspace
 * tree's expand/collapse chevron renders at 16x16 CSS-px, below the 24x24
 * minimum. The sibling `.groupToggle` already reserves 24px via
 * `min-height: var(--space-6)`; the chevron must use the same token pattern.
 *
 * Limitation: jsdom does not lay out elements, so this is a CSS-source
 * assertion, not a measurement of the rendered target. A real boundingBox()
 * check belongs in the manual accessibility protocol / a later E2E check.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = join(__dirname, "..");
const CSS_PATH = "components/shared/WorkspaceTree/workspace-tree.module.css";

/** Return the body of a single CSS rule, matched on its own selector line. */
function ruleBlock(source: string, selector: string): string {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = source.match(new RegExp(`(?:^|\\n)${escaped}\\s*\\{([^}]*)\\}`));
  if (!match) {
    throw new Error(`CSS rule "${selector}" not found in ${CSS_PATH}`);
  }
  return match[1];
}

const css = readFileSync(join(SRC, CSS_PATH), "utf-8");

describe("workspace tree chevron target size (SC 2.5.8)", () => {
  const toggle = ruleBlock(css, ".toggle");

  it("reserves the 24px AA minimum width via the existing --space-6 token", () => {
    expect(toggle).toContain("min-width: var(--space-6)");
  });

  it("reserves the 24px AA minimum height via the existing --space-6 token", () => {
    expect(toggle).toContain("min-height: var(--space-6)");
  });

  it("keeps the 16px glyph size unchanged (no visual-snapshot change)", () => {
    expect(toggle).toContain("width: 16px");
    expect(toggle).toContain("height: 16px");
  });
});
