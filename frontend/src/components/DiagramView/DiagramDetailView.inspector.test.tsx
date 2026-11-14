/**
 * DiagramDetailView — the inspector mount (#1762 / M7).
 *
 * Spec §2.1: the detail pane is a two-zone row — the content column and the
 * shared shell (Version / Diff / Links / Comments). Spec §11 D8: a diagram
 * has no derivation chain, so its Links tab lists every link type as a row.
 *
 * The comments tab is keyed on the backing Artifact UUID — `artifact_id`
 * (#1374) or its `global_uuid` alias. A legacy diagram without either gets
 * three tabs, no request, no error banner (spec §4.3).
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import type { DiagramDetail } from "../../types";
import type { DiagramDetailData } from "./useDiagramData";
import * as diagramsModule from "../../api/diagrams";
import * as commentsModule from "../../api/comments";
import * as tracelinksModule from "../../api/tracelinks";

vi.mock("../../api/diagrams");
vi.mock("../../api/comments");
vi.mock("../../api/tracelinks");
vi.mock("../../api/interviews", () => ({
  interviewsApi: { getProvenance: vi.fn().mockResolvedValue({ session_id: null }) },
}));
vi.mock("../../context/WorkspaceContext", () => ({
  useWorkspace: () => ({
    activeWorkspace: { id: "ws-1", name: "WS", default_link_type: "references" },
  }),
}));
vi.mock("../../context/LinkTypeContext", () => ({
  useLinkTypes: () => ({
    linkTypes: [{ key: "references", definition: { label: {}, allowed_pairs: [] } }],
    creatableLinkTypes: [],
    isLoading: false,
    error: null,
    reload: vi.fn(),
    definitionFor: () => undefined,
    isAllowedPair: () => true,
    labelFor: (key: string) => key,
  }),
}));
vi.mock("../WorkflowStatusEditor", () => ({ WorkflowStatusEditor: () => null }));
vi.mock("../canvas/CanvasEditor", () => ({
  CanvasEditor: () => <div data-testid="canvas-editor-mounted" />,
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, second?: unknown): string => {
      if (typeof second === "string") return second;
      if (second && typeof second === "object" && "defaultValue" in second) {
        return String((second as { defaultValue: unknown }).defaultValue);
      }
      return key;
    },
  }),
}));

const useDiagramDetailMock = vi.fn();
vi.mock("./useDiagramData", () => ({
  useDiagramDetail: (id: string) => useDiagramDetailMock(id),
}));

import { DiagramDetailView } from "./DiagramDetailView";

const DIAGRAM_ID = "diag-001";

function detailRow(over: Partial<DiagramDetail> = {}): DiagramDetail {
  return {
    id: DIAGRAM_ID,
    name: "Power Distribution",
    diagram_type: "block",
    description: "",
    current_version: null,
    created_at: "2026-02-01T10:00:00Z",
    payload_format: "plantuml",
    content: "@startuml\nA -> B\n@enduml",
    version_number: 3,
    ...over,
  } as DiagramDetail;
}

function hookResult(detail: DiagramDetail): DiagramDetailData {
  return {
    detail,
    isLoading: false,
    canvasSvg: undefined,
    isCanvasLoading: false,
    saveContent: vi.fn(),
    deleteDiagram: vi.fn(),
    isSaving: false,
    saveError: null,
    resetSaveError: vi.fn(),
  };
}

function setViewport(width: number): void {
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    writable: true,
    value: width,
  });
}

function renderDetail(detail: DiagramDetail): ReturnType<typeof render> {
  useDiagramDetailMock.mockReturnValue(hookResult(detail));
  return render(
    <MemoryRouter initialEntries={[`/diagrams/${DIAGRAM_ID}`]}>
      <DiagramDetailView
        diagramId={DIAGRAM_ID}
        onBack={vi.fn()}
        onChanged={vi.fn()}
      />
    </MemoryRouter>,
  );
}

describe("DiagramDetailView — inspector mount (#1762 M7)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    window.history.replaceState({}, "", `/diagrams/${DIAGRAM_ID}`);
    setViewport(1440);
    vi.mocked(diagramsModule.diagramsApi.versions).mockResolvedValue([]);
    vi.mocked(diagramsModule.diagramsApi.diff).mockResolvedValue({
      from_version: 0,
      to_version: 1,
      changes: [],
    } as never);
    vi.mocked(commentsModule.commentsApi.list).mockResolvedValue([]);
    vi.mocked(tracelinksModule.tracelinksApi.listForArtifact).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    } as never);
  });

  it("mounts the shell as the sibling right column of the content", () => {
    renderDetail(detailRow({ artifact_id: "artifact-diag-1" }));

    const shell = screen.getByTestId("inspector-shell");
    // Two zones, one pane: both live under the same parent, and the content
    // column still holds the diagram itself.
    expect(shell.parentElement).not.toBeNull();
    expect(shell.parentElement?.textContent).toContain("Power Distribution");
    expect(screen.getByTestId("inspector-skip-link")).toBeInTheDocument();
  });

  it("renders four tabs and keys comments on artifact_id", async () => {
    renderDetail(detailRow({ artifact_id: "artifact-diag-1" }));

    expect(screen.getByTestId("inspector-tab-comments")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("inspector-tab-comments"));

    await waitFor(() => {
      expect(commentsModule.commentsApi.list).toHaveBeenCalledWith("artifact-diag-1");
    });
    expect(commentsModule.commentsApi.list).not.toHaveBeenCalledWith(DIAGRAM_ID);
  });

  it("falls back to global_uuid for the comments id", async () => {
    renderDetail(detailRow({ global_uuid: "artifact-diag-global" }));

    fireEvent.click(screen.getByTestId("inspector-tab-comments"));

    await waitFor(() => {
      expect(commentsModule.commentsApi.list).toHaveBeenCalledWith(
        "artifact-diag-global",
      );
    });
  });

  it("renders three tabs for a legacy diagram without a backing Artifact", () => {
    renderDetail(detailRow());

    expect(screen.getByTestId("inspector-tab-links")).toBeInTheDocument();
    expect(screen.queryByTestId("inspector-tab-comments")).not.toBeInTheDocument();
    expect(commentsModule.commentsApi.list).not.toHaveBeenCalled();
  });
});
