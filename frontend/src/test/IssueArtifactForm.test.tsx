import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { resolveLocaleKey } from "./i18n-test-helpers";
import { assertNoProtectedPatchFields } from "./protected-patch-fields";

// DEVIATION from the plan brief (same class already documented in
// ArtifactForm.test.tsx / RiskArtifactForm.test.tsx): the brief's test never
// mocks react-i18next. The shared i18next singleton is never initialised in
// unit tests, so the literal-brief version crashes on
// `i18n.language.startsWith(...)` inside FieldShell's `helpText` (`i18n.language`
// is `undefined`) the moment `ArtifactForm` actually renders a field — verified
// live, both later `render()`-based tests failed with that exact TypeError
// before this mock was added.
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

import { issuesApi } from "../api/issues";
import {
  IssueArtifactForm,
  formValuesToIssuePatch,
  issueToFormValues,
} from "../components/IssueEditors/IssueArtifactForm";
import { attributeDefinitionsApi } from "../api/attribute-definitions";

vi.mock("../api/issues", () => ({
  issuesApi: { update: vi.fn(), delete: vi.fn() },
}));
vi.mock("../api/attribute-definitions", () => ({
  attributeDefinitionsApi: { getWorkspace: vi.fn() },
}));
vi.mock("../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "ws-1", preset: "standard" } }),
}));

const ISSUE = {
  id: "i-1",
  workspace_id: "ws-1",
  title: "Broken",
  description: "d",
  severity: "high",
  category: "defect",
  status: "Open",
  tags: [],
  due_date: "2026-10-01T00:00:00Z",
  version: 2,
} as never;

// Task 20 / standing runbook note (since Task 19): a REALISTIC, full
// GET-shaped payload — every field IssueSerializer actually returns, live-
// verified against a real bootstrapped Issue via `curl` (see the Task 20
// implementer report). `assignee_id`/`assignee_changed_date` are
// deliberately absent: Task 20 found they were being introspected as
// visible/editable attributes with no REST wiring at all (assignee changes
// route through the dedicated, unwired `assign_issue()`) and excluded them
// at the shared bootstrap point rather than shipping a silent-discard field,
// same class as Task 19's `uid` finding below. `due_date` IS present: Task
// 20 found and fixed a bare gap where the model/service already supported it
// but `IssueSerializer` never declared it at all.
const FULL_ISSUE_GET_PAYLOAD = {
  id: "i-1",
  workspace_id: "ws-1",
  title: "Broken",
  description: "d",
  severity: "high",
  category: "defect",
  status: "Open",
  tags: ["urgent"],
  due_date: "2026-10-01T00:00:00Z",
  uid: "ISSUE-0001",
  version: 2,
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

// F-1 fix, Task 20 review round: `severity` (plain enum) and `tags` (JSONField,
// rendered through the `tag_input` widget) as they now actually come back from
// `introspect_core_attributes("Issue", ...)` — verified live against the real
// bootstrap command, not a synthetic minimal shape.
const SEVERITY_ATTRIBUTE = {
  name: "severity", kind: "core", type: "enum", widget_key: null, fields: [],
  options: [
    { value: "low", label_de: "Niedrig", label_en: "Low" },
    { value: "medium", label_de: "Mittel", label_en: "Medium" },
    { value: "high", label_de: "Hoch", label_en: "High" },
    { value: "critical", label_de: "Kritisch", label_en: "Critical" },
  ],
  required: false, visible: true, locked: false, editable: true,
  section: "general", order: 2, label: { de: "Schweregrad", en: "Severity" },
  help_text: { de: "", en: "" }, default: null, validation: {},
  ai_elicit: false, export: true, audience: "basic",
} as never;

const TAGS_WIDGET_ATTRIBUTE = {
  name: "tag_list", kind: "core", type: "widget", widget_key: "tag_input",
  fields: ["tags"], options: [], required: false, visible: true, locked: false,
  editable: true, section: "general", order: 30, label: { de: "Tags", en: "Tags" },
  help_text: { de: "", en: "" }, default: null, validation: {},
  ai_elicit: false, export: false, audience: "basic",
} as never;

const DUE_DATE_ATTRIBUTE = {
  name: "due_date", kind: "core", type: "date", widget_key: null, fields: [],
  options: [], required: false, visible: true, locked: false, editable: true,
  section: "general", order: 4, label: { de: "Fällig am", en: "Due date" },
  help_text: { de: "", en: "" }, default: null, validation: {},
  ai_elicit: false, export: true, audience: "basic",
} as never;

describe("IssueArtifactForm", () => {
  beforeEach(() => {
    vi.mocked(attributeDefinitionsApi.getWorkspace).mockResolvedValue({
      item_type: "Issue",
      preset: "standard",
      is_customized: false,
      version: 1,
      attributes: [TITLE_ATTRIBUTE],
    });
    vi.mocked(issuesApi.update).mockReset();
    vi.mocked(issuesApi.delete).mockReset();
  });

  it("maps an Issue onto form values", () => {
    const values = issueToFormValues(ISSUE);
    expect(values.title).toBe("Broken");
    expect(values.due_date).toBe("2026-10-01T00:00:00Z");
    expect(values.custom_fields).toEqual({});
  });

  it("strips server-owned fields from the patch", () => {
    const patch = formValuesToIssuePatch(issueToFormValues(ISSUE));
    expect(patch).not.toHaveProperty("id");
    expect(patch).not.toHaveProperty("version");
    expect(patch.due_date).toBe("2026-10-01T00:00:00Z");
  });

  // Standing runbook note (since Task 19, binding for every rollout wave):
  // rebuilds the actual patch the component emits (issueToFormValues -> edit
  // -> formValuesToIssuePatch) from a full, realistic GET-shaped payload and
  // asserts zero PATCH-protected keys survive. This is the test class whose
  // absence let Risk's `uid` ship as a 100%-failure-rate bug.
  it("never leaks a PATCH-protected field, from a full realistic GET payload", () => {
    const values = issueToFormValues(FULL_ISSUE_GET_PAYLOAD);
    const edited = { ...values, title: "Broken (updated)" };
    const patch = formValuesToIssuePatch(edited);
    assertNoProtectedPatchFields(patch);
    expect(patch.title).toBe("Broken (updated)");
  });

  it("reports dirty state so the parent can warn before navigating away", async () => {
    const onDirtyChange = vi.fn();
    render(
      <IssueArtifactForm
        issue={ISSUE}
        onSaved={vi.fn()}
        onDeleted={vi.fn()}
        onDirtyChange={onDirtyChange}
      />
    );
    await userEvent.type(await screen.findByTestId("artifact-field-title"), "!");
    await waitFor(() => expect(onDirtyChange).toHaveBeenCalledWith(true));
  });

  it("saves through issuesApi.update", async () => {
    vi.mocked(issuesApi.update).mockResolvedValue(ISSUE);
    const onSaved = vi.fn();
    render(
      <IssueArtifactForm issue={ISSUE} onSaved={onSaved} onDeleted={vi.fn()} />
    );
    await userEvent.click(await screen.findByTestId("artifact-form-save"));
    await waitFor(() => expect(issuesApi.update).toHaveBeenCalled());
    expect(onSaved).toHaveBeenCalled();
  });

  it("deletes through the shared confirm dialog", async () => {
    vi.mocked(issuesApi.delete).mockResolvedValue(undefined as never);
    const onDeleted = vi.fn();
    render(
      <IssueArtifactForm issue={ISSUE} onSaved={vi.fn()} onDeleted={onDeleted} />
    );
    await userEvent.click(await screen.findByTestId("artifact-form-delete"));
    await userEvent.click(screen.getByTestId("artifact-form-delete-confirm"));
    await waitFor(() => expect(issuesApi.delete).toHaveBeenCalledWith("i-1"));
    expect(onDeleted).toHaveBeenCalled();
  });

  // F-1 fix, Task 20 review round: severity + tags used to be completely
  // absent from the introspected Issue definition (severity: global exclusion
  // meant for Risk.severity only; tags: JSONField with no widget registered),
  // so neither rendered anywhere in this form. Regression coverage against
  // the definition shape `introspect_core_attributes` now actually produces.
  describe("severity + tags editability (F-1 regression)", () => {
    beforeEach(() => {
      vi.mocked(attributeDefinitionsApi.getWorkspace).mockResolvedValue({
        item_type: "Issue",
        preset: "standard",
        is_customized: false,
        version: 1,
        attributes: [TITLE_ATTRIBUTE, SEVERITY_ATTRIBUTE, TAGS_WIDGET_ATTRIBUTE, DUE_DATE_ATTRIBUTE],
      });
    });

    it("renders an editable severity select", async () => {
      render(
        <IssueArtifactForm issue={ISSUE} onSaved={vi.fn()} onDeleted={vi.fn()} />
      );
      const select = await screen.findByTestId("artifact-field-severity");
      expect(select).not.toBeDisabled();
      expect((select as HTMLSelectElement).value).toBe("high");
    });

    it("renders the tags widget with the current tags and can add one", async () => {
      render(
        <IssueArtifactForm
          issue={{ ...(ISSUE as unknown as Record<string, unknown>), tags: ["urgent"] } as never}
          onSaved={vi.fn()}
          onDeleted={vi.fn()}
        />
      );
      expect(await screen.findByText("urgent")).toBeInTheDocument();
      const tagInput = screen.getByTestId("artifact-widget-tag_list-tags-input");
      expect(tagInput).not.toBeDisabled();
    });

    it("PATCHes an edited severity and an added tag through issuesApi.update", async () => {
      vi.mocked(issuesApi.update).mockResolvedValue(ISSUE);
      render(
        <IssueArtifactForm
          issue={{ ...(ISSUE as unknown as Record<string, unknown>), tags: [] } as never}
          onSaved={vi.fn()}
          onDeleted={vi.fn()}
        />
      );
      await userEvent.selectOptions(
        await screen.findByTestId("artifact-field-severity"),
        "critical"
      );
      const tagInput = screen.getByTestId("artifact-widget-tag_list-tags-input");
      await userEvent.type(tagInput, "regression{enter}");

      await userEvent.click(screen.getByTestId("artifact-form-save"));
      await waitFor(() => expect(issuesApi.update).toHaveBeenCalled());
      const [, patch] = vi.mocked(issuesApi.update).mock.calls[0];
      expect(patch).toMatchObject({ severity: "critical", tags: ["regression"] });
    });
  });

  // F-2 fix, Task 20 review round: `DateField` sends an explicit `null` on
  // clear; `formValuesToIssuePatch` must let it through so the round-trip
  // reaches `IssueService.update_issue`'s `_UNSET`-vs-`None` distinction.
  it("clears due_date to null in the PATCH when the date field is emptied", async () => {
    vi.mocked(attributeDefinitionsApi.getWorkspace).mockResolvedValue({
      item_type: "Issue",
      preset: "standard",
      is_customized: false,
      version: 1,
      attributes: [TITLE_ATTRIBUTE, DUE_DATE_ATTRIBUTE],
    });
    vi.mocked(issuesApi.update).mockResolvedValue(ISSUE);
    render(
      <IssueArtifactForm issue={ISSUE} onSaved={vi.fn()} onDeleted={vi.fn()} />
    );
    const dateField = await screen.findByTestId("artifact-field-due_date");
    fireEvent.change(dateField, { target: { value: "" } });

    await userEvent.click(screen.getByTestId("artifact-form-save"));
    await waitFor(() => expect(issuesApi.update).toHaveBeenCalled());
    const [, patch] = vi.mocked(issuesApi.update).mock.calls[0];
    expect(patch).toHaveProperty("due_date", null);
  });
});
