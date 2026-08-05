import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
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

// The form surfaces API failures through `extractErrorMessage`; stub it so the
// test does not drag in the axios client, and so the asserted text is exact.
vi.mock("../../api/client", () => ({
  extractErrorMessage: (err: unknown) =>
    (err as { error?: { message?: string } })?.error?.message ?? "Save failed.",
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
    // Mirrors the real defaults: with no AttributeVisibilityConfig rows (the
    // default state of a fresh workspace) every field is visible and *no*
    // field is required. #344 hinged on that second default.
    isFieldVisible: () => true,
    isFieldRequired: () => false,
  }),
}));

// Preset of the mocked active workspace; individual tests flip this to
// "extended" before rendering (see the #344 block below).
let mockPreset = "standard";

vi.mock("../../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { preset: mockPreset } }),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (k: string, d?: string) => d ?? k }),
}));

vi.mock("./MarkdownPreview", () => ({
  MarkdownPreview: ({
    value,
    onChange,
  }: {
    value: string;
    onChange: (v: string) => void;
  }) => (
    <textarea
      data-testid="req-description-input"
      value={value}
      onChange={(e) => onChange(e.target.value)}
    />
  ),
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

/**
 * Issue #344 — "Save persists nothing, silently".
 *
 * Two independent defects, one per half of this block:
 *
 *  (a) Payload: the form echoed `change_reason: ""` on every save. In the
 *      extended preset the backend requires a non-empty change reason on every
 *      update (`PresetPolicyService.is_change_reason_required`) and 400s the
 *      whole PATCH otherwise. The client-side guard was gated on
 *      `isFieldRequired('change_reason')`, which comes from
 *      AttributeVisibilityConfig and defaults to `false`, so it never fired.
 *
 *  (b) UX: the error banner was rendered ~350 lines below the Save button, off
 *      screen, so a rejected save looked like nothing happened at all.
 */
describe("RequirementForm — save persistence and failure surfacing (#344)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(requirementsApi.update).mockResolvedValue(
      {} as unknown as Requirement
    );
  });

  afterEach(() => {
    mockPreset = "standard";
  });

  it("PATCHes only content fields — no status, no empty change_reason", async () => {
    renderForm();
    fireEvent.click(screen.getByTestId("save-btn"));

    await waitFor(() => expect(requirementsApi.update).toHaveBeenCalled());
    const [id, payload] = (
      requirementsApi.update as ReturnType<typeof vi.fn>
    ).mock.calls[0];

    expect(id).toBe("req-1");
    expect(payload).not.toHaveProperty("status");
    // An empty change reason is not a content edit — it must not be sent.
    expect(payload).not.toHaveProperty("change_reason");
    expect(Object.keys(payload as object).sort()).toEqual(
      [
        "category",
        "complexity_fibonacci",
        "custom_fields",
        "description",
        "title",
        "type",
        "verification_method",
      ].sort()
    );
    // `type` must be a value the backend actually accepts.
    expect(["SyReq", "UseCase", "FeatureReq"]).toContain(
      (payload as { type: string }).type
    );
  });

  it("PATCHes the edited description", async () => {
    renderForm();
    fireEvent.change(screen.getByTestId("req-description-input"), {
      target: { value: "QA persistence probe" },
    });
    fireEvent.click(screen.getByTestId("save-btn"));

    await waitFor(() => expect(requirementsApi.update).toHaveBeenCalled());
    const payload = (requirementsApi.update as ReturnType<typeof vi.fn>).mock
      .calls[0][1];
    expect(payload).toMatchObject({ description: "QA persistence probe" });
  });

  it("surfaces a rejected save as a visible alert instead of failing silently", async () => {
    vi.mocked(requirementsApi.update).mockRejectedValueOnce({
      error: {
        code: "VALIDATION_ERROR",
        message: "change_reason required by workspace preset policy",
      },
    });

    renderForm();
    fireEvent.click(screen.getByTestId("save-btn"));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(
      "change_reason required by workspace preset policy"
    );
    // The banner must sit inside the header block that also holds the Save
    // button, not somewhere far below the fold.
    const saveButton = screen.getByTestId("save-btn");
    expect(
      alert.closest("div")?.contains(saveButton) ||
        saveButton.closest("div")?.parentElement?.parentElement?.contains(alert)
    ).toBe(true);
    expect(screen.getByTestId("req-save-error")).toBeInTheDocument();
  });

  it("blocks the save client-side when the extended preset needs a change reason", async () => {
    mockPreset = "extended";
    renderForm();

    fireEvent.click(screen.getByTestId("save-btn"));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("req.changeReasonRequired");
    // No doomed round-trip: the PATCH the backend would reject is never sent.
    expect(requirementsApi.update).not.toHaveBeenCalled();
  });

  it("sends the trimmed change reason once the extended preset is satisfied", async () => {
    mockPreset = "extended";
    renderForm();

    fireEvent.change(screen.getByTestId("change-reason-input"), {
      target: { value: "  clarified wording  " },
    });
    fireEvent.click(screen.getByTestId("save-btn"));

    await waitFor(() => expect(requirementsApi.update).toHaveBeenCalled());
    const payload = (requirementsApi.update as ReturnType<typeof vi.fn>).mock
      .calls[0][1];
    expect(payload).toMatchObject({ change_reason: "clarified wording" });
  });
});
