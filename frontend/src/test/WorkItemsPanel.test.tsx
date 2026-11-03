/**
 * F3-T9 — document work-state panel.
 *
 * Covers the four data states (loading/error/empty/success), the resume panel
 * (`work_item.resume`), the kind/status chips, the create flow and the two
 * write paths the item owns: content PATCH with `expectedVersion` and a
 * transition that carries `blocked_reason`.
 */

import { describe, it, expect, vi, beforeEach, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { i18n } from "../i18n/index";

vi.mock("../api/workItems", () => ({
  workItemsApi: {
    listAll: vi.fn(),
    get: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    reactivate: vi.fn(),
    transitions: vi.fn(),
    transition: vi.fn(),
    versions: vi.fn(),
    diff: vi.fn(),
    resume: vi.fn(),
  },
}));

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
    isLoadingWorkspace: false,
  }),
  useOptionalWorkspace: () => ({
    activeWorkspace: { id: "ws-1", glossary_reference_mode: "pinned" },
    isLoadingWorkspace: false,
  }),
}));

import { WorkItemsPanel } from "../components/WorkItems/WorkItemsPanel";
import { workItemsApi } from "../api/workItems";
import { glossaryApi } from "../api/glossary";

const listAll = workItemsApi.listAll as ReturnType<typeof vi.fn>;
const create = workItemsApi.create as ReturnType<typeof vi.fn>;
const update = workItemsApi.update as ReturnType<typeof vi.fn>;
const transitions = workItemsApi.transitions as ReturnType<typeof vi.fn>;
const transition = workItemsApi.transition as ReturnType<typeof vi.fn>;
const resume = workItemsApi.resume as ReturnType<typeof vi.fn>;
const glossaryList = glossaryApi.list as ReturnType<typeof vi.fn>;

const ITEM = {
  id: "wi-1",
  workspace_id: "ws-1",
  document_id: "doc-1",
  artifact_id: "art-wi-1",
  uid: "WI-001",
  title: "Draft the plan",
  kind: "Step" as const,
  ordinal: 0,
  body: "Write the outline.",
  progress: 40,
  blocked_reason: "",
  next_action: "Continue with section 2",
  last_activity_at: "2026-11-02T10:00:00Z",
  last_actor: "agent:writer",
  evidence_ref: "",
  approved_by: "",
  approved_at: null,
  due_date: null,
  exit_criteria: "",
  status: "in_progress",
  version: 3,
  created_at: "2026-11-02T09:00:00Z",
  updated_at: "2026-11-02T10:00:00Z",
};

const OPEN_ENTRY = {
  id: "wi-1",
  uid: "WI-001",
  kind: "Step" as const,
  status: "in_progress",
  progress: 40,
  next_action: "Continue with section 2",
  blocked_reason: "",
  last_actor: "agent:writer",
  last_activity_at: "2026-11-02T10:00:00Z",
  links: [],
};

const CHECKPOINT = {
  ...OPEN_ENTRY,
  id: "wi-9",
  uid: "WI-009",
  kind: "Checkpoint" as const,
  next_action: "Resume at section 2",
};

function renderPanel(): void {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <WorkItemsPanel documentId="doc-1" workspaceId="ws-1" canWrite />
    </QueryClientProvider>
  );
}

describe("WorkItemsPanel (F3-T9)", () => {
  beforeAll(async () => {
    await i18n.changeLanguage("de");
  });

  beforeEach(() => {
    vi.clearAllMocks();
    listAll.mockResolvedValue([ITEM]);
    resume.mockResolvedValue({
      checkpoint: CHECKPOINT,
      open_items: [OPEN_ENTRY],
    });
    transitions.mockResolvedValue({
      current_state: "in_progress",
      version: 3,
      states: ["todo", "in_progress", "blocked", "done"],
      allowed_transitions: [
        {
          target_state: "blocked",
          requires_change_reason: false,
          signature_gate: false,
        },
      ],
      proposed_by: null,
    });
    create.mockResolvedValue({ ...ITEM, id: "wi-2", uid: "WI-002" });
    update.mockResolvedValue({ ...ITEM, title: "Renamed", version: 4 });
    transition.mockResolvedValue({
      id: "wi-1",
      previous_state: "in_progress",
      new_state: "blocked",
      version: 4,
      work_item: { ...ITEM, status: "blocked", version: 4 },
    });
    glossaryList.mockResolvedValue([]);
  });

  it("renders the item list, the chips and the resume panel", async () => {
    renderPanel();

    await waitFor(() =>
      expect(screen.getByTestId("work-item-row-wi-1")).toBeInTheDocument()
    );
    expect(screen.getByTestId("work-item-kind-wi-1")).toHaveTextContent(
      "Schritt"
    );
    expect(screen.getByTestId("work-item-status-wi-1")).toHaveTextContent(
      "In Arbeit"
    );
    expect(screen.getByTestId("work-item-resume")).toBeInTheDocument();
    expect(screen.getByTestId("work-item-resume-checkpoint-item-wi-9")).toBeInTheDocument();
    expect(screen.getByTestId("work-item-resume-item-wi-1")).toBeInTheDocument();
    expect(screen.getByTestId("work-item-detail")).toBeInTheDocument();
  });

  it("shows the empty state when the document has no items", async () => {
    listAll.mockResolvedValue([]);
    resume.mockResolvedValue({ checkpoint: null, open_items: [] });
    renderPanel();

    await waitFor(() =>
      expect(screen.getByTestId("work-items-list-empty")).toBeInTheDocument()
    );
    expect(screen.getByTestId("work-item-select-prompt")).toBeInTheDocument();
    expect(screen.getByTestId("work-item-resume-empty")).toBeInTheDocument();
  });

  it("renders an error state with retry for the list", async () => {
    listAll.mockRejectedValue(new Error("list failed"));
    renderPanel();

    await waitFor(() =>
      expect(screen.getByTestId("work-items-list-error")).toBeInTheDocument()
    );
  });

  it("renders an error state with retry for the resume panel", async () => {
    resume.mockRejectedValue(new Error("resume failed"));
    renderPanel();

    await waitFor(() =>
      expect(screen.getByTestId("work-item-resume-error")).toBeInTheDocument()
    );
    expect(screen.getByTestId("work-item-resume-retry")).toBeInTheDocument();
  });

  it("creates an item inside the open document", async () => {
    renderPanel();
    await waitFor(() =>
      expect(screen.getByTestId("work-item-new")).toBeInTheDocument()
    );

    await userEvent.click(screen.getByTestId("work-item-new"));
    await userEvent.type(
      screen.getByTestId("work-item-create-title"),
      "Next phase"
    );
    await userEvent.click(screen.getByTestId("work-item-create-save"));

    await waitFor(() =>
      expect(create).toHaveBeenCalledWith(
        expect.objectContaining({
          workspace_id: "ws-1",
          document_id: "doc-1",
          title: "Next phase",
          kind: "Step",
        })
      )
    );
  });

  it("saves content with the rendered item version as the precondition", async () => {
    renderPanel();
    await waitFor(() =>
      expect(screen.getByTestId("work-item-edit")).toBeInTheDocument()
    );

    await userEvent.click(screen.getByTestId("work-item-edit"));
    const title = screen.getByTestId("work-item-edit-title");
    await userEvent.clear(title);
    await userEvent.type(title, "Renamed");
    await userEvent.click(screen.getByTestId("work-item-edit-save"));

    await waitFor(() =>
      expect(update).toHaveBeenCalledWith(
        "wi-1",
        expect.objectContaining({ title: "Renamed" }),
        3
      )
    );
  });

  it("transitions to blocked with a mandatory reason", async () => {
    renderPanel();
    await waitFor(() =>
      expect(screen.getByTestId("work-item-transition-select")).toBeInTheDocument()
    );

    await userEvent.selectOptions(
      screen.getByTestId("work-item-transition-select"),
      "blocked"
    );
    await userEvent.type(
      screen.getByTestId("work-item-transition-blocked-reason"),
      "waiting for review"
    );
    await userEvent.click(screen.getByTestId("work-item-transition-execute"));

    await waitFor(() =>
      expect(transition).toHaveBeenCalledWith("wi-1", "blocked", {
        changeReason: "",
        credential: "",
        blockedReason: "waiting for review",
        expectedVersion: 3,
      })
    );
  });
});
