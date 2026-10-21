/**
 * Issue #1368 (W12b) — the `decompose-next-level` draft flow at the
 * Requirement editor.
 *
 * The defect: the preview's drafts were counted and dropped while
 * `needs.deriveSuccess` promised "Vorschlag/Vorschläge warten unter Reviews →
 * Nur KI-Vorschläge" — a queue entry that never existed, because the endpoint
 * persists nothing (#1358) and the UI had no confirm step.
 *
 * This test pins the replacement behaviour end to end at the component level:
 *
 *   1. the trigger calls the preview and renders every draft in the shared
 *      `<AiDerivationDialog>` — the drafts are no longer discarded;
 *   2. the preview alone never produces a save message;
 *   3. Confirm calls the accept seam (`acceptAiDecomposition`) with the
 *      selected drafts and only then reports where they are reviewable;
 *   4. "Review later" uses the same seam and names the queue;
 *   5. Discard writes nothing;
 *   6. an accept whose receipt is not a proposal surfaces the server's reason
 *      instead of claiming success.
 *
 * The module graph is stubbed the same way the sibling
 * `requirement-editors-custom-fields-dirty.test.tsx` does it — the flow under
 * test lives in `RequirementEditors` itself.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("react-i18next", () => {
  const t = (
    key: string,
    fallbackOrOptions?: string | Record<string, unknown>,
  ): string => {
    if (typeof fallbackOrOptions === "string") return fallbackOrOptions;
    if (fallbackOrOptions && typeof fallbackOrOptions === "object") {
      const rendered = Object.entries(fallbackOrOptions)
        .map(([k, v]) => `${k}=${String(v)}`)
        .join(" ");
      return rendered ? `${key} ${rendered}` : key;
    }
    return key;
  };
  return { useTranslation: () => ({ t, i18n: { language: "de" } }) };
});

const navigateMock = vi.fn();
vi.mock("react-router-dom", () => ({
  useParams: () => ({ id: "req-001" }),
  useNavigate: () => navigateMock,
}));

vi.mock("../context/WorkspaceContext", () => ({
  useWorkspace: () => ({
    activeWorkspace: { id: "ws-001", preset: "standard" },
    workspaces: [{ id: "ws-001" }],
  }),
  useOptionalWorkspace: () => ({
    activeWorkspace: { id: "ws-001", preset: "standard" },
    workspaces: [{ id: "ws-001" }],
  }),
}));

vi.mock("../hooks/useHasRole", () => ({
  useHasRole: () => () => true,
}));

const MOCK_REQUIREMENT = {
  id: "req-001",
  workspace_id: "ws-001",
  artifact_id: "art-001",
  title: "Login works",
  description: "",
  category: "functional",
  uid: "REQ-001",
  suspect: false,
  status: "draft",
  version: 1,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  custom_fields: {},
} as never;

const refreshMock = vi.fn();
vi.mock("../components/RequirementEditors/useRequirementData", () => ({
  useRequirementData: () => ({
    requirements: [MOCK_REQUIREMENT],
    requirement: MOCK_REQUIREMENT,
    upstreamLinks: [],
    downstreamLinks: [],
    linkedTitles: {},
    linkedRoutes: {},
    isLoading: false,
    error: null,
    refresh: refreshMock,
  }),
}));

vi.mock("../components/RequirementEditors/RequirementArtifactForm", () => ({
  RequirementArtifactForm: () => <div data-testid="req-artifact-form-stub" />,
}));

vi.mock("../components/RequirementEditors/RequirementList", () => ({
  RequirementList: () => <div data-testid="req-list-stub" />,
}));

vi.mock("../components/SplitView/SplitView", () => ({
  SplitView: ({
    leftPanel,
    rightPanel,
  }: {
    leftPanel: React.ReactNode;
    rightPanel: React.ReactNode;
  }) => (
    <div>
      {leftPanel}
      {rightPanel}
    </div>
  ),
}));

vi.mock("../components/shared/ArtifactInspector", () => ({
  RightSidebar: () => null,
}));

vi.mock("../components/shared/TraceSpine", () => ({
  TraceSpine: () => null,
  useDerivationChain: () => ({
    stations: [],
    isLoading: false,
    error: null,
    isOpenable: false,
    resolveEntry: () => null,
  }),
}));

vi.mock("../components/RequirementEditors/ReqTraceLinkPanel", () => ({
  ReqTraceLinkPanel: () => null,
}));

vi.mock("../components/RequirementEditors/SimilarRequirementsPanel", () => ({
  SimilarRequirementsPanel: () => null,
}));

const aiDecomposeNextLevel = vi.fn();
const acceptAiDecomposition = vi.fn();
vi.mock("../api/requirements", () => ({
  requirementsApi: {
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    aiDecomposeNextLevel: (...args: unknown[]) => aiDecomposeNextLevel(...args),
    acceptAiDecomposition: (...args: unknown[]) => acceptAiDecomposition(...args),
  },
}));

vi.mock("../queries/requirements", () => ({
  useCreateRequirement: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeleteRequirement: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

vi.mock("../api/workspaces", () => ({
  workspacesApi: { downloadPdfReport: vi.fn() },
}));

// Must import AFTER vi.mock
import RequirementEditors from "../components/RequirementEditors/RequirementEditors";

const DRAFT_ONE = {
  title: "Decomposed requirement 1",
  description: "Refine the parent.",
  rationale: "Mock rationale.",
  suggested_arch_element_id: null,
};
const DRAFT_TWO = {
  title: "Decomposed requirement 2",
  description: "Second concern.",
  rationale: "",
  suggested_arch_element_id: null,
};

const PREVIEW = {
  drafts: [DRAFT_ONE, DRAFT_TWO],
  parent_requirement_id: "req-001",
  ephemeral: true,
};

const ACCEPT_OK = {
  count: 2,
  created: [
    {
      id: "child-1",
      status: "proposed",
      trace_link_id: "tl-1",
      proposal: { is_proposal: true },
    },
    {
      id: "child-2",
      status: "proposed",
      trace_link_id: "tl-2",
      proposal: { is_proposal: true },
    },
  ],
  proposal: { is_proposal: true },
};

async function openDeriveDialog(): Promise<void> {
  const user = userEvent.setup();
  await user.click(await screen.findByTestId("req-ai-derive-btn"));
  await screen.findByTestId("req-derive-drafts-dialog");
}

describe("RequirementEditors — decompose-next-level draft flow (#1368)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    aiDecomposeNextLevel.mockResolvedValue(PREVIEW);
    acceptAiDecomposition.mockResolvedValue(ACCEPT_OK);
  });

  it("renders the preview's drafts and claims nothing was saved", async () => {
    render(<RequirementEditors />);
    await openDeriveDialog();

    expect(aiDecomposeNextLevel).toHaveBeenCalledWith("req-001");
    expect(screen.getByTestId("req-derive-drafts-title-0")).toHaveTextContent(
      "Decomposed requirement 1",
    );
    expect(screen.getByTestId("req-derive-drafts-title-1")).toHaveTextContent(
      "Decomposed requirement 2",
    );
    // The preview is labelled as such — nothing is persisted yet.
    expect(screen.getByTestId("req-derive-drafts-notice")).toHaveTextContent(
      "aiDerivation.notice",
    );
    // And no success/queue claim exists at this point.
    expect(screen.queryByTestId("req-ai-derive-status")).not.toBeInTheDocument();
    expect(acceptAiDecomposition).not.toHaveBeenCalled();
  });

  it("confirm sends the selected drafts to the accept seam and then names the queue", async () => {
    const user = userEvent.setup();
    render(<RequirementEditors />);
    await openDeriveDialog();

    await user.click(screen.getByTestId("req-derive-drafts-confirm"));

    await waitFor(() => {
      expect(acceptAiDecomposition).toHaveBeenCalledWith("req-001", [
        {
          title: DRAFT_ONE.title,
          description: DRAFT_ONE.description,
          rationale: DRAFT_ONE.rationale,
        },
        {
          title: DRAFT_TWO.title,
          description: DRAFT_TWO.description,
          rationale: "",
        },
      ]);
    });
    await waitFor(() => {
      expect(screen.getByTestId("req-ai-derive-status")).toHaveTextContent(
        "aiDerivation.statusCreated",
      );
    });
    expect(screen.queryByTestId("req-derive-drafts-dialog")).not.toBeInTheDocument();
    expect(refreshMock).toHaveBeenCalled();
  });

  it("honours a deselected draft", async () => {
    const user = userEvent.setup();
    render(<RequirementEditors />);
    await openDeriveDialog();

    await user.click(screen.getByTestId("req-derive-drafts-select-1"));
    await user.click(screen.getByTestId("req-derive-drafts-confirm"));

    await waitFor(() => {
      expect(acceptAiDecomposition).toHaveBeenCalledWith("req-001", [
        {
          title: DRAFT_ONE.title,
          description: DRAFT_ONE.description,
          rationale: DRAFT_ONE.rationale,
        },
      ]);
    });
  });

  it("review later parks the same drafts in the review queue", async () => {
    const user = userEvent.setup();
    render(<RequirementEditors />);
    await openDeriveDialog();

    await user.click(screen.getByTestId("req-derive-drafts-later"));

    await waitFor(() => {
      expect(acceptAiDecomposition).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      expect(screen.getByTestId("req-ai-derive-status")).toHaveTextContent(
        "aiDerivation.statusParked",
      );
    });
  });

  it("discard writes nothing", async () => {
    const user = userEvent.setup();
    render(<RequirementEditors />);
    await openDeriveDialog();

    await user.click(screen.getByTestId("req-derive-drafts-discard"));

    expect(acceptAiDecomposition).not.toHaveBeenCalled();
    expect(screen.queryByTestId("req-derive-drafts-dialog")).not.toBeInTheDocument();
  });

  it("reports the server's reason when the accept did not become a proposal", async () => {
    acceptAiDecomposition.mockResolvedValue({
      count: 2,
      created: [],
      proposal: { is_proposal: false, reason: "no 'proposed' state in this graph" },
    });
    const user = userEvent.setup();
    render(<RequirementEditors />);
    await openDeriveDialog();

    await user.click(screen.getByTestId("req-derive-drafts-confirm"));

    await waitFor(() => {
      expect(screen.getByTestId("req-derive-drafts-submit-error")).toHaveTextContent(
        "no 'proposed' state in this graph",
      );
    });
    // No success message, and the drafts stay on screen.
    expect(screen.queryByTestId("req-ai-derive-status")).not.toBeInTheDocument();
    expect(screen.getByTestId("req-derive-drafts-drafts")).toBeInTheDocument();
  });

  it("surfaces a preview failure in the dialog instead of a false success", async () => {
    aiDecomposeNextLevel.mockRejectedValue({
      error: { code: "VALIDATION_ERROR", message: "no allocated architecture element" },
    });
    const user = userEvent.setup();
    render(<RequirementEditors />);

    await user.click(await screen.findByTestId("req-ai-derive-btn"));

    await screen.findByTestId("req-derive-drafts-error");
    expect(screen.getByTestId("req-derive-drafts-error")).toHaveTextContent(
      "no allocated architecture element",
    );
    expect(acceptAiDecomposition).not.toHaveBeenCalled();
  });
});
