/**
 * Companion tests for IMPL-001: architecture change_reason UI capability.
 *
 * Mirrors the Requirement adapter's contract — under the `extended` preset the
 * shared ArtifactForm must render its change-reason input and carry the typed
 * reason in the PATCH body; under any other preset the input is absent. The
 * stable testid is the shared one (`artifact-form-change-reason`), not a
 * bespoke alias.
 */
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { resolveLocaleKey } from "../../test/i18n-test-helpers";
import { renderWithQueryClient as render } from "../../test/query-client";

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

import { architectureApi } from "../../api/architecture";
import {
  attributeDefinitionsApi,
  type AttributeSpec,
  type ResolvedAttributeDefinition,
} from "../../api/attribute-definitions";
import { workflowTransitionsApi } from "../../api/workflow-transitions";
import type { ArchitectureElement, WorkspacePreset } from "../../types";
import { ArchitectureArtifactForm } from "./ArchitectureArtifactForm";

const workspace: { current: { id: string; preset: WorkspacePreset } } = {
  current: { id: "ws-1", preset: "standard" },
};

vi.mock("../../api/architecture", () => ({
  architectureApi: { update: vi.fn(), delete: vi.fn() },
}));
vi.mock("../../api/attribute-definitions", () => ({
  attributeDefinitionsApi: { getWorkspace: vi.fn(), getSchema: vi.fn() },
}));
vi.mock("../../api/workflow-transitions", () => ({
  workflowTransitionsApi: { getTransitions: vi.fn(), transition: vi.fn() },
}));
vi.mock("../../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: workspace.current }),
  useOptionalWorkspace: () => ({ activeWorkspace: workspace.current }),
}));

const ARCH_ELEMENT = {
  id: "arch-1",
  workspace_id: "ws-1",
  title: "AuthService",
  custom_fields: {},
  version: 3,
} as unknown as ArchitectureElement;

function attr(over: Partial<AttributeSpec>): AttributeSpec {
  return {
    name: "title",
    kind: "core",
    type: "text",
    widget_key: null,
    fields: [],
    options: [],
    required: true,
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

function definition(preset: WorkspacePreset): ResolvedAttributeDefinition {
  return {
    item_type: "ArchitectureElement",
    preset,
    is_customized: false,
    version: 1,
    attributes: [attr({ name: "title", required: true })],
    origins: {},
    sections: [],
  };
}

describe("ArchitectureArtifactForm change_reason (IMPL-001)", () => {
  beforeEach(() => {
    workspace.current = { id: "ws-1", preset: "standard" };
    vi.mocked(architectureApi.update).mockReset();
    vi.mocked(workflowTransitionsApi.getTransitions).mockReset();
    vi.mocked(attributeDefinitionsApi.getWorkspace).mockReset();
    vi.mocked(attributeDefinitionsApi.getSchema).mockReset();
    vi.mocked(attributeDefinitionsApi.getSchema).mockResolvedValue([]);
  });

  it("does not render the change-reason input outside the extended preset", async () => {
    vi.mocked(attributeDefinitionsApi.getWorkspace).mockResolvedValue(
      definition("standard")
    );
    render(
      <ArchitectureArtifactForm
        element={ARCH_ELEMENT}
        onSaved={vi.fn()}
        onDeleted={vi.fn()}
      />
    );
    await screen.findByTestId("artifact-field-title");
    expect(
      screen.queryByTestId("artifact-form-change-reason")
    ).not.toBeInTheDocument();
  });

  it("requires a change reason under the extended preset and sends it in the PATCH", async () => {
    workspace.current = { id: "ws-1", preset: "extended" };
    vi.mocked(attributeDefinitionsApi.getWorkspace).mockResolvedValue(
      definition("extended")
    );
    vi.mocked(architectureApi.update).mockResolvedValue(ARCH_ELEMENT);
    render(
      <ArchitectureArtifactForm
        element={ARCH_ELEMENT}
        onSaved={vi.fn()}
        onDeleted={vi.fn()}
      />
    );

    const changeReason = await screen.findByTestId(
      "artifact-form-change-reason"
    );
    expect(changeReason).toBeInTheDocument();

    const save = screen.getByTestId("artifact-form-save");
    await userEvent.click(save);
    expect(architectureApi.update).not.toHaveBeenCalled();

    await userEvent.type(changeReason, "clarified wording");
    await userEvent.click(save);
    await waitFor(() =>
      expect(architectureApi.update).toHaveBeenCalledWith(
        "arch-1",
        expect.objectContaining({ change_reason: "clarified wording" })
      )
    );
  });
});
