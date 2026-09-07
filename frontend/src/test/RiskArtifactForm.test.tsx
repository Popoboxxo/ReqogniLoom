import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { resolveLocaleKey } from "./i18n-test-helpers";
import { assertNoProtectedPatchFields } from "./protected-patch-fields";

// DEVIATION from the plan brief (same class already documented in
// ArtifactForm.test.tsx / ArtifactFormFields.test.tsx / ArtifactFormWidgets.test.tsx):
// the brief's test never mocks react-i18next. The shared i18next singleton is
// never initialised in unit tests, so the literal-brief version crashes on
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

import { risksApi } from "../api/risks";
import {
  RiskArtifactForm,
  formValuesToRiskPatch,
  riskToFormValues,
} from "../components/RiskEditors/RiskArtifactForm";
import { attributeDefinitionsApi } from "../api/attribute-definitions";

vi.mock("../api/risks", () => ({
  risksApi: { update: vi.fn(), delete: vi.fn() },
}));
vi.mock("../api/attribute-definitions", () => ({
  attributeDefinitionsApi: { getWorkspace: vi.fn() },
}));
vi.mock("../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "ws-1", preset: "standard" } }),
}));

const RISK = {
  id: "r-1",
  workspace_id: "ws-1",
  title: "Outage",
  description: "d",
  category: "technical",
  probability: "high",
  impact: "high",
  detection: 4,
  mitigation_strategy: "m",
  custom_fields: { sap_id: "S-1" },
  version: 3,
} as never;

// C-1 fix round: a REALISTIC, full GET-shaped payload — every field
// RiskSerializer actually returns, not the minimal hand-built `RISK` fixture
// above. The minimal fixture is exactly what let `uid` leak into the PATCH
// undetected: it never had a `uid`/`owner_user_display`/`rpn`/`status`/etc.
// key to leak in the first place.
const FULL_RISK_GET_PAYLOAD = {
  id: "r-1",
  workspace_id: "ws-1",
  artifact_id: "art-1",
  title: "Outage",
  description: "d",
  probability: "high",
  impact: "high",
  risk_score: 12,
  detection: 4,
  rpn: 48,
  severity: "high",
  category: "technical",
  owner: "legacy free text",
  owner_user_id: "u-1",
  owner_user_display: "Jane Doe",
  mitigation_strategy: "m",
  status: "open",
  version: 3,
  uid: "RISK-0001",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-02T00:00:00Z",
  custom_fields: { sap_id: "S-1" },
} as never;

describe("RiskArtifactForm", () => {
  beforeEach(() => {
    vi.mocked(attributeDefinitionsApi.getWorkspace).mockResolvedValue({
      item_type: "Risk",
      preset: "standard",
      is_customized: false,
      version: 1,
      attributes: [
        {
          name: "title", kind: "core", type: "text", widget_key: null, fields: [],
          options: [], required: true, visible: true, locked: false, editable: true,
          section: "general", order: 1, label: { de: "Titel", en: "Title" },
          help_text: { de: "", en: "" }, default: null, validation: {},
          ai_elicit: true, export: true, audience: "basic",
        },
      ],
    });
    vi.mocked(risksApi.update).mockReset();
    vi.mocked(risksApi.delete).mockReset();
  });

  it("maps a Risk onto form values, nesting extended values", () => {
    const values = riskToFormValues(RISK);
    expect(values.title).toBe("Outage");
    expect(values.detection).toBe(4);
    expect(values.custom_fields).toEqual({ sap_id: "S-1" });
  });

  it("does not send read-only identity fields in the patch", () => {
    const patch = formValuesToRiskPatch(riskToFormValues(RISK));
    expect(patch).not.toHaveProperty("id");
    expect(patch).not.toHaveProperty("workspace_id");
    expect(patch).not.toHaveProperty("version");
    expect(patch.title).toBe("Outage");
  });

  // C-1 regression test: rebuilds the actual patch the component emits
  // (riskToFormValues -> edit -> formValuesToRiskPatch) from a full,
  // realistic GET-shaped payload and asserts zero PATCH-protected keys
  // survive. This is the test class whose absence let `uid` ship as a
  // 100%-failure-rate bug: the sibling test above only ever exercised the
  // minimal `RISK` fixture, which has no `uid` key to leak.
  it("never leaks a PATCH-protected field, from a full realistic GET payload", () => {
    const values = riskToFormValues(FULL_RISK_GET_PAYLOAD);
    // simulate an edit, same as the "saves through risksApi.update" test below
    const edited = { ...values, title: "Outage (updated)" };
    const patch = formValuesToRiskPatch(edited);
    assertNoProtectedPatchFields(patch);
    expect(patch.title).toBe("Outage (updated)");
  });

  it("saves through risksApi.update and reports success upward", async () => {
    vi.mocked(risksApi.update).mockResolvedValue(RISK);
    const onSaved = vi.fn();
    render(
      <RiskArtifactForm risk={RISK} onSaved={onSaved} onDeleted={vi.fn()} />
    );
    await userEvent.type(await screen.findByTestId("artifact-field-title"), "!");
    await userEvent.click(screen.getByTestId("artifact-form-save"));
    await waitFor(() => expect(risksApi.update).toHaveBeenCalled());
    expect(onSaved).toHaveBeenCalled();
  });

  it("deletes through the shared confirm dialog", async () => {
    vi.mocked(risksApi.delete).mockResolvedValue(undefined as never);
    const onDeleted = vi.fn();
    render(
      <RiskArtifactForm risk={RISK} onSaved={vi.fn()} onDeleted={onDeleted} />
    );
    await userEvent.click(await screen.findByTestId("artifact-form-delete"));
    await userEvent.click(screen.getByTestId("artifact-form-delete-confirm"));
    await waitFor(() => expect(risksApi.delete).toHaveBeenCalledWith("r-1"));
    expect(onDeleted).toHaveBeenCalled();
  });
});
