import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { resolveLocaleKey } from "./i18n-test-helpers";
import { assertNoProtectedPatchFields } from "./protected-patch-fields";

// DEVIATION from the plan brief (same class as RiskArtifactForm.test.tsx /
// IssueArtifactForm.test.tsx): the shared i18next singleton is never
// initialised in unit tests, so the un-mocked version crashes inside
// FieldShell's `helpText` (`i18n.language` is `undefined`) the moment
// ArtifactForm actually renders a field.
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

import { architectureApi } from "../api/architecture";
import { attributeDefinitionsApi } from "../api/attribute-definitions";
import {
  ArchitectureArtifactForm,
  architectureToFormValues,
  formValuesToArchitecturePatch,
} from "../components/ArchitectureEditors/ArchitectureArtifactForm";

vi.mock("../api/architecture", () => ({
  architectureApi: { update: vi.fn(), delete: vi.fn() },
}));
vi.mock("../api/attribute-definitions", () => ({
  attributeDefinitionsApi: { getWorkspace: vi.fn() },
}));
vi.mock("../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "ws-1", preset: "standard" } }),
}));

// Task 24 live-verification finding: the real ArchitectureElement field is
// `parent_id` (DRF's own convention for a FK's raw id — same class as Task
// 19's `Risk.owner_user_id`), NOT `parent`. Verified live against
// `introspect_core_attributes("ArchitectureElement", "standard")` and a real
// GET/PATCH round-trip after adding the `parent` -> `parent_id`
// `WIDGET_FIELD_ALIASES` entry in `bootstrap_attribute_definitions.py`.
const ELEMENT = {
  id: "e-1",
  workspace_id: "ws-1",
  artifact_id: "art-1",
  title: "Gateway",
  description: "d",
  element_type: "block",
  parent_id: "e-0",
  level: 1,
  role: "component",
  asil_level: "B",
  make_or_buy: "Make",
  uid: "ARCH-0001",
  suspect: false,
  custom_fields: {},
  version: 4,
} as never;

// A REALISTIC, full GET-shaped payload — every field
// `ArchitectureElementSerializer`/`_arch_to_dict` actually returns,
// live-verified against a real bootstrapped ArchitectureElement (Task
// 24 implementer report). Standing runbook note since Task 19: a
// hand-built minimal fixture is exactly what let the original Risk `uid`
// bug ship undetected.
const FULL_ARCHITECTURE_GET_PAYLOAD = {
  id: "e-1",
  workspace_id: "ws-1",
  artifact_id: "art-1",
  title: "Gateway",
  description: "d",
  element_type: "block",
  parent_id: "e-0",
  level: 1,
  role: "component",
  asil_level: "B",
  make_or_buy: "Make",
  uid: "ARCH-0001",
  suspect: false,
  custom_fields: {},
  version: 4,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-02T00:00:00Z",
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

describe("ArchitectureArtifactForm", () => {
  beforeEach(() => {
    vi.mocked(attributeDefinitionsApi.getWorkspace).mockResolvedValue({
      item_type: "ArchitectureElement",
      preset: "standard",
      is_customized: false,
      version: 1,
      attributes: [
        attr({ name: "title", required: true }),
        attr({ name: "parent_id", type: "reference", order: 2 }),
      ],
    } as never);
    vi.mocked(architectureApi.update).mockReset();
    vi.mocked(architectureApi.delete).mockReset();
  });

  it("maps an ArchitectureElement onto form values", () => {
    const values = architectureToFormValues(ELEMENT);
    expect(values.element_type).toBe("block");
    expect(values.parent_id).toBe("e-0");
    expect(values.custom_fields).toEqual({});
  });

  it("strips server-owned fields from the patch", () => {
    const patch = formValuesToArchitecturePatch(architectureToFormValues(ELEMENT));
    expect(patch).not.toHaveProperty("version");
    expect(patch).not.toHaveProperty("workspace_id");
    expect(patch).not.toHaveProperty("level");
    expect(patch).not.toHaveProperty("role");
    expect(patch.title).toBe("Gateway");
  });

  // Standing runbook note (since Task 19, binding for every rollout wave):
  // rebuilds the actual patch the component emits from a full, realistic
  // GET-shaped payload and asserts zero PATCH-protected keys survive.
  it("never leaks a PATCH-protected field, from a full realistic GET payload", () => {
    const values = architectureToFormValues(FULL_ARCHITECTURE_GET_PAYLOAD);
    const edited = { ...values, title: "Gateway (updated)" };
    const patch = formValuesToArchitecturePatch(edited);
    assertNoProtectedPatchFields(patch);
    expect(patch.title).toBe("Gateway (updated)");
  });

  it("renders the containment parent as a reference picker", async () => {
    render(
      <ArchitectureArtifactForm
        element={ELEMENT}
        onSaved={vi.fn()}
        onDeleted={vi.fn()}
      />
    );
    expect(await screen.findByTestId("artifact-field-parent_id")).toBeInTheDocument();
  });

  it("reports dirty state so the parent can warn before navigating away", async () => {
    const onDirtyChange = vi.fn();
    render(
      <ArchitectureArtifactForm
        element={ELEMENT}
        onSaved={vi.fn()}
        onDeleted={vi.fn()}
        onDirtyChange={onDirtyChange}
      />
    );
    await userEvent.type(await screen.findByTestId("artifact-field-title"), "!");
    await waitFor(() => expect(onDirtyChange).toHaveBeenCalledWith(true));
  });

  it("saves through architectureApi.update", async () => {
    vi.mocked(architectureApi.update).mockResolvedValue(ELEMENT);
    const onSaved = vi.fn();
    render(
      <ArchitectureArtifactForm
        element={ELEMENT}
        onSaved={onSaved}
        onDeleted={vi.fn()}
      />
    );
    await userEvent.click(await screen.findByTestId("artifact-form-save"));
    await waitFor(() => expect(architectureApi.update).toHaveBeenCalled());
    expect(onSaved).toHaveBeenCalled();
  });

  it("deletes through the shared confirm dialog", async () => {
    vi.mocked(architectureApi.delete).mockResolvedValue(undefined as never);
    const onDeleted = vi.fn();
    render(
      <ArchitectureArtifactForm element={ELEMENT} onSaved={vi.fn()} onDeleted={onDeleted} />
    );
    await userEvent.click(await screen.findByTestId("artifact-form-delete"));
    await userEvent.click(screen.getByTestId("artifact-form-delete-confirm"));
    await waitFor(() => expect(architectureApi.delete).toHaveBeenCalledWith("e-1"));
    expect(onDeleted).toHaveBeenCalled();
  });
});
