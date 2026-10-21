/**
 * Issue #1263 — the create dialog reads ONLY the form definition.
 *
 * The shared `ArtifactForm` renders the resolved attribute definition; the
 * resolved *create-form* definition overlays visible/order/required/default on
 * top of it. These tests pin that overlay: a hidden entry removes the control, a
 * required entry blocks Create, an entry's order reorders the controls, and an
 * entry's default pre-fills the value. `entries === null` (unresolved) leaves the
 * attribute definition in charge — the pre-#1263 behaviour.
 */

import { render, screen, waitFor } from "@testing-library/react";
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

/** Controllable create-form definition the ArtifactForm overlays. */
let createFormEntries: unknown[] | null = null;
vi.mock("../hooks/useCreateFormFields", () => ({
  useCreateFormFields: () => ({ entries: createFormEntries, loading: false }),
}));

import { attributeDefinitionsApi } from "../api/attribute-definitions";
import { usersApi } from "../api/users";
import { actorsApi } from "../api/actors";
import { ArtifactForm } from "../components/shared/ArtifactForm";
import type { AttributeSpec, SectionSpec } from "../api/attribute-definitions";

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
  const sections: SectionSpec[] = [
    { name: "general", order: 0, visible: true, layout: "full" },
  ];
  vi.mocked(attributeDefinitionsApi.getWorkspace).mockResolvedValue({
    item_type: "Risk",
    preset: "standard",
    is_customized: false,
    version: 1,
    attributes,
    origins: {},
    sections,
  });
}

function entry(field_key: string, over: Record<string, unknown> = {}) {
  return {
    field_key,
    visible: true,
    required: false,
    order: 0,
    default: null,
    ...over,
  };
}

function renderCreate() {
  return render(
    <ArtifactForm
      itemType="Risk"
      artifactId={null}
      initialValues={{}}
      onSave={vi.fn().mockResolvedValue(undefined)}
    />
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  createFormEntries = null;
  vi.mocked(usersApi.list).mockResolvedValue([]);
  vi.mocked(actorsApi.list).mockResolvedValue([]);
});

describe("ArtifactForm create-form overlay (#1263)", () => {
  it("hides a field the form definition marks invisible", async () => {
    mockDefinition([spec({ name: "title" }), spec({ name: "secret", order: 1 })]);
    createFormEntries = [
      entry("title"),
      entry("secret", { visible: false, order: 1 }),
    ];
    renderCreate();

    await screen.findByTestId("artifact-field-title");
    expect(screen.queryByTestId("artifact-field-secret")).not.toBeInTheDocument();
  });

  it("blocks Create for a field the form definition marks required", async () => {
    mockDefinition([spec({ name: "title" })]);
    createFormEntries = [entry("title", { required: true })];
    renderCreate();

    const save = await screen.findByTestId("artifact-form-save");
    await waitFor(() => expect(save).toBeDisabled());
  });

  it("reorders the controls according to the form definition's order", async () => {
    mockDefinition([
      spec({ name: "alpha", order: 0 }),
      spec({ name: "beta", order: 1 }),
    ]);
    createFormEntries = [
      entry("beta", { order: 0 }),
      entry("alpha", { order: 1 }),
    ];
    renderCreate();

    await screen.findByTestId("artifact-field-beta");
    await waitFor(() => {
      const cells = Array.from(
        document.querySelectorAll('[data-testid^="artifact-field-cell-"]')
      ).map((el) => el.getAttribute("data-testid"));
      expect(cells).toEqual([
        "artifact-field-cell-beta",
        "artifact-field-cell-alpha",
      ]);
    });
  });

  it("pre-fills a value the form definition supplies as default", async () => {
    mockDefinition([
      spec({
        name: "priority",
        type: "enum",
        options: [
          { value: "low", label_de: "Niedrig", label_en: "Low" },
          { value: "high", label_de: "Hoch", label_en: "High" },
        ],
      }),
    ]);
    // A required enum with a `default` is pre-filled (the same rule the form
    // already applied to `attribute.default`, now sourced from the entry).
    createFormEntries = [entry("priority", { required: true, default: "high" })];
    renderCreate();

    await waitFor(() =>
      expect(screen.getByTestId("artifact-field-priority")).toHaveValue("high")
    );
  });

  it("falls back to the attribute definition when no form definition resolved", async () => {
    mockDefinition([spec({ name: "title" }), spec({ name: "secret", order: 1 })]);
    createFormEntries = null;
    renderCreate();

    // Both attributes render, exactly as before #1263.
    await screen.findByTestId("artifact-field-title");
    expect(screen.getByTestId("artifact-field-secret")).toBeInTheDocument();
  });
});
