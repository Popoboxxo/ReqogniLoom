/**
 * ARCH-L1-001 ReactFrontend — CsvImport (REQ-L0-013, REQ-L2-RF-016).
 *
 * leaf_id: COMP-RF-001 (NavigationShell scope — CSV import UI)
 * req_id:  REQ-L0-013 (Effiziente Übernahme bestehender Anforderungsdaten),
 *          REQ-L2-AS-014 (CSV Bulk Import),
 *          REQ-L2-RF-016 (Frontend CSV import UI)
 *
 * Features:
 *   - File picker / drop zone for CSV upload
 *   - Entity-type selector (Requirement / ArchitectureElement / TestCase)
 *   - Progress indicator during upload
 *   - Result display (success count, per-row errors)
 *   - i18n support (de/en)
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

  const handleFileSelect = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>): void => {
      const file = event.target.files?.[0] ?? null;
      setSelectedFile(file);
      setResult(null);
      setError(null);
    },
    []
  );

  const handleDrop = useCallback(
    (event: React.DragEvent<HTMLDivElement>): void => {
      event.preventDefault();
      setIsDragOver(false);
      const file = event.dataTransfer.files?.[0] ?? null;
      if (file && file.name.toLowerCase().endsWith(".csv")) {
        setSelectedFile(file);
        setResult(null);
        setError(null);
      }
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

  const handleUpload = useCallback(async (): Promise<void> => {
    if (!selectedFile || !activeWorkspace) return;

    setIsUploading(true);
    setError(null);
    setResult(null);

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
                onChange={() => setEntityType(type)}
                data-testid={`entity-type-${type}`}
              />
              {type}
            </label>
          ))}
        </div>
      </section>

      {/* Drop zone / file picker */}
      <section className={styles.card}>
        <h3 className={styles.cardTitle}>{t("import.selectFile", "Select CSV File")}</h3>
        <div
          data-testid="csv-drop-zone"
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onClick={() => fileInputRef.current?.click()}
          className={isDragOver ? styles.dropZoneActive : styles.dropZone}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv"
            onChange={handleFileSelect}
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

      {/* Upload button */}
      <div className={styles.actionsRow}>
        <button
          type="button"
          data-testid="csv-import-btn"
          onClick={() => void handleUpload()}
          disabled={!selectedFile || isUploading}
          className={styles.primaryBtn}
        >
          {isUploading
            ? t("import.uploading", "Importing...")
            : t("import.upload", "Import")}
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

      {/* Result display */}
      {result && (
        <div
          data-testid="csv-import-result"
          className={result.success ? styles.resultBoxSuccess : styles.resultBoxError}
        >
          {result.success ? (
            <div>
              <p data-testid="csv-import-success" className={styles.successText}>
                {t("import.success", "Successfully imported {{count}} rows", {
                  count: result.imported_count,
                })}
              </p>
              <p className={styles.fileMeta}>Status: {result.status}</p>
            </div>
          ) : (
            <div>
              <p className={styles.failText}>{t("import.failed", "Import failed")}</p>
              {result.errors.length > 0 && (
                <ul className={styles.errorList}>
                  {result.errors.slice(0, 10).map((err, idx) => (
                    <li key={idx} className={styles.errorListItem}>
                      Row {err.row_number}: {err.field} — {err.message}
                    </li>
                  ))}
                  {result.errors.length > 10 && (
                    <li className={styles.errorListMore}>
                      ... and {result.errors.length - 10} more errors
                    </li>
                  )}
                </ul>
              )}
            </div>
          )}
        </div>
      )}

      {/* ReqIF Import (REQ-147) */}
      <h2 className={styles.sectionHeading}>{t("import.reqifTitle")}</h2>

      <section data-testid="reqif-import-page" className={styles.card}>
        <h3 className={styles.cardTitle}>{t("import.reqifSelectFile")}</h3>
        <div
          data-testid="reqif-file-picker"
          onClick={() => reqifFileInputRef.current?.click()}
          className={styles.filePicker}
        >
          <input
            ref={reqifFileInputRef}
            type="file"
            accept=".reqif,.xml"
            onChange={handleReqifFileSelect}
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
            {isImportingReqif
              ? t("import.uploading", "Importing...")
              : reqifDryRun
              ? t("import.reqifPreview")
              : t("import.reqifUpload")}
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
              {type}
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
            {isExporting
              ? t("export.downloading", "Exporting...")
              : t("export.download", "Export CSV")}
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
            {isExportingReqif
              ? t("export.downloading", "Exporting...")
              : t("export.downloadReqif", "Export ReqIF")}
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
