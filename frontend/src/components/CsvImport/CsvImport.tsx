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
    return (
      <p style={{ padding: "var(--space-6)", color: "var(--color-text-muted)" }}>
        {t("errors.generic")}
      </p>
    );
  }

  return (
    <div
      data-testid="csv-import-page"
      style={{ maxWidth: "640px" }}
    >
      <h1
        style={{
          fontSize: "var(--font-size-2xl)",
          fontWeight: 700,
          color: "var(--color-text)",
          marginBottom: "var(--space-6)",
        }}
      >
        {t("import.title", "CSV Import")}
      </h1>

      {/* Entity type selector */}
      <section
        style={{
          background: "var(--color-surface)",
          border: "1px solid var(--color-border)",
          borderRadius: "var(--radius-lg)",
          padding: "var(--space-5)",
          marginBottom: "var(--space-5)",
          boxShadow: "var(--shadow-card)",
        }}
      >
        <h3
          style={{
            fontSize: "var(--font-size-lg)",
            fontWeight: 600,
            color: "var(--color-text)",
            margin: "0 0 var(--space-4) 0",
          }}
        >
          {t("import.entityType", "Entity Type")}
        </h3>
        <div style={{ display: "flex", gap: "var(--space-3)", flexWrap: "wrap" }}>
          {ENTITY_TYPES.map((type) => (
            <label
              key={type}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "var(--space-2)",
                padding: "var(--space-2) var(--space-3)",
                borderRadius: "var(--radius-md)",
                border: entityType === type
                  ? "1px solid var(--color-primary)"
                  : "1px solid var(--color-border)",
                background: entityType === type
                  ? "rgba(var(--color-primary-rgb, 79,70,229), 0.08)"
                  : "transparent",
                cursor: "pointer",
                fontSize: "var(--font-size-sm)",
              }}
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
      <section
        style={{
          background: "var(--color-surface)",
          border: "1px solid var(--color-border)",
          borderRadius: "var(--radius-lg)",
          padding: "var(--space-5)",
          marginBottom: "var(--space-5)",
          boxShadow: "var(--shadow-card)",
        }}
      >
        <h3
          style={{
            fontSize: "var(--font-size-lg)",
            fontWeight: 600,
            color: "var(--color-text)",
            margin: "0 0 var(--space-4) 0",
          }}
        >
          {t("import.selectFile", "Select CSV File")}
        </h3>
        <div
          data-testid="csv-drop-zone"
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onClick={() => fileInputRef.current?.click()}
          style={{
            border: `2px dashed ${isDragOver ? "var(--color-primary)" : "var(--color-border)"}`,
            borderRadius: "var(--radius-md)",
            padding: "var(--space-6)",
            textAlign: "center",
            cursor: "pointer",
            background: isDragOver ? "rgba(var(--color-primary-rgb, 79,70,229), 0.04)" : "transparent",
            transition: "var(--transition-fast)",
          }}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv"
            onChange={handleFileSelect}
            data-testid="csv-file-input"
            style={{ display: "none" }}
          />
          {selectedFile ? (
            <div>
              <p style={{ fontWeight: 600, margin: "0 0 var(--space-1) 0" }}>
                {selectedFile.name}
              </p>
              <p style={{ fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)", margin: 0 }}>
                {(selectedFile.size / 1024).toFixed(1)} KB
              </p>
            </div>
          ) : (
            <p style={{ color: "var(--color-text-muted)", margin: 0 }}>
              {t("import.dropHint", "Drop CSV file here or click to browse")}
            </p>
          )}
        </div>
      </section>

      {/* Upload button */}
      <div style={{ display: "flex", gap: "var(--space-3)", marginBottom: "var(--space-5)" }}>
        <button
          type="button"
          data-testid="csv-import-btn"
          onClick={() => void handleUpload()}
          disabled={!selectedFile || isUploading}
          style={{
            background: "var(--color-primary)",
            color: "white",
            border: "none",
            borderRadius: "var(--radius-md)",
            padding: "var(--space-2) var(--space-5)",
            fontSize: "var(--font-size-sm)",
            fontWeight: 600,
            cursor: !selectedFile || isUploading ? "not-allowed" : "pointer",
            opacity: !selectedFile || isUploading ? 0.5 : 1,
            transition: "var(--transition-fast)",
          }}
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
            style={{
              background: "transparent",
              color: "var(--color-text)",
              border: "1px solid var(--color-border)",
              borderRadius: "var(--radius-md)",
              padding: "var(--space-2) var(--space-4)",
              fontSize: "var(--font-size-sm)",
              cursor: "pointer",
            }}
          >
            {t("actions.reset", "Reset")}
          </button>
        )}
      </div>

      {/* Progress indicator */}
      {isUploading && (
        <div
          data-testid="csv-import-progress"
          style={{
            padding: "var(--space-3)",
            background: "var(--color-surface)",
            border: "1px solid var(--color-border)",
            borderRadius: "var(--radius-md)",
            marginBottom: "var(--space-5)",
            textAlign: "center",
            color: "var(--color-text-muted)",
          }}
        >
          {t("import.progress", "Processing CSV file...")}
        </div>
      )}

      {/* Error display */}
      {error && (
        <div
          data-testid="csv-import-error"
          role="alert"
          style={{
            padding: "var(--space-3)",
            background: "var(--color-surface)",
            border: "1px solid var(--color-danger, #f87171)",
            borderRadius: "var(--radius-md)",
            marginBottom: "var(--space-5)",
            color: "var(--color-danger, #f87171)",
          }}
        >
          {error}
        </div>
      )}

      {/* Result display */}
      {result && (
        <div
          data-testid="csv-import-result"
          style={{
            padding: "var(--space-4)",
            background: "var(--color-surface)",
            border: `1px solid ${result.success ? "var(--color-success, #16a34a)" : "var(--color-danger, #f87171)"}`,
            borderRadius: "var(--radius-md)",
            marginBottom: "var(--space-5)",
          }}
        >
          {result.success ? (
            <div>
              <p
                data-testid="csv-import-success"
                style={{
                  fontWeight: 600,
                  color: "var(--color-success, #16a34a)",
                  margin: "0 0 var(--space-2) 0",
                }}
              >
                {t("import.success", "Successfully imported {{count}} rows", {
                  count: result.imported_count,
                })}
              </p>
              <p style={{ fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)", margin: 0 }}>
                Status: {result.status}
              </p>
            </div>
          ) : (
            <div>
              <p
                style={{
                  fontWeight: 600,
                  color: "var(--color-danger, #f87171)",
                  margin: "0 0 var(--space-3) 0",
                }}
              >
                {t("import.failed", "Import failed")}
              </p>
              {result.errors.length > 0 && (
                <ul style={{ margin: 0, paddingLeft: "var(--space-4)" }}>
                  {result.errors.slice(0, 10).map((err, idx) => (
                    <li
                      key={idx}
                      style={{
                        fontSize: "var(--font-size-sm)",
                        color: "var(--color-text-muted)",
                        marginBottom: "var(--space-1)",
                      }}
                    >
                      Row {err.row_number}: {err.field} — {err.message}
                    </li>
                  ))}
                  {result.errors.length > 10 && (
                    <li style={{ fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)" }}>
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
      <h2
        style={{
          fontSize: "var(--font-size-2xl)",
          fontWeight: 700,
          color: "var(--color-text)",
          margin: "var(--space-8) 0 var(--space-6) 0",
        }}
      >
        {t("import.reqifTitle", "ReqIF Import")}
      </h2>

      <section
        data-testid="reqif-import-page"
        style={{
          background: "var(--color-surface)",
          border: "1px solid var(--color-border)",
          borderRadius: "var(--radius-lg)",
          padding: "var(--space-5)",
          marginBottom: "var(--space-5)",
          boxShadow: "var(--shadow-card)",
        }}
      >
        <h3
          style={{
            fontSize: "var(--font-size-lg)",
            fontWeight: 600,
            color: "var(--color-text)",
            margin: "0 0 var(--space-4) 0",
          }}
        >
          {t("import.reqifSelectFile", "Select ReqIF File")}
        </h3>
        <div
          data-testid="reqif-file-picker"
          onClick={() => reqifFileInputRef.current?.click()}
          style={{
            border: "2px dashed var(--color-border)",
            borderRadius: "var(--radius-md)",
            padding: "var(--space-6)",
            textAlign: "center",
            cursor: "pointer",
            marginBottom: "var(--space-4)",
          }}
        >
          <input
            ref={reqifFileInputRef}
            type="file"
            accept=".reqif,.xml"
            onChange={handleReqifFileSelect}
            data-testid="reqif-file-input"
            style={{ display: "none" }}
          />
          {selectedReqifFile ? (
            <div>
              <p style={{ fontWeight: 600, margin: "0 0 var(--space-1) 0" }}>
                {selectedReqifFile.name}
              </p>
              <p style={{ fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)", margin: 0 }}>
                {(selectedReqifFile.size / 1024).toFixed(1)} KB
              </p>
            </div>
          ) : (
            <p style={{ color: "var(--color-text-muted)", margin: 0 }}>
              {t("import.reqifDropHint", "Click to select a .reqif or .xml file")}
            </p>
          )}
        </div>

        <label
          style={{
            display: "flex",
            alignItems: "center",
            gap: "var(--space-2)",
            marginBottom: "var(--space-4)",
            fontSize: "var(--font-size-sm)",
            color: "var(--color-text)",
            cursor: "pointer",
          }}
        >
          <input
            type="checkbox"
            checked={reqifDryRun}
            onChange={(e) => setReqifDryRun(e.target.checked)}
            data-testid="reqif-dry-run-checkbox"
          />
          {t(
            "import.reqifDryRun",
            "Dry run (preview the report without saving any changes)"
          )}
        </label>

        <div style={{ display: "flex", gap: "var(--space-3)", marginBottom: "var(--space-5)" }}>
          <button
            type="button"
            data-testid="reqif-import-btn"
            onClick={() => void handleReqifImport()}
            disabled={!selectedReqifFile || isImportingReqif}
            style={{
              background: "var(--color-primary)",
              color: "white",
              border: "none",
              borderRadius: "var(--radius-md)",
              padding: "var(--space-2) var(--space-5)",
              fontSize: "var(--font-size-sm)",
              fontWeight: 600,
              cursor: !selectedReqifFile || isImportingReqif ? "not-allowed" : "pointer",
              opacity: !selectedReqifFile || isImportingReqif ? 0.5 : 1,
              transition: "var(--transition-fast)",
            }}
          >
            {isImportingReqif
              ? t("import.uploading", "Importing...")
              : reqifDryRun
              ? t("import.reqifPreview", "Preview Import")
              : t("import.reqifUpload", "Import ReqIF")}
          </button>
          {(reqifImportResult || reqifImportError) && (
            <button
              type="button"
              data-testid="reqif-import-reset"
              onClick={handleReqifReset}
              style={{
                background: "transparent",
                color: "var(--color-text)",
                border: "1px solid var(--color-border)",
                borderRadius: "var(--radius-md)",
                padding: "var(--space-2) var(--space-4)",
                fontSize: "var(--font-size-sm)",
                cursor: "pointer",
              }}
            >
              {t("actions.reset", "Reset")}
            </button>
          )}
        </div>

        {reqifImportError && (
          <div
            data-testid="reqif-import-error"
            role="alert"
            style={{
              padding: "var(--space-3)",
              background: "var(--color-surface)",
              border: "1px solid var(--color-danger, #f87171)",
              borderRadius: "var(--radius-md)",
              marginBottom: "var(--space-5)",
              color: "var(--color-danger, #f87171)",
            }}
          >
            {reqifImportError}
          </div>
        )}

        {reqifImportResult && (
          <div
            data-testid="reqif-import-result"
            style={{
              padding: "var(--space-4)",
              background: "var(--color-surface)",
              border: "1px solid var(--color-success, #16a34a)",
              borderRadius: "var(--radius-md)",
            }}
          >
            {reqifImportResult.dry_run && (
              <p
                data-testid="reqif-import-dry-run-badge"
                style={{
                  fontWeight: 600,
                  color: "var(--color-primary)",
                  margin: "0 0 var(--space-3) 0",
                }}
              >
                {t("import.reqifDryRunBadge", "Dry run — nothing was saved")}
              </p>
            )}

            {(
              [
                ["needs", t("import.reqifNeeds", "Stakeholder Needs")],
                ["requirements", t("import.reqifRequirements", "Requirements")],
                ["relations", t("import.reqifRelations", "Trace Links")],
              ] as const
            ).map(([key, label]) => {
              const report = reqifImportResult[key];
              return (
                <div key={key} style={{ marginBottom: "var(--space-3)" }}>
                  <p
                    style={{
                      fontWeight: 600,
                      color: "var(--color-text)",
                      margin: "0 0 var(--space-1) 0",
                    }}
                  >
                    {label}: {t("import.reqifCreated", "created")} {report.created},{" "}
                    {t("import.reqifUpdated", "updated")} {report.updated},{" "}
                    {t("import.reqifSkipped", "skipped")} {report.skipped}
                  </p>
                  {report.errors.length > 0 && (
                    <ul style={{ margin: 0, paddingLeft: "var(--space-4)" }}>
                      {report.errors.slice(0, 10).map((err, idx) => (
                        <li
                          key={idx}
                          style={{
                            fontSize: "var(--font-size-sm)",
                            color: "var(--color-text-muted)",
                            marginBottom: "var(--space-1)",
                          }}
                        >
                          {err.identifier}: {err.message}
                        </li>
                      ))}
                      {report.errors.length > 10 && (
                        <li style={{ fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)" }}>
                          ... and {report.errors.length - 10} more errors
                        </li>
                      )}
                    </ul>
                  )}
                </div>
              );
            })}

            {reqifImportResult.warnings.length > 0 && (
              <div>
                <p
                  style={{
                    fontWeight: 600,
                    color: "var(--color-text)",
                    margin: "0 0 var(--space-1) 0",
                  }}
                >
                  {t("import.reqifWarnings", "Warnings")}
                </p>
                <ul style={{ margin: 0, paddingLeft: "var(--space-4)" }}>
                  {reqifImportResult.warnings.slice(0, 10).map((warning, idx) => (
                    <li
                      key={idx}
                      style={{
                        fontSize: "var(--font-size-sm)",
                        color: "var(--color-text-muted)",
                        marginBottom: "var(--space-1)",
                      }}
                    >
                      {warning}
                    </li>
                  ))}
                  {reqifImportResult.warnings.length > 10 && (
                    <li style={{ fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)" }}>
                      ... and {reqifImportResult.warnings.length - 10} more warnings
                    </li>
                  )}
                </ul>
              </div>
            )}
          </div>
        )}
      </section>

      {/* CSV Export (C7 — frontend-feedback Cluster C, MVP) */}
      <h2
        style={{
          fontSize: "var(--font-size-2xl)",
          fontWeight: 700,
          color: "var(--color-text)",
          margin: "var(--space-8) 0 var(--space-6) 0",
        }}
      >
        {t("export.title", "CSV Export")}
      </h2>

      <section
        data-testid="csv-export-page"
        style={{
          background: "var(--color-surface)",
          border: "1px solid var(--color-border)",
          borderRadius: "var(--radius-lg)",
          padding: "var(--space-5)",
          marginBottom: "var(--space-5)",
          boxShadow: "var(--shadow-card)",
        }}
      >
        <h3
          style={{
            fontSize: "var(--font-size-lg)",
            fontWeight: 600,
            color: "var(--color-text)",
            margin: "0 0 var(--space-4) 0",
          }}
        >
          {t("export.entityType", "Entity Type")}
        </h3>
        <div style={{ display: "flex", gap: "var(--space-3)", flexWrap: "wrap", marginBottom: "var(--space-5)" }}>
          {EXPORT_ENTITY_TYPES.map((type) => (
            <label
              key={type}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "var(--space-2)",
                padding: "var(--space-2) var(--space-3)",
                borderRadius: "var(--radius-md)",
                border: exportEntityType === type
                  ? "1px solid var(--color-primary)"
                  : "1px solid var(--color-border)",
                background: exportEntityType === type
                  ? "rgba(var(--color-primary-rgb, 79,70,229), 0.08)"
                  : "transparent",
                cursor: "pointer",
                fontSize: "var(--font-size-sm)",
              }}
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

        <div style={{ display: "flex", gap: "var(--space-3)", flexWrap: "wrap" }}>
          <button
            type="button"
            data-testid="csv-export-btn"
            onClick={() => void handleExport()}
            disabled={isExporting}
            style={{
              background: "var(--color-primary)",
              color: "white",
              border: "none",
              borderRadius: "var(--radius-md)",
              padding: "var(--space-2) var(--space-5)",
              fontSize: "var(--font-size-sm)",
              fontWeight: 600,
              cursor: isExporting ? "not-allowed" : "pointer",
              opacity: isExporting ? 0.5 : 1,
              transition: "var(--transition-fast)",
            }}
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
            style={{
              background: "var(--color-surface)",
              color: "var(--color-text)",
              border: "1px solid var(--color-border)",
              borderRadius: "var(--radius-md)",
              padding: "var(--space-2) var(--space-5)",
              fontSize: "var(--font-size-sm)",
              fontWeight: 600,
              cursor: isExportingReqif ? "not-allowed" : "pointer",
              opacity: isExportingReqif ? 0.5 : 1,
              transition: "var(--transition-fast)",
            }}
          >
            {isExportingReqif
              ? t("export.downloading", "Exporting...")
              : t("export.downloadReqif", "Export ReqIF")}
          </button>
        </div>

        {exportError && (
          <div
            data-testid="csv-export-error"
            role="alert"
            style={{
              marginTop: "var(--space-4)",
              padding: "var(--space-3)",
              background: "var(--color-surface)",
              border: "1px solid var(--color-danger, #f87171)",
              borderRadius: "var(--radius-md)",
              color: "var(--color-danger, #f87171)",
            }}
          >
            {exportError}
          </div>
        )}

        {reqifExportError && (
          <div
            data-testid="reqif-export-error"
            role="alert"
            style={{
              marginTop: "var(--space-4)",
              padding: "var(--space-3)",
              background: "var(--color-surface)",
              border: "1px solid var(--color-danger, #f87171)",
              borderRadius: "var(--radius-md)",
              color: "var(--color-danger, #f87171)",
            }}
          >
            {reqifExportError}
          </div>
        )}
      </section>
    </div>
  );
}

export default CsvImport;
