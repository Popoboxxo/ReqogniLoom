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
import { importApi, type EntityType, type ImportResult } from "../../api/import";

// ---------------------------------------------------------------------------
// Entity type options
// ---------------------------------------------------------------------------

const ENTITY_TYPES: EntityType[] = [
  "Requirement",
  "ArchitectureElement",
  "TestCase",
];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function CsvImport(): JSX.Element {
  const { t } = useTranslation();
  const { activeWorkspace } = useWorkspace();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [entityType, setEntityType] = useState<EntityType>("Requirement");
  const [isUploading, setIsUploading] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);

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

  const handleReset = useCallback((): void => {
    setSelectedFile(null);
    setResult(null);
    setError(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
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
      <h2
        style={{
          fontSize: "var(--font-size-2xl)",
          fontWeight: 700,
          color: "var(--color-text)",
          marginBottom: "var(--space-6)",
        }}
      >
        {t("import.title", "CSV Import")}
      </h2>

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
    </div>
  );
}

export default CsvImport;
