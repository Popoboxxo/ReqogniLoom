/**
 * Tests for IcdList component.
 * REQ-L1-040 Phase 2: SE Masks Unification — dual-modal ICD list.
 *
 * Verifies:
 * - create workflow calls icdsApi.create with the registered contract payload
 * - new-version workflow fetches current detail, prefills, and calls
 *   icdsApi.createVersion(id, payload) (append-only)
 * - version number increment is displayed read-only (backend-owned)
 * - immutability hint is shown for the new-version flow
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import IcdList from "./IcdList";
import * as icdsModule from "../../api/icds";
import * as architectureModule from "../../api/architecture";
import * as workspaceContext from "../../context/WorkspaceContext";

vi.mock("../../api/icds");
vi.mock("../../api/architecture");
vi.mock("../../context/WorkspaceContext");
// Stable t reference — a fresh t per render would re-trigger the
// useCallback([activeWorkspace, t]) load effect in an endless loop.
vi.mock("react-i18next", () => {
  const t = (key: string, opts?: Record<string, unknown>): string =>
    opts && typeof opts.n === "number" ? `v${opts.n}` : key;
  return { useTranslation: () => ({ t }) };
});

const mockWorkspace = { id: "ws-123", name: "Test", preset: "standard" };

const mockElements = [
  { id: "el-1", title: "Service A", element_type: "component" },
  { id: "el-2", title: "Service B", element_type: "component" },
];

const mockIcds = [
  {
    id: "icd-1",
    name: "A->B Contract",
    workspace_id: "ws-123",
    source_element_id: "el-1",
    target_element_id: "el-2",
    current_version: "ver-1",
    created_at: "2026-01-01T00:00:00Z",
  },
];

const mockDetail = {
  ...mockIcds[0],
  version: 2,
  direction: "unidirectional" as const,
  interface_type: "REST API",
  semantic_description: "Existing contract",
  preconditions: ["auth token present"],
  postconditions: ["response persisted"],
  invariants: ["idempotent"],
};

describe("IcdList (REQ-L1-040 Phase 2)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(workspaceContext.useWorkspace).mockReturnValue({
      activeWorkspace: mockWorkspace,
    } as any);
    vi.mocked(icdsModule.icdsApi.list).mockResolvedValue({
      results: mockIcds,
    } as any);
    vi.mocked(architectureModule.architectureApi.listAll).mockResolvedValue(
      mockElements as any
    );
  });

  it("loads and displays the ICD list grouped by name", async () => {
    render(<IcdList />);

    await waitFor(() => {
      expect(screen.getByTestId("icd-groups")).toBeInTheDocument();
    });
    expect(screen.getByText("A->B Contract")).toBeInTheDocument();
    expect(icdsModule.icdsApi.list).toHaveBeenCalledWith("ws-123");
  });

  it("shows empty state when no ICDs exist", async () => {
    vi.mocked(icdsModule.icdsApi.list).mockResolvedValue({
      results: [],
    } as any);

    render(<IcdList />);

    await waitFor(() => {
      expect(screen.getByText("editor.empty")).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // CREATE workflow
  // -------------------------------------------------------------------------

  it("creates a new ICD with the registered contract payload", async () => {
    vi.mocked(icdsModule.icdsApi.create).mockResolvedValue(mockDetail as any);
    const user = userEvent.setup();
    render(<IcdList />);

    await waitFor(() => {
      expect(screen.getByTestId("icd-create-btn")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("icd-create-btn"));

    await user.type(screen.getByTestId("icd-name-input"), "New Contract");
    await user.selectOptions(screen.getByTestId("icd-source-select"), "el-1");
    await user.selectOptions(screen.getByTestId("icd-target-select"), "el-2");
    await user.type(
      screen.getByTestId("icd-contract-textarea"),
      "semantic spec"
    );
    await user.type(screen.getByTestId("icd-pre-input"), "pre-1\npre-2");

    await user.click(screen.getByTestId("icd-save-btn"));

    await waitFor(() => {
      expect(icdsModule.icdsApi.create).toHaveBeenCalledWith({
        workspace_id: "ws-123",
        name: "New Contract",
        source_element_id: "el-1",
        target_element_id: "el-2",
        direction: "unidirectional",
        interface_type: "",
        semantic_description: "semantic spec",
        preconditions: ["pre-1", "pre-2"],
        postconditions: [],
        invariants: [],
      });
    });
    // List refreshes after create (initial load + refresh)
    expect(icdsModule.icdsApi.list).toHaveBeenCalledTimes(2);
  });

  it("validates required name field on create", async () => {
    const user = userEvent.setup();
    render(<IcdList />);

    await waitFor(() => {
      expect(screen.getByTestId("icd-create-btn")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("icd-create-btn"));
    // Whitespace passes the native `required` gate; the JS trim()
    // validation must still reject it.
    await user.type(screen.getByTestId("icd-name-input"), "   ");
    await user.click(screen.getByTestId("icd-save-btn"));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(
        "icds.nameRequired"
      );
    });
    expect(icdsModule.icdsApi.create).not.toHaveBeenCalled();
  });

  it("rejects identical source and target endpoints", async () => {
    const user = userEvent.setup();
    render(<IcdList />);

    await waitFor(() => {
      expect(screen.getByTestId("icd-create-btn")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("icd-create-btn"));
    await user.type(screen.getByTestId("icd-name-input"), "Broken");
    await user.selectOptions(screen.getByTestId("icd-source-select"), "el-1");
    await user.selectOptions(screen.getByTestId("icd-target-select"), "el-1");
    await user.click(screen.getByTestId("icd-save-btn"));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(
        "traceability.sameEndpoints"
      );
    });
    expect(icdsModule.icdsApi.create).not.toHaveBeenCalled();
  });

  // -------------------------------------------------------------------------
  // NEW VERSION workflow (append-only, immutable past)
  // -------------------------------------------------------------------------

  it("opens the new-version modal prefilled from the current version", async () => {
    vi.mocked(icdsModule.icdsApi.get).mockResolvedValue(mockDetail as any);
    const user = userEvent.setup();
    render(<IcdList />);

    await waitFor(() => {
      expect(
        screen.getByTestId("icd-new-version-btn-icd-1")
      ).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("icd-new-version-btn-icd-1"));

    await waitFor(() => {
      expect(screen.getByTestId("icd-nv-create-form")).toBeInTheDocument();
    });
    expect(icdsModule.icdsApi.get).toHaveBeenCalledWith("icd-1");
    expect(screen.getByTestId("icd-nv-contract-textarea")).toHaveValue(
      "Existing contract"
    );
    expect(screen.getByTestId("icd-nv-pre-input")).toHaveValue(
      "auth token present"
    );
  });

  it("displays the auto-incremented version read-only", async () => {
    vi.mocked(icdsModule.icdsApi.get).mockResolvedValue(mockDetail as any);
    const user = userEvent.setup();
    render(<IcdList />);

    await waitFor(() => {
      expect(
        screen.getByTestId("icd-new-version-btn-icd-1")
      ).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("icd-new-version-btn-icd-1"));

    await waitFor(() => {
      expect(screen.getByTestId("icd-nv-version-display")).toBeInTheDocument();
    });
    // Read-only div (not an input) showing v2 -> v3 increment
    const display = screen.getByTestId("icd-nv-version-display");
    expect(display.tagName).toBe("DIV");
    expect(display).toHaveTextContent("v2");
    expect(display).toHaveTextContent("v3");
  });

  it("shows the immutability hint in the new-version modal", async () => {
    vi.mocked(icdsModule.icdsApi.get).mockResolvedValue(mockDetail as any);
    const user = userEvent.setup();
    render(<IcdList />);

    await waitFor(() => {
      expect(
        screen.getByTestId("icd-new-version-btn-icd-1")
      ).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("icd-new-version-btn-icd-1"));

    await waitFor(() => {
      expect(screen.getByTestId("icd-nv-immutable-hint")).toHaveTextContent(
        "icds.immutableHint"
      );
    });
  });

  it("appends a new version via createVersion(id, payload)", async () => {
    vi.mocked(icdsModule.icdsApi.get).mockResolvedValue(mockDetail as any);
    vi.mocked(icdsModule.icdsApi.createVersion).mockResolvedValue({
      ...mockDetail,
      version: 3,
    } as any);
    const user = userEvent.setup();
    render(<IcdList />);

    await waitFor(() => {
      expect(
        screen.getByTestId("icd-new-version-btn-icd-1")
      ).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("icd-new-version-btn-icd-1"));

    await waitFor(() => {
      expect(screen.getByTestId("icd-nv-create-form")).toBeInTheDocument();
    });

    const contractField = screen.getByTestId("icd-nv-contract-textarea");
    await user.clear(contractField);
    await user.type(contractField, "Updated contract");
    await user.click(screen.getByTestId("icd-nv-save-btn"));

    await waitFor(() => {
      expect(icdsModule.icdsApi.createVersion).toHaveBeenCalledWith("icd-1", {
        direction: "unidirectional",
        interface_type: "REST API",
        semantic_description: "Updated contract",
        preconditions: ["auth token present"],
        postconditions: ["response persisted"],
        invariants: ["idempotent"],
      });
    });
    // Modal closes and list refreshes
    await waitFor(() => {
      expect(
        screen.queryByTestId("icd-nv-create-form")
      ).not.toBeInTheDocument();
    });
    expect(icdsModule.icdsApi.list).toHaveBeenCalledTimes(2);
  });

  it("keeps the modals mutually exclusive", async () => {
    vi.mocked(icdsModule.icdsApi.get).mockResolvedValue(mockDetail as any);
    const user = userEvent.setup();
    render(<IcdList />);

    await waitFor(() => {
      expect(screen.getByTestId("icd-create-btn")).toBeInTheDocument();
    });

    // Open create modal, then open new-version modal
    await user.click(screen.getByTestId("icd-create-btn"));
    expect(screen.getByTestId("icd-create-form")).toBeInTheDocument();

    await user.click(screen.getByTestId("icd-new-version-btn-icd-1"));
    await waitFor(() => {
      expect(screen.getByTestId("icd-nv-create-form")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("icd-create-form")).not.toBeInTheDocument();
  });

  it("shows an error alert when the new-version request fails", async () => {
    vi.mocked(icdsModule.icdsApi.get).mockResolvedValue(mockDetail as any);
    vi.mocked(icdsModule.icdsApi.createVersion).mockRejectedValue({
      error: { message: "version conflict" },
    });
    const user = userEvent.setup();
    render(<IcdList />);

    await waitFor(() => {
      expect(
        screen.getByTestId("icd-new-version-btn-icd-1")
      ).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("icd-new-version-btn-icd-1"));
    await waitFor(() => {
      expect(screen.getByTestId("icd-nv-create-form")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("icd-nv-save-btn"));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("version conflict");
    });
    // Modal stays open so the user can retry
    expect(screen.getByTestId("icd-nv-create-form")).toBeInTheDocument();
  });
});
