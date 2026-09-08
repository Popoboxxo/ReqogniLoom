import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { resolveLocaleKey } from "./i18n-test-helpers";
import { assertNoProtectedPatchFields } from "./protected-patch-fields";

// DEVIATION from the plan brief (same class already documented in
// RiskArtifactForm.test.tsx / IssueArtifactForm.test.tsx, Tasks 19/20): the
// brief's test never mocks react-i18next. The shared i18next singleton is
// never initialised in unit tests, so the literal-brief version crashes on
// `i18n.language.startsWith(...)` inside FieldShell's `helpText`
// (`i18n.language` is `undefined`) the moment `ArtifactForm` actually renders
// a field — verified live, both `render()`-based tests failed with that exact
// TypeError before this mock was added.
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

import { adrsApi } from "../api/adrs";
import {
  AdrArtifactForm,
  adrToFormValues,
  formValuesToAdrPatch,
} from "../components/AdrEditors/AdrArtifactForm";
import { attributeDefinitionsApi } from "../api/attribute-definitions";

vi.mock("../api/adrs", () => ({
  adrsApi: { update: vi.fn(), delete: vi.fn(), supersede: vi.fn() },
}));
vi.mock("../api/attribute-definitions", () => ({
  attributeDefinitionsApi: { getWorkspace: vi.fn() },
}));
vi.mock("../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "ws-1", preset: "standard" } }),
}));

const ADR = {
  id: "a-1",
  workspace_id: "ws-1",
  title: "Use Postgres",
  description: "d",
  context: "c",
  consequences: "q",
  decision: "we use it",
  version: 1,
} as never;

// Standing runbook note (since Task 19, binding for every rollout wave): a
// REALISTIC, full GET-shaped payload — every field `AdrSerializer` actually
// declares (backend/rest_api/serializers.py::AdrSerializer), not the minimal
// hand-built `ADR` fixture above. The minimal fixture is exactly what let
// Risk's `uid` leak into the PATCH undetected in Task 19: it never had a
// `uid`/`status`/etc. key to leak in the first place.
const FULL_ADR_GET_PAYLOAD = {
  id: "a-1",
  workspace_id: "ws-1",
  title: "Use Postgres",
  description: "d",
  context: "c",
  decision: "we use it",
  consequences: "q",
  uid: "ADR-0001",
  status: "Draft",
  version: 1,
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

const DECISION_RECORD_WIDGET_ATTRIBUTE = {
  name: "decision_record", kind: "core", type: "widget", widget_key: "markdown_tab_group",
  fields: ["description", "context", "consequences"], options: [], required: false,
  visible: true, locked: false, editable: true, section: "general", order: 10,
  label: { de: "Entscheidung", en: "Decision" }, help_text: { de: "", en: "" },
  default: null, validation: {}, ai_elicit: false, export: true, audience: "basic",
} as never;

// Not `as never` itself (unlike its siblings) — spreading a `never`-typed
// object below would fail with TS2698 ("Spread types may only be created
// from object types"). Only the three concrete variants derived from it are
// cast, matching every other attribute fixture in this file.
const TEXTAREA_ATTRIBUTE_BASE = {
  kind: "core", type: "textarea", widget_key: null, fields: [],
  options: [], required: false, visible: true, locked: false, editable: true,
  section: "general", help_text: { de: "", en: "" }, default: null,
  validation: {}, ai_elicit: false, export: true, audience: "basic",
};

const DESCRIPTION_ATTRIBUTE = {
  ...TEXTAREA_ATTRIBUTE_BASE,
  name: "description", order: 3, label: { de: "Beschreibung", en: "Description" },
} as never;

const CONTEXT_ATTRIBUTE = {
  ...TEXTAREA_ATTRIBUTE_BASE,
  name: "context", order: 4, label: { de: "Kontext", en: "Context" },
} as never;

const CONSEQUENCES_ATTRIBUTE = {
  ...TEXTAREA_ATTRIBUTE_BASE,
  name: "consequences", order: 5, label: { de: "Konsequenzen", en: "Consequences" },
} as never;

// `Adr.decision` (backend #373) is a fourth markdown column the deleted
// AdrForm never bound to any editor at all — not part of the tab group, so it
// stays an ordinary textarea attribute here too.
const DECISION_ATTRIBUTE = {
  ...TEXTAREA_ATTRIBUTE_BASE,
  name: "decision", order: 6, label: { de: "Entscheidung (Text)", en: "Decision (text)" },
} as never;

describe("AdrArtifactForm", () => {
  beforeEach(() => {
    vi.mocked(attributeDefinitionsApi.getWorkspace).mockResolvedValue({
      item_type: "Adr",
      preset: "standard",
      is_customized: false,
      version: 1,
      attributes: [
        TITLE_ATTRIBUTE,
        DECISION_RECORD_WIDGET_ATTRIBUTE,
        DESCRIPTION_ATTRIBUTE,
        CONTEXT_ATTRIBUTE,
        CONSEQUENCES_ATTRIBUTE,
        DECISION_ATTRIBUTE,
      ],
    });
    vi.mocked(adrsApi.update).mockReset();
    vi.mocked(adrsApi.delete).mockReset();
  });

  it("maps an Adr onto form values", () => {
    const values = adrToFormValues(ADR);
    expect(values.context).toBe("c");
    expect(values.custom_fields).toEqual({});
  });

  it("keeps decision out of the widget and out of the read-only set", () => {
    const patch = formValuesToAdrPatch(adrToFormValues(ADR));
    expect(patch.decision).toBe("we use it");
    expect(patch).not.toHaveProperty("version");
  });

  // Standing runbook note (since Task 19, binding for every rollout wave):
  // rebuilds the actual patch the component emits (adrToFormValues -> edit ->
  // formValuesToAdrPatch) from a full, realistic GET-shaped payload and
  // asserts zero PATCH-protected keys survive.
  it("never leaks a PATCH-protected field, from a full realistic GET payload", () => {
    const values = adrToFormValues(FULL_ADR_GET_PAYLOAD);
    const edited = { ...values, title: "Use Postgres (updated)" };
    const patch = formValuesToAdrPatch(edited);
    assertNoProtectedPatchFields(patch);
    expect(patch.title).toBe("Use Postgres (updated)");
  });

  it("renders the three bound markdown fields inside the tab group only", async () => {
    render(<AdrArtifactForm adr={ADR} onSaved={vi.fn()} onDeleted={vi.fn()} />);
    expect(
      await screen.findByTestId("artifact-widget-decision_record")
    ).toBeInTheDocument();
    expect(screen.queryByTestId("artifact-field-description")).not.toBeInTheDocument();
    expect(screen.queryByTestId("artifact-field-context")).not.toBeInTheDocument();
    expect(screen.queryByTestId("artifact-field-consequences")).not.toBeInTheDocument();
    // decision is NOT bound to the widget and must still be editable on its own.
    expect(screen.getByTestId("artifact-field-decision")).toBeInTheDocument();
  });

  it("saves an edit to the decision field (outside the widget) through adrsApi.update", async () => {
    vi.mocked(adrsApi.update).mockResolvedValue(ADR);
    const onSaved = vi.fn();
    render(<AdrArtifactForm adr={ADR} onSaved={onSaved} onDeleted={vi.fn()} />);
    await userEvent.type(await screen.findByTestId("artifact-field-decision"), "!");
    await userEvent.click(screen.getByTestId("artifact-form-save"));
    await waitFor(() => expect(adrsApi.update).toHaveBeenCalled());
    expect(onSaved).toHaveBeenCalled();
    const [, patch] = vi.mocked(adrsApi.update).mock.calls[0];
    expect(patch).toMatchObject({ decision: "we use it!" });
  });

  it("saves through adrsApi.update", async () => {
    vi.mocked(adrsApi.update).mockResolvedValue(ADR);
    const onSaved = vi.fn();
    render(<AdrArtifactForm adr={ADR} onSaved={onSaved} onDeleted={vi.fn()} />);
    await userEvent.click(await screen.findByTestId("artifact-form-save"));
    await waitFor(() => expect(adrsApi.update).toHaveBeenCalled());
    expect(onSaved).toHaveBeenCalled();
  });

  it("deletes through the shared confirm dialog", async () => {
    vi.mocked(adrsApi.delete).mockResolvedValue(undefined as never);
    const onDeleted = vi.fn();
    render(<AdrArtifactForm adr={ADR} onSaved={vi.fn()} onDeleted={onDeleted} />);
    await userEvent.click(await screen.findByTestId("artifact-form-delete"));
    await userEvent.click(screen.getByTestId("artifact-form-delete-confirm"));
    await waitFor(() => expect(adrsApi.delete).toHaveBeenCalledWith("a-1"));
    expect(onDeleted).toHaveBeenCalled();
  });
});
