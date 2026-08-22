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

// Field names an AttributeVisibilityConfig row marks as required. Empty by
// default, mirroring the real defaults: with no config rows (the state of a
// fresh workspace) every field is visible and *no* field is required — #344
// hinged on that second default. #339 tests flip `change_reason` on.
let mockRequiredFields: string[] = [];

vi.mock("../../context/EntityTypeContext", () => ({
  useEntityType: () => ({
    isFieldVisible: () => true,
    isFieldRequired: (field: string) => mockRequiredFields.includes(field),
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
 * Review finding — REQ_CATEGORIES legacy-value passthrough. The backend
 * `category` field is a free-form CharField with no DB-level choices
 * constraint, so an existing requirement (CSV/ReqIF import, manual DB edit)
 * may carry a category value that is no longer in the static REQ_CATEGORIES
 * list (e.g. the removed "stakeholder" category). The category <select>
 * must render that unknown value as an extra option, selected, instead of
 * silently falling back to no/first selection and losing it on next save.
 */
describe("RequirementForm — category select preserves unknown legacy values", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(requirementsApi.update).mockResolvedValue(
      {} as unknown as Requirement
    );
  });

  it("shows a known category normally, without an extra legacy option", () => {
    render(
      <RequirementForm
        requirement={{ ...baseReq, category: "functional" } as Requirement}
        upstreamLinks={[]}
        downstreamLinks={[]}
        linkedTitles={{}}
        linkedRoutes={{}}
        requirements={[]}
        workspaceId="ws-1"
        onSaved={vi.fn()}
      />
    );
    const select = screen.getByTestId("req-category") as HTMLSelectElement;
    expect(select).toHaveValue("functional");
    expect(screen.getAllByRole("option", { name: "functional" })).toHaveLength(1);
  });

  it("keeps an unknown legacy category selected instead of blanking it", () => {
    render(
      <RequirementForm
        requirement={{ ...baseReq, category: "stakeholder" } as Requirement}
        upstreamLinks={[]}
        downstreamLinks={[]}
        linkedTitles={{}}
        linkedRoutes={{}}
        requirements={[]}
        workspaceId="ws-1"
        onSaved={vi.fn()}
      />
    );
    const select = screen.getByTestId("req-category") as HTMLSelectElement;
    // The unknown legacy value must be selectable as its own option and
    // actually selected — not silently dropped to the empty/first option.
    expect(screen.getByRole("option", { name: "stakeholder" })).toBeInTheDocument();
    expect(select).toHaveValue("stakeholder");
  });

  it("persists the unknown legacy category unchanged on save", async () => {
    render(
      <RequirementForm
        requirement={{ ...baseReq, category: "stakeholder" } as Requirement}
        upstreamLinks={[]}
        downstreamLinks={[]}
        linkedTitles={{}}
        linkedRoutes={{}}
        requirements={[]}
        workspaceId="ws-1"
        onSaved={vi.fn()}
      />
    );
    fireEvent.click(screen.getByTestId("save-btn"));

    await waitFor(() => expect(requirementsApi.update).toHaveBeenCalled());
    const payload = (requirementsApi.update as ReturnType<typeof vi.fn>).mock
      .calls[0][1];
    expect(payload).toMatchObject({ category: "stakeholder" });
  });
});

/**
 * Code review regression — the form never resynced local state when a
 * different `requirement` prop arrived (unlike every sibling editor:
 * AdrForm/RiskForm/IssueForm all reset on their entity prop). Selecting a
 * different requirement in the list, while this component instance stayed
 * mounted, kept showing (and would silently overwrite on Save) the
 * previously-selected requirement's stale field values.
 */
describe("RequirementForm — resyncs local state when the requirement prop changes", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const otherReq = {
    ...baseReq,
    id: "req-2",
    artifact_id: "art-2",
    title: "A different requirement",
    description: "other desc",
    change_reason: "",
  } as unknown as Requirement;

  it("resets the title/description fields to the newly-selected requirement", () => {
    const { rerender } = render(
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
    expect(screen.getByTestId("req-title")).toHaveValue("A requirement");

    rerender(
      <RequirementForm
        requirement={otherReq}
        upstreamLinks={[]}
        downstreamLinks={[]}
        linkedTitles={{}}
        linkedRoutes={{}}
        requirements={[]}
        workspaceId="ws-1"
        onSaved={vi.fn()}
      />
    );

    expect(screen.getByTestId("req-title")).toHaveValue("A different requirement");
  });

  it("discards an in-progress unsaved edit instead of saving it onto the new requirement", async () => {
    const { rerender } = render(
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
    fireEvent.change(screen.getByTestId("req-title"), {
      target: { value: "Unsaved edit to req-1" },
    });
    expect(screen.getByTestId("req-title")).toHaveValue("Unsaved edit to req-1");

    // User navigates to a different requirement without saving.
    rerender(
      <RequirementForm
        requirement={otherReq}
        upstreamLinks={[]}
        downstreamLinks={[]}
        linkedTitles={{}}
        linkedRoutes={{}}
        requirements={[]}
        workspaceId="ws-1"
        onSaved={vi.fn()}
      />
    );
    expect(screen.getByTestId("req-title")).toHaveValue("A different requirement");

    fireEvent.click(screen.getByTestId("save-btn"));
    await waitFor(() => expect(requirementsApi.update).toHaveBeenCalled());
    const [savedId, savedPayload] = (requirementsApi.update as ReturnType<typeof vi.fn>)
      .mock.calls[0];
    // Must save req-2 with req-2's own (unedited) title, never the stale
    // req-1 draft the user typed before switching away.
    expect(savedId).toBe("req-2");
    expect(savedPayload.title).toBe("A different requirement");
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
        "acceptance_criteria",
        "category",
        "complexity_fibonacci",
        "custom_fields",
        "description",
        "level",
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

/**
 * Issue #339 — "Change Reason is not marked as mandatory".
 *
 * A change reason is mandatory when EITHER the workspace runs the extended
 * preset (`PresetPolicyService.is_change_reason_required`, enforced on every
 * update) OR an AttributeVisibilityConfig row marks the field required. Those
 * two conditions used to disagree: `validateForm` blocked on either, while
 * the field itself only rendered for the extended preset — so a config-driven
 * requirement produced a save the user could never complete, with no input to
 * put the reason into.
 */
describe("RequirementForm — change_reason is marked and reachable (#339)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(requirementsApi.update).mockResolvedValue(
      {} as unknown as Requirement
    );
  });

  afterEach(() => {
    mockPreset = "standard";
    mockRequiredFields = [];
  });

  it("marks the field as required with an asterisk in the extended preset", () => {
    mockPreset = "extended";
    renderForm();

    const label = document.querySelector('label[for="change-reason"]');
    expect(label).not.toBeNull();
    expect(label).toHaveTextContent("*");
    expect(screen.getByTestId("change-reason-input")).toBeRequired();
    // Plus a hint in words, since a lone asterisk was reported as too easy to
    // miss for a field whose omission costs the entire edit.
    expect(screen.getByTestId("change-reason-hint")).toBeInTheDocument();
  });

  it("hides the hint once a reason has been entered", () => {
    mockPreset = "extended";
    renderForm();

    fireEvent.change(screen.getByTestId("change-reason-input"), {
      target: { value: "clarified wording" },
    });

    expect(screen.queryByTestId("change-reason-hint")).not.toBeInTheDocument();
  });

  it("renders the field when only an AttributeVisibilityConfig requires it", () => {
    mockPreset = "standard";
    mockRequiredFields = ["change_reason"];
    renderForm();

    // Without the input this save is unsatisfiable: the guard below blocks,
    // but there is nothing to type the reason into.
    expect(screen.getByTestId("change-reason-input")).toBeInTheDocument();
  });

  it("lets a config-required change reason actually be satisfied", async () => {
    mockPreset = "standard";
    mockRequiredFields = ["change_reason"];
    renderForm();

    fireEvent.click(screen.getByTestId("save-btn"));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("req.changeReasonRequired");
    expect(requirementsApi.update).not.toHaveBeenCalled();

    fireEvent.change(screen.getByTestId("change-reason-input"), {
      target: { value: "config-required reason" },
    });
    fireEvent.click(screen.getByTestId("save-btn"));

    await waitFor(() => expect(requirementsApi.update).toHaveBeenCalled());
    expect(
      (requirementsApi.update as ReturnType<typeof vi.fn>).mock.calls[0][1]
    ).toMatchObject({ change_reason: "config-required reason" });
  });

  it("keeps the field out of a workspace that does not require it", () => {
    mockPreset = "standard";
    renderForm();

    expect(screen.queryByTestId("change-reason-input")).not.toBeInTheDocument();
  });
});

/**
 * BUG-08 (Systemaudit 2026-08-18, §4, Hoch) — validateForm() already rejects
 * an empty title (`editor.titleRequired`) and raises the top-of-form
 * `saveError` banner, but the `#req-title` input itself carried no error
 * indication at all: no border color, no icon, no `aria-invalid`. A user
 * scanning the (long) form for what's wrong had nothing on the field to
 * find. WCAG: color alone would not be enough either — this also asserts an
 * icon + text, not just a class name.
 */
describe("RequirementForm — field-level validation error visibility (BUG-08)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockPreset = "standard";
  });

  it("marks the title input as invalid when Save is rejected for a blank title", async () => {
    const blankTitleReq = { ...baseReq, title: "" } as unknown as Requirement;
    render(
      <RequirementForm
        requirement={blankTitleReq}
        upstreamLinks={[]}
        downstreamLinks={[]}
        linkedTitles={{}}
        linkedRoutes={{}}
        requirements={[]}
        workspaceId="ws-1"
        onSaved={vi.fn()}
      />
    );

    const titleInput = screen.getByTestId("req-title");
    expect(titleInput).toHaveAttribute("aria-invalid", "false");

    fireEvent.click(screen.getByTestId("save-btn"));

    await waitFor(() => {
      expect(titleInput).toHaveAttribute("aria-invalid", "true");
    });
    const describedBy = titleInput.getAttribute("aria-describedby");
    expect(describedBy).toBeTruthy();

    const fieldError = screen.getByTestId("req-title-field-error");
    expect(fieldError).toHaveAttribute("id", describedBy);
    expect(fieldError.querySelector('[aria-hidden="true"]')).not.toBeNull();
    expect(requirementsApi.update).not.toHaveBeenCalled();
  });

  it("clears the title's invalid state once the user types a title", async () => {
    const blankTitleReq = { ...baseReq, title: "" } as unknown as Requirement;
    render(
      <RequirementForm
        requirement={blankTitleReq}
        upstreamLinks={[]}
        downstreamLinks={[]}
        linkedTitles={{}}
        linkedRoutes={{}}
        requirements={[]}
        workspaceId="ws-1"
        onSaved={vi.fn()}
      />
    );

    fireEvent.click(screen.getByTestId("save-btn"));
    await waitFor(() => {
      expect(screen.getByTestId("req-title")).toHaveAttribute("aria-invalid", "true");
    });

    fireEvent.change(screen.getByTestId("req-title"), { target: { value: "Now titled" } });

    expect(screen.getByTestId("req-title")).toHaveAttribute("aria-invalid", "false");
    expect(screen.queryByTestId("req-title-field-error")).not.toBeInTheDocument();
  });

  /**
   * F-01 / F-03 (code review, 2026-08-19) — a blank-title Save used to set
   * BOTH the page-level `saveError` banner AND the field marker with the
   * identical message: a screen reader announced "Title is required"
   * twice, and once the field was fixed the (stale) banner kept
   * contradicting it. Client-side validation must surface at the field
   * ONLY — never duplicated into the banner, and never left behind once
   * corrected.
   */
  it("never shows the page-level banner for a client-side blank-title error (F-03)", async () => {
    const blankTitleReq = { ...baseReq, title: "" } as unknown as Requirement;
    render(
      <RequirementForm
        requirement={blankTitleReq}
        upstreamLinks={[]}
        downstreamLinks={[]}
        linkedTitles={{}}
        linkedRoutes={{}}
        requirements={[]}
        workspaceId="ws-1"
        onSaved={vi.fn()}
      />
    );

    fireEvent.click(screen.getByTestId("save-btn"));
    await waitFor(() => {
      expect(screen.getByTestId("req-title")).toHaveAttribute("aria-invalid", "true");
    });

    // Exactly one alert (the field marker) — no duplicate banner.
    expect(screen.queryByTestId("req-save-error")).not.toBeInTheDocument();
    expect(screen.getAllByRole("alert")).toHaveLength(1);
  });

  it("clears a stale save-error banner as soon as the title is corrected (F-01)", async () => {
    vi.mocked(requirementsApi.update).mockRejectedValueOnce({
      error: { message: "Server rejected the previous attempt." },
    });
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

    // Trigger a genuine server-side failure first (banner appears).
    fireEvent.click(screen.getByTestId("save-btn"));
    const banner = await screen.findByTestId("req-save-error");
    expect(banner).toHaveTextContent("Server rejected the previous attempt.");

    // Now the user edits the title — the banner describes a *previous*
    // attempt and must not keep contradicting the field being corrected.
    fireEvent.change(screen.getByTestId("req-title"), { target: { value: "Edited title" } });

    expect(screen.queryByTestId("req-save-error")).not.toBeInTheDocument();
  });

  /**
   * N-01 (code review, 2026-08-19) — change_reason/verification_method used
   * to derive their alarming state straight from current form data, so an
   * untouched requirement opened in an extended-preset workspace (where
   * change_reason is mandatory) immediately showed a red border + ⚠ icon +
   * `aria-invalid="true"` + `role="alert"` before the user had done
   * anything at all. `role="alert"` is an assertive live region — a screen
   * reader announces it on focus/mount. Both markers must stay silent until
   * the user has actually attempted a Save.
   */
  it("does not alarm an untouched extended-preset form with an empty change_reason (N-01)", () => {
    mockPreset = "extended";
    mockRequiredFields = ["verification_method"];
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

    // The passive, pre-existing #339 hint is still shown proactively...
    expect(screen.getByTestId("change-reason-hint")).toBeInTheDocument();
    // ...but none of the alarming markers fire before any Save attempt.
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByTestId("change-reason-input")).toHaveAttribute("aria-invalid", "false");
    expect(screen.queryByTestId("verification-method-field-error")).not.toBeInTheDocument();
    expect(screen.getByTestId("verification-method")).toHaveAttribute("aria-invalid", "false");

    mockPreset = "standard";
    mockRequiredFields = [];
  });

  /**
   * N-02 (code review, 2026-08-19) — F-03's "no duplicate/stacked alert"
   * test only covered the single-invalid-field (title-only) case. In an
   * extended-preset workspace with several empty mandatory fields at once,
   * a single failed Save can legitimately raise more than one field-level
   * alert simultaneously (title + change_reason + verification_method) —
   * that is correct multi-field validation, not a duplicate of the same
   * message, and must only appear once the user has actually tried to Save.
   */
  it("shows one alert per invalid field after a failed Save, none before (N-02)", async () => {
    mockPreset = "extended";
    mockRequiredFields = ["verification_method"];
    const blankTitleReq = { ...baseReq, title: "" } as unknown as Requirement;
    render(
      <RequirementForm
        requirement={blankTitleReq}
        upstreamLinks={[]}
        downstreamLinks={[]}
        linkedTitles={{}}
        linkedRoutes={{}}
        requirements={[]}
        workspaceId="ws-1"
        onSaved={vi.fn()}
      />
    );

    // Nothing alarming before the first Save attempt.
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId("save-btn"));

    // All three fields are simultaneously invalid (blank title, blank
    // change_reason in an extended-preset workspace, unset
    // verification_method marked required via config) — each gets its own
    // alert, and the page-level banner stays empty (F-03).
    await waitFor(() => {
      expect(screen.getAllByRole("alert")).toHaveLength(3);
    });
    expect(screen.queryByTestId("req-save-error")).not.toBeInTheDocument();
    expect(requirementsApi.update).not.toHaveBeenCalled();

    mockPreset = "standard";
    mockRequiredFields = [];
  });
});
