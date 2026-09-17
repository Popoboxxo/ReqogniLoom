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

  // REQ-147: ReqIF 1.2 import (StakeholderNeeds, Requirements, TraceLinks).
  const handleReqifFileSelect = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>): void => {
      const file = event.target.files?.[0] ?? null;
      setSelectedReqifFile(file);
      setReqifImportResult(null);
      setReqifImportError(null);
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
        reqifDryRun
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
        <div className={styles.radioGroup}>
          {ENTITY_TYPES.map((type) => (
            <label
              key={type}
              className={entityType === type ? styles.radioLabelActive : styles.radioLabel}
            >
              <input
                type="radio"
                name="entityType"
                value={type}
                checked={entityType === type}
                onChange={() => handleEntityTypeChange(type)}
                data-testid={`entity-type-${type}`}
              />
              {t(ENTITY_TYPE_I18N_KEYS[type] ?? type)}
            </label>
          ))}
        </div>
      </section>

      {/* Drop zone / file picker */}
      <section className={styles.card}>
        <h3 className={styles.cardTitle}>{t("import.selectFile", "Select CSV File")}</h3>
        <div
          data-testid="csv-drop-zone"
          role="button"
          tabIndex={0}
          aria-label={t("import.dropZoneLabel")}
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onClick={() => fileInputRef.current?.click()}
          onKeyDown={handleDropZoneKeyDown}
          className={isDragOver ? styles.dropZoneActive : styles.dropZone}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv"
            onChange={handleFileSelect}
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

      {/* Pre-flight preview (UI-30) — what the backend will see, before the
          upload costs a round-trip. */}
      {preview && (
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
      )}

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
                      onClick={() => setShowAllErrors((shown) => !shown)}
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
      )}

      {/* ReqIF Import (REQ-147) */}
      <h2 className={styles.sectionHeading}>{t("import.reqifTitle")}</h2>

      <section data-testid="reqif-import-page" className={styles.card}>
        <h3 className={styles.cardTitle}>{t("import.reqifSelectFile")}</h3>
        <div
          data-testid="reqif-file-picker"
          role="button"
          tabIndex={0}
          aria-label={t("import.reqifDropZoneLabel")}
          onClick={() => reqifFileInputRef.current?.click()}
          onKeyDown={handleDropZoneKeyDown}
          className={styles.filePicker}
        >
          <input
            ref={reqifFileInputRef}
            type="file"
            accept=".reqif,.xml"
            onChange={handleReqifFileSelect}
            onClick={(event) => event.stopPropagation()}
            data-testid="reqif-file-input"
            className={styles.hiddenFileInput}
          />
          {selectedReqifFile ? (
            <div>
              <p className={styles.fileName}>{selectedReqifFile.name}</p>
              <p className={styles.fileMeta}>{(selectedReqifFile.size / 1024).toFixed(1)} KB</p>
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
            checked={reqifDryRun}
            onChange={(e) => setReqifDryRun(e.target.checked)}
            data-testid="reqif-dry-run-checkbox"
          />
          {t("import.reqifDryRun")}
        </label>

        <div className={styles.actionsRow}>
          <button
            type="button"
            data-testid="reqif-import-btn"
            onClick={() => void handleReqifImport()}
            disabled={!selectedReqifFile || isImportingReqif}
            className={styles.primaryBtn}
          >
            {isImportingReqif ? (
              <Spinner label={t("import.uploading")} />
            ) : reqifDryRun ? (
              t("import.reqifPreview")
            ) : (
              t("import.reqifUpload")
            )}
          </button>
          {(reqifImportResult || reqifImportError) && (
            <button
              type="button"
              data-testid="reqif-import-reset"
              onClick={handleReqifReset}
              className={styles.resetBtn}
            >
              {t("actions.reset")}
            </button>
          )}
        </div>

        {reqifImportError && (
          <div data-testid="reqif-import-error" role="alert" className={styles.errorBox}>
            {reqifImportError}
          </div>
        )}

        {reqifImportResult && (
          <div data-testid="reqif-import-result" className={styles.resultBoxPlain}>
            {reqifImportResult.dry_run && (
              <p data-testid="reqif-import-dry-run-badge" className={styles.dryRunBadge}>
                {t("import.reqifDryRunBadge")}
              </p>
            )}

            {(
              [
                ["needs", t("import.reqifNeeds")],
                ["requirements", t("import.reqifRequirements")],
                ["relations", t("import.reqifRelations")],
              ] as const
            ).map(([key, label]) => {
              const report = reqifImportResult[key];
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
                </div>
              );
            })}

            {reqifImportResult.warnings.length > 0 && (
              <div>
                <p className={styles.reportLine}>{t("import.reqifWarnings")}</p>
                <ul className={styles.errorList}>
                  {reqifImportResult.warnings.slice(0, 10).map((warning, idx) => (
                    <li key={idx} className={styles.errorListItem}>
                      {warning}
                    </li>
                  ))}
                  {reqifImportResult.warnings.length > 10 && (
                    <li className={styles.errorListMore}>
                      {t("import.reqifMoreWarnings", { count: reqifImportResult.warnings.length - 10 })}
                    </li>
                  )}
                </ul>
              </div>
            )}
          </div>
        )}
      </section>

      {/* CSV Export (C7 — frontend-feedback Cluster C, MVP) */}
      <h2 className={styles.sectionHeading}>{t("export.title", "CSV Export")}</h2>

      <section data-testid="csv-export-page" className={styles.card}>
        <h3 className={styles.cardTitle}>{t("export.entityType", "Entity Type")}</h3>
        <div className={styles.radioGroupSpaced}>
          {EXPORT_ENTITY_TYPES.map((type) => (
            <label
              key={type}
              className={exportEntityType === type ? styles.radioLabelActive : styles.radioLabel}
            >
              <input
                type="radio"
                name="exportEntityType"
                value={type}
                checked={exportEntityType === type}
                onChange={() => setExportEntityType(type)}
                data-testid={`export-entity-type-${type}`}
              />
              {t(ENTITY_TYPE_I18N_KEYS[type] ?? type)}
            </label>
          ))}
        </div>

        <div className={styles.radioGroup}>
          <button
            type="button"
            data-testid="csv-export-btn"
            onClick={() => void handleExport()}
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
            onClick={() => void handleExportReqif()}
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
    </div>
  );
}

export default CsvImport;
