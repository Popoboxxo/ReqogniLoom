/**
 * A11Y-005 / WCAG 2.2 SC 2.5.8 (Target Size Minimum, AA): the live axe gate
 * (S3.3) flagged the transition edge label pill (`._edgeLabel_*[role="button"]`)
 * and the state node (`div[data-testid="workflow-state-node-proposed"]`) on
 * /workflows. Both now floor their hit area at 24px via the existing
 * `--space-6` token — same pattern as the workspace-tree `.toggle` fix.
 *
 * Limitation: jsdom does not lay out elements, so these are CSS-source
 * assertions, not measurements of the rendered target. A boundingBox() check
 * belongs in the manual protocol / a later browser-based a11y check.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = join(__dirname, "..");
const CSS_PATH = "components/WorkflowEditor/WorkflowEditor.module.css";

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

describe("WorkflowEditor touch targets (SC 2.5.8)", () => {
  const edgeLabel = ruleBlock(css, ".edgeLabel");
  const stateNode = ruleBlock(css, ".stateNode");

  it("edge label reserves the 24px AA minimum width via --space-6", () => {
    expect(edgeLabel).toContain("min-width: var(--space-6)");
  });

  it("edge label reserves the 24px AA minimum height via --space-6", () => {
    expect(edgeLabel).toContain("min-height: var(--space-6)");
  });

  it("state node reserves the 24px AA minimum height via --space-6", () => {
    expect(stateNode).toContain("min-height: var(--space-6)");
  });

  it("state node keeps its wider intrinsic min-width (already above 24px)", () => {
    expect(stateNode).toContain("min-width: 160px");
  });

  it("keeps the edge label glyph/padding unchanged (no visual-snapshot change)", () => {
    expect(edgeLabel).toContain("padding: 2px 8px");
    expect(edgeLabel).toContain("font-size: var(--font-size-xs)");
  });
});
