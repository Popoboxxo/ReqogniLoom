/**
 * ARCH-L1-001 ReactFrontend — GlossaryView trace-link and synonym-link tests
 * (REQ-006, Cluster A C9/C10).
 *
 * leaf_id: COMP-RF-014 (ArtifactInspector), COMP-RF-GLOSSARY
 * req_id:  REQ-006 (C9 glossary trace links, C10 synonym linking)
 *
 * Covers:
 *   - C9: "Neue Verknüpfung" button + CreateTraceLinkDialog only render for
 *     an existing entry being edited (sourceId = the entry's id).
 *   - C10: a synonym whose text matches an existing entry's term renders as
 *     a clickable chip that selects that entry for editing.
 *   - C10: a synonym with no match renders a "link" button that opens a
 *     picker; selecting a candidate normalizes the synonym text via
 *     glossaryApi.update (no dedicated backend link field exists).
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import type { GlossaryTerm } from "../types";

// ---------------------------------------------------------------------------
// Mocks (must precede component import)
// ---------------------------------------------------------------------------

vi.mock("react-i18next", () => {
  // Second arg is either a string fallback or an i18n interpolation options
  // object (e.g. { count, defaultValue }) — mirror BaselinesView's mock so
  // PageHeader's `summary` (interpolated) doesn't render a raw object.
  const t = (key: string, fallbackOrOptions?: string | Record<string, unknown>): string =>
    typeof fallbackOrOptions === "string" ? fallbackOrOptions : key;
  return { useTranslation: () => ({ t }) };
});

vi.mock("../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "ws-001", name: "WS" } }),
}));

// Isolate from the ArtifactInspector sidebar — its own data fetching is out
// of scope for this test (TracePanel behavior for glossary is covered by the
// pre-existing "backend gap" documentation, not re-tested here).
vi.mock("../components/shared/ArtifactInspector", () => ({
  RightSidebar: () => null,
}));

// Stub CreateTraceLinkDialog so this test only asserts GlossaryView passes
// the right props (workspaceId, sourceId, allowedTypes) — the dialog's own
// behavior is covered by create-trace-link-dialog.test.tsx.
vi.mock("../components/shared/CreateTraceLinkDialog/create-trace-link-dialog", () => ({
  CreateTraceLinkDialog: (props: {
    isOpen: boolean;
    sourceId?: string;
    workspaceId: string;
    allowedTypes?: string[];
  }) =>
    props.isOpen ? (
      <div data-testid="mock-trace-link-dialog">
        source:{props.sourceId} workspace:{props.workspaceId} types:{(props.allowedTypes ?? []).join(",")}
      </div>
    ) : null,
}));

const TERM_A: GlossaryTerm = {
  id: "term-a",
  workspace_id: "ws-001",
  term: "Requirement",
  definition: "A documented need.",
  synonyms: ["Anforderung", "Unmatched Synonym"],
  abbreviation: "REQ",
};

const TERM_B: GlossaryTerm = {
  id: "term-b",
  workspace_id: "ws-001",
  term: "Anforderung",
  definition: "German synonym entry, already a real glossary term.",
  synonyms: [],
};

vi.mock("../api/glossary", () => ({
  glossaryApi: {
    list: vi.fn(),
    get: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    diff: vi.fn(),
    versions: vi.fn(),
  },
}));

// Must import AFTER vi.mock calls.
import GlossaryView from "../components/GlossaryView/GlossaryView";
import { glossaryApi } from "../api/glossary";

function renderView(): ReturnType<typeof render> {
  return render(
    <MemoryRouter>
      <GlossaryView />
    </MemoryRouter>
  );
}

describe("GlossaryView — C9 trace links + C10 synonym linking (REQ-006)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(glossaryApi.list).mockResolvedValue([TERM_A, TERM_B]);
    vi.mocked(glossaryApi.update).mockResolvedValue(TERM_A);
  });

  it("C9: does not show the create-link button before an entry is selected", async () => {
    renderView();
    await waitFor(() => {
      expect(screen.getByText("Requirement")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("glossary-create-link-button")).not.toBeInTheDocument();
  });

  it("C9: shows the create-link button and dialog wired to the selected entry once editing", async () => {
    const user = userEvent.setup();
    renderView();

    await waitFor(() => {
      expect(screen.getByText("Requirement")).toBeInTheDocument();
    });

    // Open the edit form for TERM_A via its Edit icon button.
    const editButtons = screen.getAllByTitle("Edit");
    await user.click(editButtons[0]);

    const linkButton = await screen.findByTestId("glossary-create-link-button");
    await user.click(linkButton);

    const dialog = await screen.findByTestId("mock-trace-link-dialog");
    expect(dialog).toHaveTextContent("source:term-a");
    expect(dialog).toHaveTextContent("workspace:ws-001");
    expect(dialog).toHaveTextContent("types:requirement,architecture,testcase");
  });

  it("C10: renders a synonym matching an existing term as a clickable link", async () => {
    const user = userEvent.setup();
    renderView();

    // Synonyms render in the detail pane (relocated with the SplitView
    // migration, issue #180) — select the term row first.
    await user.click(await screen.findByTestId("glossary-row-term-a"));

    // "Anforderung" (TERM_A's synonym) matches TERM_B's term text exactly.
    const linkedChip = await screen.findByTestId("glossary-synonym-link-term-a-0");
    expect(linkedChip).toHaveTextContent("Anforderung");
  });

  it("C10: clicking a linked synonym selects the matched entry for editing", async () => {
    const user = userEvent.setup();
    renderView();

    await user.click(await screen.findByTestId("glossary-row-term-a"));
    const linkedChip = await screen.findByTestId("glossary-synonym-link-term-a-0");
    await user.click(linkedChip);

    // Editing TERM_B now — its term value appears (disabled) in the form.
    await waitFor(() => {
      expect(screen.getByDisplayValue("Anforderung")).toBeInTheDocument();
    });
  });

  it("C10: an unmatched synonym shows a link-picker that normalizes the text on selection", async () => {
    const user = userEvent.setup();
    renderView();

    await user.click(await screen.findByTestId("glossary-row-term-a"));
    const linkTrigger = await screen.findByTestId("glossary-synonym-linkbtn-term-a-1");
    await user.click(linkTrigger);

    const option = await screen.findByTestId("glossary-synonym-option-term-a-1-term-b");
    await user.click(option);

    await waitFor(() => {
      expect(glossaryApi.update).toHaveBeenCalledWith("term-a", {
        synonyms: ["Anforderung", "Anforderung"],
      });
    });
  });
});
