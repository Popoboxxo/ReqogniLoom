/**
 * Unit tests for the DiagramView shared constants/helpers (REQ-050 extraction).
 * Covers the pure form defaults lifted out of the former monolithic DiagramView.
 */

import { describe, it, expect } from "vitest";
import {
  DEFAULT_CONTENT,
  DIAGRAM_TYPES,
  EMPTY_FORM,
  PAYLOAD_FORMATS,
  diagramVersionLabel,
} from "./diagram-view-shared";

describe("diagram-view-shared", () => {
  it("diagramVersionLabel shows a dash for unversioned diagrams", () => {
    expect(diagramVersionLabel(0)).toBe("—");
    expect(diagramVersionLabel(3)).toBe("3");
  });

  it("provides a default content template for every payload format", () => {
    for (const fmt of PAYLOAD_FORMATS) {
      expect(DEFAULT_CONTENT[fmt]).toBeDefined();
      expect(typeof DEFAULT_CONTENT[fmt]).toBe("string");
    }
  });

  it("EMPTY_FORM seeds a valid diagram type and mermaid default", () => {
    expect(DIAGRAM_TYPES).toContain(EMPTY_FORM.diagram_type);
    expect(EMPTY_FORM.payload_format).toBe("mermaid");
    expect(EMPTY_FORM.content).toBe(DEFAULT_CONTENT.mermaid);
    expect(EMPTY_FORM.name).toBe("");
  });
});
