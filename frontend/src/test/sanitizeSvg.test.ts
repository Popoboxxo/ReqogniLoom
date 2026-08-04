/**
 * Regression tests for the SVG sanitisation seam (utils/sanitizeSvg).
 *
 * Guards the `dangerouslySetInnerHTML` sinks in DiagramDetailView (canvas
 * export + mermaid preview) and MermaidEditor against stored XSS.
 */
import { describe, expect, it } from "vitest";
import { sanitizeSvg } from "../utils/sanitizeSvg";

describe("sanitizeSvg", () => {
  it("returns an empty string for empty input", () => {
    expect(sanitizeSvg("")).toBe("");
  });

  it("keeps harmless SVG markup renderable", () => {
    const svg =
      '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="50">' +
      '<rect x="1" y="2" width="10" height="20" fill="none" /></svg>';
    const result = sanitizeSvg(svg);
    expect(result).toContain("<svg");
    expect(result).toContain("<rect");
    expect(result).toContain('width="10"');
  });

  it("strips event-handler attributes injected into shape attributes", () => {
    const svg =
      '<svg xmlns="http://www.w3.org/2000/svg">' +
      '<rect x="0" y="0" width="0" onload="alert(1)" height="10" /></svg>';
    const result = sanitizeSvg(svg);
    expect(result).not.toMatch(/onload/i);
    expect(result).toContain("<rect");
  });

  it("strips script elements", () => {
    const result = sanitizeSvg(
      '<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script><circle r="1" /></svg>',
    );
    expect(result).not.toMatch(/<script/i);
    expect(result).toContain("<circle");
  });

  it("strips javascript: URLs", () => {
    const result = sanitizeSvg(
      '<svg xmlns="http://www.w3.org/2000/svg"><a href="javascript:alert(1)"><text>x</text></a></svg>',
    );
    expect(result).not.toMatch(/javascript:/i);
  });

  it("strips onmouseover handlers on the svg root", () => {
    const result = sanitizeSvg(
      '<svg xmlns="http://www.w3.org/2000/svg" onmouseover="alert(1)"><g /></svg>',
    );
    expect(result).not.toMatch(/onmouseover/i);
  });

  it("keeps plain SVG text labels (mermaid runs with htmlLabels: false)", () => {
    const result = sanitizeSvg(
      '<svg xmlns="http://www.w3.org/2000/svg"><g class="node">' +
        '<text><tspan x="0">Label</tspan></text></g></svg>',
    );
    expect(result).toContain("Label");
    expect(result).toContain("<tspan");
  });

  it("drops foreignObject subtrees — the reason mermaid uses htmlLabels: false", () => {
    // Documents the coupling: if this ever starts passing, the mermaid
    // initialize() calls may re-enable htmlLabels without labels vanishing.
    const result = sanitizeSvg(
      '<svg xmlns="http://www.w3.org/2000/svg"><foreignObject width="10" height="10">' +
        '<div xmlns="http://www.w3.org/1999/xhtml"><span>Label</span></div>' +
        "</foreignObject></svg>",
    );
    expect(result).not.toContain("Label");
  });
});
