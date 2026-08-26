import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { MemoryManagementSection } from "./MemoryManagementSection";
import { memoryAdminApi } from "../../api/memoryAdmin";
// Real i18n singleton, as in PermissionDefaultsTab.test.tsx — this test asserts
// against the interpolated `deleteConfirmBody` copy, so `t()` must actually
// resolve keys against the locale bundles rather than echoing the key back.
import "../../i18n/index";

vi.mock("../../api/memoryAdmin", () => ({
  memoryAdminApi: {
    listWorkspaceOverview: vi.fn(),
    deleteWorkspaceMemory: vi.fn(),
  },
}));

const ROW = {
  workspace_id: "11111111-1111-1111-1111-111111111111",
  workspace_name: "Acme Project",
  enabled: true,
  workspace_entry_count: 5,
  user_entry_count: 2,
  last_consolidated_at: "2026-08-20T10:00:00Z",
};

describe("MemoryManagementSection", () => {
  beforeEach(() => {
    vi.mocked(memoryAdminApi.listWorkspaceOverview).mockResolvedValue({ results: [ROW] });
    vi.mocked(memoryAdminApi.deleteWorkspaceMemory).mockResolvedValue({
      workspace_id: ROW.workspace_id,
      workspace_memory_deleted: 5,
      user_memory_deleted: 2,
    });
  });

  it("renders a row per workspace with counts", async () => {
    render(<MemoryManagementSection />);

    const row = await screen.findByTestId(`memory-row-${ROW.workspace_id}`);
    expect(within(row).getByText("Acme Project")).toBeInTheDocument();
    expect(within(row).getByText("5")).toBeInTheDocument();
    expect(within(row).getByText("2")).toBeInTheDocument();
  });

  it("shows an empty state when there are no workspaces", async () => {
    vi.mocked(memoryAdminApi.listWorkspaceOverview).mockResolvedValue({ results: [] });

    render(<MemoryManagementSection />);

    expect(await screen.findByTestId("memory-management-empty")).toBeInTheDocument();
  });

  it("delete flow: opens confirm dialog, confirms, calls API, reloads", async () => {
    const user = userEvent.setup();
    render(<MemoryManagementSection />);

    const row = await screen.findByTestId(`memory-row-${ROW.workspace_id}`);
    await user.click(within(row).getByTestId(`memory-delete-btn-${ROW.workspace_id}`));

    const dialog = await screen.findByTestId("memory-delete-confirm-dialog");
    expect(within(dialog).getByText(/5/)).toBeInTheDocument();
    expect(within(dialog).getByText(/2/)).toBeInTheDocument();

    vi.mocked(memoryAdminApi.listWorkspaceOverview).mockResolvedValue({ results: [] });
    await user.click(within(dialog).getByTestId("memory-delete-confirm-btn"));

    await waitFor(() => {
      expect(memoryAdminApi.deleteWorkspaceMemory).toHaveBeenCalledWith(ROW.workspace_id);
    });
    await waitFor(() => {
      expect(screen.queryByTestId("memory-delete-confirm-dialog")).not.toBeInTheDocument();
    });
    expect(await screen.findByTestId("memory-management-empty")).toBeInTheDocument();
  });
});
