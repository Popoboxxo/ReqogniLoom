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

  /**
   * C-L20 (#1258): the footer buttons are `btn-ghost <footerBtn>`. The
   * global `.btn-ghost:hover:not(:disabled)` (0,3,0) paints
   * `--color-surface-raised` — white in the light theme — over the sidebar's
   * permanently dark chrome, so the hovered label becomes unreadable. The
   * module rule has to match that specificity (class + :hover + :not) so it
   * wins by load order, and it must repaint with the nav palette rather than
   * a surface colour.
   */
  it("lets .footerBtn override the global .btn-ghost hover with nav colours", () => {
    const css = readFileSync(CSS_FILE, "utf-8");
    const rule = /\.footerBtn:hover:not\(:disabled\)\s*,\s*\.footerBtnActive\s*\{([^}]*)\}/.exec(
      css
    );
    expect(rule, "expected a `.footerBtn:hover:not(:disabled), .footerBtnActive` rule").not.toBe(
      null
    );
    const body = rule !== null ? rule[1] : "";
    expect(body).toContain("background: var(--color-nav-hover-bg)");
    expect(body).toContain("color: var(--color-nav-text)");
  });
});
