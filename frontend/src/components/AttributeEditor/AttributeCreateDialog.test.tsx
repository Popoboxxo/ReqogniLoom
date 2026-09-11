/**
 * AttributeCreateDialog.test.tsx (Task 3, spec section 4.1).
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

import { AttributeCreateDialog } from "./AttributeCreateDialog";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

describe("AttributeCreateDialog", () => {
  it("renders all 10 attribute types in the type dropdown", () => {
    render(
      <AttributeCreateDialog
        scope="global"
        section="general"
        existingNames={[]}
        onCreate={vi.fn()}
        onClose={vi.fn()}
      />
    );
    const select = screen.getByTestId("attribute-create-dialog-type");
    const options = Array.from(select.querySelectorAll("option")).map(
      (option) => option.value
    );
    expect(options).toEqual([
      "text", "textarea", "number", "boolean", "enum", "multi-enum",
      "date", "reference", "user", "widget",
    ]);
  });

  it("shows an inline error on a colliding name instead of calling onCreate", async () => {
    const onCreate = vi.fn();
    render(
      <AttributeCreateDialog
        scope="global"
        section="general"
        existingNames={["title"]}
        onCreate={onCreate}
        onClose={vi.fn()}
      />
    );
    fireEvent.change(screen.getByTestId("attribute-create-dialog-name"), {
      target: { value: "title" },
    });
    fireEvent.click(screen.getByTestId("attribute-create-dialog-submit"));

    await waitFor(() =>
      expect(screen.getByTestId("attribute-create-dialog-error")).toBeTruthy()
    );
    expect(onCreate).not.toHaveBeenCalled();
  });

  it("shows an inline error on a non-snake_case name", async () => {
    const onCreate = vi.fn();
    render(
      <AttributeCreateDialog
        scope="global"
        section="general"
        existingNames={[]}
        onCreate={onCreate}
        onClose={vi.fn()}
      />
    );
    fireEvent.change(screen.getByTestId("attribute-create-dialog-name"), {
      target: { value: "Not Valid!" },
    });
    fireEvent.click(screen.getByTestId("attribute-create-dialog-submit"));

    await waitFor(() =>
      expect(screen.getByTestId("attribute-create-dialog-error")).toBeTruthy()
    );
    expect(onCreate).not.toHaveBeenCalled();
  });

  it("calls onCreate with a well-formed NewAttributeInput on submit", async () => {
    const onCreate = vi.fn().mockResolvedValue(undefined);
    const onClose = vi.fn();
    render(
      <AttributeCreateDialog
        scope="global"
        section="details"
        existingNames={["title"]}
        onCreate={onCreate}
        onClose={onClose}
      />
    );
    fireEvent.change(screen.getByTestId("attribute-create-dialog-name"), {
      target: { value: "risk_comment" },
    });
    fireEvent.click(screen.getByTestId("attribute-create-dialog-submit"));

    await waitFor(() => expect(onCreate).toHaveBeenCalledTimes(1));
    expect(onCreate).toHaveBeenCalledWith({
      name: "risk_comment",
      type: "text",
      required: false,
      section: "details",
    });
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
  });

  it("requires a non-empty options list for an enum type", async () => {
    const onCreate = vi.fn();
    render(
      <AttributeCreateDialog
        scope="global"
        section="general"
        existingNames={[]}
        onCreate={onCreate}
        onClose={vi.fn()}
      />
    );
    fireEvent.change(screen.getByTestId("attribute-create-dialog-name"), {
      target: { value: "risk_category" },
    });
    fireEvent.change(screen.getByTestId("attribute-create-dialog-type"), {
      target: { value: "enum" },
    });
    fireEvent.click(screen.getByTestId("attribute-create-dialog-submit"));

    await waitFor(() =>
      expect(screen.getByTestId("attribute-create-dialog-error")).toBeTruthy()
    );
    expect(onCreate).not.toHaveBeenCalled();
  });

  it("builds options from a comma-separated list for an enum type", async () => {
    const onCreate = vi.fn().mockResolvedValue(undefined);
    render(
      <AttributeCreateDialog
        scope="global"
        section="general"
        existingNames={[]}
        onCreate={onCreate}
        onClose={vi.fn()}
      />
    );
    fireEvent.change(screen.getByTestId("attribute-create-dialog-name"), {
      target: { value: "risk_category" },
    });
    fireEvent.change(screen.getByTestId("attribute-create-dialog-type"), {
      target: { value: "enum" },
    });
    fireEvent.change(screen.getByTestId("attribute-create-dialog-options"), {
      target: { value: "low, medium, high" },
    });
    fireEvent.click(screen.getByTestId("attribute-create-dialog-submit"));

    await waitFor(() => expect(onCreate).toHaveBeenCalledTimes(1));
    expect(onCreate).toHaveBeenCalledWith({
      name: "risk_category",
      type: "enum",
      required: false,
      section: "general",
      options: [
        { value: "low", label_de: "low", label_en: "low" },
        { value: "medium", label_de: "medium", label_en: "medium" },
        { value: "high", label_de: "high", label_en: "high" },
      ],
    });
  });

  it('shows the workspace-only hint when scope="workspace"', () => {
    render(
      <AttributeCreateDialog
        scope="workspace"
        section="general"
        existingNames={[]}
        onCreate={vi.fn()}
        onClose={vi.fn()}
      />
    );
    expect(screen.getByTestId("attribute-create-dialog-workspace-hint")).toBeTruthy();
  });

  it('does not show the workspace-only hint when scope="global"', () => {
    render(
      <AttributeCreateDialog
        scope="global"
        section="general"
        existingNames={[]}
        onCreate={vi.fn()}
        onClose={vi.fn()}
      />
    );
    expect(screen.queryByTestId("attribute-create-dialog-workspace-hint")).toBeNull();
  });

  it("calls onClose when the cancel button is clicked", () => {
    const onClose = vi.fn();
    render(
      <AttributeCreateDialog
        scope="global"
        section="general"
        existingNames={[]}
        onCreate={vi.fn()}
        onClose={onClose}
      />
    );
    fireEvent.click(screen.getByTestId("attribute-create-dialog-cancel"));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("shows the onCreate rejection message and keeps the dialog open", async () => {
    const onCreate = vi.fn().mockRejectedValue(new Error("'risk_comment' already exists"));
    const onClose = vi.fn();
    render(
      <AttributeCreateDialog
        scope="global"
        section="general"
        existingNames={[]}
        onCreate={onCreate}
        onClose={onClose}
      />
    );
    fireEvent.change(screen.getByTestId("attribute-create-dialog-name"), {
      target: { value: "risk_comment" },
    });
    fireEvent.click(screen.getByTestId("attribute-create-dialog-submit"));

    await waitFor(() =>
      expect(screen.getByTestId("attribute-create-dialog-error").textContent).toContain(
        "already exists"
      )
    );
    expect(onClose).not.toHaveBeenCalled();
  });
});
