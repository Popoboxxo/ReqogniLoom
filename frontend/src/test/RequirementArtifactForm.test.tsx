import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { resolveLocaleKey } from "./i18n-test-helpers";
import { assertNoProtectedPatchFields } from "./protected-patch-fields";

// Same convention as Risk/Issue/Need/TestCase (Tasks 19/20/23): the real
// `useTranslation()` hook needs a real i18next instance (`i18n.language` set)
// to avoid `FieldShell`'s `helpText`/`attributeLabel` crashing on
// `undefined.startsWith` — verified live, every `render()`-based test below
// failed with that exact TypeError before this mock was added (the plan
// brief's version of this test never mocks react-i18next).
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) => {
      const { defaultValue, ...interpolation } = options ?? {};
      const resolved =
        resolveLocaleKey(key) ??
        (typeof defaultValue === "string" ? defaultValue : key);
      return Object.entries(interpolation).reduce(
        (acc, [name, value]) => acc.replace(`{{${name}}}`, String(value)),
        resolved
      );
    },
    i18n: { language: "de" },
  }),
}));

import { requirementsApi } from "../api/requirements";
import { attributeDefinitionsApi } from "../api/attribute-definitions";
import {
  RequirementArtifactForm,
  formValuesToRequirementPatch,
  requirementToFormValues,
} from "../components/RequirementEditors/RequirementArtifactForm";

const workspace = { current: { id: "ws-1", preset: "standard" } };

vi.mock("../api/requirements", () => ({
  requirementsApi: { update: vi.fn(), delete: vi.fn() },
}));
vi.mock("../api/attribute-definitions", () => ({
  attributeDefinitionsApi: { getWorkspace: vi.fn() },
}));
vi.mock("../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: workspace.current }),
}));

const REQUIREMENT = {
  id: "req-1",
  workspace_id: "ws-1",
  title: "Login",
  description: "d",
  acceptance_criteria: "ac",
  category: "functional",
  verification_method: "test",
  uid: "REQ-1",
  custom_fields: {},
  version: 7,
} as never;

// Full, realistic GET-shaped payload — every field `RequirementSerializer`
// actually returns (backend/rest_api/serializers.py), not the minimal
// hand-built `REQUIREMENT` fixture above. Task 19's C-1 fix round found that a
// minimal fixture with no `uid` key is exactly what let a protected field
// leak into a PATCH ship undetected.
const FULL_REQUIREMENT_GET_PAYLOAD = {
  id: "req-1",
  workspace_id: "ws-1",
  artifact_id: "art-1",
  parent_id: null,
  title: "Login",
  description: "d",
  acceptance_criteria: "ac",
  category: "functional",
  type: "SyReq",
  complexity_fibonacci: 3,
  verification_method: "Test",
  level: 1,
  suspect: false,
  uid: "REQ-1",
  version: 7,
  change_reason: "",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-02T00:00:00Z",
  atomicity_warning: null,
  status: "draft",
  custom_fields: {},
} as never;

function attr(over: Record<string, unknown>) {
  return {
    name: "title", kind: "core", type: "text", widget_key: null, fields: [],
    options: [], required: false, visible: true, locked: false, editable: true,
    section: "general", order: 1, label: { de: "", en: "" },
    help_text: { de: "", en: "" }, default: null, validation: {},
    ai_elicit: false, export: true, audience: "basic", ...over,
  };
}

describe("RequirementArtifactForm", () => {
  beforeEach(() => {
    workspace.current = { id: "ws-1", preset: "standard" };
    vi.mocked(attributeDefinitionsApi.getWorkspace).mockResolvedValue({
      item_type: "Requirement",
      preset: "standard",
      is_customized: false,
      version: 1,
      attributes: [
        attr({ name: "title", required: true }),
        attr({ name: "acceptance_criteria", type: "textarea", order: 2 }),
        attr({
          name: "verification_method", type: "enum", section: "classification",
          order: 1, audience: "expert",
          options: [{ value: "test", label_de: "Test", label_en: "Test" }],
        }),
        // `audience: "expert"` (bootstrap default is "basic", but the real
        // definition marks a read-only identity field like this one expert so
        // it starts collapsed, same as `artifactForm.lockedHint`'s
        // "system-critical" framing) — needed so the section actually starts
        // COLLAPSED, matching what the "renders an editable=false attribute
        // as disabled" test below exercises (click-to-reveal). With the
        // bootstrap default of "basic" this single-attribute section would
        // already be open, and the test's own click would collapse it instead.
        attr({ name: "uid", section: "change_control", order: 1, editable: false, audience: "expert" }),
      ],
    } as never);
    vi.mocked(requirementsApi.update).mockReset();
    vi.mocked(requirementsApi.delete).mockReset();
  });

  it("maps a Requirement onto form values", () => {
    const values = requirementToFormValues(REQUIREMENT);
    expect(values.acceptance_criteria).toBe("ac");
    expect(values.custom_fields).toEqual({});
  });

  it("strips server-owned fields from the patch", () => {
    const patch = formValuesToRequirementPatch(requirementToFormValues(REQUIREMENT));
    expect(patch).not.toHaveProperty("version");
    expect(patch).not.toHaveProperty("id");
    expect(patch).not.toHaveProperty("uid");
    expect(patch.title).toBe("Login");
  });

  // C-1-class regression test (Task 19 lesson): rebuilds the actual patch the
  // component emits from a full, realistic GET-shaped payload and asserts
  // zero PATCH-protected keys survive.
  it("never leaks a PATCH-protected field, from a full realistic GET payload", () => {
    const values = requirementToFormValues(FULL_REQUIREMENT_GET_PAYLOAD);
    const edited = { ...values, title: "Login (updated)" };
    const patch = formValuesToRequirementPatch(edited);
    assertNoProtectedPatchFields(patch);
    // Live-verification finding: `atomicity_warning` is a SerializerMethodField
    // (read-only, DRF silently drops it) but not in `_PROTECTED_PATCH_FIELDS`
    // (it never rejects the PATCH) — excluded anyway so the emitted body
    // never carries a value the server can never accept back.
    expect(patch).not.toHaveProperty("atomicity_warning");
    expect(patch.title).toBe("Login (updated)");
  });

  it("renders the classification and change-control sections", async () => {
    render(
      <RequirementArtifactForm
        requirement={REQUIREMENT}
        onSaved={vi.fn()}
        onDeleted={vi.fn()}
      />
    );
    expect(
      await screen.findByTestId("artifact-section-toggle-classification")
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("artifact-section-toggle-change_control")
    ).toBeInTheDocument();
  });

  it("renders an editable=false attribute as disabled", async () => {
    render(
      <RequirementArtifactForm
        requirement={REQUIREMENT}
        onSaved={vi.fn()}
        onDeleted={vi.fn()}
      />
    );
    await userEvent.click(
      await screen.findByTestId("artifact-section-toggle-change_control")
    );
    expect(screen.getByTestId("artifact-field-uid")).toBeDisabled();
  });

  it("does not ask for a change reason outside the extended preset", async () => {
    render(
      <RequirementArtifactForm
        requirement={REQUIREMENT}
        onSaved={vi.fn()}
        onDeleted={vi.fn()}
      />
    );
    await screen.findByTestId("artifact-field-title");
    expect(screen.queryByTestId("artifact-form-change-reason")).not.toBeInTheDocument();
  });

  it("requires a change reason in the extended preset before saving", async () => {
    workspace.current = { id: "ws-1", preset: "extended" };
    vi.mocked(requirementsApi.update).mockResolvedValue(REQUIREMENT);
    render(
      <RequirementArtifactForm
        requirement={REQUIREMENT}
        onSaved={vi.fn()}
        onDeleted={vi.fn()}
      />
    );
    const save = await screen.findByTestId("artifact-form-save");
    expect(screen.getByTestId("artifact-form-change-reason")).toBeInTheDocument();
    await userEvent.click(save);
    expect(requirementsApi.update).not.toHaveBeenCalled();

    await userEvent.type(
      screen.getByTestId("artifact-form-change-reason"),
      "clarified wording"
    );
    await userEvent.click(save);
    await waitFor(() =>
      expect(requirementsApi.update).toHaveBeenCalledWith(
        "req-1",
        expect.objectContaining({ change_reason: "clarified wording" })
      )
    );
  });

  it("saves and clears the dirty state", async () => {
    vi.mocked(requirementsApi.update).mockResolvedValue(REQUIREMENT);
    const onDirtyChange = vi.fn();
    render(
      <RequirementArtifactForm
        requirement={REQUIREMENT}
        onSaved={vi.fn()}
        onDeleted={vi.fn()}
        onDirtyChange={onDirtyChange}
      />
    );
    await userEvent.type(await screen.findByTestId("artifact-field-title"), "!");
    await userEvent.click(screen.getByTestId("artifact-form-save"));
    await waitFor(() => expect(onDirtyChange).toHaveBeenLastCalledWith(false));
  });

  it("deletes through the shared confirm dialog", async () => {
    vi.mocked(requirementsApi.delete).mockResolvedValue(undefined as never);
    const onDeleted = vi.fn();
    render(
      <RequirementArtifactForm
        requirement={REQUIREMENT}
        onSaved={vi.fn()}
        onDeleted={onDeleted}
      />
    );
    await userEvent.click(await screen.findByTestId("artifact-form-delete"));
    await userEvent.click(screen.getByTestId("artifact-form-delete-confirm"));
    await waitFor(() =>
      expect(requirementsApi.delete).toHaveBeenCalledWith("req-1", undefined)
    );
    expect(onDeleted).toHaveBeenCalled();
  });

  // F-1 (Task 25 fix round 1): a delete in the Extended preset without a
  // change_reason previously called `requirementsApi.delete(id)` with no
  // reason, which the backend 400s (`RequirementService.delete_requirement`
  // enforces the same `is_change_reason_required` check PATCH gets) — the
  // delete button was effectively dead in the Seed-/E2E-workspace's Extended
  // preset. This regression-tests the actual reported bug: an Extended-preset
  // delete now must carry the reason typed into the shared field.
  it("sends the typed change reason with a delete under the extended preset", async () => {
    workspace.current = { id: "ws-1", preset: "extended" };
    vi.mocked(requirementsApi.delete).mockResolvedValue(undefined as never);
    const onDeleted = vi.fn();
    render(
      <RequirementArtifactForm
        requirement={REQUIREMENT}
        onSaved={vi.fn()}
        onDeleted={onDeleted}
      />
    );
    await userEvent.type(
      await screen.findByTestId("artifact-form-change-reason"),
      "no longer needed"
    );
    await userEvent.click(screen.getByTestId("artifact-form-delete"));
    await userEvent.click(screen.getByTestId("artifact-form-delete-confirm"));
    await waitFor(() =>
      expect(requirementsApi.delete).toHaveBeenCalledWith(
        "req-1",
        "no longer needed"
      )
    );
    expect(onDeleted).toHaveBeenCalled();
  });

  it("blocks a delete under the extended preset when no change reason was typed", async () => {
    workspace.current = { id: "ws-1", preset: "extended" };
    render(
      <RequirementArtifactForm
        requirement={REQUIREMENT}
        onSaved={vi.fn()}
        onDeleted={vi.fn()}
      />
    );
    await userEvent.click(await screen.findByTestId("artifact-form-delete"));
    await userEvent.click(screen.getByTestId("artifact-form-delete-confirm"));
    expect(await screen.findByTestId("artifact-form-error")).toBeInTheDocument();
    expect(requirementsApi.delete).not.toHaveBeenCalled();
  });
});
