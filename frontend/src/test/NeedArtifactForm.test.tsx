import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { resolveLocaleKey } from "./i18n-test-helpers";
import { assertNoProtectedPatchFields } from "./protected-patch-fields";

// DEVIATION from the plan brief (same class already documented in
// RiskArtifactForm.test.tsx / IssueArtifactForm.test.tsx): the brief's test
// never mocks react-i18next. The shared i18next singleton is never
// initialised in unit tests, so the literal-brief version crashes on
// `i18n.language.startsWith(...)` inside FieldShell's `helpText`
// (`i18n.language` is `undefined`) the moment `ArtifactForm` actually renders
// a field — verified live.
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

import { stakeholderNeedApi } from "../api/stakeholder-need";
import {
  NeedArtifactForm,
  formValuesToNeedPatch,
  needToFormValues,
} from "../components/NeedsEditors/NeedArtifactForm";
import { attributeDefinitionsApi } from "../api/attribute-definitions";

vi.mock("../api/stakeholder-need", () => ({
  stakeholderNeedApi: { update: vi.fn(), delete: vi.fn() },
}));
vi.mock("../api/attribute-definitions", () => ({
  attributeDefinitionsApi: { getWorkspace: vi.fn() },
}));

const useWorkspaceMock = vi.fn();
vi.mock("../context/WorkspaceContext", () => ({
  useWorkspace: () => useWorkspaceMock(),
}));

const NEED = {
  id: "n-1",
  workspace_id: "ws-1",
  title: "Fast login",
  description: "d",
  category: "usability",
  moscow_priority: "must",
  custom_fields: {},
  version: 1,
} as never;

// Standing runbook note (since Task 19, binding for every rollout wave): a
// REALISTIC, full GET-shaped payload — every field `StakeholderNeedSerializer`
// actually returns (rest_api/serializers.py), not the minimal `NEED` fixture
// above. `change_reason`/`expected_version` are write_only (never in a GET
// response); `parent_id`/`suspect` are declared `read_only=True`.
const FULL_NEED_GET_PAYLOAD = {
  id: "n-1",
  workspace_id: "ws-1",
  artifact_id: "art-1",
  parent_id: null,
  title: "Fast login",
  description: "d",
  category: "usability",
  moscow_priority: "must",
  uid: "SN-0001",
  suspect: false,
  version: 3,
  status: "draft",
  custom_fields: { sap_id: "S-1" },
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-02T00:00:00Z",
} as never;

const TITLE_ATTRIBUTE = {
  name: "title", kind: "core", type: "text", widget_key: null, fields: [],
  options: [], required: true, visible: true, locked: false, editable: true,
  section: "general", order: 1, label: { de: "Titel", en: "Title" },
  help_text: { de: "", en: "" }, default: null, validation: {},
  ai_elicit: true, export: true, audience: "basic",
} as never;

const MOSCOW_ATTRIBUTE = {
  name: "moscow_priority", kind: "core", type: "enum", widget_key: null, fields: [],
  options: [], required: false, visible: false, locked: false, editable: true,
  section: "classification", order: 2, label: { de: "", en: "" },
  help_text: { de: "", en: "" }, default: null, validation: {},
  ai_elicit: false, export: true, audience: "basic",
} as never;

describe("NeedArtifactForm", () => {
  beforeEach(() => {
    useWorkspaceMock.mockReturnValue({ activeWorkspace: { id: "ws-1", preset: "standard" } });
    vi.mocked(attributeDefinitionsApi.getWorkspace).mockResolvedValue({
      item_type: "StakeholderNeed",
      preset: "standard",
      is_customized: false,
      version: 1,
      attributes: [TITLE_ATTRIBUTE, MOSCOW_ATTRIBUTE],
    });
    vi.mocked(stakeholderNeedApi.update).mockReset();
    vi.mocked(stakeholderNeedApi.delete).mockReset();
  });

  it("maps a StakeholderNeed onto form values", () => {
    const values = needToFormValues(NEED);
    expect(values.title).toBe("Fast login");
    expect(values.custom_fields).toEqual({});
  });

  it("strips server-owned fields from the patch", () => {
    const patch = formValuesToNeedPatch(needToFormValues(NEED));
    expect(patch).not.toHaveProperty("id");
    expect(patch).not.toHaveProperty("version");
    expect(patch.category).toBe("usability");
  });

  // Binding for every rollout wave (Task 19/20 standing runbook note):
  // rebuilds the actual patch the component emits (needToFormValues -> edit
  // -> formValuesToNeedPatch) from a full, realistic GET-shaped payload and
  // asserts zero PATCH-protected keys survive.
  it("never leaks a PATCH-protected field, from a full realistic GET payload", () => {
    const values = needToFormValues(FULL_NEED_GET_PAYLOAD);
    const edited = { ...values, title: "Fast login (updated)" };
    const patch = formValuesToNeedPatch(edited);
    assertNoProtectedPatchFields(patch);
    expect(patch.title).toBe("Fast login (updated)");
    // parent_id / suspect are read_only on the serializer (not in
    // _PROTECTED_PATCH_FIELDS, but DRF-silent-dropped) — defensive exclude.
    expect(patch).not.toHaveProperty("parent_id");
    expect(patch).not.toHaveProperty("suspect");
  });

  // Migrated from the deleted NeedForm's own regression test (#263): `status`
  // is the read-only WorkflowEngine mirror — resending it used to make the
  // backend reject the whole PATCH, silently discarding whatever content the
  // user had just typed. State changes run through POST .../transitions/
  // (WorkflowStatusEditor) only.
  it("never sends status in the save payload (#263)", () => {
    const patch = formValuesToNeedPatch(needToFormValues(FULL_NEED_GET_PAYLOAD));
    expect(patch).not.toHaveProperty("status");
    expect(patch).toHaveProperty("title");
    expect(patch).toHaveProperty("description");
  });

  it("hides an attribute the definition marks invisible", async () => {
    render(<NeedArtifactForm need={NEED} onSaved={vi.fn()} onDeleted={vi.fn()} />);
    await screen.findByTestId("artifact-field-title");
    expect(
      screen.queryByTestId("artifact-field-moscow_priority")
    ).not.toBeInTheDocument();
  });

  it("saves through stakeholderNeedApi.update", async () => {
    vi.mocked(stakeholderNeedApi.update).mockResolvedValue(NEED);
    const onSaved = vi.fn();
    render(<NeedArtifactForm need={NEED} onSaved={onSaved} onDeleted={vi.fn()} />);
    await userEvent.click(await screen.findByTestId("artifact-form-save"));
    await waitFor(() => expect(stakeholderNeedApi.update).toHaveBeenCalled());
    expect(onSaved).toHaveBeenCalled();
  });

  it("deletes through the shared confirm dialog", async () => {
    vi.mocked(stakeholderNeedApi.delete).mockResolvedValue(undefined as never);
    const onDeleted = vi.fn();
    render(<NeedArtifactForm need={NEED} onSaved={vi.fn()} onDeleted={onDeleted} />);
    await userEvent.click(await screen.findByTestId("artifact-form-delete"));
    await userEvent.click(screen.getByTestId("artifact-form-delete-confirm"));
    await waitFor(() => expect(stakeholderNeedApi.delete).toHaveBeenCalledWith("n-1"));
    expect(onDeleted).toHaveBeenCalled();
  });

  // REQ-162: unlike Risk/Issue, StakeholderNeedService.update_need() genuinely
  // enforces change_reason on the Extended preset (application/
  // stakeholder_need_service.py:296) — carried over from the deleted
  // NeedForm's own change_reason handling (formerly
  // need-form-change-reason.test.tsx). ArtifactForm itself has no concept of
  // change_reason (it is a write_only serializer param, never a model column,
  // so bootstrap introspection never produces it as an attribute), so this is
  // NeedArtifactForm's own responsibility, not the shared renderer's.
  describe("change_reason (REQ-162, Extended preset)", () => {
    it("shows the change_reason field when the workspace preset is Extended", async () => {
      useWorkspaceMock.mockReturnValue({ activeWorkspace: { id: "ws-1", preset: "extended" } });
      render(<NeedArtifactForm need={NEED} onSaved={vi.fn()} onDeleted={vi.fn()} />);
      await screen.findByTestId("artifact-field-title");
      expect(screen.getByTestId("need-change-reason-input")).toBeInTheDocument();
    });

    it("hides the change_reason field for the Standard preset", async () => {
      render(<NeedArtifactForm need={NEED} onSaved={vi.fn()} onDeleted={vi.fn()} />);
      await screen.findByTestId("artifact-field-title");
      expect(screen.queryByTestId("need-change-reason-input")).not.toBeInTheDocument();
    });

    it("blocks save and does not call the API when Extended and change_reason is empty", async () => {
      useWorkspaceMock.mockReturnValue({ activeWorkspace: { id: "ws-1", preset: "extended" } });
      render(<NeedArtifactForm need={NEED} onSaved={vi.fn()} onDeleted={vi.fn()} />);
      await userEvent.click(await screen.findByTestId("artifact-form-save"));
      const alert = await screen.findByTestId("artifact-form-error");
      expect(alert.textContent).toContain(resolveLocaleKey("req.changeReasonRequired"));
      expect(stakeholderNeedApi.update).not.toHaveBeenCalled();
    });

    it("includes change_reason in the update payload when provided", async () => {
      useWorkspaceMock.mockReturnValue({ activeWorkspace: { id: "ws-1", preset: "extended" } });
      vi.mocked(stakeholderNeedApi.update).mockResolvedValue(NEED);
      render(<NeedArtifactForm need={NEED} onSaved={vi.fn()} onDeleted={vi.fn()} />);
      await screen.findByTestId("artifact-field-title");
      await userEvent.type(
        screen.getByTestId("need-change-reason-input"),
        "Clarified wording per stakeholder review"
      );
      await userEvent.click(screen.getByTestId("artifact-form-save"));
      await waitFor(() =>
        expect(stakeholderNeedApi.update).toHaveBeenCalledWith(
          "n-1",
          expect.objectContaining({ change_reason: "Clarified wording per stakeholder review" })
        )
      );
    });

    // R-2: the component is reused across list selections (never remounted),
    // so a reason typed for need A must not silently ride along on need B's
    // PATCH once the user switches.
    it("resets change_reason when the component is reused for a different need (R-2)", async () => {
      useWorkspaceMock.mockReturnValue({ activeWorkspace: { id: "ws-1", preset: "extended" } });
      const { rerender } = render(
        <NeedArtifactForm need={NEED} onSaved={vi.fn()} onDeleted={vi.fn()} />
      );
      const input = await screen.findByTestId("need-change-reason-input");
      await userEvent.type(input, "Reason for need A");
      expect(input).toHaveValue("Reason for need A");

      const otherNeed = {
        ...(NEED as unknown as Record<string, unknown>),
        id: "n-2",
        title: "Other need",
      } as never;
      rerender(<NeedArtifactForm need={otherNeed} onSaved={vi.fn()} onDeleted={vi.fn()} />);
      await waitFor(() =>
        expect(screen.getByTestId("need-change-reason-input")).toHaveValue("")
      );
    });

    // S-1: DELETE is gated by the same is_change_reason_required check as
    // PATCH — reuse the same textarea value rather than a second prompt.
    it("sends change_reason on delete when the workspace preset is Extended (S-1)", async () => {
      useWorkspaceMock.mockReturnValue({ activeWorkspace: { id: "ws-1", preset: "extended" } });
      vi.mocked(stakeholderNeedApi.delete).mockResolvedValue(undefined as never);
      const onDeleted = vi.fn();
      render(<NeedArtifactForm need={NEED} onSaved={vi.fn()} onDeleted={onDeleted} />);
      await userEvent.type(
        await screen.findByTestId("need-change-reason-input"),
        "Superseded by REQ-200"
      );
      await userEvent.click(screen.getByTestId("artifact-form-delete"));
      await userEvent.click(screen.getByTestId("artifact-form-delete-confirm"));
      await waitFor(() =>
        expect(stakeholderNeedApi.delete).toHaveBeenCalledWith("n-1", "Superseded by REQ-200")
      );
      expect(onDeleted).toHaveBeenCalled();
    });

    // S-2: an unsubmitted change_reason must count as "dirty" too, or the
    // unsaved-changes dialog in NeedsEditors never fires for it.
    it("reports dirty when a change_reason is typed, even with no field edited (S-2)", async () => {
      useWorkspaceMock.mockReturnValue({ activeWorkspace: { id: "ws-1", preset: "extended" } });
      const onDirtyChange = vi.fn();
      render(
        <NeedArtifactForm
          need={NEED}
          onSaved={vi.fn()}
          onDeleted={vi.fn()}
          onDirtyChange={onDirtyChange}
        />
      );
      onDirtyChange.mockClear();
      await userEvent.type(
        await screen.findByTestId("need-change-reason-input"),
        "x"
      );
      await waitFor(() => expect(onDirtyChange).toHaveBeenCalledWith(true));
    });
  });

  // R-1: custom_fields is edited by a sibling CustomFieldsEditor NeedsEditors
  // renders outside this form; its current value arrives via the
  // `customFields` prop and is sent to the API as-is on save.
  it("sends the customFields prop as-is in the update payload (R-1)", async () => {
    vi.mocked(stakeholderNeedApi.update).mockResolvedValue(NEED);
    render(
      <NeedArtifactForm
        need={NEED}
        onSaved={vi.fn()}
        onDeleted={vi.fn()}
        customFields={{ sap_id: "S-42" }}
      />
    );
    await userEvent.click(await screen.findByTestId("artifact-form-save"));
    await waitFor(() =>
      expect(stakeholderNeedApi.update).toHaveBeenCalledWith(
        "n-1",
        expect.objectContaining({ custom_fields: { sap_id: "S-42" } })
      )
    );
  });

  // F-1 (Task 23 fix round 4 — reverts N-2's merge): N-2's 3-way merge
  // (`need.custom_fields` as base, `values.custom_fields` and the sibling
  // draft layered on top) is proven live-broken — `StakeholderNeedService.
  // update_need()` REPLACES `custom_fields` server-side, so re-merging the
  // STALE `need.custom_fields` baseline back in on every save silently
  // resurrected a key the sibling `CustomFieldsEditor` had just deleted.
  // The `customFields` prop must now be an unconditional OVERWRITE: a key
  // present in `need.custom_fields` but absent from the sibling's draft
  // must NOT survive into the PATCH.
  it("overwrites need.custom_fields with the customFields prop — a removed key does not survive (F-1)", async () => {
    const needWithCustomFields = {
      ...(NEED as unknown as Record<string, unknown>),
      custom_fields: { a: "1", b: "2" },
    } as never;
    vi.mocked(stakeholderNeedApi.update).mockResolvedValue(NEED);
    render(
      <NeedArtifactForm
        need={needWithCustomFields}
        onSaved={vi.fn()}
        onDeleted={vi.fn()}
        // Sibling editor's draft: key "b" was removed by the user.
        customFields={{ a: "1" }}
      />
    );
    await userEvent.click(await screen.findByTestId("artifact-form-save"));
    await waitFor(() =>
      expect(stakeholderNeedApi.update).toHaveBeenCalledWith(
        "n-1",
        expect.objectContaining({ custom_fields: { a: "1" } })
      )
    );
    const [, patchArg] = vi.mocked(stakeholderNeedApi.update).mock.calls[0];
    expect(patchArg).toHaveProperty("custom_fields", { a: "1" });
    expect(
      Object.prototype.hasOwnProperty.call(
        (patchArg as { custom_fields: Record<string, unknown> }).custom_fields,
        "b"
      )
    ).toBe(false);
  });

  // Falls back to need.custom_fields only when no sibling draft is passed at
  // all (e.g. the form mounted standalone in a test) — still an overwrite,
  // never a merge.
  it("falls back to need.custom_fields when no customFields prop is given", async () => {
    const needWithCustomFields = {
      ...(NEED as unknown as Record<string, unknown>),
      custom_fields: { a: "1" },
    } as never;
    vi.mocked(stakeholderNeedApi.update).mockResolvedValue(NEED);
    render(
      <NeedArtifactForm need={needWithCustomFields} onSaved={vi.fn()} onDeleted={vi.fn()} />
    );
    await userEvent.click(await screen.findByTestId("artifact-form-save"));
    await waitFor(() =>
      expect(stakeholderNeedApi.update).toHaveBeenCalledWith(
        "n-1",
        expect.objectContaining({ custom_fields: { a: "1" } })
      )
    );
  });
});
