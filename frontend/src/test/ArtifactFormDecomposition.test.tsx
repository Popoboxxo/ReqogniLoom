/**
 * Phase 5b decomposition characterization net (frontend audit, FE-01 / F-01).
 *
 * `shared/ArtifactForm/ArtifactForm.tsx` is decomposed behind an UNCHANGED
 * public API. These tests were written BEFORE the refactor and pinned the
 * seams the decomposition moves — the section grid/flow rendering, the
 * widget-owned field suppression, the create-vs-edit section collapse, the
 * save payload + change-reason gate, the error-to-field focus routing and the
 * deprecate flow. They pass against the un-refactored component, so a
 * decomposition that changes behaviour fails here rather than only in the
 * (much larger) primary suites.
 *
 * Deliberately narrow: this is a safety net for the move, not a replacement
 * for `ArtifactForm.test.tsx` / `artifact-form-deprecate.test.tsx`.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { resolveLocaleKey } from "./i18n-test-helpers";

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
  attributeDefinitionsApi: { getWorkspace: vi.fn(), getSchema: vi.fn() },
}));

vi.mock("../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "ws-1", preset: "standard" } }),
  useOptionalWorkspace: () => ({ activeWorkspace: { id: "ws-1", preset: "standard" } }),
}));

vi.mock("../api/users", () => ({ usersApi: { list: vi.fn() } }));
vi.mock("../api/actors", () => ({ actorsApi: { list: vi.fn() } }));
vi.mock("../api/workflow-transitions", () => ({
  workflowTransitionsApi: { getTransitions: vi.fn(), transition: vi.fn() },
}));
vi.mock("../components/WorkflowStatusEditor", () => ({
  WorkflowStatusEditor: () => <div data-testid="workflow-status-editor" />,
}));
vi.mock("../components/shared/ArtifactForm/useGateRequiredFields", () => ({
  useGateRequiredFields: () => new Set<string>(),
}));
vi.mock("../hooks/useCreateFormFields", () => ({
  useCreateFormFields: () => ({ entries: null, loading: false }),
}));

import { attributeDefinitionsApi } from "../api/attribute-definitions";
import { usersApi } from "../api/users";
import { actorsApi } from "../api/actors";
import { workflowTransitionsApi } from "../api/workflow-transitions";
import { ArtifactForm } from "../components/shared/ArtifactForm";
import type {
  AttributeSpec,
  LayoutToken,
  SectionSpec,
} from "../api/attribute-definitions";

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

const REAL_RISK_WIDGET_ATTRS: AttributeSpec[] = [
  spec({
    name: "risk_matrix",
    type: "widget",
    widget_key: "risk_matrix_rpz",
    fields: ["probability", "impact", "detection"],
    section: "classification",
    order: 10,
  }),
  spec({ name: "probability", type: "enum", section: "classification", order: 4 }),
  spec({ name: "impact", type: "enum", section: "classification", order: 5 }),
  spec({ name: "detection", type: "number", section: "classification", order: 8 }),
];

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(usersApi.list).mockResolvedValue([]);
  vi.mocked(actorsApi.list).mockResolvedValue([]);
});

describe("ArtifactForm decomposition — section grid & flow", () => {
  it("renders section entries and spacers in section_flow order, with their columns", async () => {
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
    expect(screen.getByTestId("artifact-section-general")).toHaveAttribute(
      "data-columns",
      "12"
    );
  });

  it("maps the attribute_flow of a section onto field cells and field spacers", async () => {
    mockDefinition(
      [
        spec({ name: "a", section: "general", order: 0 }),
        spec({ name: "b", section: "general", order: 1 }),
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
        initialValues={{}}
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
    ]);
    expect(screen.getByTestId("artifact-field-cell-b")).toHaveAttribute(
      "data-columns",
      "6"
    );
    expect(screen.getByTestId("artifact-field-cell-a")).toHaveAttribute(
      "data-columns",
      "3"
    );
  });
});

describe("ArtifactForm decomposition — widget-owned field suppression", () => {
  it("does not render fields a widget draws standalone", async () => {
    mockDefinition([...REAL_RISK_WIDGET_ATTRS, spec({ name: "title" })]);
    render(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        initialValues={{ title: "T" }}
        onSave={vi.fn()}
      />
    );
    expect(await screen.findByTestId("artifact-widget-risk_matrix")).toBeInTheDocument();
    expect(screen.queryByTestId("artifact-field-probability")).not.toBeInTheDocument();
    expect(screen.queryByTestId("artifact-field-impact")).not.toBeInTheDocument();
    expect(screen.queryByTestId("artifact-field-detection")).not.toBeInTheDocument();
  });

  it("still renders a widget whose own name appears in its own fields list", async () => {
    mockDefinition([
      spec({
        name: "risk_matrix",
        type: "widget",
        widget_key: "risk_matrix_rpz",
        fields: ["probability", "impact", "detection", "risk_matrix"],
      }),
      spec({ name: "probability", type: "enum" }),
      spec({ name: "impact", type: "enum" }),
      spec({ name: "detection", type: "number" }),
    ]);
    render(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        initialValues={{}}
        onSave={vi.fn()}
      />
    );
    expect(await screen.findByTestId("artifact-widget-risk_matrix")).toBeInTheDocument();
  });
});

describe("ArtifactForm decomposition — create-vs-edit section collapse", () => {
  it("create mode: the header is a plain heading (no disclosure) and the body is always rendered", async () => {
    mockDefinition([
      spec({ name: "title", section: "general" }),
      spec({ name: "deep", section: "advanced", audience: "expert" }),
    ]);
    render(
      <ArtifactForm
        itemType="Risk"
        artifactId={null}
        initialValues={{}}
        onSave={vi.fn()}
      />
    );
    await screen.findByTestId("artifact-field-title");

    const header = screen.getByTestId("artifact-section-toggle-advanced");
    expect(header.tagName).toBe("SPAN");
    expect(screen.getByTestId("artifact-section-body-advanced")).toBeInTheDocument();
  });

  it("edit mode: an all-expert section is collapsed by default and expands on toggle", async () => {
    mockDefinition([
      spec({ name: "title", section: "general" }),
      spec({ name: "deep", section: "advanced", audience: "expert" }),
    ]);
    render(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        initialValues={{ title: "T", deep: "x" }}
        onSave={vi.fn()}
      />
    );
    await screen.findByTestId("artifact-field-title");

    const toggle = screen.getByTestId("artifact-section-toggle-advanced");
    expect(toggle.tagName).toBe("BUTTON");
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(
      screen.queryByTestId("artifact-section-body-advanced")
    ).not.toBeInTheDocument();

    await userEvent.click(toggle);
    expect(screen.getByTestId("artifact-section-body-advanced")).toBeInTheDocument();
    expect(toggle).toHaveAttribute("aria-expanded", "true");
  });

  it("names the section by its stable label and never dangles aria-controls (F-03/N4, N3)", async () => {
    // F-03/N4 (SC 1.3.1/2.4.6): `aria-labelledby` used to point at the toggle
    // button, whose accessible name is its `aria-label` ("Abschnitt X
    // einklappen/erweitern") — so the region's name was an *action*, flipping
    // with the expanded state. It must resolve to the stable inner label text.
    // N3 (SC 4.1.2): a collapsed section renders no body, so `aria-controls`
    // must not reference the id of a panel that does not exist.
    mockDefinition([
      spec({ name: "title", section: "general" }),
      spec({ name: "deep", section: "advanced", audience: "expert" }),
    ]);
    render(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        initialValues={{ title: "T", deep: "x" }}
        onSave={vi.fn()}
      />
    );
    await screen.findByTestId("artifact-field-title");

    const toggle = screen.getByTestId("artifact-section-toggle-advanced");
    const section = toggle.closest("section");
    expect(section).not.toBeNull();
    const labelledBy = section!.getAttribute("aria-labelledby");
    expect(labelledBy).toBeTruthy();
    const labelEl = document.getElementById(labelledBy!);
    expect(labelEl).not.toBeNull();
    // The name comes from the label text inside the toggle, not from the
    // toggle (action) itself.
    expect(labelEl).not.toBe(toggle);
    expect(toggle.contains(labelEl!)).toBe(true);

    // Collapsed: no body panel in the DOM, therefore no dangling IDREF.
    expect(toggle).not.toHaveAttribute("aria-controls");

    await userEvent.click(toggle);

    // Expanded: aria-controls now resolves to the rendered body panel.
    const controlsId = toggle.getAttribute("aria-controls");
    expect(controlsId).toBeTruthy();
    expect(document.getElementById(controlsId!)).toBe(
      screen.getByTestId("artifact-section-body-advanced")
    );
  });
});

describe("ArtifactForm decomposition — save payload & change-reason gate", () => {
  it("strips a non-editable attribute and appends change_reason when required", async () => {
    mockDefinition([
      spec({ name: "title" }),
      spec({ name: "uid", editable: false }),
    ]);
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        initialValues={{ title: "T", uid: "R-1" }}
        onSave={onSave}
        requiresChangeReason
      />
    );
    await screen.findByTestId("artifact-field-title");

    // A save without the change reason is refused before any request.
    await userEvent.click(screen.getByTestId("artifact-form-save"));
    expect(onSave).not.toHaveBeenCalled();
    expect(await screen.findByTestId("artifact-form-error")).toBeInTheDocument();

    await userEvent.type(
      screen.getByTestId("artifact-form-change-reason"),
      "clarify title"
    );
    await userEvent.click(screen.getByTestId("artifact-form-save"));

    await waitFor(() =>
      expect(onSave).toHaveBeenCalledWith({
        title: "T",
        change_reason: "clarify title",
      })
    );
  });
});

describe("ArtifactForm decomposition — error-to-field focus routing", () => {
  it("moves focus to the first errored field after a refused save", async () => {
    mockDefinition([spec({ name: "title" })]);
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
        initialValues={{ title: "" }}
        onSave={onSave}
      />
    );

    const title = await screen.findByTestId("artifact-field-title");
    await userEvent.click(screen.getByTestId("artifact-form-save"));

    await waitFor(() => expect(document.activeElement).toBe(title));
  });

  it("falls back to focusing the form-level error banner when no field maps", async () => {
    mockDefinition([spec({ name: "title" })]);
    const onSave = vi.fn().mockRejectedValue({
      error: {
        code: "INTERNAL_SERVER_ERROR",
        message: "Internal server error",
        details: [],
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

    await screen.findByTestId("artifact-field-title");
    await userEvent.click(screen.getByTestId("artifact-form-save"));

    const banner = await screen.findByTestId("artifact-form-error");
    await waitFor(() => expect(document.activeElement).toBe(banner));
  });
});

describe("ArtifactForm decomposition — deprecate flow", () => {
  it("runs the outdated transition through the confirm dialog", async () => {
    mockDefinition([spec({ name: "title" })]);
    vi.mocked(workflowTransitionsApi.getTransitions).mockResolvedValue({
      current_state: "draft",
      states: ["draft", "deprecated"],
      allowed_transitions: [
        {
          target_state: "deprecated",
          requires_change_reason: false,
          signature_gate: false,
        },
      ],
      proposed_by: null,
    });
    const onDeprecate = vi.fn().mockResolvedValue(undefined);
    render(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        initialValues={{ title: "T" }}
        onSave={vi.fn()}
        onDeprecate={onDeprecate}
        workflowArtifactType="risk"
      />
    );

    await userEvent.click(await screen.findByTestId("artifact-form-deprecate"));
    expect(screen.getByTestId("artifact-form-deprecate-dialog")).toBeInTheDocument();
    await userEvent.click(screen.getByTestId("artifact-form-deprecate-confirm"));
    await waitFor(() =>
      expect(onDeprecate).toHaveBeenCalledWith("deprecated", "")
    );
  });
});
