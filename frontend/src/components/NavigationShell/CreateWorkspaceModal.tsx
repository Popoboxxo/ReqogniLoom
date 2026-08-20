/**
 * ARCH-L1-001 ReactFrontend — Create Workspace Modal.
 *
 * leaf_id: COMP-RF-001 (NavigationShell)
 * req_id:  REQ-D25 (Neuer-Workspace-Dialog aus Navigationsbaum herausloesen)
 *
 * Replaces the inline create-workspace form that used to live inside
 * SidebarNavigation's workspace switcher. Moving it into a modal keeps the
 * sidebar tree free of form clutter (same rationale as CreateTraceLinkDialog,
 * REQ-005).
 */

import React, { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { workspacesApi } from "../../api/workspaces";
import { Dialog } from "../shared/Dialog";
import type { TerminologyProfile, Workspace, WorkspacePreset } from "../../types";
// F-04 (code review, 2026-08-19): `.inputError`/`.fieldError` live in the
// shared module (see its own header comment) so this dialog doesn't
// duplicate them in a component-local `.module.css`.
import fieldHints from "../shared/FieldHints.module.css";

export interface CreateWorkspaceModalProps {
  /** Controls modal visibility. */
  isOpen: boolean;
  /** Called when the user closes the modal without creating a workspace. */
  onClose: () => void;
  /** Called after a workspace has been successfully created. */
  onCreated: (workspace: Workspace) => void;
}

// ---------------------------------------------------------------------------
// Styles — the overlay/panel/header chrome now comes from <Dialog>; only the
// form-content styles remain here.
// ---------------------------------------------------------------------------

const bodyStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: "var(--space-3)",
};

const footerStyle: React.CSSProperties = {
  display: "flex",
  justifyContent: "flex-end",
  gap: "var(--space-2)",
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
  fontFamily: "var(--font-sans)",
};

const labelStyle: React.CSSProperties = {
  fontWeight: 600,
  display: "block",
  marginBottom: "var(--space-1)",
  color: "var(--color-text)",
  fontSize: "var(--font-size-sm)",
};

interface CreateWorkspaceFormData {
  name: string;
  preset: WorkspacePreset;
  terminology_profile: TerminologyProfile;
  language: string;
}

const DEFAULT_FORM_DATA: CreateWorkspaceFormData = {
  name: "",
  preset: "standard",
  terminology_profile: "se_mode",
  language: "de",
};

/**
 * Modal dialog for creating a new workspace (REQ-D25).
 *
 * Owns the form state and the create API call; on success it hands the
 * created workspace to `onCreated` and closes itself. The caller (sidebar)
 * is responsible for app-level side effects such as reloading the workspace
 * list and navigating to the new workspace.
 */
export function CreateWorkspaceModal({
  isOpen,
  onClose,
  onCreated,
}: CreateWorkspaceModalProps): JSX.Element | null {
  const { t } = useTranslation();

  const [formData, setFormData] = useState<CreateWorkspaceFormData>(DEFAULT_FORM_DATA);
  const [isCreating, setIsCreating] = useState<boolean>(false);
  const [createError, setCreateError] = useState<string | null>(null);
  // BUG-08 (Systemaudit 2026-08-18, §4): the required-name check used to
  // surface only as a text banner elsewhere in the dialog — the input itself
  // never indicated it was the field at fault (no border, no icon, no
  // aria-invalid). Tracked separately from `createError` (server-side
  // rejections) so the field-level marker only reacts to *this* client-side
  // check and clears the moment the user starts correcting it.
  const [nameInvalid, setNameInvalid] = useState<boolean>(false);
  const nameInputRef = useRef<HTMLInputElement | null>(null);

  // Reset form state whenever the modal opens.
  useEffect(() => {
    if (!isOpen) return;
    setFormData(DEFAULT_FORM_DATA);
    setCreateError(null);
    setNameInvalid(false);
  }, [isOpen]);

  const handleClose = (): void => {
    if (isCreating) return;
    setCreateError(null);
    setNameInvalid(false);
    onClose();
  };

  const handleSubmit = async (
    event: React.FormEvent<HTMLFormElement>
  ): Promise<void> => {
    event.preventDefault();
    if (!formData.name.trim()) {
      // F-03 (code review, 2026-08-19): a client-side check surfaces at the
      // field itself only — never duplicated into the page-level banner
      // too (a screen reader must not announce the identical "Name is
      // required" message twice). Any stale banner from a previous
      // server-side rejection is cleared here as well.
      setCreateError(null);
      setNameInvalid(true);
      return;
    }
    setIsCreating(true);
    setCreateError(null);
    try {
      const ws = await workspacesApi.create({
        name: formData.name.trim(),
        preset: formData.preset,
        terminology_profile: formData.terminology_profile,
        language: formData.language,
      });
      onCreated(ws);
      onClose();
    } catch (err) {
      const apiErr = err as { error?: { message?: string } };
      setCreateError(
        apiErr?.error?.message ||
          t("workspaceCreate.errorGeneric") ||
          "Failed to create workspace"
      );
    } finally {
      setIsCreating(false);
    }
  };

  if (!isOpen) return null;

  // The submit/cancel buttons live in <Dialog>'s `footer` slot, which renders
  // as a sibling of the form below rather than inside it — `form` on both
  // buttons keeps Enter-to-submit and the button click wired to the same
  // <form data-testid="create-workspace-form">.
  const formId = "create-workspace-form";

  return (
    <Dialog
      title={t("workspaceCreate.title") || "Create workspace"}
      onClose={handleClose}
      size="sm"
      testId="create-workspace-modal"
      initialFocusRef={nameInputRef}
      footer={
        <div style={footerStyle}>
          <button
            type="button"
            data-testid="create-workspace-cancel"
            onClick={handleClose}
            disabled={isCreating}
            style={{
              background: "transparent",
              color: "var(--color-text)",
              border: "1px solid var(--color-border)",
              borderRadius: "var(--radius-sm)",
              padding: "var(--space-2) var(--space-4)",
              cursor: isCreating ? "not-allowed" : "pointer",
              fontSize: "var(--font-size-sm)",
              fontFamily: "inherit",
            }}
          >
            {t("workspaceCreate.cancel") || "Cancel"}
          </button>
          <button
            type="submit"
            form={formId}
            data-testid="new-workspace-submit"
            disabled={isCreating}
            style={{
              background: "var(--color-primary)",
              color: "white",
              border: "none",
              borderRadius: "var(--radius-sm)",
              padding: "var(--space-2) var(--space-4)",
              cursor: isCreating ? "not-allowed" : "pointer",
              fontSize: "var(--font-size-sm)",
              fontWeight: 600,
              fontFamily: "inherit",
              opacity: isCreating ? 0.6 : 1,
            }}
          >
            {isCreating
              ? t("workspaceCreate.creating")
              : t("workspaceCreate.submit")}
          </button>
        </div>
      }
    >
      <form id={formId} data-testid="create-workspace-form" onSubmit={handleSubmit} style={bodyStyle}>
        <div>
          <label style={labelStyle} htmlFor="new-workspace-name">
            {t("workspaceCreate.namePlaceholder") || "Name"}
          </label>
          <input
            ref={nameInputRef}
            id="new-workspace-name"
            type="text"
            data-testid="new-workspace-name"
            placeholder={t("workspaceCreate.namePlaceholder") || "Name"}
            value={formData.name}
            onChange={(e) => {
              setFormData((d) => ({ ...d, name: e.target.value }));
              // BUG-08: clear the field-level error the moment the user
              // starts correcting it, same UX as the create-form hints
              // elsewhere (#339/#412) — the message described the *previous*
              // attempt, not the one they are now typing.
              if (e.target.value.trim()) setNameInvalid(false);
              // F-01 (code review, 2026-08-19): a stale banner from a
              // previous *server-side* rejection must not keep contradicting
              // a field the user is actively correcting — same pattern as
              // RequirementEditors.tsx's create-form title input (#340).
              if (createError) setCreateError(null);
            }}
            disabled={isCreating}
            style={inputStyle}
            className={nameInvalid ? fieldHints.inputError : undefined}
            aria-invalid={nameInvalid}
            aria-describedby={nameInvalid ? "new-workspace-name-error" : undefined}
          />
          {nameInvalid && (
            <p
              id="new-workspace-name-error"
              role="alert"
              data-testid="new-workspace-name-field-error"
              className={fieldHints.fieldError}
            >
              <span aria-hidden="true">⚠</span>
              {t("workspaceCreate.errorRequired") || "Name is required"}
            </p>
          )}
        </div>

        <div>
          <label style={labelStyle} htmlFor="create-workspace-preset">
            {t("workspaceCreate.presetLabel") || "Preset"}
          </label>
          <select
            id="create-workspace-preset"
            data-testid="create-workspace-preset"
            value={formData.preset}
            onChange={(e) =>
              setFormData((d) => ({
                ...d,
                preset: e.target.value as WorkspacePreset,
              }))
            }
            disabled={isCreating}
            style={inputStyle}
          >
            <option value="minimal">minimal</option>
            <option value="standard">standard</option>
            <option value="extended">extended</option>
          </select>
        </div>

        <div>
          <label style={labelStyle} htmlFor="create-workspace-language">
            {t("workspaceCreate.languageLabel") || "Language"}
          </label>
          <select
            id="create-workspace-language"
            data-testid="create-workspace-language"
            value={formData.language}
            onChange={(e) =>
              setFormData((d) => ({ ...d, language: e.target.value }))
            }
            disabled={isCreating}
            style={inputStyle}
          >
            <option value="de">DE</option>
            <option value="en">EN</option>
          </select>
        </div>

        {createError && (
          <div
            role="alert"
            data-testid="create-workspace-error"
            style={{
              color: "var(--color-danger)",
              fontSize: "0.75rem",
            }}
          >
            {createError}
          </div>
        )}
      </form>
    </Dialog>
  );
}
