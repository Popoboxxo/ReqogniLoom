/**
 * Co-located tests for diagrams API wrapper (REQ-L1-056, REQ-L1-057).
 *
 * Tests: fetchCanvasStrokes, saveCanvasStrokes, fetchMermaidSource,
 *        saveMermaidSource, fetchMermaidPreview.
 * NOT executed — written for future Vitest run.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { diagramsApi } from "./diagrams";

// ---------------------------------------------------------------------------
// Mock the API client
// ---------------------------------------------------------------------------

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockPut = vi.fn();

vi.mock("./client", () => ({
  apiClient: {
    get: (...args: unknown[]) => mockGet(...args),
    post: (...args: unknown[]) => mockPost(...args),
    put: (...args: unknown[]) => mockPut(...args),
    patch: vi.fn(),
    delete: vi.fn(),
  },
  getList: vi.fn(),
  getAllPages: vi.fn(),
}));

// Mock tracelinks
vi.mock("./tracelinks", () => ({
  tracelinksApi: {
    listForArtifact: vi.fn().mockResolvedValue({ results: [] }),
  },
}));

describe("diagramsApi — Canvas Strokes", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("fetchCanvasStrokes calls GET with correct path", async () => {
    const mockResponse = {
      diagram_id: "abc-123",
      strokes: [{ type: "pen", points: [{ x: 0, y: 0 }] }],
      width: 800,
      height: 600,
      svg: "<svg></svg>",
      version_number: 1,
    };
    mockGet.mockResolvedValue(mockResponse);

    const result = await diagramsApi.fetchCanvasStrokes("abc-123");

    expect(mockGet).toHaveBeenCalledWith("/diagrams/abc-123/canvas-strokes/");
    expect(result).toEqual(mockResponse);
  });

  it("saveCanvasStrokes calls PUT with correct path and data", async () => {
    const strokeData = {
      strokes: [{ type: "pen" as const, points: [{ x: 10, y: 20 }] }],
      width: 800,
      height: 600,
    };
    const mockResponse = {
      diagram_id: "abc-123",
      strokes: strokeData.strokes,
      width: 800,
      height: 600,
      svg: "<svg></svg>",
      version_number: 2,
    };
    mockPut.mockResolvedValue(mockResponse);

    const result = await diagramsApi.saveCanvasStrokes("abc-123", strokeData);

    expect(mockPut).toHaveBeenCalledWith(
      "/diagrams/abc-123/canvas-strokes/",
      strokeData
    );
    expect(result).toEqual(mockResponse);
  });

  it("appendCanvasStrokes calls POST with correct path and data", async () => {
    const strokeData = {
      strokes: [{ type: "pen" as const, points: [{ x: 10, y: 20 }] }],
    };
    mockPost.mockResolvedValue({
      diagram_id: "abc-123",
      strokes: strokeData.strokes,
      width: 800,
      height: 600,
      svg: "<svg></svg>",
      version_number: 3,
    });

    const result = await diagramsApi.appendCanvasStrokes("abc-123", strokeData);

    expect(mockPost).toHaveBeenCalledWith(
      "/diagrams/abc-123/canvas-strokes/",
      strokeData
    );
    expect(result.version_number).toBe(3);
  });
});

describe("diagramsApi — Mermaid Source/Preview", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("fetchMermaidSource calls GET with correct path", async () => {
    const mockResponse = {
      diagram_id: "def-456",
      source: "flowchart TD\n  A --> B",
      diagram_type: "flowchart",
      is_valid: true,
      error_message: "",
    };
    mockGet.mockResolvedValue(mockResponse);

    const result = await diagramsApi.fetchMermaidSource("def-456");

    expect(mockGet).toHaveBeenCalledWith("/diagrams/def-456/mermaid-source/");
    expect(result.source).toBe("flowchart TD\n  A --> B");
  });

  it("saveMermaidSource calls PUT with correct path and source", async () => {
    const mockResponse = {
      diagram_id: "def-456",
      source: "flowchart TD\n  A --> C",
      diagram_type: "flowchart",
      is_valid: true,
      error_message: "",
    };
    mockPut.mockResolvedValue(mockResponse);

    const result = await diagramsApi.saveMermaidSource(
      "def-456",
      "flowchart TD\n  A --> C"
    );

    expect(mockPut).toHaveBeenCalledWith("/diagrams/def-456/mermaid-source/", {
      source: "flowchart TD\n  A --> C",
    });
    expect(result.source).toBe("flowchart TD\n  A --> C");
  });

  it("fetchMermaidPreview calls GET with correct path", async () => {
    const mockResponse = {
      diagram_id: "def-456",
      source: "flowchart TD\n  A --> B",
      diagram_type: "flowchart",
      render_hints: {
        supported_formats: ["svg"],
        renderer: "mermaid.js",
        notes: "",
      },
      fallback_mode: false,
      error_message: "",
    };
    mockGet.mockResolvedValue(mockResponse);

    const result = await diagramsApi.fetchMermaidPreview("def-456");

    expect(mockGet).toHaveBeenCalledWith(
      "/diagrams/def-456/mermaid-preview/"
    );
    expect(result.fallback_mode).toBe(false);
    expect(result.render_hints).toBeDefined();
  });

  it("fetchMermaidPreview handles fallback mode", async () => {
    const mockResponse = {
      diagram_id: "def-456",
      source: "invalid source",
      diagram_type: "",
      render_hints: null,
      fallback_mode: true,
      error_message: "Syntax error at line 1",
    };
    mockGet.mockResolvedValue(mockResponse);

    const result = await diagramsApi.fetchMermaidPreview("def-456");

    expect(result.fallback_mode).toBe(true);
    expect(result.error_message).toBe("Syntax error at line 1");
  });
});
