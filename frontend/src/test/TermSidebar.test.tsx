/**
 * F3-T9 — glossary term sidebar (drag source for inline references).
 *
 * The sidebar hands out the canonical stored token, never the `[[Begriff]]`
 * display form (ENT-F3 = a). A click inserts at the caller's caret; a drag
 * start puts the same token on the data transfer.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import "../i18n/index";

vi.mock("../api/glossary", () => ({
  glossaryApi: {
    list: vi.fn(),
    insertReference: vi.fn(),
    resolveReferences: vi.fn(),
    upgradeReferencesToHead: vi.fn(),
  },
}));

vi.mock("../context/WorkspaceContext", () => ({
  useWorkspace: () => ({
    activeWorkspace: { id: "ws-1", glossary_reference_mode: "pinned" },
  }),
}));

import { TermSidebar } from "../components/WorkItems/TermSidebar";
import { glossaryApi } from "../api/glossary";

const listMock = glossaryApi.list as ReturnType<typeof vi.fn>;

const TERM = {
  id: "term-1",
  workspace_id: "ws-1",
  term: "Trace",
  definition: "A link",
  synonyms: [],
  global_uuid: "00000000-0000-0000-0000-000000000001",
  version: 2,
};

describe("TermSidebar (F3-T9)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listMock.mockResolvedValue([TERM]);
  });

  it("inserts the pinned token on click", async () => {
    const onInsert = vi.fn();
    render(<TermSidebar workspaceId="ws-1" onInsert={onInsert} />);

    await waitFor(() =>
      expect(
        screen.getByTestId(`term-sidebar-item-${TERM.global_uuid}`)
      ).toBeInTheDocument()
    );
    fireEvent.click(screen.getByTestId(`term-sidebar-item-${TERM.global_uuid}`));

    expect(onInsert).toHaveBeenCalledWith(
      `[[glossary:${TERM.global_uuid}@2]]`
    );
  });

  it("puts the same token on the drag data transfer", async () => {
    render(<TermSidebar workspaceId="ws-1" onInsert={vi.fn()} />);

    const button = await screen.findByTestId(
      `term-sidebar-item-${TERM.global_uuid}`
    );
    const setData = vi.fn();
    fireEvent.dragStart(button, {
      dataTransfer: { setData, effectAllowed: "" },
    });

    expect(setData).toHaveBeenCalledWith(
      "text/plain",
      `[[glossary:${TERM.global_uuid}@2]]`
    );
  });

  it("shows the empty state when the workspace has no terms", async () => {
    listMock.mockResolvedValue([]);
    render(<TermSidebar workspaceId="ws-1" onInsert={vi.fn()} />);

    await waitFor(() =>
      expect(screen.getByTestId("term-sidebar-empty")).toBeInTheDocument()
    );
  });
});
