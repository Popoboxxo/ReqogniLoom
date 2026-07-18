/**
 * REQ-177 — StateDialog: Add / Edit a workflow state (Phase 2, design brief §10).
 *
 * The backend model stores a state as a plain name string (byte-identical to
 * the entity's Status.choices); the visual *type* is derived from the graph
 * topology and is not persisted, so this dialog is a focused Name form plus an
 * explanatory note rather than the mock's non-functional Type radio. A newly
 * added state is unwired — the user connects it afterwards by dragging a
 * transition to it.
 */

import { useState } from "react";
import { WorkflowModal } from "./WorkflowModal";
import styles from "./WorkflowEditor.module.css";

interface StateDialogProps {
  mode: "add" | "edit";
  /** Current name when editing (used as the initial value). */
  initialName?: string;
  onSubmit: (name: string) => Promise<void> | void;
  onClose: () => void;
  busy?: boolean;
  errorMessage?: string | null;
}

export function StateDialog({
  mode,
  initialName = "",
  onSubmit,
  onClose,
  busy = false,
  errorMessage,
}: StateDialogProps): JSX.Element {
  const [name, setName] = useState(initialName);
  const trimmed = name.trim();
  const canSubmit = trimmed.length > 0 && !trimmed.includes("__") && !busy;

  const submit = (): void => {
    if (!canSubmit) return;
    void onSubmit(trimmed);
  };

  return (
    <WorkflowModal
      title={mode === "add" ? "Add State" : "Edit State"}
      onClose={onClose}
      testId="workflow-state-dialog"
      footer={
        <>
          <button
            type="button"
            className={styles.btnGhost}
            onClick={onClose}
            data-testid="workflow-state-cancel"
          >
            Cancel
          </button>
          <button
            type="button"
            className={styles.btnPrimary}
            onClick={submit}
            disabled={!canSubmit}
            data-testid="workflow-state-submit"
          >
            {mode === "add" ? "Add State" : "Save"}
          </button>
        </>
      }
    >
      <div className={styles.field}>
        <label className={styles.fieldLabel} htmlFor="wf-state-name">
          Name
        </label>
        <input
          id="wf-state-name"
          className={styles.fieldInput}
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") submit();
          }}
          placeholder="e.g. IN_PROGRESS"
          autoComplete="off"
          spellCheck={false}
          data-testid="workflow-state-name-input"
        />
      </div>
      <p className={styles.modalText}>
        The state <strong>type</strong> (initial · active · terminal · error) is
        derived automatically from the state&apos;s transitions.
      </p>
      {errorMessage && (
        <p className={styles.modalError} role="alert" data-testid="workflow-state-error">
          {errorMessage}
        </p>
      )}
    </WorkflowModal>
  );
}
