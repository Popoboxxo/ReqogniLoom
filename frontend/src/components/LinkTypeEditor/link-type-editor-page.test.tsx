import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";

import { LinkTypeEditorPage } from "./LinkTypeEditorPage";
import { linkTypesApi } from "../../api/link-types";

vi.mock("../../api/link-types", () => ({
  linkTypesApi: {
    listForWorkspace: vi.fn(),
    updateForWorkspace: vi.fn(),
    resetForWorkspace: vi.fn(),
    listGlobal: vi.fn(),
    createGlobal: vi.fn(),
    updateGlobal: vi.fn(),
    deleteGlobal: vi.fn(),
  },
}));

vi.mock("../../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "ws-1" } }),
}));

const definition = {
  label: {
    de: { downstream: "verifiziert", upstream: "wird verifiziert von", neutral: "Verifikation" },
    en: { downstream: "verifies", upstream: "is verified by", neutral: "Verification" },
  },
  allowed_pairs: [{ source_type: "TestCase", target_type: "Requirement" }],
  coverage_relevant: true,
  suspect_rule: "target_change_flags_source" as const,
  impact_weight: 1,
  manual_creatable: true,
  system_owned: false,
  active: true,
  built_in: true,
};

const verifies = {
  id: "1",
  workspace_id: "ws-1",
  key: "verifies",
  definition,
  is_customized: false,
  source_global_id: null,
  version: 1,
};

const diagramRef = {
  ...verifies,
  id: "2",
  key: "diagram-ref",
  definition: { ...definition, system_owned: true, manual_creatable: false },
};

describe("LinkTypeEditorPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(linkTypesApi.listForWorkspace).mockResolvedValue([verifies, diagramRef]);
    vi.mocked(linkTypesApi.listGlobal).mockResolvedValue([
      { id: "1", key: "verifies", definition, version: 1 },
    ]);
  });

  it("lists the workspace types in workspace scope", async () => {
    render(<LinkTypeEditorPage scope="workspace" />);
    expect(await screen.findByTestId("link-type-row-verifies")).toBeInTheDocument();
    expect(linkTypesApi.listForWorkspace).toHaveBeenCalledWith("ws-1");
  });

  it("lists the global templates in global scope", async () => {
    render(<LinkTypeEditorPage scope="global" />);
    await waitFor(() => expect(linkTypesApi.listGlobal).toHaveBeenCalled());
    expect(linkTypesApi.listForWorkspace).not.toHaveBeenCalled();
  });

  it("locks a system-owned row", async () => {
    render(<LinkTypeEditorPage scope="workspace" />);
    const row = await screen.findByTestId("link-type-row-diagram-ref");
    expect(row).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByTestId("link-type-lock-diagram-ref")).toBeInTheDocument();
  });

  it("does not lock an ordinary row", async () => {
    render(<LinkTypeEditorPage scope="workspace" />);
    const row = await screen.findByTestId("link-type-row-verifies");
    expect(row).not.toHaveAttribute("aria-disabled", "true");
  });

  it("saves an impact-weight edit through the workspace endpoint", async () => {
    vi.mocked(linkTypesApi.updateForWorkspace).mockResolvedValue({
      ...verifies,
      is_customized: true,
    });
    render(<LinkTypeEditorPage scope="workspace" />);
    await userEvent.click(await screen.findByTestId("link-type-edit-verifies"));
    const weight = await screen.findByTestId("link-type-impact-weight-input");
    await userEvent.clear(weight);
    await userEvent.type(weight, "0.6");
    await userEvent.click(screen.getByTestId("link-type-save-button"));

    await waitFor(() =>
      expect(linkTypesApi.updateForWorkspace).toHaveBeenCalledWith(
        "ws-1",
        "verifies",
        expect.objectContaining({ impact_weight: 0.6 }),
      ),
    );
  });

  it("offers reset only for a customized row", async () => {
    vi.mocked(linkTypesApi.listForWorkspace).mockResolvedValue([
      { ...verifies, is_customized: true },
    ]);
    render(<LinkTypeEditorPage scope="workspace" />);
    expect(await screen.findByTestId("link-type-reset-verifies")).toBeInTheDocument();
  });

  it("hides reset for an on-default row", async () => {
    render(<LinkTypeEditorPage scope="workspace" />);
    await screen.findByTestId("link-type-row-verifies");
    expect(screen.queryByTestId("link-type-reset-verifies")).not.toBeInTheDocument();
  });

  it("offers a new-type button in global scope only", async () => {
    const { unmount } = render(<LinkTypeEditorPage scope="global" />);
    expect(await screen.findByTestId("link-type-new-button")).toBeInTheDocument();
    unmount();
    render(<LinkTypeEditorPage scope="workspace" />);
    await screen.findByTestId("link-type-row-verifies");
    expect(screen.queryByTestId("link-type-new-button")).not.toBeInTheDocument();
  });

  it("restricts the suspect-rule select to the four supported values", async () => {
    render(<LinkTypeEditorPage scope="workspace" />);
    await userEvent.click(await screen.findByTestId("link-type-edit-verifies"));
    const select = await screen.findByTestId("link-type-suspect-rule-select");
    const options = Array.from(select.querySelectorAll("option")).map((o) => o.value);
    expect(options).toEqual([
      "none",
      "target_change_flags_source",
      "source_change_flags_target",
      "parent_change_flags_children",
    ]);
  });

  it("surfaces a save error instead of silently discarding the edit", async () => {
    vi.mocked(linkTypesApi.updateForWorkspace).mockRejectedValue(
      new Error("suspect_rule invalid"),
    );
    render(<LinkTypeEditorPage scope="workspace" />);
    await userEvent.click(await screen.findByTestId("link-type-edit-verifies"));
    await userEvent.click(screen.getByTestId("link-type-save-button"));
    expect(await screen.findByTestId("link-type-error")).toHaveTextContent(
      "suspect_rule invalid",
    );
  });
});
