import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";

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
