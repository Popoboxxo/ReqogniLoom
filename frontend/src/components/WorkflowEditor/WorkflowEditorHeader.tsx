/**
 * REQ-176 — WorkflowEditorHeader.
 *
 * Title, active-preset badge, a disabled Edit-Mode toggle (Phase 2), and an
 * Export dropdown. "Copy as Mermaid" is functional; PNG/SVG download are
 * Phase-1 placeholders (design brief §3).
 */

import { useEffect, useRef, useState, type ReactNode } from "react";
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
  title = "Workflow Editor",
  presetControl,
}: WorkflowEditorHeaderProps): JSX.Element {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement | null>(null);

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
        <h1 className={styles.headerTitle}>{title}</h1>
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
              ? "Switch to read-only"
              : "Enable edit mode"
            : "Edit mode requires the admin role"
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
          {editMode ? "Editing" : "Read-only"}
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
          Export
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
              Copy as Mermaid
            </button>
            <button
              type="button"
              className={styles.dropdownItem}
              role="menuitem"
              disabled
              title="Coming soon"
            >
              <Download size={14} />
              Download PNG
            </button>
            <button
              type="button"
              className={styles.dropdownItem}
              role="menuitem"
              disabled
              title="Coming soon"
            >
              <Download size={14} />
              Download SVG
            </button>
          </div>
        )}
      </div>
    </header>
  );
}
