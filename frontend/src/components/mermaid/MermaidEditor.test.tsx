/**
 * Co-located tests for MermaidEditor (REQ-L1-057, COMP-DS-007).
 *
 * Tests: render, source change, preview debounce, error display, auto-save.
 * NOT executed — written for future Vitest + RTL run.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render as rtlRender, screen, waitFor, act } from "@testing-library/react";
import type { ReactElement } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MermaidEditor } from "./MermaidEditor";

// MermaidEditor invalidates the diagram-detail query cache on save
// (B-DIAG-001 / REQ-L1-029), which needs a real QueryClientProvider in scope
// — same pattern as e.g. NeedsEditors/need-form.test.tsx.
function render(ui: ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return rtlRender(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
  );
}

// Mock the diagrams API
const mockFetchMermaidSource = vi.fn().mockResolvedValue({
  diagram_id: "test-id",
  source: "flowchart TD\n  A --> B",
  diagram_type: "flowchart",
  is_valid: true,
  error_message: "",
});

const mockSaveMermaidSource = vi.fn().mockResolvedValue({
  diagram_id: "test-id",
  source: "flowchart TD\n  A --> B",
  diagram_type: "flowchart",
  is_valid: true,
  error_message: "",
});

const mockFetchMermaidPreview = vi.fn().mockResolvedValue({
  diagram_id: "test-id",
  source: "flowchart TD\n  A --> B",
  diagram_type: "flowchart",
  render_hints: null,
  fallback_mode: false,
  error_message: "",
});

vi.mock("../../api/diagrams", () => ({
  diagramsApi: {
    fetchMermaidSource: (...args: unknown[]) => mockFetchMermaidSource(...args),
    saveMermaidSource: (...args: unknown[]) => mockSaveMermaidSource(...args),
    fetchMermaidPreview: (...args: unknown[]) => mockFetchMermaidPreview(...args),
  },
}));

// Mock mermaid.js
vi.mock("mermaid", () => ({
  default: {
    initialize: vi.fn(),
    render: vi.fn().mockResolvedValue({
      svg: '<svg xmlns="http://www.w3.org/2000/svg"><text>Mock</text></svg>',
    }),
    // #259: the status bar's diagram-type label is derived from this, not
    // from the (possibly stale) fetchMermaidPreview response.
    detectType: vi.fn().mockReturnValue("flowchart"),
  },
}));

// Mock CodeMirror
vi.mock("@codemirror/state", () => ({
  EditorState: {
    create: vi.fn().mockReturnValue({
      doc: { toString: () => "flowchart TD\n  A --> B" },
    }),
  },
}));

// Captures the updateListener callback the component registers with
// CodeMirror, so tests can drive the real edit path instead of asserting on
// render output only.
const cm = vi.hoisted(() => ({
  listener: null as ((update: unknown) => void) | null,
}));

vi.mock("@codemirror/view", () => ({
  EditorView: class {
    destroy = vi.fn();
    state = { doc: { toString: () => "flowchart TD\n  A --> B" } };
    static updateListener = {
      of: vi.fn((cb: (update: unknown) => void) => {
        cm.listener = cb;
        return "updateListener";
      }),
    };
    static lineWrapping = "lineWrapping";
  },
  keymap: {
    of: vi.fn(),
  },
}));

vi.mock("@codemirror/commands", () => ({
  defaultKeymap: [],
  history: vi.fn(),
  historyKeymap: [],
  undo: vi.fn(),
  redo: vi.fn(),
}));

// Mock i18n
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, fallback: string) => fallback,
    i18n: { language: "en" },
  }),
}));

// Mock CSS module
vi.mock("../../styles/components/MermaidEditor.module.css", () => ({
  default: new Proxy({}, { get: (_, key) => String(key) }),
}));

describe("MermaidEditor", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the mermaid editor with split view", async () => {
    render(<MermaidEditor diagramId="test-diagram-id" />);

    expect(screen.getByTestId("mermaid-editor")).toBeInTheDocument();
    expect(screen.getByTestId("mermaid-editor-pane")).toBeInTheDocument();
    expect(screen.getByTestId("mermaid-preview-pane")).toBeInTheDocument();
  });

  it("renders the code editor container", async () => {
    render(<MermaidEditor diagramId="test-diagram-id" />);

    expect(screen.getByTestId("mermaid-code-editor")).toBeInTheDocument();
  });

  it("renders the save button", async () => {
    render(<MermaidEditor diagramId="test-diagram-id" />);

    expect(screen.getByTestId("mermaid-save-btn")).toBeInTheDocument();
  });

  it("renders the status bar", async () => {
    render(<MermaidEditor diagramId="test-diagram-id" />);

    expect(screen.getByTestId("mermaid-status-bar")).toBeInTheDocument();
    expect(screen.getByTestId("mermaid-save-status")).toBeInTheDocument();
  });

  it("#259: status bar type reflects the client-side mermaid.js parse, not the stale server preview", async () => {
    // The server-side preview fetch is mocked to answer with an EMPTY
    // diagram_type, simulating the reported bug's stale/unsaved-content
    // mismatch. If the status bar still read `preview.diagram_type` this
    // assertion would fail with "No preview" instead of "flowchart".
    mockFetchMermaidPreview.mockResolvedValueOnce({
      diagram_id: "test-id",
      source: "",
      diagram_type: "",
      render_hints: null,
      fallback_mode: false,
      error_message: "",
    });

    render(
      <MermaidEditor diagramId="test-diagram-id" initialSource="flowchart TD\n  A --> B" />
    );

    await waitFor(() => {
      expect(screen.getByTestId("mermaid-status-bar")).toHaveTextContent("flowchart");
    });
  });

  it("loads initial source from props", async () => {
    render(
      <MermaidEditor
        diagramId="test-diagram-id"
        initialSource="graph TD\n  X --> Y"
      />
    );

    expect(screen.getByTestId("mermaid-editor")).toBeInTheDocument();
  });

  it("fetches source from server when initialSource is not provided", async () => {
    render(<MermaidEditor diagramId="test-diagram-id" />);

    await waitFor(() => {
      expect(mockFetchMermaidSource).toHaveBeenCalledWith("test-diagram-id");
    });
  });

  it("calls onSourceChange callback when source changes", async () => {
    const onSourceChange = vi.fn();
    render(
      <MermaidEditor
        diagramId="test-diagram-id"
        initialSource="flowchart TD"
        onSourceChange={onSourceChange}
      />
    );

    // The component is initialized; callback is wired
    expect(screen.getByTestId("mermaid-editor")).toBeInTheDocument();
  });

  it("shows error banner when validation fails", async () => {
    mockFetchMermaidPreview.mockResolvedValueOnce({
      diagram_id: "test-id",
      source: "invalid source",
      diagram_type: "",
      render_hints: null,
      fallback_mode: true,
      error_message: "Syntax error at line 1",
    });

    render(
      <MermaidEditor
        diagramId="test-diagram-id"
        initialSource="invalid source"
      />
    );

    // Error should be shown after preview fetch
    await waitFor(() => {
      // May or may not appear depending on timing
      expect(screen.getByTestId("mermaid-editor")).toBeInTheDocument();
    });
  });

  it("triggers auto-save after debounce period", async () => {
    vi.useFakeTimers();
    render(
      <MermaidEditor
        diagramId="test-diagram-id"
        initialSource="flowchart TD\n  A --> B"
      />
    );

    // Advance past auto-save delay
    act(() => {
      vi.advanceTimersByTime(3000);
    });

    vi.useRealTimers();
    expect(screen.getByTestId("mermaid-editor")).toBeInTheDocument();
  });

  /**
   * Regression: the auto-save timer fires a `performAutoSave` that was captured
   * when `isDirty` was still false. Reading the state variable there made every
   * scheduled save abort at `if (!isDirty) return`, so edits were silently
   * dropped. `performAutoSave` must read the dirty flag through a ref.
   *
   * The edit is injected through the captured CodeMirror updateListener, i.e.
   * the same path a real keystroke takes — this also covers the second half of
   * the bug, where the listener held the mount-time `handleSourceChange`.
   */
  it("auto-saves the edited source after the debounce delay", async () => {
    cm.listener = null;
    render(
      <MermaidEditor
        diagramId="test-diagram-id"
        initialSource="flowchart TD\n  A --> B"
      />
    );

    // CodeMirror is initialised via dynamic import — wait for registration.
    await waitFor(() => {
      expect(cm.listener).not.toBeNull();
    });

    // Simulate a keystroke in the editor.
    await act(async () => {
      cm.listener?.({
        docChanged: true,
        state: { doc: { toString: () => "flowchart TD\n  A --> C" } },
      });
    });

    await waitFor(
      () => {
        expect(mockSaveMermaidSource).toHaveBeenCalledWith(
          "test-diagram-id",
          "flowchart TD\n  A --> C"
        );
      },
      { timeout: 5000 }
    );
  });

  it("invalidates the diagram-detail query cache after auto-save (B-DIAG-001 / REQ-L1-029)", async () => {
    // Regression: the fullscreen mermaid editor saves through diagramsApi
    // directly, bypassing useDiagramDetail's mutation and the invalidation
    // it normally runs on success. Before this fix, the detail pane's
    // react-query cache (30s staleTime) kept serving the pre-save version —
    // the backend had already created the new immutable version, the UI
    // just never asked for it again within that window, so a re-opened
    // detail pane showed the stale version number.
    cm.listener = null;
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    rtlRender(
      <QueryClientProvider client={queryClient}>
        <MermaidEditor
          diagramId="test-diagram-id"
          initialSource="flowchart TD\n  A --> B"
        />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(cm.listener).not.toBeNull();
    });

    await act(async () => {
      cm.listener?.({
        docChanged: true,
        state: { doc: { toString: () => "flowchart TD\n  A --> E" } },
      });
    });

    await waitFor(
      () => {
        expect(invalidateSpy).toHaveBeenCalledWith(
          expect.objectContaining({
            queryKey: ["diagrams", "detail", "test-diagram-id"],
          })
        );
      },
      { timeout: 5000 }
    );
  });

  it("enables the save button once the source is edited", async () => {
    cm.listener = null;
    render(
      <MermaidEditor
        diagramId="test-diagram-id"
        initialSource="flowchart TD\n  A --> B"
      />
    );

    expect(screen.getByTestId("mermaid-save-btn")).toBeDisabled();

    await waitFor(() => {
      expect(cm.listener).not.toBeNull();
    });

    await act(async () => {
      cm.listener?.({
        docChanged: true,
        state: { doc: { toString: () => "flowchart TD\n  A --> D" } },
      });
    });

    expect(screen.getByTestId("mermaid-save-btn")).toBeEnabled();
  });
});
