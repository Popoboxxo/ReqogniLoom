import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";

/**
 * REQ-161: RequirementForm delegates its lifecycle-state control to the shared
 * <WorkflowStatusEditor/> (WorkflowFacade-driven) instead of an inline status
 * <select>. These tests verify:
 *  - the form mounts the WorkflowStatusEditor with the requirement's identity,
 *  - the form no longer owns a status dropdown,
 *  - saving writes content only (never a `status` field) and no longer bundles
 *    a workflow transition into Save (that now runs inside the editor).
 */

vi.mock("../../api/requirements", () => ({
  requirementsApi: {
    update: vi.fn().mockResolvedValue({}),
  },
}));

// Stub the workflow editor so this stays a focused unit test of the form.
vi.mock("../WorkflowStatusEditor", () => ({
  WorkflowStatusEditor: (props: {
    artifactType: string;
    artifactId: string;
    currentStatus: string;
  }) => (
    <div
      data-testid="workflow-status-editor-stub"
      data-artifact-type={props.artifactType}
      data-artifact-id={props.artifactId}
      data-current-status={props.currentStatus}
    />
  ),
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

describe("RequirementForm — unified workflow editor (REQ-161)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("mounts the WorkflowStatusEditor for this requirement", () => {
    renderForm();
    const editor = screen.getByTestId("workflow-status-editor-stub");
    expect(editor).toHaveAttribute("data-artifact-type", "requirement");
    expect(editor).toHaveAttribute("data-artifact-id", "req-1");
    expect(editor).toHaveAttribute("data-current-status", "draft");
  });

  it("no longer renders an inline status dropdown", () => {
    renderForm();
    expect(screen.queryByTestId("req-workflow")).not.toBeInTheDocument();
    expect(screen.queryByTestId("req-workflow-current")).not.toBeInTheDocument();
  });

  it("saves content only — never writes a status field", async () => {
    renderForm();
    fireEvent.click(screen.getByTestId("save-btn"));

    await waitFor(() => expect(requirementsApi.update).toHaveBeenCalled());
    const updateArgs = (requirementsApi.update as ReturnType<typeof vi.fn>).mock
      .calls[0][1];
    expect(updateArgs).not.toHaveProperty("status");
  });
});
