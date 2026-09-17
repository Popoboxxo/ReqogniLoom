import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/react";

import { PermissionMatrixEditor } from "./PermissionMatrixEditor";
import { i18n } from "../../i18n/index";
import { normalizeMatrix } from "../../api/permission-defaults";

describe("PermissionMatrixEditor i18n (#659)", () => {
  afterEach(() => {
    cleanup();
    void i18n.changeLanguage("en");
  });

  it("renders capability column headers in German when locale is de", () => {
    void i18n.changeLanguage("de");
    const matrix = normalizeMatrix({
      admin: { read: true, write: true },
      editor: { read: true, write: false },
      viewer: { read: true, write: false },
      approver: { read: true, write: false },
    });

    render(<PermissionMatrixEditor value={matrix} onSave={vi.fn()} />);

    expect(screen.getByText("Lesen")).toBeInTheDocument();
    expect(screen.getByText("Schreiben")).toBeInTheDocument();
    expect(screen.queryByText("Read")).not.toBeInTheDocument();
  });
});

// -----------------------------------------------------------------------
// UI-40 (Systemaudit 2026-08-27 AP-5): unsaved-changes protection.
// -----------------------------------------------------------------------
describe("PermissionMatrixEditor unsaved-changes guard (UI-40)", () => {
  afterEach(() => {
    cleanup();
  });

  const MATRIX = normalizeMatrix({
    admin: { read: true, write: true },
    editor: { read: true, write: false },
    viewer: { read: true, write: false },
    approver: { read: true, write: false },
  });

  it("does not block a tab close/reload while the grid is clean", () => {
    render(<PermissionMatrixEditor value={MATRIX} onSave={vi.fn()} />);

    const event = fireEvent(window, new Event("beforeunload", { cancelable: true }));
    // jsdom's fireEvent returns false only if preventDefault() was called.
    expect(event).toBe(true);
  });

  it("blocks a tab close/reload once a checkbox is toggled", () => {
    render(<PermissionMatrixEditor value={MATRIX} onSave={vi.fn()} />);

    fireEvent.click(screen.getByTestId("permission-matrix-cell-editor-write"));

    const event = fireEvent(window, new Event("beforeunload", { cancelable: true }));
    expect(event).toBe(false);
  });

  it("stops blocking again once the change is saved back into `value`", () => {
    const { rerender } = render(<PermissionMatrixEditor value={MATRIX} onSave={vi.fn()} />);

    fireEvent.click(screen.getByTestId("permission-matrix-cell-editor-write"));
    expect(fireEvent(window, new Event("beforeunload", { cancelable: true }))).toBe(false);

    // Parent re-fetches/re-syncs `value` after a successful save.
    rerender(
      <PermissionMatrixEditor
        value={normalizeMatrix({
          admin: { read: true, write: true },
          editor: { read: true, write: true },
          viewer: { read: true, write: false },
          approver: { read: true, write: false },
        })}
        onSave={vi.fn()}
      />
    );

    expect(fireEvent(window, new Event("beforeunload", { cancelable: true }))).toBe(true);
  });
});
