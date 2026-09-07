import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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

vi.mock("../components/WorkflowStatusEditor", () => ({
  WorkflowStatusEditor: () => <div data-testid="workflow-status-editor" />,
}));

import { attributeDefinitionsApi } from "../api/attribute-definitions";
import { usersApi } from "../api/users";
import {
  ArtifactForm,
  fieldErrorsFromException,
  groupIntoSections,
  parseFieldErrors,
} from "../components/shared/ArtifactForm";
import type { AttributeSpec } from "../api/attribute-definitions";

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

function mockDefinition(attributes: AttributeSpec[]): void {
  vi.mocked(attributeDefinitionsApi.getWorkspace).mockResolvedValue({
    item_type: "Risk",
    preset: "standard",
    is_customized: false,
    version: 1,
    attributes,
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
    expect(await screen.findByTestId("artifact-form-load-error")).toBeInTheDocument();
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
