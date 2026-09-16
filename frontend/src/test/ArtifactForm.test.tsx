import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it, vi, beforeEach } from "vitest";

import { resolveLocaleKey } from "./i18n-test-helpers";

// DEVIATION from the plan brief (same class as ArtifactFormFields.test.tsx and
// ArtifactFormWidgets.test.tsx): the brief's Task 18 test never mocks
// react-i18next, but the shared i18next singleton is not initialised in unit
// tests — verified live: without this mock the save button renders the literal
// key "actions.save" and every `defaultValue` fallback is ignored.
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

vi.mock("../api/attribute-definitions", () => ({
  attributeDefinitionsApi: { getWorkspace: vi.fn() },
}));

vi.mock("../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "ws-1", preset: "standard" } }),
}));

// `api/users` exports exactly one runtime binding (`usersApi`); `ManagedUser`
// and `CreateUserPayload` are types and erase at compile time, so this factory
// is complete and cannot trip the "mock is missing an export" failure.
vi.mock("../api/users", () => ({
  usersApi: { list: vi.fn() },
}));

// Attribut v3 WS2 (#936): the `actor` field renderer reads the workspace-member
// directory through `api/actors`.
vi.mock("../api/actors", () => ({
  actorsApi: { list: vi.fn() },
}));

vi.mock("../components/WorkflowStatusEditor", () => ({
  WorkflowStatusEditor: () => <div data-testid="workflow-status-editor" />,
}));

import { attributeDefinitionsApi } from "../api/attribute-definitions";
import { usersApi } from "../api/users";
import { actorsApi } from "../api/actors";
import {
  ArtifactForm,
  fieldErrorsFromException,
  groupIntoSections,
  parseFieldErrors,
  stripNonEditableValues,
} from "../components/shared/ArtifactForm";
import type { AttributeSpec, LayoutToken, SectionSpec } from "../api/attribute-definitions";

function spec(over: Partial<AttributeSpec>): AttributeSpec {
  return {
    name: "title",
    kind: "core",
    type: "text",
    widget_key: null,
    fields: [],
    options: [],
    required: false,
    visible: true,
    locked: false,
    editable: true,
    section: "general",
    order: 0,
    label: { de: "Titel", en: "Title" },
    help_text: { de: "", en: "" },
    default: null,
    validation: {},
    ai_elicit: false,
    export: false,
    audience: "basic",
    ...over,
  };
}

function section(over: Partial<SectionSpec>): SectionSpec {
  return { name: "general", order: 0, visible: true, layout: "full", ...over };
}

function mockDefinition(
  attributes: AttributeSpec[],
  sections: SectionSpec[] = [],
  sectionFlow?: LayoutToken[]
): void {
  vi.mocked(attributeDefinitionsApi.getWorkspace).mockResolvedValue({
    item_type: "Risk",
    preset: "standard",
    is_customized: false,
    version: 1,
    attributes,
    origins: {},
    sections,
    ...(sectionFlow !== undefined ? { section_flow: sectionFlow } : {}),
  });
}

/**
 * The `risk_matrix` widget attribute exactly as the live bootstrap emits it —
 * dumped from `introspect_core_attributes("Risk", "standard")` against the
 * running backend, not hand-written. Its siblings are the three real core
 * attributes the widget binds.
 */
const REAL_RISK_WIDGET_ATTRS: AttributeSpec[] = [
  spec({
    name: "risk_matrix",
    type: "widget",
    widget_key: "risk_matrix_rpz",
    fields: ["probability", "impact", "detection"],
    section: "classification",
    order: 10,
    label: { de: "Risikomatrix", en: "Risk matrix" },
  }),
  spec({ name: "probability", type: "enum", section: "classification", order: 4 }),
  spec({ name: "impact", type: "enum", section: "classification", order: 5 }),
  spec({ name: "detection", type: "number", section: "classification", order: 8 }),
];

describe("parseFieldErrors", () => {
  it("reverses the backend's joined message format", () => {
    expect(parseFieldErrors("title: is required; uid: does not match")).toEqual({
      title: ["is required"],
      uid: ["does not match"],
    });
  });

  it("splits multiple messages for one attribute", () => {
    expect(parseFieldErrors("effort: must be a number, must be >= 1")).toEqual({
      effort: ["must be a number", "must be >= 1"],
    });
  });

  it("returns nothing for a message that does not match the format", () => {
    expect(parseFieldErrors("Internal server error")).toEqual({});
  });
});

describe("fieldErrorsFromException", () => {
  it("prefers the structured error.details envelope over the flat message", () => {
    // `apiClient` throws the parsed body itself — no axios `.response.data`.
    const thrown = {
      error: {
        code: "VALIDATION_ERROR",
        message: "title: is required; effort: must be >= 1",
        details: [
          { field: "title", errors: ["is required"] },
          { field: "effort", errors: ["must be >= 1"] },
        ],
      },
    };
    expect(fieldErrorsFromException(thrown, "is required")).toEqual({
      title: ["is required"],
      effort: ["must be >= 1"],
    });
  });

  it("falls back to parsing the message when no details are present", () => {
    expect(
      fieldErrorsFromException(new Error("x"), "title: is required")
    ).toEqual({ title: ["is required"] });
  });
});

describe("groupIntoSections", () => {
  it("keeps the definition's section and order", () => {
    const sections = groupIntoSections([
      spec({ name: "b", section: "classification", order: 1 }),
      spec({ name: "a", section: "general", order: 2 }),
      spec({ name: "c", section: "general", order: 1 }),
    ]);
    expect(sections.map((s) => s.name)).toEqual(["classification", "general"]);
    expect(sections[1].attributes.map((a) => a.name)).toEqual(["c", "a"]);
  });

  it("marks a section expert only when every attribute is expert", () => {
    const [mixed] = groupIntoSections([
      spec({ name: "a", audience: "expert" }),
      spec({ name: "b", audience: "basic" }),
    ]);
    expect(mixed.audience).toBe("basic");
    const [all] = groupIntoSections([
      spec({ name: "a", section: "x", audience: "expert" }),
      spec({ name: "b", section: "x", audience: "expert" }),
    ]);
    expect(all.audience).toBe("expert");
  });
});

// Issue #886: `editable: false` is a payload contract, not a rendering hint.
// The backend rejects an UPDATE carrying such a value ("is not editable and
// must not be sent in an update payload", field_validation.py) — the disabled
// control alone is not enough, the field must be OMITTED. Create is
// deliberately exempt (same backend docstring): a `required` + `editable: false`
// attribute would otherwise be unsatisfiable by any caller.
describe("stripNonEditableValues", () => {
  const attrs: AttributeSpec[] = [
    spec({ name: "title" }),
    spec({ name: "frozen", editable: false }),
    spec({ name: "frozen_ext", kind: "extended", editable: false }),
    spec({ name: "auto", editable: "system" }),
  ];

  it("omits editable:false (core and extended) and system on update", () => {
    const out = stripNonEditableValues(
      {
        title: "T",
        frozen: "x",
        auto: "id-1",
        custom_fields: { frozen_ext: "y", kept: "z" },
      },
      attrs,
      "update"
    );
    expect(out).toEqual({ title: "T", custom_fields: { kept: "z" } });
  });

  it("keeps editable:false on create but still omits system", () => {
    const out = stripNonEditableValues(
      { title: "T", frozen: "x", auto: "id-1", custom_fields: { frozen_ext: "y" } },
      attrs,
      "create"
    );
    expect(out).toEqual({
      title: "T",
      frozen: "x",
      custom_fields: { frozen_ext: "y" },
    });
  });

  it("returns the same object when nothing is stripped", () => {
    const values = { title: "T" };
    expect(
      stripNonEditableValues(values, [spec({ name: "title" })], "update")
    ).toBe(values);
  });
});

describe("ArtifactForm non-editable payload contract (#886)", () => {
  beforeEach(() => {
    vi.mocked(attributeDefinitionsApi.getWorkspace).mockReset();
    vi.mocked(usersApi.list).mockReset();
    vi.mocked(usersApi.list).mockResolvedValue([]);
  });

  it("omits an editable:false attribute from the update payload", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    mockDefinition([spec({ name: "title" }), spec({ name: "frozen", editable: false })]);
    render(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        initialValues={{ title: "T", frozen: "old" }}
        onSave={onSave}
      />
    );
    await userEvent.click(await screen.findByTestId("artifact-form-save"));
    await waitFor(() => expect(onSave).toHaveBeenCalled());
    const payload = onSave.mock.calls[0][0] as Record<string, unknown>;
    expect(payload).not.toHaveProperty("frozen");
    expect(payload.title).toBe("T");
  });

  it("keeps an editable:false attribute in the create payload", async () => {
    // Create is exempt from the update-only rejection: dropping the value
    // would make a `required` + `editable:false` attribute unsatisfiable.
    const onSave = vi.fn().mockResolvedValue(undefined);
    mockDefinition([
      spec({ name: "title" }),
      spec({ name: "frozen", required: true, editable: false }),
    ]);
    render(
      <ArtifactForm
        itemType="Risk"
        artifactId={null}
        initialValues={{ title: "T", frozen: "initial" }}
        onSave={onSave}
      />
    );
    await userEvent.click(await screen.findByTestId("artifact-form-save"));
    await waitFor(() => expect(onSave).toHaveBeenCalled());
    expect(onSave.mock.calls[0][0]).toMatchObject({ frozen: "initial" });
  });

  it("omits an editable:false extended attribute from custom_fields on update", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    mockDefinition([
      spec({ name: "title" }),
      spec({ name: "frozen_ext", kind: "extended", editable: false, section: "custom" }),
    ]);
    render(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        initialValues={{
          title: "T",
          custom_fields: { frozen_ext: "locked", kept: "yes" },
        }}
        onSave={onSave}
      />
    );
    await userEvent.click(await screen.findByTestId("artifact-form-save"));
    await waitFor(() => expect(onSave).toHaveBeenCalled());
    expect(onSave.mock.calls[0][0].custom_fields).toEqual({ kept: "yes" });
  });
});

describe("ArtifactForm", () => {
  beforeEach(() => {
    vi.mocked(attributeDefinitionsApi.getWorkspace).mockReset();
    vi.mocked(usersApi.list).mockReset();
    vi.mocked(usersApi.list).mockResolvedValue([]);
  });

  it("renders every visible attribute of the definition", async () => {
    mockDefinition([spec({ name: "title" }), spec({ name: "description", type: "textarea" })]);
    render(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        initialValues={{ title: "T", description: "D" }}
        onSave={vi.fn()}
      />
    );
    expect(await screen.findByTestId("artifact-field-title")).toHaveValue("T");
    expect(screen.getByTestId("artifact-field-description")).toHaveValue("D");
  });

  it("does not render an invisible attribute", async () => {
    mockDefinition([spec({ name: "title" }), spec({ name: "hidden", visible: false })]);
    render(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        initialValues={{ title: "T" }}
        onSave={vi.fn()}
      />
    );
    await screen.findByTestId("artifact-field-title");
    expect(screen.queryByTestId("artifact-field-hidden")).not.toBeInTheDocument();
  });

  it("hides a whole section (and its attributes) when the section is invisible, regardless of each attribute's own visible flag", async () => {
    mockDefinition(
      [
        spec({ name: "title", section: "general" }),
        // Individually visible=true -- the section-level flag must still win
        // (spec section 4.4's AND-condition).
        spec({ name: "note", section: "hidden_section", visible: true }),
      ],
      [
        section({ name: "general", order: 0 }),
        section({ name: "hidden_section", order: 1, visible: false }),
      ]
    );
    render(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        initialValues={{ title: "T" }}
        onSave={vi.fn()}
      />
    );
    await screen.findByTestId("artifact-field-title");
    expect(screen.queryByTestId("artifact-field-note")).not.toBeInTheDocument();
    expect(screen.queryByTestId("artifact-section-hidden_section")).not.toBeInTheDocument();
  });

  it("defaults a section not listed in definition.sections to visible", async () => {
    mockDefinition([spec({ name: "title", section: "general" })], []);
    render(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        initialValues={{ title: "T" }}
        onSave={vi.fn()}
      />
    );
    expect(await screen.findByTestId("artifact-field-title")).toBeInTheDocument();
  });

  it("applies the half layout to two consecutive half sections and full to a plain one", async () => {
    mockDefinition(
      [
        spec({ name: "a", section: "left", order: 0 }),
        spec({ name: "b", section: "right", order: 0 }),
        spec({ name: "c", section: "wide", order: 0 }),
      ],
      [
        section({ name: "left", order: 0, layout: "half" }),
        section({ name: "right", order: 1, layout: "half" }),
        section({ name: "wide", order: 2, layout: "full" }),
      ]
    );
    render(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        initialValues={{}}
        onSave={vi.fn()}
      />
    );
    await screen.findByTestId("artifact-field-a");
    expect(screen.getByTestId("artifact-section-left")).toHaveAttribute("data-layout", "half");
    expect(screen.getByTestId("artifact-section-right")).toHaveAttribute("data-layout", "half");
    expect(screen.getByTestId("artifact-section-wide")).toHaveAttribute("data-layout", "full");
  });

  it("renders the workflow status editor instead of a control for editable=workflow", async () => {
    mockDefinition([
      spec({ name: "status", type: "enum", editable: "workflow", locked: true }),
      spec({ name: "title" }),
    ]);
    render(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        initialValues={{ title: "T", status: "draft" }}
        onSave={vi.fn()}
        workflowArtifactType="risk"
      />
    );
    expect(await screen.findByTestId("workflow-status-editor")).toBeInTheDocument();
    expect(screen.queryByTestId("artifact-field-status")).not.toBeInTheDocument();
  });

  it("does not render a field a widget already draws", async () => {
    mockDefinition([...REAL_RISK_WIDGET_ATTRS, spec({ name: "title" })]);
    render(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        initialValues={{ title: "T", probability: "low", impact: "low", detection: 3 }}
        onSave={vi.fn()}
      />
    );
    expect(await screen.findByTestId("artifact-widget-risk_matrix")).toBeInTheDocument();
    expect(screen.queryByTestId("artifact-field-probability")).not.toBeInTheDocument();
    expect(screen.queryByTestId("artifact-field-impact")).not.toBeInTheDocument();
    expect(screen.queryByTestId("artifact-field-detection")).not.toBeInTheDocument();
  });

  it("collapses an all-expert section by default", async () => {
    mockDefinition([
      spec({ name: "title", section: "general" }),
      spec({ name: "deep", section: "advanced", audience: "expert" }),
    ]);
    render(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        initialValues={{ title: "T", deep: "D" }}
        onSave={vi.fn()}
      />
    );
    await screen.findByTestId("artifact-field-title");
    expect(screen.queryByTestId("artifact-field-deep")).not.toBeInTheDocument();
    await userEvent.click(screen.getByTestId("artifact-section-toggle-advanced"));
    expect(screen.getByTestId("artifact-field-deep")).toBeInTheDocument();
  });

  it("routes extended values through custom_fields on save", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    mockDefinition([
      spec({ name: "title" }),
      spec({ name: "sap_id", kind: "extended", section: "custom" }),
    ]);
    render(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        initialValues={{ title: "T", custom_fields: { sap_id: "S-1" } }}
        onSave={onSave}
      />
    );
    await userEvent.clear(await screen.findByTestId("artifact-field-sap_id"));
    await userEvent.type(screen.getByTestId("artifact-field-sap_id"), "S-2");
    await userEvent.click(screen.getByTestId("artifact-form-save"));
    await waitFor(() =>
      expect(onSave).toHaveBeenCalledWith(
        expect.objectContaining({ custom_fields: { sap_id: "S-2" } })
      )
    );
  });

  it("reports dirty state to the parent and clears it after a save", async () => {
    const onDirtyChange = vi.fn();
    mockDefinition([spec({ name: "title" })]);
    render(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        initialValues={{ title: "T" }}
        onSave={vi.fn().mockResolvedValue(undefined)}
        onDirtyChange={onDirtyChange}
      />
    );
    await userEvent.type(await screen.findByTestId("artifact-field-title"), "X");
    await waitFor(() => expect(onDirtyChange).toHaveBeenCalledWith(true));
    await userEvent.click(screen.getByTestId("artifact-form-save"));
    await waitFor(() => expect(onDirtyChange).toHaveBeenLastCalledWith(false));
  });

  it("keeps in-progress edits when the parent re-renders with a fresh initialValues object", async () => {
    mockDefinition([spec({ name: "title" })]);
    const props = {
      itemType: "Risk" as const,
      artifactId: "r-1",
      onSave: vi.fn().mockResolvedValue(undefined),
    };
    const { rerender } = render(<ArtifactForm {...props} initialValues={{ title: "T" }} />);
    await userEvent.type(await screen.findByTestId("artifact-field-title"), "X");
    expect(screen.getByTestId("artifact-field-title")).toHaveValue("TX");
    // Same DATA, new object identity — exactly what an inline
    // `initialValues={{ ... }}` at a call site produces on every parent render.
    rerender(<ArtifactForm {...props} initialValues={{ title: "T" }} />);
    expect(screen.getByTestId("artifact-field-title")).toHaveValue("TX");
  });

  it("keeps in-progress edits when initialValues has the same content in a different key order", async () => {
    // I-2 fix round: a parent building initialValues via a conditional spread
    // (e.g. `{...(isNew ? {} : {status}), ...artifact}`) can produce the same
    // content in a different key order across renders. A content-signature
    // comparison (`JSON.stringify`) is insertion-order sensitive and would
    // treat this as "changed", silently wiping the user's typing.
    mockDefinition([spec({ name: "title" }), spec({ name: "status", type: "text" })]);
    const props = {
      itemType: "Risk" as const,
      artifactId: "r-1",
      onSave: vi.fn().mockResolvedValue(undefined),
    };
    const { rerender } = render(
      <ArtifactForm {...props} initialValues={{ title: "T", status: "open" }} />
    );
    await userEvent.type(await screen.findByTestId("artifact-field-title"), "X");
    expect(screen.getByTestId("artifact-field-title")).toHaveValue("TX");
    // Same content, keys reordered.
    rerender(
      <ArtifactForm {...props} initialValues={{ status: "open", title: "T" }} />
    );
    expect(screen.getByTestId("artifact-field-title")).toHaveValue("TX");
  });

  it("resets form state when the parent switches to a genuinely different artifact", async () => {
    // The "legitimate reset" case the original fix must not break: switching
    // to a different artifact (the rollout waves reuse one mounted form
    // across a list selection) must still discard the previous artifact's
    // in-progress edits and load the new one's values.
    mockDefinition([spec({ name: "title" })]);
    const onSave = vi.fn().mockResolvedValue(undefined);
    const { rerender } = render(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        initialValues={{ title: "First" }}
        onSave={onSave}
      />
    );
    await userEvent.type(await screen.findByTestId("artifact-field-title"), "X");
    expect(screen.getByTestId("artifact-field-title")).toHaveValue("FirstX");
    rerender(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-2"
        initialValues={{ title: "Second" }}
        onSave={onSave}
      />
    );
    expect(await screen.findByTestId("artifact-field-title")).toHaveValue("Second");
  });

  it("attaches a server field error to its own field", async () => {
    mockDefinition([spec({ name: "title" })]);
    // The real client throws the parsed body; `extractErrorMessage` prefers
    // `details[0].errors[0]`, so the flat message alone would be "is required"
    // with the attribute name already stripped.
    const onSave = vi.fn().mockRejectedValue({
      error: {
        code: "VALIDATION_ERROR",
        message: "title: is required",
        details: [{ field: "title", errors: ["is required"] }],
      },
    });
    render(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        initialValues={{ title: "T" }}
        onSave={onSave}
      />
    );
    await userEvent.click(await screen.findByTestId("artifact-form-save"));
    await waitFor(() =>
      expect(screen.getByTestId("artifact-field-title")).toHaveAttribute(
        "aria-invalid",
        "true"
      )
    );
  });

  it("shows an unmatched error message in the form-level banner", async () => {
    mockDefinition([spec({ name: "title" })]);
    const onSave = vi.fn().mockRejectedValue({
      error: { code: "INTERNAL_SERVER_ERROR", message: "Internal server error", details: [] },
    });
    render(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        initialValues={{ title: "T" }}
        onSave={onSave}
      />
    );
    await userEvent.click(await screen.findByTestId("artifact-form-save"));
    expect(await screen.findByTestId("artifact-form-error")).toHaveTextContent(
      "Internal server error"
    );
  });

  // GitHub #677: the shared save-error banner replaced the hand-written
  // RequirementForm/TestCaseForm banners. A save that fails must be announced
  // to screen-reader users — the banner is an assertive live region, not just
  // a red paragraph that silently appears.
  it("announces a failed save through an assertive live region (#677)", async () => {
    mockDefinition([spec({ name: "title" })]);
    const onSave = vi.fn().mockRejectedValue({
      error: { code: "INTERNAL_SERVER_ERROR", message: "Internal server error", details: [] },
    });
    render(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        initialValues={{ title: "T" }}
        onSave={onSave}
      />
    );
    await userEvent.click(await screen.findByTestId("artifact-form-save"));
    const banner = await screen.findByTestId("artifact-form-error");
    expect(banner).toHaveAttribute("role", "alert");
    expect(banner).toHaveAttribute("aria-live", "assertive");
  });

  it("offers delete behind ConfirmDialog only when onDelete is supplied", async () => {
    mockDefinition([spec({ name: "title" })]);
    const onDelete = vi.fn().mockResolvedValue(undefined);
    const { rerender } = render(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        initialValues={{ title: "T" }}
        onSave={vi.fn()}
      />
    );
    await screen.findByTestId("artifact-field-title");
    expect(screen.queryByTestId("artifact-form-delete")).not.toBeInTheDocument();

    rerender(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        initialValues={{ title: "T" }}
        onSave={vi.fn()}
        onDelete={onDelete}
      />
    );
    await userEvent.click(screen.getByTestId("artifact-form-delete"));
    await userEvent.click(screen.getByTestId("artifact-form-delete-confirm"));
    await waitFor(() => expect(onDelete).toHaveBeenCalled());
  });

  it("disables every control in read mode", async () => {
    mockDefinition([spec({ name: "title" })]);
    render(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        initialValues={{ title: "T" }}
        onSave={vi.fn()}
        mode="read"
      />
    );
    expect(await screen.findByTestId("artifact-field-title")).toBeDisabled();
    expect(screen.queryByTestId("artifact-form-save")).not.toBeInTheDocument();
  });

  it("shows an error banner when the definition cannot be loaded", async () => {
    vi.mocked(attributeDefinitionsApi.getWorkspace).mockRejectedValue(new Error("boom"));
    render(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        initialValues={{ title: "T" }}
        onSave={vi.fn()}
      />
    );
    const banner = await screen.findByTestId("artifact-form-load-error");
    expect(banner).toBeInTheDocument();
    // GitHub #677: the banner appears dynamically, so it is an assertive live
    // region — a screen reader user is told the form failed to load.
    expect(banner).toHaveAttribute("role", "alert");
    expect(banner).toHaveAttribute("aria-live", "assertive");
  });
});

// F-4 (Task 25 fix round 1): `requiresChangeReason` had zero coverage in the
// shared suite — every prior assertion lived only in `RequirementArtifactForm
// .test.tsx`, which exercises the adapter, not the shared renderer's own
// gating logic (create-mode suppression, read-mode suppression, the
// cross-artifact reset, and the "reason-only edit is still dirty" fold-in).
describe("ArtifactForm requiresChangeReason", () => {
  beforeEach(() => {
    vi.mocked(attributeDefinitionsApi.getWorkspace).mockReset();
    vi.mocked(usersApi.list).mockReset();
    vi.mocked(usersApi.list).mockResolvedValue([]);
  });

  it("does not render the change-reason field in create mode", async () => {
    mockDefinition([spec({ name: "title" })]);
    render(
      <ArtifactForm
        itemType="Risk"
        artifactId={null}
        initialValues={{ title: "T" }}
        onSave={vi.fn()}
        requiresChangeReason
      />
    );
    await screen.findByTestId("artifact-field-title");
    expect(screen.queryByTestId("artifact-form-change-reason")).not.toBeInTheDocument();
  });

  it("does not render the change-reason field in read mode", async () => {
    mockDefinition([spec({ name: "title" })]);
    render(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        initialValues={{ title: "T" }}
        onSave={vi.fn()}
        requiresChangeReason
        mode="read"
      />
    );
    expect(await screen.findByTestId("artifact-field-title")).toBeDisabled();
    expect(screen.queryByTestId("artifact-form-change-reason")).not.toBeInTheDocument();
  });

  it("clears a typed change reason when the parent switches to a different artifact", async () => {
    mockDefinition([spec({ name: "title" })]);
    const { rerender } = render(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        initialValues={{ title: "First" }}
        onSave={vi.fn()}
        requiresChangeReason
      />
    );
    await userEvent.type(
      await screen.findByTestId("artifact-form-change-reason"),
      "explaining the edit"
    );
    expect(screen.getByTestId("artifact-form-change-reason")).toHaveValue(
      "explaining the edit"
    );
    rerender(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-2"
        initialValues={{ title: "Second" }}
        onSave={vi.fn()}
        requiresChangeReason
      />
    );
    await waitFor(() =>
      expect(screen.getByTestId("artifact-form-change-reason")).toHaveValue("")
    );
  });

  it("reports dirty when only the change reason was typed, no field edited", async () => {
    mockDefinition([spec({ name: "title" })]);
    const onDirtyChange = vi.fn();
    render(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        initialValues={{ title: "T" }}
        onSave={vi.fn()}
        requiresChangeReason
        onDirtyChange={onDirtyChange}
      />
    );
    await userEvent.type(
      await screen.findByTestId("artifact-form-change-reason"),
      "x"
    );
    await waitFor(() => expect(onDirtyChange).toHaveBeenCalledWith(true));
  });
});

/**
 * The backend never checks that a widget attribute's `fields` match its
 * `widget_key` (`validate_meta_only_change` ignores
 * `CORE_EDITABLE_META_PROPERTIES`), so both of these definitions are things a
 * tenant admin can actually PUT today.
 */
describe("ArtifactForm widget guard", () => {
  beforeEach(() => {
    vi.mocked(attributeDefinitionsApi.getWorkspace).mockReset();
    vi.mocked(usersApi.list).mockReset();
    vi.mocked(usersApi.list).mockResolvedValue([]);
  });

  it("degrades to a visible message for an unknown widget_key instead of crashing the form", async () => {
    mockDefinition([
      spec({ name: "title" }),
      spec({
        name: "future_thing",
        type: "widget",
        // A key this frontend build predates — reachable whenever the backend's
        // WIDGET_KEYS grows ahead of a deployed bundle.
        widget_key: "some_future_widget" as never,
        fields: ["title"],
      }),
    ]);
    render(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        initialValues={{ title: "T" }}
        onSave={vi.fn()}
      />
    );
    expect(
      await screen.findByTestId("artifact-widget-unsupported-future_thing")
    ).toBeInTheDocument();
    // The rest of the form still rendered — this is the whole point.
    expect(screen.getByTestId("artifact-form-save")).toBeInTheDocument();
  });

  it("does not hand a mismatched widget its fields, and keeps those fields editable", async () => {
    // `steps_editor` (reads fields[0] only) pointed at Risk's three-field
    // matrix: without the guard, `impact` and `detection` would be suppressed
    // as "a widget draws them" while nothing draws them.
    mockDefinition([
      spec({
        name: "risk_matrix",
        type: "widget",
        widget_key: "steps_editor",
        fields: ["probability", "impact", "detection"],
        section: "classification",
      }),
      spec({ name: "probability", type: "enum", section: "classification", order: 4 }),
      spec({ name: "impact", type: "enum", section: "classification", order: 5 }),
      spec({ name: "detection", type: "number", section: "classification", order: 8 }),
    ]);
    render(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        initialValues={{ probability: "low", impact: "high", detection: 3 }}
        onSave={vi.fn()}
      />
    );
    expect(
      await screen.findByTestId("artifact-widget-unsupported-risk_matrix")
    ).toBeInTheDocument();
    expect(screen.queryByTestId("artifact-widget-risk_matrix")).not.toBeInTheDocument();
    expect(screen.getByTestId("artifact-field-probability")).toBeInTheDocument();
    expect(screen.getByTestId("artifact-field-impact")).toBeInTheDocument();
    expect(screen.getByTestId("artifact-field-detection")).toHaveValue(3);
  });

  it("still renders a widget whose own name is included in its own fields list", async () => {
    // I-1 fix round: a `markdown_tab_group` widget named "notes" with
    // `fields: ["notes"]` used to add "notes" to `widgetOwned` (from the
    // widget's OWN `fields` list) as well as excluding it from standalone
    // rendering as the field it names, then also NOT rendering the widget
    // itself because... — proven live: the widget rendered NEITHER as itself
    // NOR as a standalone field. It just vanished, no error, no warning.
    mockDefinition([
      spec({ name: "title" }),
      spec({
        name: "notes",
        type: "widget",
        widget_key: "markdown_tab_group",
        fields: ["notes"],
        section: "general",
      }),
    ]);
    render(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        initialValues={{ title: "T", notes: "some text" }}
        onSave={vi.fn()}
      />
    );
    expect(await screen.findByTestId("artifact-widget-notes")).toBeInTheDocument();
    expect(screen.queryByTestId("artifact-field-notes")).not.toBeInTheDocument();
  });

  it("renders the real bootstrapped risk_matrix definition as a widget", async () => {
    mockDefinition(REAL_RISK_WIDGET_ATTRS);
    render(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        initialValues={{ probability: "high", impact: "high", detection: 4 }}
        onSave={vi.fn()}
      />
    );
    const widget = await screen.findByTestId("artifact-widget-risk_matrix");
    expect(widget).toBeInTheDocument();
    // 3 x 3 x 4 — proves the widget actually received its bound values.
    expect(screen.getByTestId("artifact-widget-risk_matrix-rpn")).toHaveTextContent("36");
    expect(
      screen.queryByTestId("artifact-widget-unsupported-risk_matrix")
    ).not.toBeInTheDocument();
  });
});

describe("ArtifactForm user directory", () => {
  beforeEach(() => {
    vi.mocked(attributeDefinitionsApi.getWorkspace).mockReset();
    vi.mocked(usersApi.list).mockReset();
  });

  it("signals that the user directory is unreadable instead of showing an empty picker", async () => {
    // `GET /api/v1/users/` is tenant-admin-only; every other role gets a 403.
    vi.mocked(usersApi.list).mockRejectedValue(new Error("Forbidden"));
    mockDefinition([spec({ name: "owner_user", type: "user" })]);
    render(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        initialValues={{ owner_user: "u-1" }}
        onSave={vi.fn()}
      />
    );
    expect(
      await screen.findByTestId("artifact-field-owner_user-directory-unavailable")
    ).toBeInTheDocument();
    // The already-assigned user is still selectable, so a save cannot silently
    // drop the owner.
    expect(screen.getByTestId("artifact-field-owner_user")).toHaveValue("u-1");
  });

  it("shows no warning when the directory loads", async () => {
    vi.mocked(usersApi.list).mockResolvedValue([
      { id: "u-1", username: "alice", email: "a@example.com" } as never,
    ]);
    mockDefinition([spec({ name: "owner_user", type: "user" })]);
    render(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        initialValues={{ owner_user: "u-1" }}
        onSave={vi.fn()}
      />
    );
    await screen.findByTestId("artifact-field-owner_user");
    await waitFor(() =>
      expect(
        screen.queryByTestId("artifact-field-owner_user-directory-unavailable")
      ).not.toBeInTheDocument()
    );
  });
});

// Attribut v3 WS2 (#936): the definition-driven renderer maps the new `actor`
// type onto `ActorPicker` (single/multiple by the attribute's `multiple`), the
// `priority` enum onto `EnumSelect`, and keeps a locked `editable="system"`
// field non-editable.
describe("ArtifactForm field mapping (WS2 #936)", () => {
  beforeEach(() => {
    vi.mocked(attributeDefinitionsApi.getWorkspace).mockReset();
    vi.mocked(usersApi.list).mockReset();
    vi.mocked(usersApi.list).mockResolvedValue([]);
    vi.mocked(actorsApi.list).mockReset();
    vi.mocked(actorsApi.list).mockResolvedValue([
      { id: "u-1", name: "Alice Admin", email: "alice@example.com" },
    ]);
  });

  it("maps an actor attribute onto the ActorPicker combobox instead of a text input", async () => {
    mockDefinition([spec({ name: "owner", type: "actor" })]);
    render(
      <ArtifactForm
        itemType="Requirement"
        artifactId="r-1"
        initialValues={{ owner: { kind: "user", id: "u-1" } }}
        onSave={vi.fn()}
      />
    );
    expect(await screen.findByRole("combobox")).toBeInTheDocument();
    // The generic TextField must NOT have rendered the value.
    expect(screen.queryByDisplayValue("u-1")).not.toBeInTheDocument();
  });

  it("renders a multiple actor attribute as a chip list", async () => {
    mockDefinition([spec({ name: "deciders", type: "actor", multiple: true })]);
    render(
      <ArtifactForm
        itemType="Requirement"
        artifactId="r-1"
        initialValues={{
          deciders: { multiple: true, items: [{ kind: "user", id: "u-1" }] },
        }}
        onSave={vi.fn()}
      />
    );
    const chip = await screen.findByTestId("artifact-field-deciders-chip");
    expect(chip).toHaveTextContent("Alice Admin");
  });

  it("maps the priority enum onto a select with the low|medium|high|critical scale", async () => {
    mockDefinition([
      spec({
        name: "priority",
        type: "enum",
        options: [
          { value: "low", label_de: "Niedrig", label_en: "Low" },
          { value: "medium", label_de: "Mittel", label_en: "Medium" },
          { value: "high", label_de: "Hoch", label_en: "High" },
          { value: "critical", label_de: "Kritisch", label_en: "Critical" },
        ],
      }),
    ]);
    render(
      <ArtifactForm
        itemType="Requirement"
        artifactId="r-1"
        initialValues={{ priority: "high" }}
        onSave={vi.fn()}
      />
    );
    const control = await screen.findByTestId("artifact-field-priority");
    expect(control.tagName).toBe("SELECT");
    expect(control).toHaveValue("high");
    expect(
      Array.from(control.querySelectorAll("option")).map((o) => o.value)
    ).toEqual(["", "low", "medium", "high", "critical"]);
  });

  it("renders the locked system id field as static text, never an editable input", async () => {
    mockDefinition([
      spec({
        name: "id",
        type: "text",
        editable: "system",
        locked: true,
        visible: true,
      }),
    ]);
    render(
      <ArtifactForm
        itemType="Requirement"
        artifactId="r-1"
        initialValues={{ id: "00000000-0000-0000-0000-000000000123" }}
        onSave={vi.fn()}
      />
    );
    const field = await screen.findByTestId("artifact-field-id");
    // A locked `editable: "system"` attribute is the Artifact's own identity:
    // shown as text, never typed over (reveal/copy/mask: WS3 #937).
    expect(field.tagName).toBe("SPAN");
    expect(field).toHaveTextContent("00000000-0000-0000-0000-000000000123");
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });
});

describe("ArtifactForm display properties (WS3 #937)", () => {
  beforeEach(() => {
    vi.mocked(attributeDefinitionsApi.getWorkspace).mockReset();
    vi.mocked(usersApi.list).mockReset();
    vi.mocked(usersApi.list).mockResolvedValue([]);
  });

  it("renders an attribute without special display properties exactly as before", async () => {
    mockDefinition([spec({ name: "title" })]);
    render(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        initialValues={{ title: "T" }}
        onSave={vi.fn()}
      />
    );
    // The ordinary control stays, and no RevealValue affordances appear.
    expect(await screen.findByTestId("artifact-field-title")).toHaveValue("T");
    expect(screen.queryByTestId("artifact-field-title-copy")).not.toBeInTheDocument();
    expect(screen.queryByTestId("artifact-field-title-reveal")).not.toBeInTheDocument();
  });

  it("applies display_format=mono to an editable text field", async () => {
    mockDefinition([spec({ name: "title", display_format: "mono" })]);
    render(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        initialValues={{ title: "T" }}
        onSave={vi.fn()}
      />
    );
    const control = await screen.findByTestId("artifact-field-title");
    // `.control` plus the mono modifier — the visual-only property.
    expect(control.classList.length).toBeGreaterThan(1);
  });

  it("renders a configured read-only list field through RevealValue as chips", async () => {
    mockDefinition([
      spec({
        name: "tags",
        type: "multi-enum",
        options: [
          { value: "a", label_de: "Alpha", label_en: "Alpha" },
          { value: "b", label_de: "Beta", label_en: "Beta" },
        ],
        display_format: "chips",
        copyable: true,
        mask: "short",
      }),
    ]);
    render(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        mode="read"
        initialValues={{ tags: ["a", "b"] }}
        onSave={vi.fn()}
      />
    );
    expect(await screen.findByTestId("artifact-field-tags-chips")).toBeInTheDocument();
    expect(screen.getAllByTestId("artifact-field-tags-chip")).toHaveLength(2);
    expect(screen.getByTestId("artifact-field-tags-copy")).toBeInTheDocument();
    // The editable multi-enum control is not rendered in the display path.
    expect(screen.queryByTestId("artifact-field-tags-option-a")).not.toBeInTheDocument();
  });

  it("drives the system id field from reveal=click + mask=short + copyable", async () => {
    const user = userEvent.setup();
    const uuid = "12345678-1234-4abc-8def-1234567890ab";
    mockDefinition([
      spec({
        name: "uid",
        type: "text",
        editable: "system",
        visible: true,
        reveal: "click",
        mask: "short",
        copyable: true,
      }),
    ]);
    render(
      <ArtifactForm
        itemType="Requirement"
        artifactId="r-1"
        initialValues={{ uid: uuid }}
        onSave={vi.fn()}
      />
    );
    // Hidden until revealed.
    const reveal = await screen.findByTestId("artifact-field-uid-reveal");
    expect(screen.queryByTestId("artifact-field-uid-value")).not.toBeInTheDocument();

    await user.click(reveal);
    const shown = screen.getByTestId("artifact-field-uid-value");
    // mask="short": 8 chars + ellipsis, not the full UUID.
    expect(shown).toHaveTextContent("12345678…");
    expect(shown).not.toHaveTextContent(uuid);
    // copyable is offered independently of the mask.
    expect(screen.getByTestId("artifact-field-uid-copy")).toBeInTheDocument();
  });
});


describe("ArtifactForm layout engine (WS4 #938)", () => {
  beforeEach(() => {
    vi.mocked(attributeDefinitionsApi.getWorkspace).mockReset();
    vi.mocked(usersApi.list).mockReset();
    vi.mocked(usersApi.list).mockResolvedValue([]);
  });

  it("defaults every section and field to full span when no flow is stored", async () => {
    mockDefinition([
      spec({ name: "title", section: "general", order: 0 }),
      spec({ name: "description", type: "textarea", section: "general", order: 1 }),
    ]);
    render(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        initialValues={{ title: "T" }}
        onSave={vi.fn()}
      />
    );
    await screen.findByTestId("artifact-field-title");
    expect(screen.getByTestId("artifact-section-general")).toHaveAttribute("data-columns", "12");
    expect(screen.getByTestId("artifact-field-cell-title")).toHaveAttribute("data-columns", "12");
    expect(screen.getByTestId("artifact-field-cell-description")).toHaveAttribute(
      "data-columns",
      "12"
    );
    // No flow => no spacers at all (the pre-WS4 rendering).
    expect(screen.queryByTestId(/^artifact-section-spacer-/)).not.toBeInTheDocument();
    expect(screen.queryByTestId(/^artifact-field-spacer-/)).not.toBeInTheDocument();
  });

  it("orders sections and spacers by the stored section_flow", async () => {
    mockDefinition(
      [
        spec({ name: "title", section: "general", order: 0 }),
        spec({ name: "uid", section: "change_control", order: 0 }),
      ],
      [
        section({ name: "general", order: 0 }),
        section({ name: "change_control", order: 1 }),
      ],
      [
        { kind: "section", name: "change_control" },
        { kind: "spacer", size: "md" },
        { kind: "section", name: "general" },
      ]
    );
    render(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        initialValues={{ title: "T" }}
        onSave={vi.fn()}
      />
    );
    await screen.findByTestId("artifact-field-title");
    const grid = screen.getByTestId("artifact-sections-grid");
    expect(
      Array.from(grid.children).map((child) => child.getAttribute("data-testid"))
    ).toEqual([
      "artifact-section-change_control",
      "artifact-section-spacer-1",
      "artifact-section-general",
    ]);
    expect(screen.getByTestId("artifact-section-spacer-1")).toHaveAttribute(
      "data-columns",
      "2"
    );
  });

  it("maps attribute spans and spacers from the stored attribute_flow", async () => {
    mockDefinition(
      [
        spec({ name: "a", section: "general", order: 0 }),
        spec({ name: "b", section: "general", order: 1 }),
        spec({ name: "c", section: "general", order: 2 }),
      ],
      [
        section({
          name: "general",
          attribute_flow: [
            { kind: "attribute", name: "b", span: "half" },
            { kind: "spacer", size: "sm" },
            { kind: "attribute", name: "a", span: "quarter" },
          ],
        }),
      ]
    );
    render(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        initialValues={{ a: "A", b: "B", c: "C" }}
        onSave={vi.fn()}
      />
    );
    await screen.findByTestId("artifact-field-a");
    const body = screen.getByTestId("artifact-section-body-general");
    expect(
      Array.from(body.children).map((child) => child.getAttribute("data-testid"))
    ).toEqual([
      "artifact-field-cell-b",
      "artifact-field-spacer-general-1",
      "artifact-field-cell-a",
      "artifact-field-cell-c",
    ]);
    expect(screen.getByTestId("artifact-field-cell-b")).toHaveAttribute("data-columns", "6");
    expect(screen.getByTestId("artifact-field-cell-a")).toHaveAttribute("data-columns", "3");
    expect(screen.getByTestId("artifact-field-spacer-general-1")).toHaveAttribute(
      "data-columns",
      "1"
    );
    // Unpositioned attribute keeps full width (additive derivation).
    expect(screen.getByTestId("artifact-field-cell-c")).toHaveAttribute("data-columns", "12");
  });

  it("maps a half section onto the 12-column grid", async () => {
    mockDefinition(
      [spec({ name: "a", section: "left", order: 0 })],
      [section({ name: "left", order: 0, layout: "half" })]
    );
    render(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        initialValues={{}}
        onSave={vi.fn()}
      />
    );
    await screen.findByTestId("artifact-field-a");
    expect(screen.getByTestId("artifact-section-left")).toHaveAttribute("data-columns", "6");
  });

  it("collapses the grid to one column and hides spacers below the md breakpoint (CSS contract)", () => {
    const css = readFileSync(
      join(__dirname, "..", "components", "shared", "ArtifactForm", "ArtifactForm.module.css"),
      "utf-8"
    );
    expect(css).toContain("grid-template-columns: repeat(12, 1fr)");
    expect(css).toContain("@media (max-width: 768px)");
    expect(css).toContain("grid-column: 1 / -1;");
    expect(css).toMatch(/\.spacerToken\s*\{\s*display:\s*none;/);
  });
});
