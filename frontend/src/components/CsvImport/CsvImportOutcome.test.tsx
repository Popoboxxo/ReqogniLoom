/**
 * ARCH-L1-001 ReactFrontend — CsvImport outcome states + error report (UI-30).
 *
 * leaf_id: COMP-RF-001 (CsvImport)
 * req_id:  REQ-L0-013 (CSV bulk import), REQ-L2-RF-016 (Frontend CSV import UI)
 *
 * Three regressions are pinned here:
 *
 *  1. A rejected import rendered nothing but "Import failed" — the per-row
 *     report never reached the DOM because the API client turned the HTTP 400
 *     (which carries the full ImportResult) into an opaque Error.
 *  2. A successful import that silently dropped an unrecognised column was
 *     painted as a clean green success, hiding the backend's `warnings`.
 *  3. The error list was sliced to 10 entries with no way to see the rest.
 */

import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { render, screen, cleanup, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { CsvImport } from "./CsvImport";
import { i18n } from "../../i18n/index";
import { importApi, type ImportResult } from "../../api/import";

vi.mock("../../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "ws-001", name: "Test Workspace" } }),
}));

vi.mock("../../api/import", () => ({
  importApi: { importCsv: vi.fn(), importReqif: vi.fn() },
}));

vi.mock("../../api/export", () => ({
  exportApi: { downloadCsv: vi.fn(), downloadReqif: vi.fn() },
}));

const importCsvMock = vi.mocked(importApi.importCsv);

function result(overrides: Partial<ImportResult>): ImportResult {
  return {
    success: true,
    imported_count: 0,
    skipped_count: 0,
    status: "ok",
    errors: [],
    warnings: [],
    ...overrides,
  };
}

/** Picks a CSV file through the hidden input, mirroring a real selection. */
async function pickCsv(user: ReturnType<typeof userEvent.setup>, content: string): Promise<void> {
  const file = new File([content], "rows.csv", { type: "text/csv" });
  await user.upload(screen.getByTestId("csv-file-input"), file);
}

describe("CsvImport outcomes (UI-30)", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en");
    importCsvMock.mockReset();
  });

  afterEach(() => {
    cleanup();
  });

  it("renders a plain success when nothing was dropped", async () => {
    const user = userEvent.setup();
    importCsvMock.mockResolvedValue(result({ imported_count: 3 }));

    render(<CsvImport />);
    await pickCsv(user, "title\nA\nB\nC\n");
    await user.click(screen.getByTestId("csv-import-btn"));

    const box = await screen.findByTestId("csv-import-result");
    expect(box).toHaveAttribute("data-outcome", "imported");
    expect(screen.queryByTestId("csv-import-warnings")).not.toBeInTheDocument();
    // `import.statusValue.<status>` is a nested lookup — a missing branch
    // would render the raw key path instead of a label.
    expect(box).not.toHaveTextContent("import.statusValue");
    expect(box).toHaveTextContent("Status: OK");
  });

  it("marks an import that dropped a column as partial, not as a clean success", async () => {
    const user = userEvent.setup();
    importCsvMock.mockResolvedValue(
      result({
        imported_count: 3,
        warnings: ["Unrecognized column(s) ignored, their data was NOT imported: Beschreibung."],
      }),
    );

    render(<CsvImport />);
    await pickCsv(user, "title,Beschreibung\nA,x\n");
    await user.click(screen.getByTestId("csv-import-btn"));

    const box = await screen.findByTestId("csv-import-result");
    expect(box).toHaveAttribute("data-outcome", "partial");
    expect(screen.getByTestId("csv-import-warnings")).toHaveTextContent("Beschreibung");
  });

  it("renders the per-row error report of a rejected import", async () => {
    const user = userEvent.setup();
    importCsvMock.mockResolvedValue(
      result({
        success: false,
        status: "validation_error",
        skipped_count: 2,
        errors: [
          { row_number: 2, field: "title", message: "Required field is empty" },
          { row_number: 3, field: "level", message: "not an integer" },
        ],
      }),
    );

    render(<CsvImport />);
    await pickCsv(user, "title,level\n,1\nB,x\n");
    await user.click(screen.getByTestId("csv-import-btn"));

    const box = await screen.findByTestId("csv-import-result");
    expect(box).toHaveAttribute("data-outcome", "rejected");
    const list = screen.getByTestId("csv-import-error-list");
    expect(list).toHaveTextContent("Required field is empty");
    expect(list).toHaveTextContent("not an integer");
    // The import is one transaction — say so instead of leaving the user to
    // guess whether the first row landed.
    expect(screen.getByTestId("csv-import-atomicity-note")).toBeInTheDocument();
  });

  it("offers the remaining errors instead of silently capping at 10", async () => {
    const user = userEvent.setup();
    const errors = Array.from({ length: 14 }, (_, i) => ({
      row_number: i + 2,
      field: "title",
      message: `problem ${i}`,
    }));
    importCsvMock.mockResolvedValue(
      result({ success: false, status: "validation_error", skipped_count: 14, errors }),
    );

    render(<CsvImport />);
    await pickCsv(user, "title\nA\n");
    await user.click(screen.getByTestId("csv-import-btn"));

    await screen.findByTestId("csv-import-error-list");
    expect(screen.getAllByRole("listitem").length).toBe(10);

    const toggle = screen.getByTestId("csv-import-toggle-errors");
    expect(toggle).toHaveTextContent("4");
    await user.click(toggle);

    expect(screen.getAllByRole("listitem").length).toBe(14);
  });
});

describe("CsvImport pre-flight preview (UI-30)", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en");
    importCsvMock.mockReset();
  });

  afterEach(() => {
    cleanup();
  });

  it("shows the first rows and flags unrecognised columns before uploading", async () => {
    const user = userEvent.setup();
    render(<CsvImport />);

    await pickCsv(user, "title,Beschreibung\nA,x\nB,y\n");

    await waitFor(() => expect(screen.getByTestId("csv-preview")).toBeInTheDocument());
    expect(screen.getAllByTestId("csv-preview-row")).toHaveLength(2);
    expect(screen.getByTestId("csv-preview-unknown-columns")).toHaveTextContent("Beschreibung");
    expect(importCsvMock).not.toHaveBeenCalled();
  });

  it("re-evaluates the columns when the entity type changes", async () => {
    const user = userEvent.setup();
    render(<CsvImport />);

    await pickCsv(user, "title,element_type\nA,block\n");
    await waitFor(() => expect(screen.getByTestId("csv-preview")).toBeInTheDocument());
    // `element_type` is unknown for the default Requirement type...
    expect(screen.getByTestId("csv-preview-unknown-columns")).toBeInTheDocument();

    await user.click(screen.getByTestId("entity-type-ArchitectureElement"));

    // ...and known once the matching entity type is selected.
    await waitFor(() =>
      expect(screen.queryByTestId("csv-preview-unknown-columns")).not.toBeInTheDocument(),
    );
  });

  it("warns up front about a missing required title column", async () => {
    const user = userEvent.setup();
    render(<CsvImport />);

    await pickCsv(user, "description,category\nx,functional\n");

    await waitFor(() => expect(screen.getByTestId("csv-preview-blocking")).toBeInTheDocument());
  });
});

describe("CsvImport drop zone keyboard operation (UI-30)", () => {
  afterEach(() => cleanup());

  it("exposes both drop zones as focusable buttons", async () => {
    await i18n.changeLanguage("en");
    render(<CsvImport />);

    for (const testId of ["csv-drop-zone", "reqif-file-picker"]) {
      const zone = screen.getByTestId(testId);
      expect(zone).toHaveAttribute("role", "button");
      expect(zone).toHaveAttribute("tabindex", "0");
      expect(zone).toHaveAccessibleName();
    }
  });

  it("opens the file dialog on Enter and Space", async () => {
    await i18n.changeLanguage("en");
    const user = userEvent.setup();
    render(<CsvImport />);

    const input = screen.getByTestId("csv-file-input") as HTMLInputElement;
    const click = vi.spyOn(input, "click").mockImplementation(() => undefined);

    screen.getByTestId("csv-drop-zone").focus();
    await user.keyboard("{Enter}");
    await user.keyboard(" ");

    expect(click).toHaveBeenCalledTimes(2);
  });
});
