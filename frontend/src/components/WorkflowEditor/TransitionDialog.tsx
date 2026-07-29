/**
 * REQ-177 — TransitionDialog: Add / Edit a workflow transition (design brief §10).
 *
 * Fields map 1:1 onto the backend model (allowed_roles, requires_change_reason,
 * signature_gate). The mock's free-text "Name" field is omitted — the backend
 * has no transition-name column and the edge label is derived as ``from → to``
 * (Phase 1 behaviour). ``from``/``to`` form the transition identity, so they are
 * read-only when editing; on add, ``from`` is prefilled and ``to`` is chosen
 * from the remaining states.
 */

import { useState } from "react";
import { Trans, useTranslation } from "react-i18next";
import { WorkflowModal } from "./WorkflowModal";
import type { WorkflowState } from "../../api/workflows";
import styles from "./WorkflowEditor.module.css";

export interface TransitionDraft {
  from_state: string;
  to_state: string;
  allowed_roles: string[];
  requires_change_reason: boolean;
  signature_gate: boolean;
}

interface TransitionDialogProps {
  mode: "add" | "edit";
  states: WorkflowState[];
  /** Prefilled/locked source state. */
  fromState: string;
  /** Prefilled target (edit mode, or drag-to-connect target). */
  toState?: string;
  initial?: {
    allowed_roles?: string[];
    requires_change_reason?: boolean;
    signature_gate?: boolean;
  };
  onSubmit: (draft: TransitionDraft) => Promise<void> | void;
  onClose: () => void;
  busy?: boolean;
  errorMessage?: string | null;
}

export function TransitionDialog({
  mode,
  states,
  fromState,
  toState = "",
  initial,
  onSubmit,
  onClose,
  busy = false,
  errorMessage,
}: TransitionDialogProps): JSX.Element {
  const { t } = useTranslation();
  const [to, setTo] = useState(toState);
  const [roles, setRoles] = useState(
    (initial?.allowed_roles ?? []).filter((r) => r !== "admin").join(", ")
  );
  const [requireReason, setRequireReason] = useState(
    initial?.requires_change_reason ?? false
  );
  const [signatureGate, setSignatureGate] = useState(
    initial?.signature_gate ?? false
  );

  const targets = states.filter((s) => s.id !== fromState);
  const canSubmit = to.length > 0 && !busy;

  const submit = (): void => {
    if (!canSubmit) return;
    void onSubmit({
      from_state: fromState,
      to_state: to,
      allowed_roles: roles
        .split(",")
        .map((r) => r.trim())
        .filter((r) => r.length > 0),
      requires_change_reason: requireReason,
      signature_gate: signatureGate,
    });
  };

  return (
    <WorkflowModal
      title={
        mode === "add"
          ? t("workflow.transitionDialog.addTitle")
          : t("workflow.transitionDialog.editTitle")
      }
      onClose={onClose}
      testId="workflow-transition-dialog"
      footer={
        <>
          <button
            type="button"
            className={styles.btnGhost}
            onClick={onClose}
            data-testid="workflow-transition-cancel"
          >
            {t("actions.cancel")}
          </button>
          <button
            type="button"
            className={styles.btnPrimary}
            onClick={submit}
            disabled={!canSubmit}
            data-testid="workflow-transition-submit"
          >
            {mode === "add"
              ? t("workflow.transitionDialog.submitAdd")
              : t("workflow.transitionDialog.submitSave")}
          </button>
        </>
      }
    >
      <div className={styles.field}>
        <span className={styles.fieldLabel}>{t("workflow.transitionDialog.from")}</span>
        <input
          className={styles.fieldInput}
          value={fromState}
          readOnly
          disabled
          data-testid="workflow-transition-from"
        />
      </div>

      <div className={styles.field}>
        <label className={styles.fieldLabel} htmlFor="wf-transition-to">
          {t("workflow.transitionDialog.toState")}
        </label>
        {mode === "edit" ? (
          <input
            id="wf-transition-to"
            className={styles.fieldInput}
            value={to}
            readOnly
            disabled
            data-testid="workflow-transition-to"
          />
        ) : (
          <select
            id="wf-transition-to"
            className={styles.fieldSelect}
            value={to}
            onChange={(e) => setTo(e.target.value)}
            data-testid="workflow-transition-to"
          >
            <option value="">{t("workflow.transitionDialog.toStatePlaceholder")}</option>
            {targets.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        )}
      </div>

      <div className={styles.field}>
        <label className={styles.fieldLabel} htmlFor="wf-transition-roles">
          {t("workflow.transitionDialog.allowedRoles")}
        </label>
        <input
          id="wf-transition-roles"
          className={styles.fieldInput}
          value={roles}
          onChange={(e) => setRoles(e.target.value)}
          placeholder={t("workflow.transitionDialog.allowedRolesPlaceholder")}
          autoComplete="off"
          data-testid="workflow-transition-roles"
        />
        <p className={styles.modalText}>
          <Trans i18nKey="workflow.transitionDialog.allowedRolesHint">
            Comma-separated. <strong>admin</strong> always retains transition
            rights.
          </Trans>
        </p>
      </div>

      <label className={styles.checkboxRow}>
        <input
          type="checkbox"
          checked={requireReason}
          onChange={(e) => setRequireReason(e.target.checked)}
          data-testid="workflow-transition-reason"
        />
        {t("workflow.transitionDialog.requireChangeReason")}
      </label>

      <label className={styles.checkboxRow}>
        <input
          type="checkbox"
          checked={signatureGate}
          onChange={(e) => setSignatureGate(e.target.checked)}
          data-testid="workflow-transition-signature"
        />
        {t("workflow.transitionDialog.requireSignature")}
      </label>

      {errorMessage && (
        <p
          className={styles.modalError}
          role="alert"
          data-testid="workflow-transition-error"
        >
          {errorMessage}
        </p>
      )}
    </WorkflowModal>
  );
}
