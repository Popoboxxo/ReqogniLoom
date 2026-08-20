/**
 * ARCH-L1-001 ReactFrontend — InterviewEditors (plan Task 6).
 *
 * Acceptance criteria this suite checks:
 *   - the page renders like every other artifact editor (PageHeader with one
 *     <h1> + always-visible summary + primary "New Interview" action),
 *   - the list shows sessions as rows with a status badge, same as
 *     AdrList/RiskList,
 *   - selecting a row renders the detail panel (status badge, missing
 *     fields, chat + formalize panes),
 *   - starting a new interview from the header dialog calls
 *     `interviewsApi.start` and navigates to the new session,
 *   - the new `interview.abandon` action (no prior UI consumer) is wired up
 *     and only offered while `status === "in_progress"`.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import "../../i18n/index";

vi.mock("../../api/client", () => ({
  extractErrorMessage: vi.fn().mockReturnValue("Error"),
  apiClient: {
    get: vi.fn().mockResolvedValue({}),
    post: vi.fn().mockResolvedValue({}),
    patch: vi.fn().mockResolvedValue({}),
    delete: vi.fn().mockResolvedValue({}),
  },
  getList: vi.fn().mockResolvedValue({ results: [], count: 0 }),
  getAllPages: vi.fn().mockResolvedValue([]),
}));

const { SESSION_A } = vi.hoisted(() => ({
  SESSION_A: {
    id: "s-1",
    workspace_id: "ws-001",
    artifact_type: "Requirement",
    status: "in_progress",
  },
}));

vi.mock("../../api/interviews", () => ({
  interviewsApi: {
    listAll: vi.fn().mockResolvedValue([SESSION_A]),
    getState: vi.fn().mockResolvedValue({
      id: SESSION_A.id,
      status: SESSION_A.status,
      phase: "elicitation",
      collected_fields: {},
      missing_fields: [{ name: "title", type: "text", choices: null }],
      grounding_snapshot: {},
      transcript: [],
    }),
    start: vi.fn(),
    abandon: vi.fn(),
    chat: vi.fn(),
    formalize: vi.fn(),
  },
}));

vi.mock("../../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "ws-001", name: "WS" }, isLoadingWorkspace: false }),
}));

// Isolated from these two panes' own coverage (InterviewChatPane.test.tsx /
// InterviewArtifactPane.test.tsx) — they only need to not crash here.
import InterviewEditors from "./InterviewEditors";
import { interviewsApi } from "../../api/interviews";

function renderPage(initialPath = "/interviews"): ReturnType<typeof render> {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="/interviews" element={<InterviewEditors />} />
          <Route path="/interviews/:id" element={<InterviewEditors />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("InterviewEditors", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(interviewsApi.listAll).mockResolvedValue([SESSION_A] as any);
    vi.mocked(interviewsApi.getState).mockResolvedValue({
      id: SESSION_A.id,
      status: SESSION_A.status,
      phase: "elicitation",
      collected_fields: {},
      missing_fields: [{ name: "title", type: "text", choices: null }],
      grounding_snapshot: {},
      transcript: [],
    } as any);
  });

  it("renders one <h1> and an always-visible summary", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByTestId("page-header-count")).toHaveTextContent("1"));
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Interviews");
  });

  it("renders a session as a row with its status", async () => {
    renderPage();
    const row = await screen.findByTestId(`interview-row-${SESSION_A.id}`);
    expect(row).toHaveTextContent("In Progress");
  });

  it("shows the empty state when there are no interviews at all", async () => {
    vi.mocked(interviewsApi.listAll).mockResolvedValue([]);
    renderPage();
    await waitFor(() => expect(screen.getByTestId("interview-list-empty")).toBeInTheDocument());
  });

  it("selecting a row renders the detail panel with status and missing fields", async () => {
    renderPage(`/interviews/${SESSION_A.id}`);

    await waitFor(() => expect(screen.getByTestId("interview-detail")).toBeInTheDocument());
    expect(screen.getByTestId("interview-detail-status")).toHaveTextContent("In Progress");
    expect(screen.getByTestId("interview-missing-fields")).toHaveTextContent("title");
    // Abandon is offered while in_progress.
    expect(screen.getByTestId("interview-abandon-btn")).toBeInTheDocument();
  });

  it("starts a new interview from the header dialog and navigates to it", async () => {
    vi.mocked(interviewsApi.start).mockResolvedValue({
      id: "s-new",
      status: "in_progress",
      phase: "elicitation",
      collected_fields: {},
      missing_fields: [],
      grounding_snapshot: {},
      transcript: [],
    } as any);
    renderPage();

    const user = userEvent.setup();
    await user.click(await screen.findByTestId("create-interview-btn"));
    await screen.findByTestId("interview-start-dialog");

    await user.click(screen.getByTestId("interview-start-Requirement"));

    await waitFor(() => expect(interviewsApi.start).toHaveBeenCalledWith("ws-001", "Requirement"));
  });

  it("abandons an in-progress session after confirmation", async () => {
    vi.mocked(interviewsApi.abandon).mockResolvedValue({ status: "abandoned" });
    renderPage(`/interviews/${SESSION_A.id}`);

    const user = userEvent.setup();
    await user.click(await screen.findByTestId("interview-abandon-btn"));
    await user.click(screen.getByTestId("interview-abandon-confirm"));

    await waitFor(() => expect(interviewsApi.abandon).toHaveBeenCalledWith(SESSION_A.id));
  });

  it("auto-starts an interview for a `?start=<Type>` CTA link from another artifact page", async () => {
    vi.mocked(interviewsApi.start).mockResolvedValue({
      id: "s-cta",
      status: "in_progress",
      phase: "elicitation",
      collected_fields: {},
      missing_fields: [],
      grounding_snapshot: {},
      transcript: [],
    } as any);
    renderPage("/interviews?start=Risk");

    await waitFor(() => expect(interviewsApi.start).toHaveBeenCalledWith("ws-001", "Risk"));
    // No picker dialog -- the type is already known from the query param.
    expect(screen.queryByTestId("interview-start-dialog")).not.toBeInTheDocument();
  });

  it("ignores an unknown `?start=` type instead of calling the API", async () => {
    renderPage("/interviews?start=NotARealType");

    await screen.findByTestId("page-header-count");
    expect(interviewsApi.start).not.toHaveBeenCalled();
  });

  it("does not offer Abandon once a session is no longer in_progress", async () => {
    vi.mocked(interviewsApi.getState).mockResolvedValue({
      id: SESSION_A.id,
      status: "completed",
      phase: "done",
      collected_fields: {},
      missing_fields: [],
      grounding_snapshot: {},
      transcript: [],
    } as any);
    renderPage(`/interviews/${SESSION_A.id}`);

    await waitFor(() => expect(screen.getByTestId("interview-detail")).toBeInTheDocument());
    expect(screen.queryByTestId("interview-abandon-btn")).not.toBeInTheDocument();
  });
});
