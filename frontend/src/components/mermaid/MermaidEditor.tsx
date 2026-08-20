/**
 * ARCH-L1-001 ReactFrontend — MermaidEditor (COMP-RF-005 Mermaid).
 *
 * leaf_id: COMP-RF-005 (MermaidEditor)
 * req_id:  REQ-L1-057 (Mermaid Live Preview), REQ-L2-DS-007 (MermaidLiveRenderer)
 *
 * Split-view Mermaid editor:
 *   Left: CodeMirror 6 code editor for Mermaid source
 *   Right: Live preview (debounced 300ms via GET /mermaid-preview/)
 *
 * Features:
 *   - Split-view: code left, preview right
 *   - Live preview on input (debounced 300ms)
 *   - Error display for invalid Mermaid syntax
 *   - Auto-Save 2s after last input via PUT /mermaid-source/
 *   - data-testid on all interactive elements
 *
 * Interfaces:
 *   IF-L1-059 (input):  PUT mermaid-source
 *   IF-L1-061 (output): GET mermaid-preview
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";
import { diagramsApi } from "../../api/diagrams";
import { diagramKeys } from "../DiagramView/useDiagramData";
import styles from "../../styles/components/MermaidEditor.module.css";
import { sanitizeSvg } from "../../utils/sanitizeSvg";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PREVIEW_DEBOUNCE_MS = 300;
const AUTO_SAVE_DELAY_MS = 2000;

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface MermaidEditorProps {
  diagramId: string;
  initialSource?: string;
  onSourceChange?: (source: string) => void;
}

// ---------------------------------------------------------------------------
// MermaidEditor component
// ---------------------------------------------------------------------------

export function MermaidEditor({
  diagramId,
  initialSource,
  onSourceChange,
}: MermaidEditorProps): JSX.Element {
  const { t } = useTranslation();
  const queryClient = useQueryClient();

  const [source, setSource] = useState(initialSource ?? "");
  // #259: the status bar's diagram-type label used to read `preview.diagram_type`,
  // which only updates 300ms after a *debounced, backend-persisted* round-trip
  // (GET /mermaid-preview/, driven by `diagramId` alone -- see fetchPreview
  // below) -- it never reflected what the user had just typed but not yet
  // saved. `detectedType` is derived synchronously from the same client-side
  // mermaid.js parse that already renders `previewSvg`, so it always matches
  // the current `source`.
  const [detectedType, setDetectedType] = useState<string>("");
  const [previewSvg, setPreviewSvg] = useState<string>("");
  const [validationError, setValidationError] = useState<string>("");
  const [isDirty, setIsDirty] = useState(false);
  const [saveStatus, setSaveStatus] = useState<
    "idle" | "saving" | "saved" | "error"
  >("idle");
  const [isLoadingPreview, setIsLoadingPreview] = useState(false);

  const previewTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const editorContainerRef = useRef<HTMLDivElement>(null);
  const cmViewRef = useRef<InstanceType<typeof import("@codemirror/view").EditorView> | null>(null);

  // Mirror of `isDirty` for use inside callbacks that must stay referentially
  // stable. `performAutoSave` runs from a 2s timer that was scheduled during a
  // render where `isDirty` was still false; reading the state variable there
  // would capture that stale value and abort every scheduled save. The ref is
  // written synchronously next to every `setIsDirty` call, so it is always
  // current when the timer fires.
  const isDirtyRef = useRef(false);

  // Always points at the newest `handleSourceChange`. The CodeMirror instance
  // is created once per `diagramId` and its `updateListener` closes over
  // whatever binding existed at that moment — without this indirection the
  // editor would keep calling the mount-time callback forever.
  const handleSourceChangeRef = useRef<(newSource: string) => void>(() => {});

  // -----------------------------------------------------------------------
  // Load initial source from server if not provided
  // -----------------------------------------------------------------------

  useEffect(() => {
    if (initialSource !== undefined) return;

    diagramsApi
      .fetchMermaidSource(diagramId)
      .then((resp) => {
        setSource(resp.source);
      })
      .catch((err) => {
        console.error("Failed to load Mermaid source", err);
      });
  }, [diagramId, initialSource]);

  // -----------------------------------------------------------------------
  // CodeMirror 6 initialization
  // -----------------------------------------------------------------------

  useEffect(() => {
    let destroyed = false;

    async function initEditor(): Promise<void> {
      if (!editorContainerRef.current || cmViewRef.current) return;

      const [
        { EditorState },
        { EditorView, keymap },
        { defaultKeymap },
        { history, historyKeymap },
      ] = await Promise.all([
        import("@codemirror/state"),
        import("@codemirror/view"),
        import("@codemirror/commands"),
        import("@codemirror/commands"),
      ]);

      if (destroyed || !editorContainerRef.current) return;

      // Clear container
      editorContainerRef.current.innerHTML = "";

      const state = EditorState.create({
        doc: source,
        extensions: [
          keymap.of([
            ...defaultKeymap,
            ...historyKeymap,
          ]),
          history(),
          EditorView.updateListener.of((update) => {
            if (update.docChanged) {
              const newSource = update.state.doc.toString();
              handleSourceChangeRef.current(newSource);
            }
          }),
          EditorView.lineWrapping,
        ],
      });

      const view = new EditorView({
        state,
        parent: editorContainerRef.current,
      });

      cmViewRef.current = view;
    }

    void initEditor();

    return () => {
      destroyed = true;
      cmViewRef.current?.destroy();
      cmViewRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [diagramId]);

  // -----------------------------------------------------------------------
  // Source change handler — debounce preview + schedule auto-save
  // -----------------------------------------------------------------------

  const handleSourceChange = useCallback(
    (newSource: string) => {
      setSource(newSource);
      setIsDirty(true);
      isDirtyRef.current = true;
      onSourceChange?.(newSource);

      // Debounced preview fetch (300ms)
      if (previewTimerRef.current) {
        clearTimeout(previewTimerRef.current);
      }
      previewTimerRef.current = setTimeout(() => {
        void fetchPreview(newSource);
      }, PREVIEW_DEBOUNCE_MS);

      // Auto-save after 2s of inactivity
      if (saveTimerRef.current) {
        clearTimeout(saveTimerRef.current);
      }
      saveTimerRef.current = setTimeout(() => {
        void performAutoSave(newSource);
      }, AUTO_SAVE_DELAY_MS);
    },
    // `fetchPreview` and `performAutoSave` are intentionally omitted: both are
    // declared further down, so naming them here would evaluate a `const` in
    // its temporal dead zone on every render. Omitting them is safe because
    // neither reads render-scoped state any more — `performAutoSave` goes
    // through `isDirtyRef`, and both only close over `diagramId`, which is
    // already a dependency.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [diagramId, onSourceChange]
  );

  // Publish the current callback for the CodeMirror updateListener.
  handleSourceChangeRef.current = handleSourceChange;

  // -----------------------------------------------------------------------
  // Preview fetch
  // -----------------------------------------------------------------------

  const fetchPreview = useCallback(
    async (currentSource: string) => {
      if (!currentSource.trim()) {
        setValidationError("");
        return;
      }

      setIsLoadingPreview(true);
      try {
        const resp = await diagramsApi.fetchMermaidPreview(diagramId);

        // #259: this GET is a server-side validity double-check (the source
        // it validates is whatever was last persisted, not `currentSource` --
        // see the module docstring). It must never touch `previewSvg`: that
        // is owned exclusively by the client-side mermaid.js render effect
        // above, which resolves faster (no network round-trip) on every
        // keystroke. This call used to `setPreviewSvg("")` in its
        // non-fallback branch too, discarding whatever the render effect had
        // *already* drawn once this slower, debounced fetch caught up.
        if (resp.fallback_mode) {
          setValidationError(resp.error_message || t("mermaid.preview.error", "Render error"));
        }
      } catch (err) {
        const msg =
          (err as { error?: { message?: string } })?.error?.message ??
          String(err);
        setValidationError(msg);
      } finally {
        setIsLoadingPreview(false);
      }
    },
    [diagramId, t]
  );

  // -----------------------------------------------------------------------
  // Client-side Mermaid rendering (via mermaid.js)
  // -----------------------------------------------------------------------

  useEffect(() => {
    if (!source.trim()) {
      setPreviewSvg("");
      setDetectedType("");
      return;
    }

    let cancelled = false;

    async function renderMermaid(): Promise<void> {
      try {
        const mermaid = (await import("mermaid")).default;
        if (cancelled) return;

        mermaid.initialize({
          startOnLoad: false,
          theme: "default",
          securityLevel: "strict",
          // Labels must be plain SVG <text>: the rendered markup passes
          // through sanitizeSvg, which drops <foreignObject> (mXSS vector).
          htmlLabels: false,
          flowchart: { htmlLabels: false },
        });

        // #259: detectType() is a synchronous, purely local parse of the
        // *current* source -- unlike the debounced GET /mermaid-preview/
        // round-trip (fetchPreview below), it can never lag behind what the
        // user just typed. Its own failure (unparseable source) must not
        // block the render attempt below, so it gets its own try/catch.
        try {
          setDetectedType(mermaid.detectType(source));
        } catch {
          setDetectedType("");
        }

        const id = `mermaid-preview-${Date.now()}`;
        const { svg } = await mermaid.render(id, source);
        if (!cancelled) {
          // Rendered via dangerouslySetInnerHTML below — sanitise first.
          setPreviewSvg(sanitizeSvg(svg));
          setValidationError("");
        }
      } catch (err) {
        if (cancelled) return;
        const msg =
          err instanceof Error ? err.message : String(err);
        setValidationError(msg);
        setPreviewSvg("");
      }
    }

    void renderMermaid();

    return () => {
      cancelled = true;
    };
  }, [source]);

  // -----------------------------------------------------------------------
  // Auto-Save
  // -----------------------------------------------------------------------

  const performAutoSave = useCallback(
    async (currentSource: string) => {
      // Read the ref, not the `isDirty` state: this function is invoked from a
      // debounce timer scheduled by an older render, so the state variable
      // captured here would still be the mount-time `false` and would abort
      // every auto-save.
      if (!isDirtyRef.current) return;

      setSaveStatus("saving");
      try {
        await diagramsApi.saveMermaidSource(diagramId, currentSource);
        setIsDirty(false);
        isDirtyRef.current = false;
        setSaveStatus("saved");

        // REQ-L1-029 / B-DIAG-001: this save goes straight through
        // diagramsApi, bypassing useDiagramDetail's mutation and the
        // invalidation it normally triggers. Without this, the detail pane's
        // react-query cache (30s staleTime) keeps serving the pre-save
        // version — the backend has already created v2, the UI just never
        // asks for it again within that window.
        void queryClient.invalidateQueries({
          queryKey: diagramKeys.detail(diagramId),
        });

        setTimeout(() => setSaveStatus("idle"), 2000);
      } catch (err) {
        console.error("Mermaid auto-save failed", err);
        setSaveStatus("error");
      }
    },
    [diagramId, queryClient]
  );

  // Manual save
  const handleManualSave = useCallback(() => {
    void performAutoSave(source);
  }, [performAutoSave, source]);

  // Cleanup timers
  useEffect(() => {
    return () => {
      if (previewTimerRef.current) clearTimeout(previewTimerRef.current);
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    };
  }, []);

  // -----------------------------------------------------------------------
  // Render
  // -----------------------------------------------------------------------

  return (
    <div className={styles.container} data-testid="mermaid-editor">
      {/* Split view */}
      <div className={styles.splitView}>
        {/* Left: Code editor */}
        <div className={styles.editorPane} data-testid="mermaid-editor-pane">
          <div className={styles.editorHeader}>
            <span>{t("mermaid.editor.title", "Mermaid Source")}</span>
            <button
              type="button"
              data-testid="mermaid-save-btn"
              onClick={handleManualSave}
              disabled={!isDirty || saveStatus === "saving"}
              style={{
                padding: "var(--space-1) var(--space-2)",
                background: "var(--color-primary)",
                color: "white",
                border: "none",
                borderRadius: "var(--radius-sm)",
                cursor: isDirty ? "pointer" : "not-allowed",
                fontSize: "var(--font-size-sm)",
                opacity: isDirty ? 1 : 0.6,
              }}
            >
              {saveStatus === "saving"
                ? t("actions.saving", "Saving...")
                : t("actions.save", "Save")}
            </button>
          </div>
          <div className={styles.editorBody}>
            <div
              ref={editorContainerRef}
              className={styles.codeMirrorWrapper}
              data-testid="mermaid-code-editor"
            />
          </div>
        </div>

        {/* Right: Live preview */}
        <div className={styles.previewPane} data-testid="mermaid-preview-pane">
          <div className={styles.editorHeader}>
            <span>{t("mermaid.preview.title", "Live Preview")}</span>
            {detectedType && (
              <span style={{ fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)" }}>
                {detectedType}
              </span>
            )}
          </div>
          <div className={styles.previewBody}>
            {isLoadingPreview ? (
              <div className={styles.previewLoading} data-testid="mermaid-preview-loading">
                {t("mermaid.preview.loading", "Rendering...")}
              </div>
            ) : previewSvg ? (
              <div
                className={styles.previewSvg}
                data-testid="mermaid-preview-svg"
                dangerouslySetInnerHTML={{ __html: previewSvg }}
              />
            ) : validationError ? (
              <div className={styles.previewFallback} data-testid="mermaid-preview-fallback">
                {source || t("mermaid.preview.empty", "No source code")}
              </div>
            ) : (
              <div className={styles.previewLoading}>
                {t("mermaid.preview.empty", "No source code")}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Error banner */}
      {validationError && (
        <div className={styles.errorBanner} data-testid="mermaid-error" role="alert">
          <span className={styles.errorIcon}>⚠</span>
          <span>{validationError}</span>
        </div>
      )}

      {/* Status bar */}
      <div className={styles.statusBar} data-testid="mermaid-status-bar">
        <span>
          {detectedType
            ? `${t("mermaid.status.type", "Type")}: ${detectedType}`
            : t("mermaid.status.noPreview", "No preview")}
        </span>
        <span
          className={
            saveStatus === "saved"
              ? styles.statusSaved
              : saveStatus === "error"
                ? styles.statusError
                : isDirty
                  ? styles.statusUnsaved
                  : ""
          }
          data-testid="mermaid-save-status"
          role={saveStatus === "error" ? "alert" : "status"}
        >
          {saveStatus === "saving"
            ? t("canvas.status.saving", "Saving...")
            : saveStatus === "saved"
              ? t("canvas.status.saved", "Saved")
              : saveStatus === "error"
                ? t("canvas.status.error", "Save failed")
                : isDirty
                  ? t("canvas.status.unsaved", "Unsaved changes")
                  : t("canvas.status.idle", "Ready")}
        </span>
      </div>
    </div>
  );
}

export default MermaidEditor;
