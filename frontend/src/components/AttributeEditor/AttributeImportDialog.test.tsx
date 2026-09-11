/**
 * AttributeImportDialog.test.tsx (Task 11, spec section 6).
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

import { AttributeImportDialog } from "./AttributeImportDialog";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

describe("AttributeImportDialog", () => {
  it("defaults to 'skip' and calls onConfirm with the selected on_collision value", async () => {
    const onConfirm = vi.fn().mockResolvedValue(undefined);
    const onClose = vi.fn();
    render(
      <AttributeImportDialog fileName="export.json" onConfirm={onConfirm} onClose={onClose} />
    );
    expect(screen.getByTestId("attribute-import-dialog-on-collision-skip")).toBeChecked();

    fireEvent.click(screen.getByTestId("attribute-import-dialog-confirm"));
    await waitFor(() => expect(onConfirm).toHaveBeenCalledWith("skip"));
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
  });

  it("sends 'overwrite' when that radio is selected", async () => {
    const onConfirm = vi.fn().mockResolvedValue(undefined);
    render(
      <AttributeImportDialog fileName="export.json" onConfirm={onConfirm} onClose={vi.fn()} />
    );
    fireEvent.click(screen.getByTestId("attribute-import-dialog-on-collision-overwrite"));
    fireEvent.click(screen.getByTestId("attribute-import-dialog-confirm"));
    await waitFor(() => expect(onConfirm).toHaveBeenCalledWith("overwrite"));
  });

  it("sends 'rename' when that radio is selected", async () => {
    const onConfirm = vi.fn().mockResolvedValue(undefined);
    render(
      <AttributeImportDialog fileName="export.json" onConfirm={onConfirm} onClose={vi.fn()} />
    );
    fireEvent.click(screen.getByTestId("attribute-import-dialog-on-collision-rename"));
    fireEvent.click(screen.getByTestId("attribute-import-dialog-confirm"));
    await waitFor(() => expect(onConfirm).toHaveBeenCalledWith("rename"));
  });

  it("calls onClose when cancel is clicked, without calling onConfirm", () => {
    const onConfirm = vi.fn();
    const onClose = vi.fn();
    render(
      <AttributeImportDialog fileName="export.json" onConfirm={onConfirm} onClose={onClose} />
    );
    fireEvent.click(screen.getByTestId("attribute-import-dialog-cancel"));
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("shows the rejection message and keeps the dialog open on failure", async () => {
    const onConfirm = vi.fn().mockRejectedValue(new Error("unrecognized schema_version"));
    const onClose = vi.fn();
    render(
      <AttributeImportDialog fileName="export.json" onConfirm={onConfirm} onClose={onClose} />
    );
    fireEvent.click(screen.getByTestId("attribute-import-dialog-confirm"));
    await waitFor(() =>
      expect(screen.getByTestId("attribute-import-dialog-error").textContent).toContain(
        "unrecognized schema_version"
      )
    );
    expect(onClose).not.toHaveBeenCalled();
  });
});
