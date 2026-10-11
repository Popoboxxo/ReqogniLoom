/**
 * ARCH-L1-001 ReactFrontend — CsvImport (REQ-L0-013, REQ-L2-RF-016).
 *
 * leaf_id: COMP-RF-001 (NavigationShell scope — CSV import UI)
 * req_id:  REQ-L0-013 (Effiziente Übernahme bestehender Anforderungsdaten),
 *          REQ-L2-AS-014 (CSV Bulk Import),
 *          REQ-L2-RF-016 (Frontend CSV import UI)
 *
 * Features:
 *   - File picker / drop zone for CSV upload (pointer and keyboard operable)
 *   - Entity-type selector (Requirement / ArchitectureElement / TestCase)
 *   - Pre-flight row preview with column recognition (UI-30)
 *   - Progress indicator during upload
 *   - Result display: imported / partially-imported / rejected, with the full
 *     per-row error report (UI-30)
 *   - i18n support (de/en)
 *
 * UI-30 outcome model — why there is no row-level "partial success":
 * `ImportService.import_csv` writes every row inside a single
 * `transaction.atomic()` (REQ-L3-IMP-002), so a file either lands completely
 * or not at all; `imported_count > 0` together with `errors` is unreachable by
 * construction. The state the audit was after does exist though, one level up:
 * an import can succeed *and* have silently dropped an unrecognised column
 * (`warnings`, fix #120). That is the "partial" outcome rendered below, and it
 * is deliberately not painted green.
 */

import { useState, useCallback, useRef } from "react";
import { useTranslation } from "react-i18next";
import { useWorkspace } from "../../context/WorkspaceContext";
import {
  importApi,
  type EntityType,
  type ImportResult,
  type ReqifImportResult,
} from "../../api/import";
import { exportApi, type ExportEntityType } from "../../api/export";
import { PageHeader } from "../shared/PageHeader";
import { Spinner } from "../shared/Spinner/Spinner";
import { ENTITY_TYPE_I18N_KEYS } from "../../constants/entityTypeLabels";
import {
  buildCsvPreview,
  previewHasBlockingIssue,
  readTextFile,
  MAX_CSV_ROWS,
  PREVIEW_ROW_LIMIT,
  type CsvPreview,
} from "./csvPreview";
import styles from "./CsvImport.module.css";

// ---------------------------------------------------------------------------
// Entity type options
// ---------------------------------------------------------------------------

const ENTITY_TYPES: EntityType[] = [
  "Requirement",
  "ArchitectureElement",
  "TestCase",
];

// C7 (frontend-feedback Cluster C): MVP export scope — Requirements,
// StakeholderNeeds, ArchitectureElements.
const EXPORT_ENTITY_TYPES: ExportEntityType[] = [
  "Requirement",
  "StakeholderNeed",
  "ArchitectureElement",
];

/**
 * Error rows shown before the "show all" toggle. The list used to be sliced to
 * this many entries with no way back — a 400-row file reported 10 problems and
 * hid the rest (UI-30).
 */
const ERROR_PREVIEW_LIMIT = 10;

/**
 * Semantic outcome of a finished import, derived from the backend result.
 *
 * `partial` is *not* "some rows failed" (impossible, see the module docstring)
 * but "all rows landed, yet the file carried columns the backend does not know
 * and threw their data away".
 */
type ImportOutcome = "imported" | "partial" | "rejected";

function outcomeOf(result: ImportResult): ImportOutcome {
  if (!result.success) return "rejected";
  return result.warnings.length > 0 ? "partial" : "imported";
}

/**
 * Generate a v4 UUID for a new ReqIF idempotency scope.
 *
 * `crypto.randomUUID` only exists in secure contexts (HTTPS/localhost); on a
 * plain-HTTP origin it is `undefined` and calling it would abort the file
 * selection. Fall back to building an RFC4122 v4 UUID from `getRandomValues`
 * when available, and finally to the `Date.now()`/`Math.random()` id style
 * used by canvas-geometry.ts when `crypto` itself is missing.
 */
function generateIdempotencyUuid(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  if (typeof crypto !== "undefined" && typeof crypto.getRandomValues === "function") {
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    // RFC4122 v4: version 4 in byte 6, variant 10xx in byte 8.
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = Array.from(bytes, (b): string => b.toString(16).padStart(2, "0"));
    return (
      `${hex.slice(0, 4).join("")}-${hex.slice(4, 6).join("")}-` +
      `${hex.slice(6, 8).join("")}-${hex.slice(8, 10).join("")}-${hex.slice(10, 16).join("")}`
    );
  }
  // `Math.random()` may return exactly 0, whose base-36 form is "0" — `.slice(2)`
  // then yields an empty suffix and the id degrades to `reqif-<ts>-`, breaking the
  // `^reqif-\d+-[0-9a-z]+$` contract. Retry once, then pin a non-empty token.
  const rand = Math.random().toString(36).slice(2) || Math.random().toString(36).slice(2) || "0";
  return `${Date.now()}-${rand}`;
}

interface EntityTypeRadioGroupProps<T extends string> {
  name: string;
  options: readonly T[];
  selected: T;
  onSelect: (type: T) => void;
  groupClassName: string;
  testIdPrefix: string;
}

function EntityTypeRadioGroup<T extends string>({
  name,
  options,
  selected,
  onSelect,
  groupClassName,
  testIdPrefix,
}: EntityTypeRadioGroupProps<T>): JSX.Element {
  const { t } = useTranslation();
  return (
    <div className={groupClassName}>
      {options.map((type) => (
        <label
          key={type}
          className={selected === type ? styles.radioLabelActive : styles.radioLabel}
        >
          <input
            type="radio"
            name={name}
            value={type}
            checked={selected === type}
            onChange={() => onSelect(type)}
            data-testid={`${testIdPrefix}${type}`}
          />
          {t(ENTITY_TYPE_I18N_KEYS[type] ?? type)}
        </label>
      ))}
    </div>
  );
}

interface CsvDropZoneProps {
  fileInputRef: React.RefObject<HTMLInputElement | null>;
  isDragOver: boolean;
  selectedFile: File | null;
  onFileSelect: (event: React.ChangeEvent<HTMLInputElement>) => void;
  onDrop: (event: React.DragEvent<HTMLDivElement>) => void;
  onDragOver: (event: React.DragEvent<HTMLDivElement>) => void;
  onDragLeave: (event: React.DragEvent<HTMLDivElement>) => void;
  onKeyDown: (event: React.KeyboardEvent<HTMLDivElement>) => void;
}

function CsvDropZone({
  fileInputRef,
  isDragOver,
  selectedFile,
  onFileSelect,
  onDrop,
  onDragOver,
  onDragLeave,
  onKeyDown,
}: CsvDropZoneProps): JSX.Element {
  const { t } = useTranslation();
  return (
    <section className={styles.card}>
      {/* Drop zone / file picker */}
      <h3 className={styles.cardTitle}>{t("import.selectFile", "Select CSV File")}</h3>
      <div
        data-testid="csv-drop-zone"
        role="button"
        tabIndex={0}
        aria-label={t("import.dropZoneLabel")}
        onDrop={onDrop}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onClick={() => fileInputRef.current?.click()}
        onKeyDown={onKeyDown}
        className={isDragOver ? styles.dropZoneActive : styles.dropZone}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".csv"
          onChange={onFileSelect}
          onClick={(event) => event.stopPropagation()}
          data-testid="csv-file-input"
          className={styles.hiddenFileInput}
        />
        {selectedFile ? (
          <div>
            <p className={styles.fileName}>{selectedFile.name}</p>
            <p className={styles.fileMeta}>{(selectedFile.size / 1024).toFixed(1)} KB</p>
          </div>
        ) : (
          <p className={styles.hintText}>
            {t("import.dropHint", "Drop CSV file here or click to browse")}
          </p>
        )}
      </div>
    </section>
  );
}

interface CsvPreviewPanelProps {
  preview: CsvPreview;
}

function CsvPreviewPanel({ preview }: CsvPreviewPanelProps): JSX.Element {
  const { t } = useTranslation();
  return (
    <section data-testid="csv-preview" className={styles.card}>
      <h3 className={styles.cardTitle}>{t("import.previewTitle")}</h3>

      {preview.parseError ? (
        <p data-testid="csv-preview-parse-error" role="alert" className={styles.failText}>
          {t("import.previewUnparsable")}
        </p>
      ) : (
        <>
          <p data-testid="csv-preview-summary" className={styles.fileMeta}>
            {t("import.previewSummary", {
              rows: preview.totalRows,
              columns: preview.headers.length,
              shown: Math.min(preview.rows.length, PREVIEW_ROW_LIMIT),
            })}
          </p>

          {previewHasBlockingIssue(preview) && (
            <ul data-testid="csv-preview-blocking" role="alert" className={styles.blockingList}>
              {preview.missingRequiredColumn && (
                <li>{t("import.previewMissingTitleColumn")}</li>
              )}
              {preview.rowsWithEmptyTitle.length > 0 && (
                <li>
                  {t("import.previewEmptyTitleRows", {
                    count: preview.rowsWithEmptyTitle.length,
                    rows: preview.rowsWithEmptyTitle.slice(0, 5).join(", "),
                  })}
                </li>
              )}
              {preview.exceedsRowLimit && (
                <li>{t("import.previewRowLimit", { max: MAX_CSV_ROWS })}</li>
              )}
            </ul>
          )}

          {preview.unknownColumns.length > 0 && (
            <p data-testid="csv-preview-unknown-columns" className={styles.warningText}>
              {t("import.previewUnknownColumns", {
                columns: preview.unknownColumns.join(", "),
              })}
            </p>
          )}

          {preview.duplicateColumns.length > 0 && (
            <p data-testid="csv-preview-duplicate-columns" className={styles.warningText}>
              {t("import.previewDuplicateColumns", {
                columns: preview.duplicateColumns.join(", "),
              })}
            </p>
          )}

          {preview.rows.length > 0 && (
            <div className={styles.previewTableWrap}>
              <table data-testid="csv-preview-table" className={styles.previewTable}>
                <caption className={styles.srOnly}>{t("import.previewTableCaption")}</caption>
                <thead>
                  <tr>
                    <th scope="col" className={styles.previewRowNumHeader}>
                      {t("import.previewRowColumn")}
                    </th>
                    {preview.headers.map((header, idx) => (
                      <th
                        key={`${header}-${idx}`}
                        scope="col"
                        data-unknown={
                          preview.unknownColumns.includes(header) ? "true" : undefined
                        }
                        className={
                          preview.unknownColumns.includes(header)
                            ? styles.previewHeaderUnknown
                            : styles.previewHeader
                        }
                      >
                        {header}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {preview.rows.map((row) => (
                    <tr key={row.rowNumber} data-testid="csv-preview-row">
                      <th scope="row" className={styles.previewRowNum}>
                        {row.rowNumber}
                      </th>
                      {row.cells.map((cell, idx) => (
                        <td key={idx} className={styles.previewCell}>
                          {cell}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  );
}

interface ImportResultPanelProps {
  result: ImportResult;
  showAllErrors: boolean;
  onToggleShowAllErrors: () => void;
}

function ImportResultPanel({
  result,
  showAllErrors,
  onToggleShowAllErrors,
}: ImportResultPanelProps): JSX.Element {
  const { t } = useTranslation();
  return (
    <div
      data-testid="csv-import-result"
      data-outcome={outcomeOf(result)}
      className={
        outcomeOf(result) === "imported"
          ? styles.resultBoxSuccess
          : outcomeOf(result) === "partial"
          ? styles.resultBoxWarning
          : styles.resultBoxError
      }
    >
      {result.success ? (
        <div>
          <p
            data-testid="csv-import-success"
            className={
              outcomeOf(result) === "partial" ? styles.warningText : styles.successText
            }
          >
            {outcomeOf(result) === "partial"
              ? t("import.partialSuccess", { count: result.imported_count })
              : t("import.success", { count: result.imported_count })}
          </p>
          <p className={styles.fileMeta}>
            {t("import.statusLabel")}: {t(`import.statusValue.${result.status}`)}
          </p>
        </div>
      ) : (
        <div>
          <p data-testid="csv-import-failed" className={styles.failText}>
            {result.status === "rollback"
              ? t("import.failedRollback")
              : t("import.failedValidation")}
          </p>
          {/* REQ-L3-IMP-002: the import is one transaction, so a rejected
              file changed nothing at all. Saying so explicitly is the
              difference between "retry after fixing" and "check what
              landed". */}
          <p data-testid="csv-import-atomicity-note" className={styles.fileMeta}>
            {t("import.nothingWritten", { count: result.skipped_count })}
          </p>

          {result.errors.length > 0 && (
            <>
              <ul data-testid="csv-import-error-list" className={styles.errorList}>
                {(showAllErrors
                  ? result.errors
                  : result.errors.slice(0, ERROR_PREVIEW_LIMIT)
                ).map((err, idx) => (
                  <li key={idx} className={styles.errorListItem}>
                    {t("import.errorRow", {
                      row: err.row_number,
                      field: err.field,
                      message: err.message,
                    })}
                  </li>
                ))}
              </ul>
              {result.errors.length > ERROR_PREVIEW_LIMIT && (
                <button
                  type="button"
                  data-testid="csv-import-toggle-errors"
                  onClick={onToggleShowAllErrors}
                  className={styles.linkBtn}
                  aria-expanded={showAllErrors}
                >
                  {showAllErrors
                    ? t("import.showFewerErrors")
                    : t("import.moreErrors", {
                        count: result.errors.length - ERROR_PREVIEW_LIMIT,
                      })}
                </button>
              )}
            </>
          )}
        </div>
      )}

      {/* Dropped-column notice — the one signal a green "imported N rows"
          box would otherwise swallow (fix #120). */}
      {result.warnings.length > 0 && (
        <ul data-testid="csv-import-warnings" className={styles.warningList}>
          {result.warnings.map((warning, idx) => (
            <li key={idx} className={styles.warningListItem}>
              {warning}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

interface ReqifImportSectionProps {
  fileInputRef: React.RefObject<HTMLInputElement | null>;
  dropZoneKeyDown: (event: React.KeyboardEvent<HTMLDivElement>) => void;
  selectedFile: File | null;
  onFileSelect: (event: React.ChangeEvent<HTMLInputElement>) => void;
  dryRun: boolean;
  onDryRunChange: (checked: boolean) => void;
  isImporting: boolean;
  onImport: () => void;
  importResult: ReqifImportResult | null;
  importError: string | null;
  onReset: () => void;
}

function ReqifImportSection({
  fileInputRef,
  dropZoneKeyDown,
  selectedFile,
  onFileSelect,
  dryRun,
  onDryRunChange,
  isImporting,
  onImport,
  importResult,
  importError,
  onReset,
}: ReqifImportSectionProps): JSX.Element {
  const { t } = useTranslation();
  return (
    <>
      {/* ReqIF Import (REQ-147) */}
      <h2 className={styles.sectionHeading}>{t("import.reqifTitle")}</h2>

      <section data-testid="reqif-import-page" className={styles.card}>
        <h3 className={styles.cardTitle}>{t("import.reqifSelectFile")}</h3>
        <div
          data-testid="reqif-file-picker"
          role="button"
          tabIndex={0}
          aria-label={t("import.reqifDropZoneLabel")}
          onClick={() => fileInputRef.current?.click()}
          onKeyDown={dropZoneKeyDown}
          className={styles.filePicker}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".reqif,.xml"
            onChange={onFileSelect}
            onClick={(event) => event.stopPropagation()}
            data-testid="reqif-file-input"
            className={styles.hiddenFileInput}
          />
          {selectedFile ? (
            <div>
              <p className={styles.fileName}>{selectedFile.name}</p>
              <p className={styles.fileMeta}>{(selectedFile.size / 1024).toFixed(1)} KB</p>
            </div>
          ) : (
            <p className={styles.hintText}>
              {t("import.reqifDropHint")}
            </p>
          )}
        </div>

        <label className={styles.checkboxLabel}>
          <input
            type="checkbox"
            checked={dryRun}
            onChange={(e) => onDryRunChange(e.target.checked)}
            data-testid="reqif-dry-run-checkbox"
          />
          {t("import.reqifDryRun")}
        </label>

        <div className={styles.actionsRow}>
          <button
            type="button"
            data-testid="reqif-import-btn"
            onClick={() => void onImport()}
            disabled={!selectedFile || isImporting}
            className={styles.primaryBtn}
          >
            {isImporting ? (
              <Spinner label={t("import.uploading")} />
            ) : dryRun ? (
              t("import.reqifPreview")
            ) : (
              t("import.reqifUpload")
            )}
          </button>
          {(importResult || importError) && (
            <button
              type="button"
              data-testid="reqif-import-reset"
              onClick={onReset}
              className={styles.resetBtn}
            >
              {t("actions.reset")}
            </button>
          )}
        </div>

        {importError && (
          <div data-testid="reqif-import-error" role="alert" className={styles.errorBox}>
            {importError}
          </div>
        )}

        {importResult && (
          <div data-testid="reqif-import-result" className={styles.resultBoxPlain}>
            {importResult.dry_run && (
              <p data-testid="reqif-import-dry-run-badge" className={styles.dryRunBadge}>
                {t("import.reqifDryRunBadge")}
              </p>
            )}

            {importResult.idempotent_replay && (
              <p data-testid="reqif-import-replay-badge" className={styles.dryRunBadge}>
                {t("import.reqifIdempotentReplay", "Replay of an earlier import — no second write.")}
              </p>
            )}

            {importResult.counts && (
              <p data-testid="reqif-import-counts" className={styles.reportLine}>
                {t("import.reqifCounts", {
                  succeeded: importResult.counts.succeeded,
                  skipped: importResult.counts.skipped,
                  failed: importResult.counts.failed,
                  defaultValue:
                    "Succeeded: {{succeeded}}, skipped: {{skipped}}, failed: {{failed}}",
                })}
              </p>
            )}

            {(
              [
                ["needs", t("import.reqifNeeds")],
                ["requirements", t("import.reqifRequirements")],
                ["relations", t("import.reqifRelations")],
              ] as const
            ).map(([key, label]) => {
              const report = importResult[key];
              return (
                <div key={key} className={styles.reportBlock}>
                  <p className={styles.reportLine}>
                    {label}: {t("import.reqifCreated")} {report.created},{" "}
                    {t("import.reqifUpdated")} {report.updated},{" "}
                    {t("import.reqifSkipped")} {report.skipped}
                  </p>
                  {report.errors.length > 0 && (
                    <ul className={styles.errorList}>
                      {report.errors.slice(0, 10).map((err, idx) => (
                        <li key={idx} className={styles.errorListItem}>
                          {err.identifier}: {err.message}
                        </li>
                      ))}
                      {report.errors.length > 10 && (
                        <li className={styles.errorListMore}>
                          {t("import.reqifMoreErrors", { count: report.errors.length - 10 })}
                        </li>
                      )}
                    </ul>
                  )}
                  {/* ADR-014 §1: failed objects are first-class in v2 — render
                      them from the structured items (errors is failures-only
                      but the items list is authoritative). */}
                  {report.items.filter((item) => item.status === "failed").length > 0 && (
                    <ul data-testid={`reqif-import-failed-${key}`} className={styles.errorList}>
                      {report.items
                        .filter((item) => item.status === "failed")
                        .slice(0, 10)
                        .map((item, idx) => (
                          <li key={idx} className={styles.errorListItem}>
                            {item.identifier ?? "-"}: [{item.cause.code}] {item.cause.message}
                          </li>
                        ))}
                    </ul>
                  )}
                </div>
              );
            })}

            {importResult.warnings.length > 0 && (
              <div>
                <p className={styles.reportLine}>{t("import.reqifWarnings")}</p>
                <ul className={styles.errorList}>
                  {importResult.warnings.slice(0, 10).map((warning, idx) => (
                    <li key={idx} className={styles.errorListItem}>
                      {warning}
                    </li>
                  ))}
                  {importResult.warnings.length > 10 && (
                    <li className={styles.errorListMore}>
                      {t("import.reqifMoreWarnings", { count: importResult.warnings.length - 10 })}
                    </li>
                  )}
                </ul>
              </div>
            )}
          </div>
        )}
      </section>
    </>
  );
}

interface CsvExportSectionProps {
  exportEntityType: ExportEntityType;
  onExportEntityTypeChange: (type: ExportEntityType) => void;
  isExporting: boolean;
  onExport: () => void;
  isExportingReqif: boolean;
  onExportReqif: () => void;
  exportError: string | null;
  reqifExportError: string | null;
}

function CsvExportSection({
  exportEntityType,
  onExportEntityTypeChange,
  isExporting,
  onExport,
  isExportingReqif,
  onExportReqif,
  exportError,
  reqifExportError,
}: CsvExportSectionProps): JSX.Element {
  const { t } = useTranslation();
  return (
    <>
      {/* CSV Export (C7 — frontend-feedback Cluster C, MVP) */}
      <h2 className={styles.sectionHeading}>{t("export.title", "CSV Export")}</h2>

      <section data-testid="csv-export-page" className={styles.card}>
        <h3 className={styles.cardTitle}>{t("export.entityType", "Entity Type")}</h3>
        <EntityTypeRadioGroup
          name="exportEntityType"
          options={EXPORT_ENTITY_TYPES}
          selected={exportEntityType}
          onSelect={onExportEntityTypeChange}
          groupClassName={styles.radioGroupSpaced}
          testIdPrefix="export-entity-type-"
        />

        <div className={styles.radioGroup}>
          <button
            type="button"
            data-testid="csv-export-btn"
            onClick={() => void onExport()}
            disabled={isExporting}
            className={styles.primaryBtn}
          >
            {isExporting ? (
              <Spinner label={t("export.downloading")} />
            ) : (
              t("export.download")
            )}
          </button>

          {/* REQ-146: ReqIF 1.2 export — whole-workspace (Needs + Requirements
              + TraceLinks), independent of the entity-type radio above. */}
          <button
            type="button"
            data-testid="reqif-export-btn"
            onClick={() => void onExportReqif()}
            disabled={isExportingReqif}
            title={t(
              "export.reqifHint",
              "Exports the whole workspace (Needs, Requirements, TraceLinks) as ReqIF 1.2 for DOORS/Polarion"
            )}
            className={styles.secondaryBtn}
          >
            {isExportingReqif ? (
              <Spinner label={t("export.downloading")} />
            ) : (
              t("export.downloadReqif")
            )}
          </button>
        </div>

        {exportError && (
          <div data-testid="csv-export-error" role="alert" className={styles.errorBoxTopSpaced}>
            {exportError}
          </div>
        )}

        {reqifExportError && (
          <div data-testid="reqif-export-error" role="alert" className={styles.errorBoxTopSpaced}>
            {reqifExportError}
          </div>
        )}
      </section>
    </>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function CsvImport(): JSX.Element {
  const { t } = useTranslation();
  const { activeWorkspace } = useWorkspace();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const reqifFileInputRef = useRef<HTMLInputElement>(null);

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [entityType, setEntityType] = useState<EntityType>("Requirement");
  const [isUploading, setIsUploading] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const [preview, setPreview] = useState<CsvPreview | null>(null);
  const [showAllErrors, setShowAllErrors] = useState(false);

  const [exportEntityType, setExportEntityType] = useState<ExportEntityType>("Requirement");
  const [isExporting, setIsExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  // REQ-146: ReqIF 1.2 export (StakeholderNeeds, Requirements, TraceLinks).
  const [isExportingReqif, setIsExportingReqif] = useState(false);
  const [reqifExportError, setReqifExportError] = useState<string | null>(null);

  // REQ-147: ReqIF 1.2 import (StakeholderNeeds, Requirements, TraceLinks).
  const [selectedReqifFile, setSelectedReqifFile] = useState<File | null>(null);
  const [reqifDryRun, setReqifDryRun] = useState(false);
  const [isImportingReqif, setIsImportingReqif] = useState(false);
  const [reqifImportResult, setReqifImportResult] = useState<ReqifImportResult | null>(null);
  const [reqifImportError, setReqifImportError] = useState<string | null>(null);
  // ADR-014 §3: one Idempotency-Key per selected file/attempt so a retry after
  // a partial failure replays without a second write effect.
  const reqifIdempotencyKeyRef = useRef<string | null>(null);

  /**
   * Accepts a picked/dropped file and builds the pre-flight preview.
   *
   * The preview is best-effort: if the file cannot be read the import stays
   * available and the backend keeps the final word.
   */
  const acceptFile = useCallback(
    async (file: File | null): Promise<void> => {
      setSelectedFile(file);
      setResult(null);
      setError(null);
      setShowAllErrors(false);

      if (!file) {
        setPreview(null);
        return;
      }
      try {
        setPreview(buildCsvPreview(await readTextFile(file), entityType));
      } catch {
        setPreview(null);
      }
    },
    [entityType]
  );

  const handleFileSelect = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>): void => {
      void acceptFile(event.target.files?.[0] ?? null);
    },
    [acceptFile]
  );

  const handleDrop = useCallback(
    (event: React.DragEvent<HTMLDivElement>): void => {
      event.preventDefault();
      setIsDragOver(false);
      const file = event.dataTransfer.files?.[0] ?? null;
      if (file && file.name.toLowerCase().endsWith(".csv")) {
        void acceptFile(file);
      }
    },
    [acceptFile]
  );

  /**
   * Enter/Space on the drop zone opens the file dialog. The zone is a plain
   * `<div>`: a native button element cannot host the file input without
   * swallowing its click, so `role`/`tabIndex`/key handling are explicit.
   */
  const handleDropZoneKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLDivElement>): void => {
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      (event.currentTarget.querySelector("input[type=file]") as HTMLInputElement | null)?.click();
    },
    []
  );

  const handleDragOver = useCallback(
    (event: React.DragEvent<HTMLDivElement>): void => {
      event.preventDefault();
      setIsDragOver(true);
    },
    []
  );

  const handleDragLeave = useCallback(
    (event: React.DragEvent<HTMLDivElement>): void => {
      event.preventDefault();
      setIsDragOver(false);
    },
    []
  );

  /**
   * Switching the entity type re-runs the column check: the same header is
   * valid for one type and unknown for another, so a stale preview would
   * assert the wrong verdict.
   */
  const handleEntityTypeChange = useCallback(
    (type: EntityType): void => {
      setEntityType(type);
      setResult(null);
      setShowAllErrors(false);
      if (!selectedFile) return;
      void readTextFile(selectedFile)
        .then((text) => setPreview(buildCsvPreview(text, type)))
        .catch(() => setPreview(null));
    },
    [selectedFile]
  );

  const handleUpload = useCallback(async (): Promise<void> => {
    if (!selectedFile || !activeWorkspace) return;

    setIsUploading(true);
    setError(null);
    setResult(null);
    setShowAllErrors(false);

    try {
      const importResult = await importApi.importCsv(
        activeWorkspace.id,
        selectedFile,
        entityType
      );
      setResult(importResult);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : t("import.errorGeneric", "Import failed")
      );
    } finally {
      setIsUploading(false);
    }
  }, [selectedFile, activeWorkspace, entityType, t]);

  const handleExport = useCallback(async (): Promise<void> => {
    if (!activeWorkspace) return;

    setIsExporting(true);
    setExportError(null);

    try {
      await exportApi.downloadCsv(activeWorkspace.id, exportEntityType);
    } catch (err) {
      setExportError(
        err instanceof Error ? err.message : t("export.errorGeneric", "Export failed")
      );
    } finally {
      setIsExporting(false);
    }
  }, [activeWorkspace, exportEntityType, t]);

  // REQ-146: ReqIF 1.2 export (StakeholderNeeds, Requirements, TraceLinks).
  const handleExportReqif = useCallback(async (): Promise<void> => {
    if (!activeWorkspace) return;

    setIsExportingReqif(true);
    setReqifExportError(null);

    try {
      await exportApi.downloadReqif(activeWorkspace.id);
    } catch (err) {
      setReqifExportError(
        err instanceof Error ? err.message : t("export.errorGeneric", "Export failed")
      );
    } finally {
      setIsExportingReqif(false);
    }
  }, [activeWorkspace, t]);

  const handleReset = useCallback((): void => {
    setSelectedFile(null);
    setResult(null);
    setError(null);
    setPreview(null);
    setShowAllErrors(false);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }, []);

  const handleToggleShowAllErrors = useCallback((): void => {
    setShowAllErrors((shown) => !shown);
  }, []);

  // REQ-147: ReqIF 1.2 import (StakeholderNeeds, Requirements, TraceLinks).
  const handleReqifFileSelect = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>): void => {
      const file = event.target.files?.[0] ?? null;
      setSelectedReqifFile(file);
      setReqifImportResult(null);
      setReqifImportError(null);
      // A new file selection starts a new idempotency scope.
      reqifIdempotencyKeyRef.current = file
        ? `reqif-${generateIdempotencyUuid()}`
        : null;
    },
    []
  );

  const handleReqifImport = useCallback(async (): Promise<void> => {
    if (!selectedReqifFile || !activeWorkspace) return;

    setIsImportingReqif(true);
    setReqifImportError(null);
    setReqifImportResult(null);

    try {
      const importResult = await importApi.importReqif(
        activeWorkspace.id,
        selectedReqifFile,
        reqifDryRun,
        reqifIdempotencyKeyRef.current ?? undefined
      );
      setReqifImportResult(importResult);
    } catch (err) {
      setReqifImportError(
        err instanceof Error ? err.message : t("import.errorGeneric", "Import failed")
      );
    } finally {
      setIsImportingReqif(false);
    }
  }, [selectedReqifFile, activeWorkspace, reqifDryRun, t]);

  const handleReqifReset = useCallback((): void => {
    setSelectedReqifFile(null);
    setReqifImportResult(null);
    setReqifImportError(null);
    reqifIdempotencyKeyRef.current = null;
    if (reqifFileInputRef.current) {
      reqifFileInputRef.current.value = "";
    }
  }, []);

  if (!activeWorkspace) {
    return <p className={styles.errorPage}>{t("errors.generic")}</p>;
  }

  return (
    <div data-testid="csv-import-page" className={styles.page}>
      <PageHeader
        title={t("import.title", "CSV Import")}
        summary={t(
          "import.pageSummary",
          "Massendaten per CSV importieren oder Requirements, Bedarfe und Architekturelemente exportieren.",
        )}
      />

      {/* Entity type selector */}
      <section className={styles.card}>
        <h3 className={styles.cardTitle}>{t("import.entityType", "Entity Type")}</h3>
        <EntityTypeRadioGroup
          name="entityType"
          options={ENTITY_TYPES}
          selected={entityType}
          onSelect={handleEntityTypeChange}
          groupClassName={styles.radioGroup}
          testIdPrefix="entity-type-"
        />
      </section>

      <CsvDropZone
        fileInputRef={fileInputRef}
        isDragOver={isDragOver}
        selectedFile={selectedFile}
        onFileSelect={handleFileSelect}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onKeyDown={handleDropZoneKeyDown}
      />

      {/* Pre-flight preview (UI-30) — what the backend will see, before the
          upload costs a round-trip. */}
      {preview && <CsvPreviewPanel preview={preview} />}

      {/* Upload button */}
      <div className={styles.actionsRow}>
        <button
          type="button"
          data-testid="csv-import-btn"
          onClick={() => void handleUpload()}
          disabled={!selectedFile || isUploading}
          className={styles.primaryBtn}
        >
          {isUploading ? (
            <Spinner label={t("import.uploading")} />
          ) : (
            t("import.upload")
          )}
        </button>
        {(result || error) && (
          <button
            type="button"
            data-testid="csv-import-reset"
            onClick={handleReset}
            className={styles.resetBtn}
          >
            {t("actions.reset")}
          </button>
        )}
      </div>

      {/* Progress indicator */}
      {isUploading && (
        <div data-testid="csv-import-progress" className={styles.progressBox}>
          {t("import.progress", "Processing CSV file...")}
        </div>
      )}

      {/* Error display */}
      {error && (
        <div data-testid="csv-import-error" role="alert" className={styles.errorBox}>
          {error}
        </div>
      )}

      {/* Result display — three outcomes, see `outcomeOf` / module docstring. */}
      {result && (
        <ImportResultPanel
          result={result}
          showAllErrors={showAllErrors}
          onToggleShowAllErrors={handleToggleShowAllErrors}
        />
      )}

      <ReqifImportSection
        fileInputRef={reqifFileInputRef}
        dropZoneKeyDown={handleDropZoneKeyDown}
        selectedFile={selectedReqifFile}
        onFileSelect={handleReqifFileSelect}
        dryRun={reqifDryRun}
        onDryRunChange={setReqifDryRun}
        isImporting={isImportingReqif}
        onImport={handleReqifImport}
        importResult={reqifImportResult}
        importError={reqifImportError}
        onReset={handleReqifReset}
      />

      <CsvExportSection
        exportEntityType={exportEntityType}
        onExportEntityTypeChange={setExportEntityType}
        isExporting={isExporting}
        onExport={handleExport}
        isExportingReqif={isExportingReqif}
        onExportReqif={handleExportReqif}
        exportError={exportError}
        reqifExportError={reqifExportError}
      />
    </div>
  );
}

export default CsvImport;
