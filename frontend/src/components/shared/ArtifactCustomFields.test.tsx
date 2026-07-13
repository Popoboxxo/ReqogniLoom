/**
 * Tests for ArtifactCustomFields (REQ-016).
 *
 * Verifies:
 * - renders a typed control per workspace field
 * - number fields use type=number, dropdown fields render a select
 * - Save posts the edited draft values via putValues
 * - renders nothing when the workspace has no custom fields
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ArtifactCustomFields } from "./ArtifactCustomFields";
import * as cfModule from "../../api/custom-fields";

vi.mock("../../api/custom-fields");
vi.mock("react-i18next", () => {
  const t = (_key: string, fallback?: string): string => fallback ?? _key;
  return { useTranslation: () => ({ t }) };
});

const ARTIFACT = "22222222-2222-2222-2222-222222222222";

describe("ArtifactCustomFields (REQ-016)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(cfModule.customFieldsApi.getValues).mockResolvedValue([
      {
        id: null,
        definition_id: "def-text",
        artifact_id: ARTIFACT,
        value: "",
        name: "Reviewer",
        field_type: "text",
        is_required: false,
        options: [],
        order: 0,
      },
      {
        id: null,
        definition_id: "def-num",
        artifact_id: ARTIFACT,
        value: "",
        name: "Estimate",
        field_type: "number",
        is_required: false,
        options: [],
        order: 1,
      },
      {
        id: null,
        definition_id: "def-drop",
        artifact_id: ARTIFACT,
        value: "",
        name: "Severity",
        field_type: "dropdown",
        is_required: false,
        options: ["low", "high"],
        order: 2,
      },
    ]);
    vi.mocked(cfModule.customFieldsApi.putValues).mockResolvedValue([]);
  });

  it("renders a control per field with correct types", async () => {
    render(<ArtifactCustomFields artifactId={ARTIFACT} />);
    const textInput = await screen.findByTestId("cf-input-def-text");
    expect(textInput).toHaveAttribute("type", "text");
    expect(screen.getByTestId("cf-input-def-num")).toHaveAttribute(
      "type",
      "number"
    );
    // Dropdown renders a <select> (no type attribute).
    expect(screen.getByTestId("cf-input-def-drop").tagName).toBe("SELECT");
  });

  it("saves edited draft values via putValues", async () => {
    render(<ArtifactCustomFields artifactId={ARTIFACT} />);
    const textInput = await screen.findByTestId("cf-input-def-text");
    await userEvent.type(textInput, "alice");
    await userEvent.click(screen.getByTestId("artifact-custom-fields-save"));

    await waitFor(() =>
      expect(cfModule.customFieldsApi.putValues).toHaveBeenCalled()
    );
    const [artifactId, values] = vi.mocked(
      cfModule.customFieldsApi.putValues
    ).mock.calls[0];
    expect(artifactId).toBe(ARTIFACT);
    expect(values).toContainEqual({
      definition_id: "def-text",
      value: "alice",
    });
  });

  it("renders nothing when no custom fields are defined", async () => {
    vi.mocked(cfModule.customFieldsApi.getValues).mockResolvedValue([]);
    const { container } = render(<ArtifactCustomFields artifactId={ARTIFACT} />);
    await waitFor(() =>
      expect(
        screen.queryByTestId("artifact-custom-fields")
      ).not.toBeInTheDocument()
    );
    expect(container).toBeEmptyDOMElement();
  });
});
