/**
 * Tests for CustomFieldsSection (REQ-016).
 *
 * Verifies:
 * - definitions render in the table after load
 * - admins see the create form and can add a text field
 * - the add button is disabled for a dropdown without options
 * - delete calls the API
 * - non-admins do not see the create form
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CustomFieldsSection } from "./CustomFieldsSection";
import * as cfModule from "../../api/custom-fields";
import * as authModule from "../../context/AuthContext";

vi.mock("../../api/custom-fields");
vi.mock("../../context/AuthContext");
vi.mock("react-i18next", () => {
  const t = (_key: string, fallback?: string): string => fallback ?? _key;
  return { useTranslation: () => ({ t }) };
});

const WS = "11111111-1111-1111-1111-111111111111";

function mockRoles(roles: string[]): void {
  vi.mocked(authModule.useAuth).mockReturnValue({
    roles,
  } as unknown as ReturnType<typeof authModule.useAuth>);
}

describe("CustomFieldsSection (REQ-016)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (cfModule as { CUSTOM_FIELD_TYPES: readonly string[] }).CUSTOM_FIELD_TYPES =
      ["text", "number", "dropdown"];
    vi.mocked(cfModule.customFieldsApi.listDefinitions).mockResolvedValue([
      {
        id: "def-1",
        workspace_id: WS,
        name: "Reviewer",
        field_type: "text",
        is_required: false,
        options: [],
        order: 0,
      },
    ]);
    vi.mocked(cfModule.customFieldsApi.createDefinition).mockResolvedValue({
      id: "def-2",
      workspace_id: WS,
      name: "New",
      field_type: "text",
      is_required: false,
      options: [],
      order: 0,
    });
    vi.mocked(cfModule.customFieldsApi.deleteDefinition).mockResolvedValue();
    mockRoles(["admin"]);
  });

  it("renders existing definitions in the table", async () => {
    render(<CustomFieldsSection workspaceId={WS} />);
    expect(await screen.findByText("Reviewer")).toBeInTheDocument();
  });

  it("shows the create form for admins", async () => {
    render(<CustomFieldsSection workspaceId={WS} />);
    expect(
      await screen.findByTestId("custom-field-create-form")
    ).toBeInTheDocument();
  });

  it("hides the create form for non-admins", async () => {
    mockRoles(["editor"]);
    render(<CustomFieldsSection workspaceId={WS} />);
    await screen.findByText("Reviewer");
    expect(
      screen.queryByTestId("custom-field-create-form")
    ).not.toBeInTheDocument();
  });

  it("creates a text field", async () => {
    render(<CustomFieldsSection workspaceId={WS} />);
    const nameInput = await screen.findByTestId("custom-field-name-input");
    await userEvent.type(nameInput, "Priority");
    await userEvent.click(screen.getByTestId("custom-field-add-button"));

    await waitFor(() =>
      expect(cfModule.customFieldsApi.createDefinition).toHaveBeenCalled()
    );
    const [, payload] = vi.mocked(
      cfModule.customFieldsApi.createDefinition
    ).mock.calls[0];
    expect(payload).toMatchObject({ name: "Priority", field_type: "text" });
  });

  it("disables add for a dropdown without options", async () => {
    render(<CustomFieldsSection workspaceId={WS} />);
    const nameInput = await screen.findByTestId("custom-field-name-input");
    await userEvent.type(nameInput, "Severity");
    await userEvent.selectOptions(
      screen.getByTestId("custom-field-type-select"),
      "dropdown"
    );
    expect(screen.getByTestId("custom-field-add-button")).toBeDisabled();
  });

  // Regression test for the WCAG 4.1.2/3.3.2 fix: the type select must be
  // queryable via its accessible name (a visually-hidden <label htmlFor>),
  // not just via its data-testid.
  it("a11y: the field-type select is queryable by its accessible name", async () => {
    render(<CustomFieldsSection workspaceId={WS} />);
    await screen.findByTestId("custom-field-create-form");
    expect(screen.getByLabelText("Typ")).toBe(
      screen.getByTestId("custom-field-type-select")
    );
  });

  it("deletes a definition", async () => {
    render(<CustomFieldsSection workspaceId={WS} />);
    const delBtn = await screen.findByTestId("custom-field-delete-def-1");
    await userEvent.click(delBtn);
    // UI-09 (system audit P4): deleting a custom field is destructive —
    // requires an explicit confirmation before the API call fires.
    const confirmBtn = await screen.findByTestId("custom-field-delete-confirm-confirm");
    await userEvent.click(confirmBtn);
    await waitFor(() =>
      expect(cfModule.customFieldsApi.deleteDefinition).toHaveBeenCalledWith(
        "def-1"
      )
    );
  });
});
