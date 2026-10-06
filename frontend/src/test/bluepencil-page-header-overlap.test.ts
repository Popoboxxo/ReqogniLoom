/**
 * Page-header / Bluepencil top-band overlap (issue #1176).
 *
 * The review layer's viewport-fixed `bp-bar` paints over the shell's top-right
 * primary action row, so a real mouse click on a page's create button landed on
 * `DIV.bp-bar` instead of the button (`document.elementFromPoint` returned the
 * overlay; Playwright `.click()` timed out).
 *
 * The fix reserves the bar's band on the shell main region. jsdom cannot
 * hit-test and Vitest does not apply CSS (`css: false`), so this suite pins the
 * *contract* instead of a pixel overlap:
 *
 *   1. `styles/bluepencil.css` reserves the band while the layer's mount
 *      element is present, using the *measured* bottom (`inset.ts` publishes
 *      it) rather than a fixed guess — the bar wraps to a second row at 1024px,
 *      so a static value would under-reserve there.
 *   2. It releases the reservation when the layer chrome is docked bottom.
 *   3. The runtime geometry token is defined in `styles/tokens.css` with a
 *      safe `0px` default.
 *   4. The `:has()` scoping matches the DOM the vendored `attach.js` creates.
 *
 * The measurement itself is covered by `inset.test.ts`; the browser-level
 * behaviour (a real `.click()` reaching the button at 1024px and above) is a
 * Playwright check — see the issue's repro.
 */
import { readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const SRC_DIR = resolve(__dirname, "..");
const BLUEPENCIL_CSS = readFileSync(join(SRC_DIR, "styles", "bluepencil.css"), "utf-8");
const TOKENS_CSS = readFileSync(join(SRC_DIR, "styles", "tokens.css"), "utf-8");

/** Extracts the declaration block of the first rule matching `selectorPattern`. */
function ruleBody(css: string, selectorPattern: RegExp): string | null {
  const match = selectorPattern.exec(css);
  return match === null ? null : match[1];
}

describe("bluepencil top-band reservation (issue #1176)", () => {
  it("reserves the measured band on the shell main region while the layer is mounted", () => {
    const body = ruleBody(
      BLUEPENCIL_CSS,
      /body:has\(>\s*bluepencil-notes\)\s+main\[role="main"\]\s*\{([^}]*)\}/,
    );
    expect(
      body,
      'expected a `body:has(> bluepencil-notes) main[role="main"]` rule in bluepencil.css',
    ).not.toBeNull();
    expect(body).toContain("var(--review-layer-bar-bottom, 0px)");
    // The clearance gap and the default-padding floor come from the token scale.
    expect(body).toContain("var(--space-4)");
    expect(body).toContain("var(--space-6)");
  });

  it("releases the reservation when the layer chrome is docked bottom", () => {
    const body = ruleBody(
      BLUEPENCIL_CSS,
      /body:has\(>\s*bluepencil-notes\):has\(\s*\.bp-root\[data-bp-dock="bottom"\]\s*\)\s+main\[role="main"\]\s*\{([^}]*)\}/,
    );
    expect(body, "expected a bottom-dock override rule in bluepencil.css").not.toBeNull();
    expect(body).toContain("padding-top: var(--space-6)");
  });

  it("defines --review-layer-bar-bottom with a safe default in tokens.css", () => {
    const declaration = /--review-layer-bar-bottom:\s*([^;]+);/.exec(TOKENS_CSS);
    expect(declaration, "expected --review-layer-bar-bottom in styles/tokens.css").not.toBeNull();
    expect(declaration![1].trim()).toBe("0px");
  });

  it("scopes the reservation to the mount element the vendored loader appends to <body>", () => {
    // Mirror attach.js: the attach element is a direct child of <body>, while
    // the element's own `.bp-root` (which carries the dock attribute) is
    // mounted at body level beside it. The :has() conditions the CSS relies on
    // must match exactly this shape.
    document.body.innerHTML = "";
    const notes = document.createElement("bluepencil-notes");
    const bpRoot = document.createElement("div");
    bpRoot.className = "bp-root";
    bpRoot.setAttribute("data-bp-dock", "top");
    document.body.appendChild(notes);
    document.body.appendChild(bpRoot);

    const TOP_SELECTOR = ":has(> bluepencil-notes)";
    const DOCK_BOTTOM_SELECTOR = ':has(> bluepencil-notes):has(.bp-root[data-bp-dock="bottom"])';

    expect(document.body.matches(TOP_SELECTOR)).toBe(true);
    expect(document.body.matches(DOCK_BOTTOM_SELECTOR)).toBe(false);

    bpRoot.setAttribute("data-bp-dock", "bottom");
    expect(document.body.matches(DOCK_BOTTOM_SELECTOR)).toBe(true);
  });
});
