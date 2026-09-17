/**
 * Guard for the mermaid + DOMPurify pairing.
 *
 * sanitizeSvg keeps DOMPurify's strict defaults, which drop `<foreignObject>`
 * subtrees. Mermaid must therefore be initialised with `htmlLabels: false` in
 * every call site (DiagramDetailView, MermaidEditor), otherwise node labels
 * would silently disappear from the rendered preview. This test renders a real
 * flowchart with that configuration and asserts the labels survive the
 * sanitising pass.
 */
import { beforeAll, describe, expect, it } from "vitest";
import { sanitizeSvg } from "../utils/sanitizeSvg";

const MERMAID_OPTIONS = {
  startOnLoad: false,
  theme: "default" as const,
  securityLevel: "strict" as const,
  htmlLabels: false,
  flowchart: { htmlLabels: false },
};

beforeAll(() => {
  // jsdom implements no SVG layout, which mermaid uses to measure labels.
  const proto = SVGElement.prototype as unknown as Record<string, unknown>;
  proto.getBBox = () => ({ x: 0, y: 0, width: 50, height: 20 });
  proto.getComputedTextLength = () => 50;
});

describe("mermaid render -> sanitizeSvg", () => {
  it("keeps node labels and emits no foreignObject", async () => {
    const mermaid = (await import("mermaid")).default;
    mermaid.initialize(MERMAID_OPTIONS);

    const { svg } = await mermaid.render(
      "sanitize-roundtrip",
      "flowchart TD\n  A[Alpha] --> B[Beta]",
    );

    expect(svg).not.toMatch(/foreignobject/i);

    const clean = sanitizeSvg(svg);
    expect(clean).toContain("Alpha");
    expect(clean).toContain("Beta");
    // Screen-reader semantics survive the sanitiser (ADD_ATTR: role).
    expect(clean).toContain('role="graphics-document');
    expect(clean).not.toMatch(/<script/i);
  });
});
