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

const overlayStyle: React.CSSProperties = {
  position: "fixed",
  inset: 0,
  background: "rgba(0, 0, 0, 0.45)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  zIndex: 1000,
};

const dialogStyle: React.CSSProperties = {
  background: "var(--color-surface)",
  borderRadius: "var(--radius-lg)",
  boxShadow: "var(--shadow-md)",
  width: "100%",
  maxWidth: "480px",
  display: "flex",
  flexDirection: "column",
  overflow: "hidden",
};

const headerStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  padding: "var(--space-4) var(--space-5)",
  borderBottom: "1px solid var(--color-border)",
};

const bodyStyle: React.CSSProperties = {
  padding: "var(--space-4) var(--space-5)",
  display: "flex",
  flexDirection: "column",
  gap: "var(--space-3)",
};

const footerStyle: React.CSSProperties = {
  display: "flex",
  justifyContent: "flex-end",
  gap: "var(--space-2)",
  padding: "var(--space-4) var(--space-5)",
  borderTop: "1px solid var(--color-border)",
};

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "var(--space-2) var(--space-3)",
  borderRadius: "var(--radius-md)",
  border: "1px solid var(--color-border)",
  fontSize: "var(--font-size-sm)",
  background: "var(--color-surface)",
  color: "var(--color-text)",
  boxSizing: "border-box",
};

const labelStyle: React.CSSProperties = {
  fontWeight: 600,
  display: "block",
  marginBottom: "var(--space-1)",
  color: "var(--color-text)",
  fontSize: "var(--font-size-sm)",
};

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

  const handleBackdropClick = useCallback(
    (e: React.MouseEvent<HTMLDivElement>): void => {
      if (e.target === e.currentTarget) onClose();
    },
    [onClose]
  );

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

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={t("reviews.signatureDialog.title", "Confirm with signature")}
      data-testid="signature-dialog"
      style={overlayStyle}
      onClick={handleBackdropClick}
    >
      <div style={dialogStyle}>
        <div style={headerStyle}>
          <h3 style={{ margin: 0, fontSize: "var(--font-size-lg)", fontWeight: 700 }}>
            {t("reviews.signatureDialog.title", "Confirm with signature")} ({targetState})
          </h3>
          <button
            type="button"
            data-testid="signature-dialog-close"
            onClick={onClose}
            aria-label={t("actions.close", "Close")}
            style={{ background: "none", border: "none", cursor: "pointer", fontSize: "1.25rem" }}
          >
            ×
          </button>
        </div>

        <form onSubmit={(e) => void handleSubmit(e)} style={{ display: "contents" }}>
          <div style={bodyStyle}>
            <p style={{ margin: 0, color: "var(--color-text-muted)", fontSize: "var(--font-size-sm)" }}>
              {t(
                "reviews.signatureDialog.description",
                "This transition requires a signature. Enter your password or a 6-digit TOTP code to continue."
              )}
            </p>

            <div>
              <label htmlFor="signature-dialog-credential" style={labelStyle}>
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
                style={inputStyle}
              />
            </div>

            <div>
              <label htmlFor="signature-dialog-reason" style={labelStyle}>
                {t("reviews.signatureDialog.reasonLabel", "Reason")}
                {requiresChangeReason && <span style={{ color: "var(--color-danger)" }}> *</span>}
              </label>
              <textarea
                id="signature-dialog-reason"
                data-testid="signature-dialog-reason-input"
                value={changeReason}
                onChange={(e) => setChangeReason(e.target.value)}
                placeholder={t("reviews.signatureDialog.reasonPlaceholder", "Reason for this decision")}
                rows={3}
                disabled={isSubmitting}
                style={{ ...inputStyle, fontFamily: "inherit" }}
              />
            </div>

            {submitError && (
              <p
                role="alert"
                data-testid="signature-dialog-error"
                style={{ margin: 0, color: "var(--color-danger)", fontSize: "var(--font-size-sm)" }}
              >
                {submitError}
              </p>
            )}
          </div>

          <div style={footerStyle}>
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
              data-testid="signature-dialog-submit"
              className="btn-primary"
              disabled={isSubmitting}
            >
              {isSubmitting
                ? t("reviews.signatureDialog.submitting", "Confirming...")
                : t("reviews.signatureDialog.submit", "Confirm")}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

SignatureDialog.displayName = "SignatureDialog";
