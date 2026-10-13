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
        resolved,
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
}));

vi.mock("../api/users", () => ({ usersApi: { list: vi.fn() } }));

vi.mock("../api/actors", () => ({ actorsApi: { list: vi.fn() } }));

vi.mock("../components/WorkflowStatusEditor", () => ({
  WorkflowStatusEditor: () => <div data-testid="workflow-status-editor" />,
}));

vi.mock("../api/workflow-transitions", () => ({
  workflowTransitionsApi: { getTransitions: vi.fn(), transition: vi.fn() },
}));

import { attributeDefinitionsApi } from "../api/attribute-definitions";
import type { AttributeSpec } from "../api/attribute-definitions";
import { workflowTransitionsApi } from "../api/workflow-transitions";
import { ArtifactForm } from "../components/shared/ArtifactForm";

function spec(over: Partial<AttributeSpec> = {}): AttributeSpec {
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

function mockAllowed(transitions: Array<Partial<{ target_state: string; requires_change_reason: boolean; signature_gate: boolean }>>): void {
  vi.mocked(workflowTransitionsApi.getTransitions).mockResolvedValue({
    current_state: "draft",
    states: ["draft", "deprecated"],
    allowed_transitions: transitions.map((t) => ({
      target_state: t.target_state ?? "deprecated",
      requires_change_reason: t.requires_change_reason ?? false,
      signature_gate: t.signature_gate ?? false,
    })),
    proposed_by: null,
  });
}

function mockDefinition(): void {
  vi.mocked(attributeDefinitionsApi.getWorkspace).mockResolvedValue({
    item_type: "Risk",
    preset: "standard",
    is_customized: false,
    version: 1,
    attributes: [spec()],
    origins: {},
    sections: [],
  });
}

describe("ArtifactForm deprecate action (D6)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockDefinition();
  });

  it("offers the deprecate action only when an outdated transition is allowed", async () => {
    mockAllowed([{ target_state: "approved" }]);
    const first = render(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        initialValues={{ title: "T" }}
        onSave={vi.fn()}
        workflowArtifactType="risk"
      />,
    );
    await screen.findByTestId("artifact-field-title");
    await waitFor(() =>
      expect(workflowTransitionsApi.getTransitions).toHaveBeenCalled(),
    );
    expect(screen.queryByTestId("artifact-form-deprecate")).not.toBeInTheDocument();
    first.unmount();

    mockAllowed([{ target_state: "deprecated" }]);
    render(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        initialValues={{ title: "T" }}
        onSave={vi.fn()}
        onDeprecate={vi.fn()}
        workflowArtifactType="risk"
      />,
    );
    expect(await screen.findByTestId("artifact-form-deprecate")).toBeInTheDocument();
  });

  it("runs the workflow transition to the outdated state on confirm", async () => {
    mockAllowed([{ target_state: "deprecated" }]);
    const onDeprecate = vi.fn().mockResolvedValue(undefined);
    render(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        initialValues={{ title: "T" }}
        onSave={vi.fn()}
        onDeprecate={onDeprecate}
        workflowArtifactType="risk"
      />,
    );
    await userEvent.click(await screen.findByTestId("artifact-form-deprecate"));
    await userEvent.click(screen.getByTestId("artifact-form-deprecate-confirm"));
    await waitFor(() =>
      expect(onDeprecate).toHaveBeenCalledWith("deprecated", ""),
    );
  });

  it("requires a change reason before deprecating when the transition demands one", async () => {
    mockAllowed([{ target_state: "deprecated", requires_change_reason: true }]);
    const onDeprecate = vi.fn().mockResolvedValue(undefined);
    render(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        initialValues={{ title: "T" }}
        onSave={vi.fn()}
        onDeprecate={onDeprecate}
        workflowArtifactType="risk"
      />,
    );
    await userEvent.click(await screen.findByTestId("artifact-form-deprecate"));
    expect(screen.getByTestId("artifact-form-deprecate-confirm")).toBeDisabled();
    await userEvent.type(
      screen.getByTestId("artifact-form-deprecate-reason"),
      "superseded by new spec",
    );
    await userEvent.click(screen.getByTestId("artifact-form-deprecate-confirm"));
    await waitFor(() =>
      expect(onDeprecate).toHaveBeenCalledWith("deprecated", "superseded by new spec"),
    );
  });

  it("never renders the hard-delete action and its confirm dialog", async () => {
    mockAllowed([{ target_state: "deprecated" }]);
    render(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        initialValues={{ title: "T" }}
        onSave={vi.fn()}
        onDeprecate={vi.fn()}
        workflowArtifactType="risk"
      />,
    );
    await screen.findByTestId("artifact-field-title");
    expect(screen.queryByTestId("artifact-form-delete")).not.toBeInTheDocument();
    expect(screen.queryByTestId("artifact-form-delete-dialog")).not.toBeInTheDocument();
  });
});
