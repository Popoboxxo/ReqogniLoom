import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";

/**
 * REQ-143: RequirementForm drives its lifecycle-state control from the
 * WorkflowEngine transitions API instead of a free enum. These tests verify:
 *  - the current state is shown read-only,
 *  - only backend-allowed transitions are offered,
 *  - saving performs a transition (not a status write),
 *  - with no allowed transitions the state is locked (read-only).
 */

vi.mock("../../api/requirements", () => ({
  requirementsApi: {
    getTransitions: vi.fn(),
    update: vi.fn().mockResolvedValue({}),
    transition: vi.fn().mockResolvedValue({}),
  },
}));

vi.mock("../../context/EntityTypeContext", () => ({
  useEntityType: () => ({
    isFieldVisible: () => true,
    isFieldRequired: () => false,
  }),
}));

vi.mock("../../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { preset: "standard" } }),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (k: string, d?: string) => d ?? k }),
}));

vi.mock("./MarkdownPreview", () => ({
  MarkdownPreview: ({ value }: { value: string }) => <div>{value}</div>,
}));
vi.mock("../shared/CustomFieldsEditor", () => ({
  CustomFieldsEditor: () => <div data-testid="custom-fields" />,
}));
vi.mock("../shared/ArtifactCustomFields", () => ({
  ArtifactCustomFields: () => <div data-testid="artifact-custom-fields" />,
}));
vi.mock("../shared/VersionBadge", () => ({
  VersionBadge: () => <span data-testid="version-badge" />,
}));

import { RequirementForm } from "./RequirementForm";
import { requirementsApi } from "../../api/requirements";
import type { Requirement } from "../../types";

const baseReq = {
  id: "req-1",
  artifact_id: "art-1",
  title: "A requirement",
  description: "desc",
  category: "",
  status: "draft",
  change_reason: "",
  type: "SyReq",
  complexity_fibonacci: 1,
  verification_method: "",
  custom_fields: {},
  suspect: false,
  uid: null,
  version: 1,
} as unknown as Requirement;

const renderForm = () =>
  render(
    <RequirementForm
      requirement={baseReq}
      upstreamLinks={[]}
      downstreamLinks={[]}
      linkedTitles={{}}
      linkedRoutes={{}}
      requirements={[]}
      workspaceId="ws-1"
      onSaved={vi.fn()}
    />
  );

describe("RequirementForm — workflow-driven status (REQ-143)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows current state read-only and only backend-allowed transitions", async () => {
    (requirementsApi.getTransitions as ReturnType<typeof vi.fn>).mockResolvedValue({
      current_state: "draft",
      states: ["draft", "approved", "deprecated"],
      allowed_transitions: [
        { target_state: "approved", requires_change_reason: false, signature_gate: false },
      ],
    });

    renderForm();

    await waitFor(() =>
      expect(screen.getByTestId("req-workflow")).toBeInTheDocument()
    );
    // Current state read-only.
    expect(screen.getByTestId("req-workflow-current")).toHaveTextContent("draft");
    // Only the allowed target appears as an option.
    const select = screen.getByTestId("req-workflow") as HTMLSelectElement;
    expect(select.querySelectorAll("option")).toHaveLength(2); // no-change + approved
    expect(screen.getByRole("option", { name: "→ approved" })).toBeInTheDocument();
  });

  it("performs a transition on save instead of writing status", async () => {
    (requirementsApi.getTransitions as ReturnType<typeof vi.fn>).mockResolvedValue({
      current_state: "draft",
      states: ["draft", "approved", "deprecated"],
      allowed_transitions: [
        { target_state: "approved", requires_change_reason: false, signature_gate: false },
      ],
    });

    renderForm();
    await waitFor(() =>
      expect(screen.getByTestId("req-workflow")).toBeInTheDocument()
    );

    fireEvent.change(screen.getByTestId("req-workflow"), {
      target: { value: "approved" },
    });
    fireEvent.click(screen.getByTestId("save-btn"));

    await waitFor(() =>
      expect(requirementsApi.transition).toHaveBeenCalledWith(
        "req-1",
        "approved",
        ""
      )
    );
    // The content update must NOT carry a `status` field (REQ-143).
    const updateArgs = (requirementsApi.update as ReturnType<typeof vi.fn>).mock
      .calls[0][1];
    expect(updateArgs).not.toHaveProperty("status");
  });

  it("locks the state when no transitions are allowed", async () => {
    (requirementsApi.getTransitions as ReturnType<typeof vi.fn>).mockResolvedValue({
      current_state: "deprecated",
      states: ["draft", "approved", "deprecated"],
      allowed_transitions: [],
    });

    renderForm();

    await waitFor(() =>
      expect(screen.getByTestId("req-workflow-locked")).toBeInTheDocument()
    );
    expect(screen.queryByTestId("req-workflow")).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId("save-btn"));
    await waitFor(() => expect(requirementsApi.update).toHaveBeenCalled());
    expect(requirementsApi.transition).not.toHaveBeenCalled();
  });
});
