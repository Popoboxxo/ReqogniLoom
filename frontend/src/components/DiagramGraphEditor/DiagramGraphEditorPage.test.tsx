/**
 * GH-353 Task 8 — DiagramGraphEditorPage: handle-threading regression test.
 *
 * Reviewer finding (round 1): `handleConnectNodes` used to hardcode
 * `sourceHandle: "bottom"`/`targetHandle: "top"` on every manually-drawn
 * edge, discarding the handle the user actually dragged from/to (copied
 * verbatim from `WorkflowEditor/WorkflowCanvas.tsx`, where that default made
 * sense for a rank-oriented state machine but not for this free-form
 * editor). This test drives `GraphCanvas`'s `onConnectNodes` callback (the
 * prop `DiagramGraphEditorPage` passes to it) exactly as React Flow would —
 * with an explicit non-default handle pair — and asserts the created edge's
 * `source_handle`/`target_handle` (read back via the Code view, i.e. the
 * actual saved-payload shape from `flowToPayload`) reflect the real handles,
 * not the old hardcoded bottom/top. A second case covers the `null`/`null`
 * fallback (no specific handle reported), which must still default to
 * bottom/top rather than crash or write an invalid enum value.
 */
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

vi.mock("react-i18next", () => {
  const t = (key: string, fallbackOrOptions?: string | Record<string, unknown>): string =>
    typeof fallbackOrOptions === "string" ? fallbackOrOptions : key;
  return { useTranslation: () => ({ t }) };
});

// GraphCanvas pulls in @xyflow/react's full viewport (ResizeObserver, DOM
// measurement) which jsdom doesn't provide — stub it with a lightweight
// component that exposes the exact prop this test targets, `onConnectNodes`,
// via clickable buttons carrying the (source, target, sourceHandle,
// targetHandle) tuples under test.
vi.mock("./GraphCanvas", () => ({
  GraphCanvas: (props: {
    nodes: { id: string; width?: number; height?: number }[];
    onConnectNodes: (
      source: string,
      target: string,
      sourceHandle: string | null,
      targetHandle: string | null
    ) => void;
    onAddNode: () => void;
  }) => (
    <div data-testid="graph-canvas-stub">
      <button
        type="button"
        data-testid="stub-connect-left-right"
        onClick={() => props.onConnectNodes("n1", "n2", "left", "right")}
      >
        connect left-&gt;right
      </button>
      <button
        type="button"
        data-testid="stub-connect-no-handle"
        onClick={() => props.onConnectNodes("n1", "n2", null, null)}
      >
        connect null-&gt;null
      </button>
      <button type="button" data-testid="stub-add-node" onClick={() => props.onAddNode()}>
        add node
      </button>
      {/* The dimensions the page hands React Flow, exposed for assertion. */}
      <div
        data-testid="stub-node-dimensions"
        data-dimensions={JSON.stringify(
          props.nodes.map((n) => ({ id: n.id, width: n.width, height: n.height }))
        )}
      />
    </div>
  ),
}));

import * as useGraphPayloadModule from "./useGraphPayload";
import { DiagramGraphEditorPage } from "./DiagramGraphEditorPage";
import { DEFAULT_NODE_HEIGHT, DEFAULT_NODE_WIDTH } from "./graph-layout";
import { payloadToFlowNodes } from "./useGraphPayload";
import type { NodeGraphPayload } from "../../types";

vi.mock("./useGraphPayload", async (importOriginal) => {
  const actual = await importOriginal<typeof useGraphPayloadModule>();
  return { ...actual, useGraphPayload: vi.fn() };
});

const PAYLOAD: NodeGraphPayload = {
  schema_version: 1,
  nodes: [
    { id: "n1", type: "box", label: "N1", position: { x: 0, y: 0 } },
    { id: "n2", type: "box", label: "N2", position: { x: 200, y: 0 } },
  ],
  edges: [],
};

function renderPage(): void {
  vi.mocked(useGraphPayloadModule.useGraphPayload).mockReturnValue({
    payload: PAYLOAD,
    diagramName: "Test Diagram",
    isLoading: false,
    error: null,
    save: vi.fn().mockResolvedValue(undefined),
    isSaving: false,
    saveError: null,
    resetSaveError: vi.fn(),
  });

  render(
    <MemoryRouter initialEntries={["/diagrams/d1/graph"]}>
      <Routes>
        <Route path="/diagrams/:id/graph" element={<DiagramGraphEditorPage />} />
      </Routes>
    </MemoryRouter>
  );
}

/** Read back the width/height the page hands React Flow for each node. */
function readNodeDimensions(): { id: string; width?: number; height?: number }[] {
  const raw = screen.getByTestId("stub-node-dimensions").getAttribute("data-dimensions") ?? "[]";
  return JSON.parse(raw) as { id: string; width?: number; height?: number }[];
}

/** Toggle to the Code view and parse the live in-editor JSON payload. */
function readCodeViewPayload(): NodeGraphPayload {
  fireEvent.click(screen.getByTestId("graph-viewmode-code-btn"));
  const text = screen.getByTestId("graph-code-view-content").textContent ?? "";
  return JSON.parse(text) as NodeGraphPayload;
}

describe("DiagramGraphEditorPage — connect handle threading", () => {
  it("threads the real dragged-from/to handle into the created edge (left -> right)", () => {
    renderPage();

    fireEvent.click(screen.getByTestId("stub-connect-left-right"));

    const payload = readCodeViewPayload();
    expect(payload.edges).toHaveLength(1);
    expect(payload.edges[0].source).toBe("n1");
    expect(payload.edges[0].target).toBe("n2");
    expect(payload.edges[0].source_handle).toBe("left");
    expect(payload.edges[0].target_handle).toBe("right");
  });

  it("falls back to bottom/top only when React Flow reports no specific handle", () => {
    renderPage();

    fireEvent.click(screen.getByTestId("stub-connect-no-handle"));

    const payload = readCodeViewPayload();
    expect(payload.edges).toHaveLength(1);
    expect(payload.edges[0].source_handle).toBe("bottom");
    expect(payload.edges[0].target_handle).toBe("top");
  });
});

/**
 * GH-353 regression: React Flow only measures a node's DOM box when the node
 * does NOT declare `width`/`height`. `handleAddNode` used to omit both, so a
 * freshly added node was measured (~140x44) while the identical node re-read
 * from the saved payload declares 180x64 — different `fitView` bounds before
 * and after a reload, i.e. the diagram visibly jumps even though the saved
 * position round-trips correctly (E2E
 * test_graph_save_persists_and_positions_survive_reload failed with a 40px
 * x-shift). Every GraphFlowNode construction path must produce the identical
 * shape; this pins the add-node path against the load path.
 */
describe("DiagramGraphEditorPage — node dimension consistency", () => {
  it("gives a newly added node the same width/height the load path declares", () => {
    renderPage();

    fireEvent.click(screen.getByTestId("stub-add-node"));

    const dimensions = readNodeDimensions();
    expect(dimensions).toHaveLength(PAYLOAD.nodes.length + 1);

    const loadPathDimensions = payloadToFlowNodes(PAYLOAD).map((n) => ({
      width: n.width,
      height: n.height,
    }));
    // Sanity-check the reference path itself so this test cannot pass by
    // both paths degrading to `undefined` together.
    expect(loadPathDimensions[0]).toEqual({
      width: DEFAULT_NODE_WIDTH,
      height: DEFAULT_NODE_HEIGHT,
    });

    for (const node of dimensions) {
      expect({ width: node.width, height: node.height }).toEqual({
        width: DEFAULT_NODE_WIDTH,
        height: DEFAULT_NODE_HEIGHT,
      });
    }
  });
});
