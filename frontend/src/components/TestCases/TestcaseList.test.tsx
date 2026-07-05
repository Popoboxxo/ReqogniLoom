/**
 * Tests for TestcaseList component.
 * REQ-L1-040 Phase 3: SE Masks Rollout — test case list view.
 *
 * Verifies:
 * - list loads on mount
 * - form validation (title required)
 * - create calls testcasesApi.create with the registered contract payload
 * - list refreshes after create
 * - ModalDialogBase pattern integration
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import userEvent from "@testing-library/user-event";
import { TestcaseList } from "./TestcaseList";
import * as testcasesModule from "../../api/testcases";
import * as workspaceContext from "../../context/WorkspaceContext";

vi.mock("../../api/testcases");
vi.mock("../../context/WorkspaceContext");
vi.mock("../../api/client", () => ({
  getList: vi.fn().mockResolvedValue({ results: [], count: 0 }),
  extractErrorMessage: vi.fn().mockReturnValue("duplicate title"),
  apiClient: {
    get: vi.fn().mockResolvedValue({}),
    post: vi.fn().mockResolvedValue({}),
    put: vi.fn().mockResolvedValue({}),
    patch: vi.fn().mockResolvedValue({}),
    delete: vi.fn().mockResolvedValue({}),
  },
}));
// Stable t reference — a fresh t per render would re-trigger the
// useCallback([activeWorkspace, t]) load effect in an endless loop.
vi.mock("react-i18next", () => {
  const t = (key: string): string => key;
  return { useTranslation: () => ({ t }) };
});

const mockWorkspace = { id: "ws-123", name: "Test", preset: "standard" };

const mockTestcases = [
  {
    id: "tc-1",
    workspace_id: "ws-123",
    title: "User login flow",
    description: "Test login with valid credentials",
    status: "active",
    version: 1,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
  {
    id: "tc-2",
    workspace_id: "ws-123",
    title: "Invalid password handling",
    description: "",
    status: "draft",
    version: 2,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
];

describe("TestcaseList (REQ-L1-040 Phase 3)", () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  const renderComponent = () => {
    render(
      <QueryClientProvider client={queryClient}>
        <TestcaseList />
      </QueryClientProvider>
    );
  };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(workspaceContext.useWorkspace).mockReturnValue({
      activeWorkspace: mockWorkspace,
    } as any);
    vi.mocked(testcasesModule.testcasesApi.list).mockResolvedValue({
      results: mockTestcases,
    } as any);
  });

  it("loads the test case list on mount", async () => {
    renderComponent();

    await waitFor(() => {
      expect(screen.getByTestId("testcase-item-tc-1")).toBeInTheDocument();
    });
    expect(testcasesModule.testcasesApi.list).toHaveBeenCalledWith("ws-123");
    expect(screen.getByText("User login flow")).toBeInTheDocument();
    expect(screen.getByText("Invalid password handling")).toBeInTheDocument();
  });

  it("displays status for each test case", async () => {
    renderComponent();

    await waitFor(() => {
      expect(screen.getByTestId("testcase-item-tc-1")).toBeInTheDocument();
    });
    expect(screen.getByText(/— active/)).toBeInTheDocument();
    expect(screen.getByText(/— draft/)).toBeInTheDocument();
  });

  it("shows empty state when no test cases exist", async () => {
    vi.mocked(testcasesModule.testcasesApi.list).mockResolvedValue({
      results: [],
    } as any);

    renderComponent();

    await waitFor(() => {
      expect(screen.queryByTestId(/testcase-item/)).not.toBeInTheDocument();
    });
  });

  it("validates that title is required before create", async () => {
    const user = userEvent.setup();
    renderComponent();

    await waitFor(() => {
      expect(screen.getByTestId("testcase-create-btn")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("testcase-create-btn"));
    // Try submitting with only whitespace
    await user.type(screen.getByTestId("testcase-title-input"), "   ");
    await user.click(screen.getByTestId("testcase-save-btn"));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
    expect(testcasesModule.testcasesApi.create).not.toHaveBeenCalled();
  });

  it("creates a test case with the registered contract payload", async () => {
    vi.mocked(testcasesModule.testcasesApi.create).mockResolvedValue({
      id: "tc-3",
    } as any);
    const user = userEvent.setup();
    renderComponent();

    await waitFor(() => {
      expect(screen.getByTestId("testcase-create-btn")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("testcase-create-btn"));

    await user.type(
      screen.getByTestId("testcase-title-input"),
      "New test case"
    );
    await user.type(
      screen.getByTestId("testcase-description-input"),
      "Test description"
    );
    await user.selectOptions(
      screen.getByTestId("testcase-status-select"),
      "active"
    );
    await user.click(screen.getByTestId("testcase-save-btn"));

    await waitFor(() => {
      expect(testcasesModule.testcasesApi.create).toHaveBeenCalledWith({
        workspace_id: "ws-123",
        title: "New test case",
        description: "Test description",
        status: "active",
      });
    });
  });

  it("refreshes the list after a successful create", async () => {
    vi.mocked(testcasesModule.testcasesApi.create).mockResolvedValue({
      id: "tc-3",
      workspace_id: "ws-123",
    } as any);
    const user = userEvent.setup();
    renderComponent();

    await waitFor(() => {
      expect(screen.getByTestId("testcase-create-btn")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("testcase-create-btn"));
    await user.type(screen.getByTestId("testcase-title-input"), "New test");
    await user.click(screen.getByTestId("testcase-save-btn"));

    await waitFor(() => {
      // initial load + refresh after create
      expect(testcasesModule.testcasesApi.list).toHaveBeenCalledTimes(2);
    });
  });

  it("shows an API error in the form alert", async () => {
    vi.mocked(testcasesModule.testcasesApi.create).mockRejectedValue({
      error: { message: "duplicate title" },
    });
    const user = userEvent.setup();
    renderComponent();

    await waitFor(() => {
      expect(screen.getByTestId("testcase-create-btn")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("testcase-create-btn"));
    await user.type(screen.getByTestId("testcase-title-input"), "Dup");
    await user.click(screen.getByTestId("testcase-save-btn"));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("duplicate title");
    });
  });
});
