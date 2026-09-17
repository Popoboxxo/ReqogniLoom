/**
 * ARCH-L1-001 ReactFrontend — Requirement Bundle Export Panel.
 *
 * Requirement Bundle Export — Plan 3: UI Panel Implementation Plan, Task 4.
 *
 * Lazy-loaded (only mounted once the user opens the dialog — no API calls on
 * Architecture View mount, see the plan's Global Constraints). Lets the user
 * fetch every Requirement under a selected ArchitectureElement, either raw
 * (JSON/Markdown/CSV, `mode=raw`) or AI-compressed (`mode=compressed`, sync
 * or async with progress polling via `useBundleCompressionStatus`).
 *
 * data-testid is set on every interactive element (E2E convention), prefix
 * `arch-bundle-export-*` mirroring `arch-decompose-*`.
 */

import type { CSSProperties } from "react";
import { useCallback, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import ReactMarkdown from "react-markdown";

import { requirementBundleApi } from "../../api/requirementBundle";
import type {
  BundleRawResult,
  CompressedResult,
  FilterMode,
  OutputFormat,
} from "../../api/requirementBundle";
import { extractErrorMessage } from "../../api/client";
import { useBundleCompressionStatus } from "../../hooks/useBundleCompressionStatus";

export interface RequirementBundleExportPanelProps {
  elementId: string;
  elementTitle: string;
}

type Mode = "raw" | "compressed";
type Phase = "idle" | "exporting";

const styles: Record<string, CSSProperties> = {
  panel: {
    display: "flex",
    flexDirection: "column",
    gap: "var(--space-4)",
    padding: "var(--space-5)",
    background: "var(--color-surface)",
    border: "1px solid var(--color-border)",
    borderRadius: "var(--radius-lg)",
    color: "var(--color-text)",
  },
  controls: {
    display: "flex",
    gap: "var(--space-3)",
    alignItems: "flex-end",
    flexWrap: "wrap",
  },
  field: { display: "flex", flexDirection: "column", gap: "var(--space-1)" },
  numberInput: { width: "5rem", padding: "var(--space-1) var(--space-2)" },
  textInput: { padding: "var(--space-1) var(--space-2)", minWidth: "16rem" },
  banner: {
    background: "var(--color-badge-warning-bg)",
    color: "var(--color-badge-warning-text)",
    borderRadius: "var(--radius-sm)",
    padding: "var(--space-2) var(--space-3)",
    fontSize: "var(--font-size-sm)",
  },
  info: {
    background: "var(--color-badge-info-bg)",
    color: "var(--color-badge-info-text)",
    borderRadius: "var(--radius-sm)",
    padding: "var(--space-2) var(--space-3)",
    fontSize: "var(--font-size-sm)",
  },
  error: {
    background: "var(--color-badge-danger-bg)",
    color: "var(--color-badge-danger-text)",
    borderRadius: "var(--radius-sm)",
    padding: "var(--space-2) var(--space-3)",
  },
  result: {
    border: "1px solid var(--color-border)",
    borderRadius: "var(--radius-md)",
    padding: "var(--space-3)",
    background: "var(--color-surface-raised)",
    maxHeight: "24rem",
    overflow: "auto",
  },
  actions: { display: "flex", gap: "var(--space-3)", flexWrap: "wrap" },
  muted: { color: "var(--color-text-muted)", fontSize: "var(--font-size-sm)" },
  modeToggle: { display: "flex", gap: "var(--space-2)" },
};

const POLL_FAILURE_STATUSES = new Set(["failed", "not_found"]);

export function RequirementBundleExportPanel({
  elementId,
}: RequirementBundleExportPanelProps): JSX.Element {
  const { t } = useTranslation();

  const [phase, setPhase] = useState<Phase>("idle");
  const [mode, setMode] = useState<Mode>("raw");
  const [depthInput, setDepthInput] = useState("");
  const [filterMode, setFilterMode] = useState<FilterMode>("all");
  const [fieldsInput, setFieldsInput] = useState("");
  const [outputFormat, setOutputFormat] = useState<OutputFormat>("json");
  const [asyncMode, setAsyncMode] = useState(false);

  const [rawResult, setRawResult] = useState<BundleRawResult | null>(null);
  const [compressedResult, setCompressedResult] = useState<CompressedResult | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const {
    status: pollStatus,
    result: pollResult,
    error: pollError,
    isPolling,
  } = useBundleCompressionStatus(taskId);

  // pollStatus is still null for the one render between dispatch (setTaskId)
  // and the hook's effect actually firing its first poll — isPolling alone
  // would report `false` during that gap, so also treat "just dispatched,
  // no status yet" as busy.
  const polling = taskId !== null && (pollStatus === null || isPolling);
  const busy = phase === "exporting" || polling;

  const parsedDepth = useMemo(() => {
    const trimmed = depthInput.trim();
    return trimmed === "" ? undefined : Number(trimmed);
  }, [depthInput]);

  const parsedFields = useMemo(
    () =>
      fieldsInput
        .split(",")
        .map((f) => f.trim())
        .filter((f) => f.length > 0),
    [fieldsInput]
  );

  const handleSubmit = useCallback(async () => {
    setError(null);
    setRawResult(null);
    setCompressedResult(null);
    setTaskId(null);
    setPhase("exporting");
    try {
      if (mode === "raw") {
        const result = await requirementBundleApi.exportRaw(elementId, {
          depth: parsedDepth,
          filter_mode: filterMode,
          fields: filterMode === "custom" ? parsedFields : undefined,
          output_format: outputFormat,
        });
        setRawResult(result);
      } else {
        const result = await requirementBundleApi.exportCompressed(elementId, {
          depth: parsedDepth,
          filter_mode: filterMode,
          fields: filterMode === "custom" ? parsedFields : undefined,
          async: asyncMode,
        });
        if ("task_id" in result) {
          setTaskId(result.task_id);
        } else {
          setCompressedResult(result);
        }
      }
      setPhase("idle");
    } catch (err) {
      setError(extractErrorMessage(err));
      setPhase("idle");
    }
  }, [elementId, mode, parsedDepth, filterMode, parsedFields, outputFormat, asyncMode]);

  // A terminal poll status of "failed" or "not_found" must always surface
  // *some* message — the backend's own "failed" status doesn't always carry
  // a non-null `error` string, and "not_found" (a genuinely-expired task OR
  // a cross-tenant task_id, ADR-03 makes the two indistinguishable) never
  // carries one at all. Without a fallback here the panel silently stops
  // polling and renders nothing (found in review).
  const displayError =
    error ??
    (taskId && pollStatus && POLL_FAILURE_STATUSES.has(pollStatus)
      ? pollError ??
        (pollStatus === "not_found"
          ? t("bundleExport.taskNotFound", "Compression task not found (it may have expired).")
          : t("bundleExport.compressionFailed", "Compression failed."))
      : null);

  return (
    <section style={styles.panel} data-testid="arch-bundle-export-panel">
      <div style={styles.controls}>
        <label style={styles.field}>
          <span style={styles.muted}>{t("bundleExport.depthLabel", "Depth")}</span>
          <input
            type="number"
            min={0}
            max={20}
            value={depthInput}
            disabled={busy}
            placeholder={t("bundleExport.depthFullHint", "Leave empty for full hierarchy")}
            onChange={(e) => setDepthInput(e.target.value)}
            style={styles.numberInput}
            data-testid="arch-bundle-export-depth"
          />
        </label>

        <label style={styles.field}>
          <span style={styles.muted}>{t("bundleExport.filterModeLabel", "Filter mode")}</span>
          <select
            value={filterMode}
            disabled={busy}
            onChange={(e) => setFilterMode(e.target.value as FilterMode)}
            data-testid="arch-bundle-export-filter-mode"
          >
            <option value="all">{t("bundleExport.filterModeAll", "All fields")}</option>
            <option value="visible">{t("bundleExport.filterModeVisible", "Visible fields")}</option>
            <option value="custom">{t("bundleExport.filterModeCustom", "Custom fields")}</option>
          </select>
        </label>

        {filterMode === "custom" && (
          <label style={styles.field}>
            <span style={styles.muted}>{t("bundleExport.fieldsLabel", "Fields (comma-separated)")}</span>
            <input
              type="text"
              value={fieldsInput}
              disabled={busy}
              placeholder={t("bundleExport.fieldsPlaceholder", "e.g. title, status, priority")}
              onChange={(e) => setFieldsInput(e.target.value)}
              style={styles.textInput}
              data-testid="arch-bundle-export-fields"
            />
          </label>
        )}

        {mode === "raw" && (
          <label style={styles.field}>
            <span style={styles.muted}>{t("bundleExport.formatLabel", "Format")}</span>
            <select
              value={outputFormat}
              disabled={busy}
              onChange={(e) => setOutputFormat(e.target.value as OutputFormat)}
              data-testid="arch-bundle-export-output-format"
            >
              <option value="json">{t("bundleExport.formatJson", "JSON")}</option>
              <option value="markdown">{t("bundleExport.formatMarkdown", "Markdown")}</option>
              <option value="csv">{t("bundleExport.formatCsv", "CSV")}</option>
            </select>
          </label>
        )}

        <div style={styles.field}>
          <span style={styles.muted}>{t("bundleExport.modeLabel", "Mode")}</span>
          <div style={styles.modeToggle}>
            <button
              type="button"
              aria-pressed={mode === "raw"}
              disabled={busy}
              onClick={() => setMode("raw")}
              data-testid="arch-bundle-export-mode-raw"
            >
              {t("bundleExport.modeRaw", "Raw")}
            </button>
            <button
              type="button"
              aria-pressed={mode === "compressed"}
              disabled={busy}
              onClick={() => setMode("compressed")}
              data-testid="arch-bundle-export-mode-compressed"
            >
              {t("bundleExport.modeCompressed", "AI-compressed")}
            </button>
          </div>
        </div>

        {mode === "compressed" && (
          <label style={styles.field}>
            <span style={styles.muted}>{t("bundleExport.asyncLabel", "Run in background (async)")}</span>
            <input
              type="checkbox"
              checked={asyncMode}
              disabled={busy}
              onChange={(e) => setAsyncMode(e.target.checked)}
              data-testid="arch-bundle-export-async"
            />
          </label>
        )}

        <button
          type="button"
          onClick={handleSubmit}
          disabled={busy}
          data-testid="arch-bundle-export-submit"
        >
          {phase === "exporting" ? t("bundleExport.exporting", "Exporting...") : t("bundleExport.export", "Export")}
        </button>
      </div>

      {polling && (
        <div style={styles.info} data-testid="arch-bundle-export-polling">
          {t("bundleExport.polling", "Compression in progress...")}
        </div>
      )}

      {displayError && (
        <div style={styles.error} role="alert" data-testid="arch-bundle-export-error">
          {displayError}
        </div>
      )}

      {rawResult && (
        <div style={styles.result} data-testid="arch-bundle-export-result">
          {rawResult.format === "json" &&
            (rawResult.items.length === 0 ? (
              <p style={styles.muted}>{t("bundleExport.empty", "No requirements found for this element.")}</p>
            ) : (
              <pre>{JSON.stringify(rawResult.items, null, 2)}</pre>
            ))}
          {rawResult.format === "markdown" && <ReactMarkdown>{rawResult.content}</ReactMarkdown>}
          {rawResult.format === "csv" && <pre>{rawResult.content}</pre>}
        </div>
      )}

      {compressedResult && (
        <div style={styles.result} data-testid="arch-bundle-export-result">
          {compressedResult.is_mock_fallback && (
            <div style={styles.banner} data-testid="arch-bundle-export-mock-fallback">
              {t("bundleExport.mockFallback", "Note: deterministic mock output (no real LLM provider configured).")}
            </div>
          )}
          {compressedResult.cache_hit && (
            <div style={styles.muted} data-testid="arch-bundle-export-cache-hit">
              {t("bundleExport.cacheHit", "Served from cache")}
            </div>
          )}
          <ReactMarkdown>{compressedResult.text}</ReactMarkdown>
        </div>
      )}

      {taskId && pollStatus === "done" && pollResult && (
        <div style={styles.result} data-testid="arch-bundle-export-result">
          <ReactMarkdown>{pollResult}</ReactMarkdown>
        </div>
      )}
    </section>
  );
}
