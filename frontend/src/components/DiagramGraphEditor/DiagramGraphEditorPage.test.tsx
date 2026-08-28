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
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useNavigate } from "react-router-dom";

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
import { GRAPH_AUTOSAVE_DELAY_MS } from "./useGraphAutosave";
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

type SaveFn = (payload: NodeGraphPayload) => Promise<void>;
type FlushFn = (payload: NodeGraphPayload) => void;

interface RenderedPage {
  save: Mock<SaveFn>;
  flush: Mock<FlushFn>;
  unmount: () => void;
}

function renderPage(overrides: { save?: Mock<SaveFn> } = {}): RenderedPage {
  const save = overrides.save ?? vi.fn<SaveFn>().mockResolvedValue(undefined);
  const flush = vi.fn<FlushFn>();

  vi.mocked(useGraphPayloadModule.useGraphPayload).mockReturnValue({
    payload: PAYLOAD,
    diagramName: "Test Diagram",
    isLoading: false,
    error: null,
    save,
    flush,
    isSaving: false,
    saveError: null,
    resetSaveError: vi.fn(),
  });

  const { unmount } = render(
    <MemoryRouter initialEntries={["/diagrams/d1/graph"]}>
      <Routes>
        <Route path="/diagrams/:id/graph" element={<DiagramGraphEditorPage />} />
      </Routes>
    </MemoryRouter>
  );

  return { save, flush, unmount };
}

/**
 * Drives a real in-app route change while staying inside the same
 * `<MemoryRouter>` — `rerender`ing the router with different `initialEntries`
 * does NOT move the location, since MemoryRouter builds its history once.
 */
function DiagramSwitcher({ to }: { to: string }): JSX.Element {
  const navigate = useNavigate();
  return (
    <button type="button" data-testid="stub-switch-diagram" onClick={() => navigate(to)}>
      switch diagram
    </button>
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

/**
 * UI-02 (docs/SYSTEMAUDIT_2026-08-27_RESTPLAN.md, AP-3): the editor used to
 * hold its whole draft in local state and push it to the server only on an
 * explicit Save click — every other exit (sidebar link, browser Back, tab
 * close, reload) discarded the edit session silently. These tests pin the
 * three mechanisms that close that gap, plus the two invariants that keep
 * autosave *additive* rather than a replacement for the manual path.
 */
describe("DiagramGraphEditorPage — autosave + unsaved-changes guards", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    // `cleanup` must run on fake timers: unmounting is what triggers the
    // flush-on-exit path, and the assertions below depend on it happening
    // while the timers are still controllable.
    cleanup();
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("does not autosave on load — merely opening a diagram must not re-version it", () => {
    const { save } = renderPage();

    act(() => {
      vi.advanceTimersByTime(GRAPH_AUTOSAVE_DELAY_MS * 2);
    });

    expect(save).not.toHaveBeenCalled();
    expect(screen.getByTestId("graph-editor-save-status")).toHaveAttribute("data-status", "idle");
  });

  it("marks the draft dirty immediately and autosaves once the debounce elapses", async () => {
    const { save } = renderPage();

    fireEvent.click(screen.getByTestId("stub-add-node"));

    const status = screen.getByTestId("graph-editor-save-status");
    expect(status).toHaveAttribute("data-dirty", "true");
    expect(status).toHaveAttribute("data-status", "dirty");

    // Still nothing on the wire just before the debounce window closes — the
    // point of the debounce is that a burst of edits costs one request.
    act(() => {
      vi.advanceTimersByTime(GRAPH_AUTOSAVE_DELAY_MS - 1);
    });
    expect(save).not.toHaveBeenCalled();

    await act(async () => {
      vi.advanceTimersByTime(1);
    });

    expect(save).toHaveBeenCalledTimes(1);
    // The saved payload is the live draft, not the server copy it was seeded from.
    const saved = save.mock.calls[0][0];
    expect(saved.nodes).toHaveLength(PAYLOAD.nodes.length + 1);
    expect(screen.getByTestId("graph-editor-save-status")).toHaveAttribute("data-dirty", "false");
  });

  it("collapses a burst of edits into a single request", async () => {
    const { save } = renderPage();

    fireEvent.click(screen.getByTestId("stub-add-node"));
    act(() => {
      vi.advanceTimersByTime(GRAPH_AUTOSAVE_DELAY_MS - 100);
    });
    fireEvent.click(screen.getByTestId("stub-add-node"));
    act(() => {
      vi.advanceTimersByTime(GRAPH_AUTOSAVE_DELAY_MS - 100);
    });
    fireEvent.click(screen.getByTestId("stub-connect-left-right"));

    await act(async () => {
      vi.advanceTimersByTime(GRAPH_AUTOSAVE_DELAY_MS);
    });

    expect(save).toHaveBeenCalledTimes(1);
    const saved = save.mock.calls[0][0];
    expect(saved.nodes).toHaveLength(PAYLOAD.nodes.length + 2);
    expect(saved.edges).toHaveLength(1);
  });

  it("keeps the manual Save unconditional even when autosave already persisted the draft", async () => {
    const { save } = renderPage();

    fireEvent.click(screen.getByTestId("stub-add-node"));
    await act(async () => {
      vi.advanceTimersByTime(GRAPH_AUTOSAVE_DELAY_MS);
    });
    expect(save).toHaveBeenCalledTimes(1);

    // The draft is clean now. An explicit click must still issue the request:
    // the pre-existing manual contract (and the GH-353 E2E, which arms a
    // `waitForResponse` on the PATCH *before* clicking) depends on it.
    await act(async () => {
      fireEvent.click(screen.getByTestId("graph-editor-save"));
    });

    expect(save).toHaveBeenCalledTimes(2);
  });

  it("flushes the pending draft on unmount — the in-app navigation guard", async () => {
    const { save, flush, unmount } = renderPage();

    fireEvent.click(screen.getByTestId("stub-add-node"));
    expect(save).not.toHaveBeenCalled();

    // Navigate away well inside the debounce window: without the flush this
    // is exactly the silent total data loss UI-02 reports.
    await act(async () => {
      unmount();
    });

    expect(flush).toHaveBeenCalledTimes(1);
    const flushed = flush.mock.calls[0][0];
    expect(flushed.nodes).toHaveLength(PAYLOAD.nodes.length + 1);
  });

  it("does not flush on unmount when there is nothing unsaved", async () => {
    const { flush, unmount } = renderPage();

    await act(async () => {
      unmount();
    });

    expect(flush).not.toHaveBeenCalled();
  });

  it("registers a beforeunload guard only while the draft is dirty", async () => {
    const addSpy = vi.spyOn(window, "addEventListener");
    const removeSpy = vi.spyOn(window, "removeEventListener");

    renderPage();
    expect(addSpy.mock.calls.filter(([type]) => type === "beforeunload")).toHaveLength(0);

    fireEvent.click(screen.getByTestId("stub-add-node"));
    const registered = addSpy.mock.calls.filter(([type]) => type === "beforeunload");
    expect(registered).toHaveLength(1);

    // The handler must actually cancel the unload, otherwise no browser
    // prompt appears.
    const handler = registered[0][1] as (event: BeforeUnloadEvent) => void;
    const event = { preventDefault: vi.fn(), returnValue: undefined } as unknown as BeforeUnloadEvent;
    handler(event);
    expect(event.preventDefault).toHaveBeenCalled();

    // ...and it must be gone again once the draft is persisted, so a clean
    // reload (what the Playwright specs do) never sees a dialog.
    await act(async () => {
      vi.advanceTimersByTime(GRAPH_AUTOSAVE_DELAY_MS);
    });
    expect(removeSpy.mock.calls.filter(([type]) => type === "beforeunload")).toHaveLength(1);
  });

  it("never autosaves a draft that belongs to a different diagram", async () => {
    // `/diagrams/:id/graph` is one route element, so switching diagrams
    // reuses this component instance: the draft still holds the OLD graph
    // while `save` already targets the NEW id. An autosave armed before the
    // switch must not fire in that window — it would write the old graph over
    // the newly routed diagram.
    const save = vi.fn<SaveFn>().mockResolvedValue(undefined);
    const flush = vi.fn<FlushFn>();
    const hookResult = {
      payload: PAYLOAD,
      diagramName: "Test Diagram",
      isLoading: false,
      error: null,
      save,
      flush,
      isSaving: false,
      saveError: null,
      resetSaveError: vi.fn(),
    };
    vi.mocked(useGraphPayloadModule.useGraphPayload).mockReturnValue(hookResult);

    render(
      <MemoryRouter initialEntries={["/diagrams/d1/graph"]}>
        <DiagramSwitcher to="/diagrams/d2/graph" />
        <Routes>
          <Route path="/diagrams/:id/graph" element={<DiagramGraphEditorPage />} />
        </Routes>
      </MemoryRouter>
    );

    fireEvent.click(screen.getByTestId("stub-add-node"));
    expect(screen.getByTestId("graph-editor-save-status")).toHaveAttribute("data-dirty", "true");

    // Route to a different diagram whose content has not arrived yet. Both
    // URLs match the same <Route>, so React keeps the SAME component instance
    // alive — no unmount, and therefore no flush either.
    vi.mocked(useGraphPayloadModule.useGraphPayload).mockReturnValue({
      ...hookResult,
      payload: null,
    });
    act(() => {
      fireEvent.click(screen.getByTestId("stub-switch-diagram"));
    });
    expect(screen.getByTestId("graph-editor-save-status")).toHaveAttribute("data-dirty", "false");

    await act(async () => {
      vi.advanceTimersByTime(GRAPH_AUTOSAVE_DELAY_MS * 2);
    });

    expect(save).not.toHaveBeenCalled();
    expect(flush).not.toHaveBeenCalled();

    // ...and once the new diagram's content lands, that freshly seeded draft
    // is a *load*, not an edit: opening a second diagram must no more
    // re-version it than opening the first one did.
    vi.mocked(useGraphPayloadModule.useGraphPayload).mockReturnValue(hookResult);
    // Any re-render now lets the page seed the draft from the new content
    // (the edit toggle is the cheapest one that touches no graph state).
    act(() => {
      fireEvent.click(screen.getByTestId("graph-edit-toggle"));
    });
    await act(async () => {
      vi.advanceTimersByTime(GRAPH_AUTOSAVE_DELAY_MS * 2);
    });

    expect(save).not.toHaveBeenCalled();
    expect(screen.getByTestId("graph-editor-save-status")).toHaveAttribute("data-status", "idle");
  });

  it("stays dirty and reports the failure when an autosave is rejected", async () => {
    const save = vi.fn<SaveFn>().mockRejectedValue(new Error("boom"));
    const { flush, unmount } = renderPage({ save });

    fireEvent.click(screen.getByTestId("stub-add-node"));
    await act(async () => {
      vi.advanceTimersByTime(GRAPH_AUTOSAVE_DELAY_MS);
    });

    const status = screen.getByTestId("graph-editor-save-status");
    expect(status).toHaveAttribute("data-status", "error");
    // Dirty must survive the failure: the guards are the user's last line of
    // defence precisely when persistence is broken.
    expect(status).toHaveAttribute("data-dirty", "true");

    await act(async () => {
      unmount();
    });
    expect(flush).toHaveBeenCalledTimes(1);
  });
});
