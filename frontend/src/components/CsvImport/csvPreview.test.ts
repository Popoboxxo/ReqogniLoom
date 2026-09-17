/**
 * ARCH-L1-001 ReactFrontend — CSV pre-flight preview (UI-30).
 *
 * leaf_id: COMP-RF-001 (CsvImport)
 * req_id:  REQ-L2-RF-016 (Frontend CSV import UI)
 *
 * The preview's whole value is that its verdict matches what
 * `ImportService.import_csv` would say, so these cases pin the two rules it
 * mirrors (unknown columns, required `title`) plus the parsing quirks the
 * backend has (comment lines, RFC-4180 quoting, backend row numbering).
 */

import { describe, expect, it } from "vitest";

import {
  buildCsvPreview,
  previewHasBlockingIssue,
  KNOWN_CSV_COLUMNS,
  MAX_CSV_ROWS,
} from "./csvPreview";

describe("buildCsvPreview", () => {
  it("numbers data rows the way the backend does (header is line 1)", () => {
    const preview = buildCsvPreview("title,description\nA,one\nB,two\n", "Requirement");

    expect(preview.totalRows).toBe(2);
    expect(preview.rows.map((r) => r.rowNumber)).toEqual([2, 3]);
    expect(preview.rows[0].cells).toEqual(["A", "one"]);
  });

  it("caps the rendered rows without misreporting the total", () => {
    const body = Array.from({ length: 20 }, (_, i) => `T${i},d`).join("\n");
    const preview = buildCsvPreview(`title,description\n${body}\n`, "Requirement", 3);

    expect(preview.rows).toHaveLength(3);
    expect(preview.totalRows).toBe(20);
  });

  it("flags header columns the backend does not know", () => {
    const preview = buildCsvPreview(
      "title,Beschreibung,category\nA,x,functional\n",
      "Requirement",
    );

    expect(preview.unknownColumns).toEqual(["Beschreibung"]);
    // A dropped column is data loss, but the import itself still succeeds —
    // exactly the "partial" case, so it must not read as blocking.
    expect(previewHasBlockingIssue(preview)).toBe(false);
  });

  it("treats a column as unknown per entity type, not globally", () => {
    const csv = "title,element_type\nA,block\n";

    expect(buildCsvPreview(csv, "ArchitectureElement").unknownColumns).toEqual([]);
    expect(buildCsvPreview(csv, "TestCase").unknownColumns).toEqual(["element_type"]);
  });

  it("blocks when the required title column is missing", () => {
    const preview = buildCsvPreview("description,category\nx,functional\n", "Requirement");

    expect(preview.missingRequiredColumn).toBe(true);
    expect(previewHasBlockingIssue(preview)).toBe(true);
  });

  it("blocks and names the rows whose title cell is empty", () => {
    const preview = buildCsvPreview("title,description\nA,one\n,two\nC,three\n", "Requirement");

    expect(preview.rowsWithEmptyTitle).toEqual([3]);
    expect(previewHasBlockingIssue(preview)).toBe(true);
  });

  it("reports duplicate header columns", () => {
    const preview = buildCsvPreview("title,title,description\nA,B,c\n", "Requirement");

    expect(preview.duplicateColumns).toEqual(["title"]);
  });

  it("strips comment lines the way ImportService._parse_csv does", () => {
    const preview = buildCsvPreview(
      "# terminology: se_mode\ntitle,description\nA,one\n",
      "Requirement",
    );

    expect(preview.headers).toEqual(["title", "description"]);
    expect(preview.totalRows).toBe(1);
  });

  it("keeps commas, newlines and escaped quotes inside quoted fields", () => {
    const preview = buildCsvPreview(
      'title,description\n"A, with comma","line1\nline2"\n"say ""hi""",x\n',
      "Requirement",
    );

    expect(preview.totalRows).toBe(2);
    expect(preview.rows[0].cells).toEqual(["A, with comma", "line1\nline2"]);
    expect(preview.rows[1].cells[0]).toBe('say "hi"');
  });

  it("blocks when the file exceeds the backend row cap", () => {
    const body = Array.from({ length: MAX_CSV_ROWS + 1 }, (_, i) => `T${i}`).join("\n");
    const preview = buildCsvPreview(`title\n${body}\n`, "Requirement");

    expect(preview.exceedsRowLimit).toBe(true);
    expect(previewHasBlockingIssue(preview)).toBe(true);
  });

  it("reports an empty file as unparsable rather than an empty success", () => {
    const preview = buildCsvPreview("   \n", "Requirement");

    expect(preview.parseError).toBe("empty");
    expect(previewHasBlockingIssue(preview)).toBe(true);
  });

  it("lists `title` as a known column for every supported entity type", () => {
    for (const columns of Object.values(KNOWN_CSV_COLUMNS)) {
      expect(columns).toContain("title");
    }
  });
});
