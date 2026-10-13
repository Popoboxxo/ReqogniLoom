/**
 * Regression guard for issue #1239: saving on a detail page must emit exactly
 * one PATCH, and the form must adopt the server's response (version included)
 * as the new truth. The guard runs for Requirement and Architecture, and for
 * the `extended` preset asserts the `change_reason` is part of the PATCH body.
 *
 * It also pins that the `transitions/` GET is mount-time only — the save path
 * must not trigger a refetch of it.
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

vi.mock("../api/requirements", () => ({
  requirementsApi: { update: vi.fn(), delete: vi.fn() },
}));
vi.mock("../api/architecture", () => ({
  architectureApi: { update: vi.fn(), delete: vi.fn() },
}));
vi.mock("../api/attribute-definitions", () => ({
  attributeDefinitionsApi: { getWorkspace: vi.fn(), getSchema: vi.fn() },
}));
vi.mock("../api/workflow-transitions", () => ({
  workflowTransitionsApi: { getTransitions: vi.fn(), transition: vi.fn() },
}));

const workspace = { current: { id: "ws-1", preset: "standard" } };
vi.mock("../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: workspace.current }),
}));

import { requirementsApi } from "../api/requirements";
import { architectureApi } from "../api/architecture";
import { attributeDefinitionsApi } from "../api/attribute-definitions";
import { workflowTransitionsApi } from "../api/workflow-transitions";
import type { AttributeSpec, ResolvedAttributeDefinition } from "../api/attribute-definitions";
import { RequirementArtifactForm } from "../components/RequirementEditors/RequirementArtifactForm";
import { ArchitectureArtifactForm } from "../components/ArchitectureEditors/ArchitectureArtifactForm";
import type { ArchitectureElement, Requirement, WorkspacePreset } from "../types";

function attr(over: Partial<AttributeSpec>): AttributeSpec {
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
    order: 1,
    label: { de: "", en: "" },
    help_text: { de: "", en: "" },
    default: null,
    validation: {},
    ai_elicit: false,
    export: true,
    audience: "basic",
    ...over,
  };
}

function definition(
  itemType: "Requirement" | "ArchitectureElement",
  preset: WorkspacePreset,
  attributes: AttributeSpec[]
): ResolvedAttributeDefinition {
  return {
    item_type: itemType,
    preset,
    is_customized: false,
    version: 1,
    attributes,
    origins: {},
    sections: [],
  };
}

const REQUIREMENT = {
  id: "req-1",
  workspace_id: "ws-1",
  title: "Login",
  custom_fields: {},
  version: 7,
} as unknown as Requirement;

const ARCH_ELEMENT = {
  id: "arch-1",
  workspace_id: "ws-1",
  title: "AuthService",
  custom_fields: {},
  version: 3,
} as unknown as ArchitectureElement;

beforeEach(() => {
  workspace.current = { id: "ws-1", preset: "standard" };
  vi.mocked(requirementsApi.update).mockReset();
  vi.mocked(requirementsApi.delete).mockReset();
  vi.mocked(architectureApi.update).mockReset();
  vi.mocked(architectureApi.delete).mockReset();
  vi.mocked(workflowTransitionsApi.getTransitions).mockReset();
  vi.mocked(attributeDefinitionsApi.getWorkspace).mockReset();
  vi.mocked(attributeDefinitionsApi.getSchema).mockReset();
  vi.mocked(attributeDefinitionsApi.getSchema).mockResolvedValue([]);
});

describe("Detail save guard (#1239)", () => {
  it("Requirement: sends exactly one PATCH and adopts the server-returned version (standard)", async () => {
    vi.mocked(attributeDefinitionsApi.getWorkspace).mockResolvedValue(
      definition("Requirement", "standard", [attr({ name: "title", required: true })])
    );
    vi.mocked(requirementsApi.update).mockResolvedValue({
      ...REQUIREMENT,
      title: "Login (server)",
      version: 8,
    } as never);

    render(
      <RequirementArtifactForm
        requirement={REQUIREMENT}
        onSaved={vi.fn()}
        onDeleted={vi.fn()}
      />
    );

    const title = await screen.findByTestId("artifact-field-title");
    await userEvent.clear(title);
    await userEvent.type(title, "Login (edited)");
    await userEvent.click(screen.getByTestId("artifact-form-save"));

    await waitFor(() => expect(requirementsApi.update).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(screen.getByTestId("artifact-form")).toHaveAttribute("data-version", "8")
    );
    expect(screen.getByTestId("artifact-field-title")).toHaveValue("Login (server)");
  });

  it("Requirement: sends exactly one PATCH carrying change_reason under the extended preset", async () => {
    workspace.current = { id: "ws-1", preset: "extended" };
    vi.mocked(attributeDefinitionsApi.getWorkspace).mockResolvedValue(
      definition("Requirement", "extended", [attr({ name: "title", required: true })])
    );
    vi.mocked(requirementsApi.update).mockResolvedValue({
      ...REQUIREMENT,
      version: 8,
    } as never);

    render(
      <RequirementArtifactForm
        requirement={REQUIREMENT}
        onSaved={vi.fn()}
        onDeleted={vi.fn()}
      />
    );

    await userEvent.type(
      await screen.findByTestId("artifact-form-change-reason"),
      "clarified wording"
    );
    await userEvent.click(screen.getByTestId("artifact-form-save"));

    await waitFor(() => expect(requirementsApi.update).toHaveBeenCalledTimes(1));
    expect(requirementsApi.update).toHaveBeenCalledWith(
      "req-1",
      expect.objectContaining({ change_reason: "clarified wording" }),
      7
    );
    await waitFor(() =>
      expect(screen.getByTestId("artifact-form")).toHaveAttribute("data-version", "8")
    );
  });

  it("Architecture: sends exactly one PATCH and adopts the server-returned version", async () => {
    vi.mocked(attributeDefinitionsApi.getWorkspace).mockResolvedValue(
      definition("ArchitectureElement", "standard", [
        attr({ name: "title", required: true }),
      ])
    );
    vi.mocked(architectureApi.update).mockResolvedValue({
      ...ARCH_ELEMENT,
      title: "AuthService (server)",
      version: 4,
    } as never);

    render(
      <ArchitectureArtifactForm
        element={ARCH_ELEMENT}
        onSaved={vi.fn()}
        onDeleted={vi.fn()}
      />
    );

    const title = await screen.findByTestId("artifact-field-title");
    await userEvent.clear(title);
    await userEvent.type(title, "AuthService (edited)");
    await userEvent.click(screen.getByTestId("artifact-form-save"));

    await waitFor(() => expect(architectureApi.update).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(screen.getByTestId("artifact-form")).toHaveAttribute("data-version", "4")
    );
    expect(screen.getByTestId("artifact-field-title")).toHaveValue(
      "AuthService (server)"
    );
  });

  it("does not refetch transitions/ from the save path", async () => {
    vi.mocked(attributeDefinitionsApi.getWorkspace).mockResolvedValue(
      definition("Requirement", "standard", [
        attr({ name: "title", required: true }),
        attr({ name: "status", editable: "workflow", section: "workflow", order: 2 }),
      ])
    );
    vi.mocked(workflowTransitionsApi.getTransitions).mockResolvedValue({
      current_state: "draft",
      states: ["draft"],
      allowed_transitions: [],
      proposed_by: null,
    });
    vi.mocked(requirementsApi.update).mockResolvedValue({
      ...REQUIREMENT,
      version: 8,
    } as never);

    render(
      <RequirementArtifactForm
        requirement={REQUIREMENT}
        onSaved={vi.fn()}
        onDeleted={vi.fn()}
      />
    );

    await screen.findByTestId("artifact-field-title");
    await waitFor(() =>
      expect(workflowTransitionsApi.getTransitions).toHaveBeenCalled()
    );
    const mountCalls = vi.mocked(workflowTransitionsApi.getTransitions).mock.calls.length;

    await userEvent.click(screen.getByTestId("artifact-form-save"));
    await waitFor(() => expect(requirementsApi.update).toHaveBeenCalledTimes(1));

    expect(workflowTransitionsApi.getTransitions).toHaveBeenCalledTimes(mountCalls);
  });
});
