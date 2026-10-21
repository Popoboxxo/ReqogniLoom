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
import { render, screen, cleanup, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { CsvImport } from "./CsvImport";
import { i18n } from "../../i18n/index";
import { importApi, type ImportResult } from "../../api/import";

vi.mock("../../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "ws-001", name: "Test Workspace" } }),
  useOptionalWorkspace: () => ({ activeWorkspace: { id: "ws-001", name: "Test Workspace" } }),
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

describe("CsvImport skipped-row causes (ADR-014 §5 / #1178)", () => {
  /**
   * The legacy CSV-import body as `CsvImportView.post` answers it on the
   * default contract (ADR-014 §5): the counts plus the ADDITIVE `skipped`
   * key — one shallow copy per skipped `result.items` entry, ordered by row
   * number, reusing the contract-v2 item structure
   * (`row`/`identifier`/`kind`/`status`/`cause`).
   *
   * Mirrors the backend fixture of
   * `backend/rest_api/tests/test_csv_import_hardening.py::
   * test_legacy_response_carries_skipped_rows_with_cause`: a re-upload of an
   * already-imported file, where one row is reported as an in-file duplicate
   * and the other by title match against the workspace — the exact message
   * wording the backend's `ImportService._duplicate_item` emits.
   */
  const LEGACY_IMPORT_WITH_SKIPPED: ImportResult = {
    success: true,
    imported_count: 0,
    skipped_count: 2,
    status: "ok",
    errors: [],
    warnings: [],
    skipped: [
      {
        row: 2,
        identifier: "INT04 Req One",
        kind: "Requirement",
        status: "skipped",
        cause: {
          code: "DUPLICATE",
          message:
            "A row with this uid/id/title already exists in the workspace; skipped.",
        },
      },
      {
        row: 3,
        identifier: "INT04 Req Two",
        kind: "Requirement",
        status: "skipped",
        cause: {
          code: "DUPLICATE",
          message: "Duplicate of row 2 in the same file; skipped.",
        },
      },
    ],
  };

  beforeEach(async () => {
    await i18n.changeLanguage("en");
    importCsvMock.mockReset();
  });

  afterEach(() => {
    cleanup();
  });

  it("renders row, identifier and cause for every skipped row", async () => {
    const user = userEvent.setup();
    importCsvMock.mockResolvedValue(LEGACY_IMPORT_WITH_SKIPPED);

    render(<CsvImport />);
    await pickCsv(user, "title\nINT04 Req One\nINT04 Req Two\n");
    await user.click(screen.getByTestId("csv-import-btn"));

    // The skip causes are additive: the success outcome itself is unchanged.
    const box = await screen.findByTestId("csv-import-result");
    expect(box).toHaveAttribute("data-outcome", "imported");
    expect(screen.getByTestId("csv-import-success")).toBeInTheDocument();

    expect(screen.getByTestId("csv-import-skipped-summary")).toHaveTextContent("2");

    const list = screen.getByTestId("csv-import-skipped-list");
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("Row 2");
    expect(items[0]).toHaveTextContent("INT04 Req One");
    expect(items[0]).toHaveTextContent("DUPLICATE");
    expect(items[0]).toHaveTextContent("already exists in the workspace");
    expect(items[1]).toHaveTextContent("Row 3");
    expect(items[1]).toHaveTextContent("INT04 Req Two");
    expect(items[1]).toHaveTextContent("Duplicate of row 2");
  });

  it("renders no skip list for a clean import", async () => {
    const user = userEvent.setup();
    // A clean import answers with an empty `skipped` list, not a missing key.
    importCsvMock.mockResolvedValue(result({ imported_count: 3, skipped: [] }));

    render(<CsvImport />);
    await pickCsv(user, "title\nA\nB\nC\n");
    await user.click(screen.getByTestId("csv-import-btn"));

    const box = await screen.findByTestId("csv-import-result");
    expect(box).toHaveAttribute("data-outcome", "imported");
    expect(screen.getByTestId("csv-import-success")).toBeInTheDocument();
    expect(screen.queryByTestId("csv-import-skipped-list")).not.toBeInTheDocument();
    expect(screen.queryByTestId("csv-import-skipped-summary")).not.toBeInTheDocument();
  });

  it("tolerates a body without the skipped key (backend predating the key)", async () => {
    const user = userEvent.setup();
    // The `result()` factory builds a body with no `skipped` field at all.
    importCsvMock.mockResolvedValue(result({ imported_count: 1 }));

    render(<CsvImport />);
    await pickCsv(user, "title\nA\n");
    await user.click(screen.getByTestId("csv-import-btn"));

    const box = await screen.findByTestId("csv-import-result");
    expect(box).toHaveAttribute("data-outcome", "imported");
    expect(screen.queryByTestId("csv-import-skipped-list")).not.toBeInTheDocument();
  });

  it("degrades gracefully when a skipped entry carries no cause", async () => {
    const user = userEvent.setup();
    importCsvMock.mockResolvedValue(
      result({
        imported_count: 1,
        skipped_count: 1,
        skipped: [
          {
            row: 4,
            identifier: "Orphan Row",
            kind: "Requirement",
            status: "skipped",
          },
        ],
      }),
    );

    render(<CsvImport />);
    await pickCsv(user, "title\nA\n");
    await user.click(screen.getByTestId("csv-import-btn"));

    const list = await screen.findByTestId("csv-import-skipped-list");
    expect(list).toHaveTextContent("Row 4");
    expect(list).toHaveTextContent("Orphan Row");
    // A neutral fallback instead of "[undefined] undefined" or a crash.
    expect(list).toHaveTextContent("no cause reported");
    expect(list).not.toHaveTextContent("undefined");
  });

  it("offers the remaining skipped rows instead of capping the list at 10", async () => {
    const user = userEvent.setup();
    const skipped = Array.from({ length: 12 }, (_, i) => ({
      row: i + 2,
      identifier: `Row ${i + 2}`,
      kind: "Requirement",
      status: "skipped" as const,
      cause: { code: "DUPLICATE", message: "already exists in the workspace" },
    }));
    importCsvMock.mockResolvedValue(result({ skipped }));

    render(<CsvImport />);
    await pickCsv(user, "title\nA\n");
    await user.click(screen.getByTestId("csv-import-btn"));

    const list = await screen.findByTestId("csv-import-skipped-list");
    expect(within(list).getAllByRole("listitem")).toHaveLength(10);

    const toggle = screen.getByTestId("csv-import-toggle-skipped");
    expect(toggle).toHaveTextContent("2");
    await user.click(toggle);

    expect(within(list).getAllByRole("listitem")).toHaveLength(12);
    expect(screen.getByTestId("csv-import-toggle-skipped")).toHaveTextContent(
      "Show fewer",
    );
  });

  it("renders skip causes and dropped-column warnings independently", async () => {
    const user = userEvent.setup();
    importCsvMock.mockResolvedValue({
      ...LEGACY_IMPORT_WITH_SKIPPED,
      warnings: ["Unrecognized column(s) ignored, their data was NOT imported: note."],
    });

    render(<CsvImport />);
    await pickCsv(user, "title,note\nINT04 Req One,x\n");
    await user.click(screen.getByTestId("csv-import-btn"));

    const box = await screen.findByTestId("csv-import-result");
    // A dropped column still marks the outcome as partial, not as a clean
    // success — the skip list must not swallow that signal.
    expect(box).toHaveAttribute("data-outcome", "partial");
    expect(screen.getByTestId("csv-import-warnings")).toHaveTextContent("note");
    const list = screen.getByTestId("csv-import-skipped-list");
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    expect(list).toHaveTextContent("INT04 Req One");
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

describe("CsvImport ReqIF v2 outcome (ADR-014)", () => {
  const importReqifMock = vi.mocked(importApi.importReqif);

  function reqifEnv(overrides: Record<string, unknown> = {}) {
    return {
      created: 0,
      updated: 0,
      skipped: 0,
      failed: 0,
      errors: [],
      items: [],
      ...overrides,
    };
  }

  beforeEach(async () => {
    await i18n.changeLanguage("en");
    importReqifMock.mockReset();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  async function pickReqif(
    user: ReturnType<typeof userEvent.setup>,
  ): Promise<void> {
    const file = new File(["<req-if/>"], "a.reqif", { type: "application/xml" });
    await user.upload(screen.getByTestId("reqif-file-input"), file);
  }

  it("renders the v2 failed items of a 207 partial success", async () => {
    const user = userEvent.setup();
    importReqifMock.mockResolvedValue({
      success: false,
      dry_run: false,
      contract: "v2",
      counts: { succeeded: 1, skipped: 0, failed: 1, total: 2 },
      needs: reqifEnv({ created: 1 }),
      requirements: reqifEnv({
        failed: 1,
        items: [
          {
            row: 2,
            identifier: "REQ-2",
            kind: "Requirement",
            status: "failed",
            cause: { code: "INVALID_VALUE", message: "Title too long" },
          },
        ],
      }),
      relations: reqifEnv(),
      warnings: [],
    });

    render(<CsvImport />);
    await pickReqif(user);
    await user.click(screen.getByTestId("reqif-import-btn"));

    const failedList = await screen.findByTestId("reqif-import-failed-requirements");
    expect(failedList).toHaveTextContent("INVALID_VALUE");
    expect(failedList).toHaveTextContent("Title too long");
    expect(screen.getByTestId("reqif-import-counts")).toHaveTextContent("failed: 1");
  });

  it("flags an idempotent replay", async () => {
    const user = userEvent.setup();
    importReqifMock.mockResolvedValue({
      success: true,
      dry_run: false,
      contract: "v2",
      counts: { succeeded: 1, skipped: 0, failed: 0, total: 1 },
      idempotent_replay: true,
      needs: reqifEnv({ created: 1 }),
      requirements: reqifEnv(),
      relations: reqifEnv(),
      warnings: [],
    });

    render(<CsvImport />);
    await pickReqif(user);
    await user.click(screen.getByTestId("reqif-import-btn"));

    expect(await screen.findByTestId("reqif-import-replay-badge")).toBeInTheDocument();
  });

  it("falls back to a v4 UUID when crypto.randomUUID is unavailable (#1128)", async () => {
    // Secure-context API missing — e.g. a plain-HTTP origin. `getRandomValues`
    // is still there, so a real RFC4122 v4 UUID must be synthesized.
    vi.stubGlobal("crypto", {
      getRandomValues: (array: Uint8Array): Uint8Array => {
        array.fill(0);
        return array;
      },
    });

    const user = userEvent.setup();
    importReqifMock.mockResolvedValue({
      success: true,
      dry_run: false,
      contract: "v2",
      counts: { succeeded: 1, skipped: 0, failed: 0, total: 1 },
      needs: reqifEnv({ created: 1 }),
      requirements: reqifEnv(),
      relations: reqifEnv(),
      warnings: [],
    });

    render(<CsvImport />);
    await pickReqif(user);
    await user.click(screen.getByTestId("reqif-import-btn"));

    await waitFor(() => expect(importReqifMock).toHaveBeenCalled());
    // All-zero bytes with version/variant bits set → deterministic UUID.
    expect(importReqifMock.mock.calls[0][3]).toBe(
      "reqif-00000000-0000-4000-8000-000000000000"
    );
  });

  it("falls back to a time-random id when crypto is entirely absent (#1128)", async () => {
    // No `crypto` at all — the date/random style from canvas-geometry.ts.
    vi.stubGlobal("crypto", {});

    const user = userEvent.setup();
    importReqifMock.mockResolvedValue({
      success: true,
      dry_run: false,
      contract: "v2",
      counts: { succeeded: 1, skipped: 0, failed: 0, total: 1 },
      needs: reqifEnv({ created: 1 }),
      requirements: reqifEnv(),
      relations: reqifEnv(),
      warnings: [],
    });

    render(<CsvImport />);
    await pickReqif(user);
    await user.click(screen.getByTestId("reqif-import-btn"));

    await waitFor(() => expect(importReqifMock).toHaveBeenCalled());
    expect(importReqifMock.mock.calls[0][3]).toMatch(/^reqif-\d+-[0-9a-z]+$/);
  });
});
