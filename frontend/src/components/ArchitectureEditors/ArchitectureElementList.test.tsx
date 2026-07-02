/**
 * ArchitectureElementList.test.tsx
 *
 * Tests for ArchitectureElementList component:
 * - Form validation (required fields)
 * - API call verification
 * - List refresh
 * - Delete functionality
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ArchitectureElementList } from "./ArchitectureElementList";
import * as architectureApi from "../../api/architecture";
import * as workspaceContext from "../../context/WorkspaceContext";

vi.mock("../../api/architecture");
vi.mock("../../context/WorkspaceContext");
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

describe("ArchitectureElementList", () => {
  const mockWorkspace = { id: "ws-123", name: "Test", preset: "standard" };
  const mockElements = [
    { id: "el-1", title: "Component A", element_type: "component", description: "", level: 0, version: 1, created_at: "", updated_at: "", workspace_id: "ws-123" },
    { id: "el-2", title: "Interface B", element_type: "interface", description: "", level: 1, parent_id: "el-1", version: 1, created_at: "", updated_at: "", workspace_id: "ws-123" },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(workspaceContext.useWorkspace).mockReturnValue({
      activeWorkspace: mockWorkspace,
    } as any);
  });

  it("renders empty state when no elements exist", async () => {
    vi.mocked(architectureApi.architectureApi.list).mockResolvedValue({ results: [] } as any);

    render(<ArchitectureElementList />);

    await waitFor(() => {
      expect(screen.getByText("editor.empty")).toBeInTheDocument();
    });
  });

  it("displays list of architecture elements", async () => {
    vi.mocked(architectureApi.architectureApi.list).mockResolvedValue({
      results: mockElements,
    } as any);

    render(<ArchitectureElementList />);

    await waitFor(() => {
      expect(screen.getByText("Component A")).toBeInTheDocument();
      expect(screen.getByText("Interface B")).toBeInTheDocument();
    });
  });

  it("opens create form when button is clicked", async () => {
    vi.mocked(architectureApi.architectureApi.list).mockResolvedValue({
      results: mockElements,
    } as any);

    const user = userEvent.setup();
    render(<ArchitectureElementList />);

    await waitFor(() => {
      expect(screen.getByTestId("arch-element-create-btn")).toBeInTheDocument();
    });

    await user.click(screen.getByTestId("arch-element-create-btn"));

    expect(screen.getByTestId("arch-element-create-form")).toBeInTheDocument();
  });

  it("validates required name field", async () => {
    vi.mocked(architectureApi.architectureApi.list).mockResolvedValue({
      results: [],
    } as any);

    const user = userEvent.setup();
    render(<ArchitectureElementList />);

    await waitFor(() => {
      expect(screen.getByTestId("arch-element-create-btn")).toBeInTheDocument();
    });

    await user.click(screen.getByTestId("arch-element-create-btn"));

    const form = screen.getByTestId("arch-element-create-form");
    const saveBtn = screen.getByTestId("arch-element-save-btn");

    fireEvent.submit(form);

    await waitFor(() => {
      // Error message should be displayed
      expect(screen.getByText("editor.titleRequired")).toBeInTheDocument();
    });
  });

  it("calls API with form data on submit", async () => {
    vi.mocked(architectureApi.architectureApi.list).mockResolvedValue({
      results: [],
    } as any);
    vi.mocked(architectureApi.architectureApi.create).mockResolvedValue({} as any);

    const user = userEvent.setup();
    render(<ArchitectureElementList />);

    await waitFor(() => {
      expect(screen.getByTestId("arch-element-create-btn")).toBeInTheDocument();
    });

    await user.click(screen.getByTestId("arch-element-create-btn"));

    const nameInput = screen.getByTestId("arch-element-name");
    const form = screen.getByTestId("arch-element-create-form");

    await user.type(nameInput, "New Component");
    fireEvent.submit(form);

    await waitFor(() => {
      expect(architectureApi.architectureApi.create).toHaveBeenCalledWith(
        expect.objectContaining({
          workspace_id: "ws-123",
          title: "New Component",
          element_type: "component",
        })
      );
    });
  });

  it("reloads list after successful creation", async () => {
    vi.mocked(architectureApi.architectureApi.list).mockResolvedValue({
      results: [],
    } as any);
    vi.mocked(architectureApi.architectureApi.create).mockResolvedValue({} as any);

    const user = userEvent.setup();
    render(<ArchitectureElementList />);

    await waitFor(() => {
      expect(screen.getByTestId("arch-element-create-btn")).toBeInTheDocument();
    });

    await user.click(screen.getByTestId("arch-element-create-btn"));

    const nameInput = screen.getByTestId("arch-element-name");
    const form = screen.getByTestId("arch-element-create-form");

    await user.type(nameInput, "New Component");
    fireEvent.submit(form);

    await waitFor(() => {
      expect(architectureApi.architectureApi.list).toHaveBeenCalledTimes(2);
    });
  });

  it("shows delete confirmation dialog when delete is clicked", async () => {
    vi.mocked(architectureApi.architectureApi.list).mockResolvedValue({
      results: mockElements,
    } as any);

    const user = userEvent.setup();
    render(<ArchitectureElementList />);

    await waitFor(() => {
      expect(screen.getByText("Component A")).toBeInTheDocument();
    });

    const deleteBtn = screen.getByTestId("delete-arch-element-el-1");
    await user.click(deleteBtn);

    expect(screen.getByTestId("confirm-delete-btn")).toBeInTheDocument();
    expect(screen.getByText("arch.deleteConfirm")).toBeInTheDocument();
  });

  it("calls delete API when confirmed", async () => {
    vi.mocked(architectureApi.architectureApi.list).mockResolvedValue({
      results: mockElements,
    } as any);
    vi.mocked(architectureApi.architectureApi.delete).mockResolvedValue({} as any);

    const user = userEvent.setup();
    render(<ArchitectureElementList />);

    await waitFor(() => {
      expect(screen.getByText("Component A")).toBeInTheDocument();
    });

    const deleteBtn = screen.getByTestId("delete-arch-element-el-1");
    await user.click(deleteBtn);

    const confirmBtn = screen.getByTestId("confirm-delete-btn");
    await user.click(confirmBtn);

    await waitFor(() => {
      expect(architectureApi.architectureApi.delete).toHaveBeenCalledWith("el-1");
    });
  });

  it("displays level for elements in the list", async () => {
    vi.mocked(architectureApi.architectureApi.list).mockResolvedValue({
      results: mockElements,
    } as any);

    render(<ArchitectureElementList />);

    await waitFor(() => {
      expect(screen.getByTestId("arch-element-level-el-1")).toHaveTextContent("arch.level");
      expect(screen.getByTestId("arch-element-level-el-2")).toHaveTextContent("arch.level");
    });

    // Verify level values are displayed
    const level0Element = screen.getByTestId("arch-element-level-el-1");
    expect(level0Element).toHaveTextContent("0");

    const level1Element = screen.getByTestId("arch-element-level-el-2");
    expect(level1Element).toHaveTextContent("1");
  });

  it("applies indentation based on hierarchy level", async () => {
    vi.mocked(architectureApi.architectureApi.list).mockResolvedValue({
      results: mockElements,
    } as any);

    render(<ArchitectureElementList />);

    await waitFor(() => {
      expect(screen.getAllByTestId("arch-element-item").length).toBeGreaterThan(0);
    });

    const items = screen.getAllByTestId("arch-element-item");

    // First element (level 0) should have 0px indent
    expect(items[0]).toHaveStyle("margin-left: 0px");

    // Second element (level 1) should have 24px indent
    expect(items[1]).toHaveStyle("margin-left: 24px");
  });
});
