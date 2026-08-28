/**
 * ARCH-L1-001 ReactFrontend — client-side CSV pre-flight preview (UI-30).
 *
 * leaf_id: COMP-RF-001 (CsvImport)
 * req_id:  REQ-L0-013 (Effiziente Übernahme bestehender Anforderungsdaten),
 *          REQ-L2-AS-014 (CSV Bulk Import),
 *          REQ-L2-RF-016 (Frontend CSV import UI)
 *
 * Why this exists: `ImportService.import_csv` is strictly all-or-nothing
 * (REQ-L3-IMP-002 — one `transaction.atomic()` around every insert). A single
 * unparsable row or a missing `title` therefore rejects the *whole* file, and
 * a mistyped header column is silently dropped without failing anything. Both
 * cost the user a full upload round-trip to discover. This module reproduces
 * exactly the two checks the backend performs on the header/row level so the
 * verdict is visible *before* the upload:
 *
 *   - unrecognised columns  -> `ImportService._unknown_columns` (fix #120)
 *   - missing `title`       -> `ImportService._REQUIRED_FIELDS` (every entity
 *                              type requires a non-empty `title`)
 *
 * It deliberately does NOT re-implement per-value type coercion
 * (`_import_value`); the backend stays the authority for that, and its
 * per-row error list is rendered verbatim after the upload.
 */

import type { EntityType } from "../../api/import";

/**
 * Column names accepted by the backend per entity type.
 *
 * SSOT is `backend/application/export_service.py::ENTITY_FIELD_SPECS` — the
 * same registry drives export serialisation and import deserialisation, so a
 * round-trip is lossless. This mirror exists only to give a pre-flight verdict
 * without an extra endpoint; `backend/rest_api/tests/test_csv_import.py`
 * asserts the two lists stay identical, so a new backend column cannot start
 * being reported as "unknown" here.
 */
export const KNOWN_CSV_COLUMNS: Readonly<Record<EntityType, readonly string[]>> = {
  Requirement: [
    "title",
    "description",
    "category",
    "status",
    "type",
    "level",
    "complexity_fibonacci",
    "verification_method",
    "suspect",
    "lifecycle_status",
    "uid",
    "id",
    "artifact_id",
    "version",
    "created_at",
    "modified_at",
  ],
  ArchitectureElement: [
    "title",
    "description",
    "element_type",
    "asil_level",
    "make_or_buy",
    "suspect",
    "lifecycle_status",
    "uid",
    "id",
    "artifact_id",
    "version",
    "created_at",
    "modified_at",
  ],
  TestCase: [
    "title",
    "description",
    "steps",
    "test_type",
    "suspect",
    "status",
    "uid",
    "id",
    "artifact_id",
    "version",
    "created_at",
    "modified_at",
  ],
};

/** Every entity type requires a non-empty `title` (`_REQUIRED_FIELDS`). */
export const REQUIRED_CSV_COLUMN = "title";

/** Row cap enforced by the backend before any DB write (REQ-L3-IMP-003). */
export const MAX_CSV_ROWS = 1000;

/** Number of data rows shown in the preview table. */
export const PREVIEW_ROW_LIMIT = 5;

export interface CsvPreviewRow {
  /**
   * Row number as the backend counts it: the header is line 1 of the
   * comment-stripped text, data rows start at 2 (`enumerate(reader, start=2)`).
   * Matching the numbering is what lets a post-import `ImportRowError` be tied
   * back to a row the user saw in the preview.
   */
  rowNumber: number;
  cells: readonly string[];
}

export interface CsvPreview {
  headers: readonly string[];
  rows: readonly CsvPreviewRow[];
  /** Total data rows in the file (not just the previewed ones). */
  totalRows: number;
  /** Header columns the backend does not know — their data is dropped. */
  unknownColumns: readonly string[];
  /** True when the required `title` column is absent from the header. */
  missingRequiredColumn: boolean;
  /** Header names occurring more than once — later ones win in DictReader. */
  duplicateColumns: readonly string[];
  /** Row numbers whose `title` cell is empty — the backend rejects the file. */
  rowsWithEmptyTitle: readonly number[];
  /** True when `totalRows` exceeds the backend's hard row cap. */
  exceedsRowLimit: boolean;
  /** Set when the text could not be parsed as CSV at all. */
  parseError: string | null;
}

/**
 * Reads *file* as UTF-8 text.
 *
 * `Blob.prototype.text()` would be the one-liner, but the jsdom build the unit
 * tests run on does not implement it — a preview that only works in the
 * browser is a preview no test can defend. `FileReader` is available in both.
 */
export function readTextFile(file: File): Promise<string> {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ""));
    reader.onerror = () => reject(reader.error ?? new Error("File could not be read"));
    reader.readAsText(file);
  });
}

/**
 * Splits RFC-4180 CSV text into rows of cells.
 *
 * Handles quoted fields containing commas, newlines and escaped (`""`) quotes,
 * and normalises CRLF. Kept local rather than pulling in a parser dependency:
 * the preview needs a few rows and a header, not a full csv library.
 */
function splitCsvRecords(text: string): string[][] {
  const records: string[][] = [];
  let cells: string[] = [];
  let cell = "";
  let inQuotes = false;

  for (let i = 0; i < text.length; i++) {
    const char = text[i];

    if (inQuotes) {
      if (char === '"') {
        if (text[i + 1] === '"') {
          cell += '"';
          i++;
        } else {
          inQuotes = false;
        }
      } else {
        cell += char;
      }
      continue;
    }

    if (char === '"') {
      inQuotes = true;
    } else if (char === ",") {
      cells.push(cell);
      cell = "";
    } else if (char === "\n" || char === "\r") {
      // Consume the LF of a CRLF pair as one terminator.
      if (char === "\r" && text[i + 1] === "\n") i++;
      cells.push(cell);
      records.push(cells);
      cells = [];
      cell = "";
    } else {
      cell += char;
    }
  }

  if (cell !== "" || cells.length > 0) {
    cells.push(cell);
    records.push(cells);
  }

  return records;
}

/**
 * Builds the pre-flight verdict for *csvText*.
 *
 * Mirrors `ImportService._parse_csv`'s comment handling: lines starting with
 * `#` are stripped line-wise *before* parsing (that is what the exporter's
 * terminology header relies on), so the same quirk applies here — a `#` at the
 * start of a line inside a quoted field is dropped on both sides.
 */
export function buildCsvPreview(
  csvText: string,
  entityType: EntityType,
  previewRowLimit: number = PREVIEW_ROW_LIMIT,
): CsvPreview {
  const empty: CsvPreview = {
    headers: [],
    rows: [],
    totalRows: 0,
    unknownColumns: [],
    missingRequiredColumn: false,
    duplicateColumns: [],
    rowsWithEmptyTitle: [],
    exceedsRowLimit: false,
    parseError: null,
  };

  const cleanText = csvText
    .split("\n")
    .map((line) => (line.endsWith("\r") ? line.slice(0, -1) : line))
    .filter((line) => !line.startsWith("#"))
    .join("\n");

  if (!cleanText.trim()) {
    return { ...empty, parseError: "empty" };
  }

  const records = splitCsvRecords(cleanText).filter(
    (record) => !(record.length === 1 && record[0].trim() === ""),
  );
  if (records.length === 0) {
    return { ...empty, parseError: "empty" };
  }

  const headers = records[0].map((h) => h.trim());
  const dataRecords = records.slice(1);

  const known = new Set(KNOWN_CSV_COLUMNS[entityType] ?? []);
  const seen = new Set<string>();
  const duplicateColumns: string[] = [];
  const unknownColumns: string[] = [];
  for (const header of headers) {
    if (seen.has(header)) {
      if (!duplicateColumns.includes(header)) duplicateColumns.push(header);
    }
    seen.add(header);
    if (!known.has(header) && !unknownColumns.includes(header)) {
      unknownColumns.push(header);
    }
  }

  const titleIndex = headers.indexOf(REQUIRED_CSV_COLUMN);
  const rowsWithEmptyTitle: number[] = [];
  if (titleIndex !== -1) {
    dataRecords.forEach((record, idx) => {
      if (!(record[titleIndex] ?? "").trim()) rowsWithEmptyTitle.push(idx + 2);
    });
  }

  const rows: CsvPreviewRow[] = dataRecords
    .slice(0, previewRowLimit)
    .map((record, idx) => ({
      rowNumber: idx + 2,
      cells: headers.map((_, col) => record[col] ?? ""),
    }));

  return {
    headers,
    rows,
    totalRows: dataRecords.length,
    unknownColumns,
    missingRequiredColumn: titleIndex === -1,
    duplicateColumns,
    rowsWithEmptyTitle,
    exceedsRowLimit: dataRecords.length > MAX_CSV_ROWS,
    parseError: null,
  };
}

/**
 * True when the preview found a condition that makes the backend reject the
 * whole file. Purely advisory — the import button stays enabled so the backend
 * keeps the final word (its per-row report is strictly more precise).
 */
export function previewHasBlockingIssue(preview: CsvPreview): boolean {
  return (
    preview.parseError !== null ||
    preview.missingRequiredColumn ||
    preview.rowsWithEmptyTitle.length > 0 ||
    preview.exceedsRowLimit
  );
}
