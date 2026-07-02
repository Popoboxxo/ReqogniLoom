/**
 * Tests for RequirementsList component.
 * REQ-L1-040 Phase 2: SE Masks Unification — requirements list view.
 *
 * Verifies:
 * - list loads on mount
 * - form validation (title required)
 * - create calls requirementsApi.create with the registered contract payload
 * - list refreshes after create
 * - edit action navigates to RequirementEditors detail route
 * - delete calls the API after confirmation
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import RequirementsList from "./RequirementsList";
import * as requirementsModule from "../../api/requirements";
import * as workspaceContext from "../../context/WorkspaceContext";

const mockNavigate = vi.fn();

vi.mock("../../api/requirements");
vi.mock("../../context/WorkspaceContext");
vi.mock("react-router-dom", () => ({
  useNavigate: () => mockNavigate,
}));
// Stable t reference — a fresh t per render would re-trigger the
// useCallback([activeWorkspace, t]) load effect in an endless loop.
vi.mock("react-i18next", () => {
  const t = (key: string): string => key;
  return { useTranslation: () => ({ t }) };
});

const mockWorkspace = { id: "ws-123", name: "Test", preset: "standard" };

const mockRequirements = [
  {
    id: "req-1",
    workspace_id: "ws-123",
    title: "Login works",
    description: "",
    category: "functional",
    status: "draft",
    version: 1,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
  {
    id: "req-2",
    workspace_id: "ws-123",
    title: "Fast response",
    description: "",
    category: "non-functional",
    status: "approved",
    version: 3,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
];

describe("RequirementsList (REQ-L1-040 Phase 2)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(workspaceContext.useWorkspace).mockReturnValue({
      activeWorkspace: mockWorkspace,
    } as any);
    vi.mocked(requirementsModule.requirementsApi.list).mockResolvedValue({
      results: mockRequirements,
    } as any);
  });

  it("loads the requirements list on mount", async () => {
    render(<RequirementsList />);

    await waitFor(() => {
      expect(screen.getByTestId("req-list-table")).toBeInTheDocument();
    });
    expect(requirementsModule.requirementsApi.list).toHaveBeenCalledWith(
      "ws-123"
    );
    expect(screen.getByText("Login works")).toBeInTheDocument();
    expect(screen.getByText("Fast response")).toBeInTheDocument();
  });

  it("shows title, category, status and version columns", async () => {
    render(<RequirementsList />);

    await waitFor(() => {
      expect(screen.getByTestId("req-list-item-req-1")).toBeInTheDocument();
    });
    const row = screen.getByTestId("req-list-item-req-2");
    expect(row).toHaveTextContent("Fast response");
    expect(row).toHaveTextContent("categories.non-functional");
    expect(row).toHaveTextContent("approved");
    expect(row).toHaveTextContent("3");
  });

  it("shows empty state when no requirements exist", async () => {
    vi.mocked(requirementsModule.requirementsApi.list).mockResolvedValue({
      results: [],
    } as any);

    render(<RequirementsList />);

    await waitFor(() => {
      expect(screen.getByText("editor.empty")).toBeInTheDocument();
    });
  });

  it("validates that title is required before create", async () => {
    const user = userEvent.setup();
    render(<RequirementsList />);

    await waitFor(() => {
      expect(screen.getByTestId("req-list-create-btn")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("req-list-create-btn"));
    // Whitespace passes the native `required` gate; the JS trim()
    // validation must still reject it.
    await user.type(screen.getByTestId("req-list-title-input"), "   ");
    await user.click(screen.getByTestId("req-list-save-btn"));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
    expect(requirementsModule.requirementsApi.create).not.toHaveBeenCalled();
  });

  it("creates a requirement with the registered contract payload", async () => {
    vi.mocked(requirementsModule.requirementsApi.create).mockResolvedValue({
      id: "req-3",
    } as any);
    const user = userEvent.setup();
    render(<RequirementsList />);

    await waitFor(() => {
      expect(screen.getByTestId("req-list-create-btn")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("req-list-create-btn"));

    await user.type(
      screen.getByTestId("req-list-title-input"),
      "New requirement"
    );
    await user.type(
      screen.getByTestId("req-list-description-input"),
      "Some detail"
    );
    await user.selectOptions(
      screen.getByTestId("req-list-category-select"),
      "functional"
    );
    await user.click(screen.getByTestId("req-list-save-btn"));

    await waitFor(() => {
      expect(requirementsModule.requirementsApi.create).toHaveBeenCalledWith({
        workspace_id: "ws-123",
        title: "New requirement",
        description: "Some detail",
        category: "functional",
      });
    });
  });

  it("refreshes the list after a successful create", async () => {
    vi.mocked(requirementsModule.requirementsApi.create).mockResolvedValue({
      id: "req-3",
    } as any);
    const user = userEvent.setup();
    render(<RequirementsList />);

    await waitFor(() => {
      expect(screen.getByTestId("req-list-create-btn")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("req-list-create-btn"));
    await user.type(screen.getByTestId("req-list-title-input"), "Another");
    await user.click(screen.getByTestId("req-list-save-btn"));

    await waitFor(() => {
      // initial load + refresh after create
      expect(requirementsModule.requirementsApi.list).toHaveBeenCalledTimes(2);
    });
    // Form closes after successful create
    expect(
      screen.queryByTestId("req-list-create-form")
    ).not.toBeInTheDocument();
  });

  it("shows an API error in the form alert", async () => {
    vi.mocked(requirementsModule.requirementsApi.create).mockRejectedValue({
      error: { message: "duplicate title" },
    });
    const user = userEvent.setup();
    render(<RequirementsList />);

    await waitFor(() => {
      expect(screen.getByTestId("req-list-create-btn")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("req-list-create-btn"));
    await user.type(screen.getByTestId("req-list-title-input"), "Dup");
    await user.click(screen.getByTestId("req-list-save-btn"));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("duplicate title");
    });
    // Form stays open for retry
    expect(screen.getByTestId("req-list-create-form")).toBeInTheDocument();
  });

  it("navigates to the RequirementEditors detail view on edit", async () => {
    const user = userEvent.setup();
    render(<RequirementsList />);

    await waitFor(() => {
      expect(screen.getByTestId("req-list-edit-req-1")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("req-list-edit-req-1"));

    expect(mockNavigate).toHaveBeenCalledWith("/requirements/req-1");
  });

  it("deletes a requirement after confirmation and reloads", async () => {
    vi.mocked(requirementsModule.requirementsApi.delete).mockResolvedValue(
      undefined as any
    );
    const confirmSpy = vi
      .spyOn(window, "confirm")
      .mockImplementation(() => true);
    const user = userEvent.setup();
    render(<RequirementsList />);

    await waitFor(() => {
      expect(screen.getByTestId("req-list-delete-req-1")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("req-list-delete-req-1"));

    await waitFor(() => {
      expect(requirementsModule.requirementsApi.delete).toHaveBeenCalledWith(
        "req-1"
      );
    });
    expect(requirementsModule.requirementsApi.list).toHaveBeenCalledTimes(2);
    confirmSpy.mockRestore();
  });

  it("does not delete when confirmation is declined", async () => {
    const confirmSpy = vi
      .spyOn(window, "confirm")
      .mockImplementation(() => false);
    const user = userEvent.setup();
    render(<RequirementsList />);

    await waitFor(() => {
      expect(screen.getByTestId("req-list-delete-req-1")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("req-list-delete-req-1"));

    expect(requirementsModule.requirementsApi.delete).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });
});
