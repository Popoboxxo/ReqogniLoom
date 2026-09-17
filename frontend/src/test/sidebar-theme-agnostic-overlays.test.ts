/**
 * SidebarNavigation.module.css theme-agnostic overlays (Theme Presets, Task 7).
 *
 * The sidebar must render correctly in BOTH modes once a palette can light
 * it up. Literal white/black rgba() overlays assume a dark background and
 * invert/near-vanish on a light one — every such literal must go through a
 * --color-nav-overlay-* token instead. (Blue-tinted focus rings etc. are
 * palette-colored by design and deliberately NOT matched here.)
 */
import { readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const CSS_FILE = join(
  resolve(__dirname, ".."),
  "components/NavigationShell/SidebarNavigation.module.css"
);

describe("SidebarNavigation.module.css theme-agnostic overlays", () => {
  it("has no hardcoded white/black rgba overlay literals", () => {
    const css = readFileSync(CSS_FILE, "utf-8");
    const rgbaWhiteOrBlack = /rgba\(\s*(255,\s*255,\s*255|0,\s*0,\s*0)\s*,/g;
    const matches = css.match(rgbaWhiteOrBlack) || [];
    expect(matches).toHaveLength(0);
  });

  it("consumes the --color-nav-overlay-* tokens for those call sites", () => {
    const css = readFileSync(CSS_FILE, "utf-8");
    expect(css).toContain("var(--color-nav-overlay-hover)");
    expect(css).toContain("var(--color-nav-overlay-hover-border)");
    expect(css).toContain("var(--color-nav-overlay-shadow)");
  });
});
