/**
 * ARCH-L1-001 ReactFrontend — SignatureDialog (COMP-RF-REV-002).
 *
 * leaf_id: COMP-RF-REV-002
 * req_id:  REQ-144 (Review/Approval UI — signature-gated transitions)
 *
 * Modal collecting a credential (password or TOTP code) plus an optional
 * change_reason before a `signature_gate: true` workflow transition is
 * POSTed. Adapted from the CreateTraceLinkDialog modal shell (overlay +
 * header + body + footer) so the visual language matches the rest of the
 * app.
 *
 * Error states surfaced verbatim from the backend (workflow/transition_
 * validator.py):
 *   - "Signature required"  → credential missing/empty (EC_SIGNATURE_REQUIRED)
 *   - "Signature invalid"   → wrong password/TOTP     (EC_SIGNATURE_INVALID)
 * A 403 (ForbiddenError) means the caller lacks the approver role for the
 * target state; the parent's `onSubmit` re-throws these so this dialog can
 * render them inline instead of closing.
 */

import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";
import { extractErrorMessage } from "../../api/client";
import { ForbiddenError } from "../../api/errors";
import { Dialog } from "../shared/Dialog";
import styles from "./SignatureDialog.module.css";

export interface SignatureDialogProps {
  isOpen: boolean;
  /** The workflow state this transition moves to (shown in the title). */
  targetState: string;
  /** Whether the underlying transition requires a non-empty change_reason. */
  requiresChangeReason: boolean;
  /** Pre-fill the reason field with whatever the caller already typed. */
  initialChangeReason?: string;
  onClose: () => void;
  /** POSTs the transition; rejects on validation/permission failure. */
  onSubmit: (credential: string, changeReason: string) => Promise<void>;
}

export function SignatureDialog({
  isOpen,
  targetState,
  requiresChangeReason,
  initialChangeReason,
  onClose,
  onSubmit,
}: SignatureDialogProps): JSX.Element | null {
  const { t } = useTranslation();
  const [credential, setCredential] = useState("");
  const [changeReason, setChangeReason] = useState(initialChangeReason ?? "");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const handleSubmit = useCallback(
    async (e: React.FormEvent<HTMLFormElement>): Promise<void> => {
      e.preventDefault();

      if (!credential.trim()) {
        setSubmitError(t("reviews.signatureDialog.credentialRequired"));
        return;
      }
      if (requiresChangeReason && !changeReason.trim()) {
        setSubmitError(t("reviews.changeReasonRequired"));
        return;
      }

      setIsSubmitting(true);
      setSubmitError(null);
      try {
        await onSubmit(credential, changeReason);
      } catch (err: unknown) {
        if (err instanceof ForbiddenError) {
          setSubmitError(err.message || t("reviews.forbidden"));
        } else {
          setSubmitError(extractErrorMessage(err));
        }
      } finally {
        setIsSubmitting(false);
      }
    },
    [credential, changeReason, requiresChangeReason, onSubmit, t]
  );

  if (!isOpen) return null;

  const formId = "signature-dialog-form";

  return (
    <Dialog
      title={`${t("reviews.signatureDialog.title", "Confirm with signature")} (${targetState})`}
      onClose={onClose}
      size="sm"
      testId="signature-dialog"
      footer={
        <div className={styles.footer}>
          <button
            type="button"
            data-testid="signature-dialog-cancel"
            className="btn-secondary"
            onClick={onClose}
            disabled={isSubmitting}
          >
            {t("reviews.signatureDialog.cancel", "Cancel")}
          </button>
          <button
            type="submit"
            form={formId}
            data-testid="signature-dialog-submit"
            className="btn-primary"
            disabled={isSubmitting}
          >
            {isSubmitting
              ? t("reviews.signatureDialog.submitting", "Confirming...")
              : t("reviews.signatureDialog.submit", "Confirm")}
          </button>
        </div>
      }
    >
      <form id={formId} onSubmit={(e) => void handleSubmit(e)} className={styles.body}>
        <p className={styles.description}>
          {t(
            "reviews.signatureDialog.description",
            "This transition requires a signature. Enter your password or a 6-digit TOTP code to continue."
          )}
        </p>

        <div>
          <label htmlFor="signature-dialog-credential" className={styles.label}>
            {t("reviews.signatureDialog.credentialLabel", "Password or TOTP code")}
          </label>
          <input
            id="signature-dialog-credential"
            data-testid="signature-dialog-credential-input"
            type="password"
            autoComplete="off"
            value={credential}
            onChange={(e) => setCredential(e.target.value)}
            placeholder={t(
              "reviews.signatureDialog.credentialPlaceholder",
              "Enter your password or TOTP code"
            )}
            disabled={isSubmitting}
            className={styles.input}
          />
        </div>

        <div>
          <label htmlFor="signature-dialog-reason" className={styles.label}>
            {t("reviews.signatureDialog.reasonLabel", "Reason")}
            {requiresChangeReason && <span className={styles.required}> *</span>}
          </label>
          <textarea
            id="signature-dialog-reason"
            data-testid="signature-dialog-reason-input"
            value={changeReason}
            onChange={(e) => setChangeReason(e.target.value)}
            placeholder={t("reviews.signatureDialog.reasonPlaceholder", "Reason for this decision")}
            rows={3}
            disabled={isSubmitting}
            className={styles.input + " " + styles.reasonInput}
          />
        </div>

        {submitError && (
          <p
            role="alert"
            data-testid="signature-dialog-error"
            className={styles.errorText}
          >
            {submitError}
          </p>
        )}
      </form>
    </Dialog>
  );
}

SignatureDialog.displayName = "SignatureDialog";
