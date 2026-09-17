/**
 * REQ-176 — WorkflowEditorHeader.
 *
 * Title, active-preset badge, a disabled Edit-Mode toggle (Phase 2), and an
 * Export dropdown. "Copy as Mermaid" is functional; PNG/SVG download are
 * Phase-1 placeholders (design brief §3).
 */

import { useEffect, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, Code2, Download, Upload } from "lucide-react";
import styles from "./WorkflowEditor.module.css";

interface WorkflowEditorHeaderProps {
  preset: string;
  onCopyMermaid: () => void;
  canExport: boolean;
  editMode: boolean;
  onToggleEditMode: () => void;
  /** When false the toggle is disabled (user lacks the admin role). */
  canEdit: boolean;
  /** Header title — defaults to the workspace-scope "Workflow Editor". */
  title?: string;
  /**
   * Replaces the static preset badge with an interactive control (the global
   * preset segmented control, SCR-205). When omitted, the read-only badge shows.
   */
  presetControl?: ReactNode;
}

export function WorkflowEditorHeader({
  preset,
  onCopyMermaid,
  canExport,
  editMode,
  onToggleEditMode,
  canEdit,
  title,
  presetControl,
}: WorkflowEditorHeaderProps): JSX.Element {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const effectiveTitle = title ?? t("workflow.header.titleDefault");

  useEffect(() => {
    if (!open) return;
    function onDocClick(e: MouseEvent): void {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open]);

  return (
    <header className={styles.header} data-testid="workflow-editor-header">
      <div className={styles.headerTitleGroup}>
        <span className={styles.headerDot} aria-hidden="true" />
        <h1 className={styles.headerTitle}>{effectiveTitle}</h1>
      </div>

      {presetControl ?? (
        <span className={styles.presetBadge} data-testid="workflow-preset-badge">
          {preset}
        </span>
      )}

      <div className={styles.headerSpacer} />

      {/* Edit-mode toggle (REQ-177) — admin-gated. */}
      <button
        type="button"
        className={styles.toggleButton}
        role="switch"
        aria-checked={editMode}
        disabled={!canEdit}
        title={
          canEdit
            ? editMode
              ? t("workflow.header.editModeSwitchToReadOnly")
              : t("workflow.header.editModeEnable")
            : t("workflow.header.editModeRequiresAdmin")
        }
        onClick={onToggleEditMode}
        data-testid="workflow-edit-toggle"
      >
        <span
          className={`${styles.toggleTrack} ${
            editMode ? styles.toggleTrackOn : ""
          }`}
        >
          <span
            className={`${styles.toggleThumb} ${
              editMode ? styles.toggleThumbOn : ""
            }`}
          />
        </span>
        <span className={editMode ? styles.toggleTextOn : ""}>
          {editMode ? t("workflow.header.editing") : t("workflow.header.readOnly")}
        </span>
      </button>

      <div className={styles.dropdownWrap} ref={wrapRef}>
        <button
          type="button"
          className={`${styles.iconButton} ${styles.iconButtonPrimary}`}
          aria-haspopup="menu"
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
          data-testid="workflow-export-button"
        >
          <Upload size={14} />
          {t("workflow.header.export")}
          <ChevronDown size={14} />
        </button>
        {open && (
          <div className={styles.dropdownMenu} role="menu">
            <button
              type="button"
              className={styles.dropdownItem}
              role="menuitem"
              disabled={!canExport}
              onClick={() => {
                onCopyMermaid();
                setOpen(false);
              }}
              data-testid="workflow-copy-mermaid"
            >
              <Code2 size={14} />
              {t("workflow.header.copyAsMermaid")}
            </button>
            <button
              type="button"
              className={styles.dropdownItem}
              role="menuitem"
              disabled
              title={t("workflow.header.comingSoon")}
            >
              <Download size={14} />
              {t("workflow.header.downloadPng")}
            </button>
            <button
              type="button"
              className={styles.dropdownItem}
              role="menuitem"
              disabled
              title={t("workflow.header.comingSoon")}
            >
              <Download size={14} />
              {t("workflow.header.downloadSvg")}
            </button>
          </div>
        )}
      </div>
    </header>
  );
}
