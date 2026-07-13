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

import React, { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { workspacesApi } from "../../api/workspaces";
import type { TerminologyProfile, Workspace, WorkspacePreset } from "../../types";

export interface CreateWorkspaceModalProps {
  /** Controls modal visibility. */
  isOpen: boolean;
  /** Called when the user closes the modal without creating a workspace. */
  onClose: () => void;
  /** Called after a workspace has been successfully created. */
  onCreated: (workspace: Workspace) => void;
}

// ---------------------------------------------------------------------------
// Styles — mirrors the CreateTraceLinkDialog modal pattern.
// ---------------------------------------------------------------------------

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
  maxWidth: "420px",
  maxHeight: "90vh",
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
  overflowY: "auto",
  flex: 1,
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

  // Reset form state whenever the modal opens.
  useEffect(() => {
    if (!isOpen) return;
    setFormData(DEFAULT_FORM_DATA);
    setCreateError(null);
  }, [isOpen]);

  // Prevent background scroll while the modal is open (same as CreateTraceLinkDialog).
  useEffect(() => {
    if (!isOpen) return;
    const scrollbarWidth = window.innerWidth - document.documentElement.clientWidth;
    document.body.style.overflow = "hidden";
    document.body.style.paddingRight = `${scrollbarWidth}px`;
    return () => {
      document.body.style.overflow = "";
      document.body.style.paddingRight = "";
    };
  }, [isOpen]);

  const handleClose = (): void => {
    if (isCreating) return;
    setCreateError(null);
    onClose();
  };

  const handleSubmit = async (
    event: React.FormEvent<HTMLFormElement>
  ): Promise<void> => {
    event.preventDefault();
    if (!formData.name.trim()) {
      setCreateError(
        t("workspaceCreate.errorRequired") ||
          t("workspace.create.nameRequired") ||
          "Name is required"
      );
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
          t("workspace.create.error") ||
          "Failed to create workspace"
      );
    } finally {
      setIsCreating(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div
      style={overlayStyle}
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) handleClose();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={t("workspace.create.title") || "Create workspace"}
        data-testid="create-workspace-modal"
        style={dialogStyle}
      >
        <form data-testid="create-workspace-form" onSubmit={handleSubmit}>
          <div style={headerStyle}>
            <h2 style={{ margin: 0, fontSize: "1.1rem", color: "var(--color-text)" }}>
              {t("workspace.create.title") || "Create workspace"}
            </h2>
            <button
              type="button"
              data-testid="create-workspace-close"
              onClick={handleClose}
              disabled={isCreating}
              aria-label={t("common.close") || "Close"}
              style={{
                background: "transparent",
                border: "none",
                fontSize: "1.25rem",
                lineHeight: 1,
                cursor: isCreating ? "not-allowed" : "pointer",
                color: "var(--color-text-muted)",
              }}
            >
              ×
            </button>
          </div>

          <div style={bodyStyle}>
            <div>
              <label style={labelStyle} htmlFor="new-workspace-name">
                {t("workspace.create.namePlaceholder") || "Name"}
              </label>
              <input
                id="new-workspace-name"
                type="text"
                data-testid="new-workspace-name"
                placeholder={t("workspace.create.namePlaceholder") || "Name"}
                value={formData.name}
                onChange={(e) =>
                  setFormData((d) => ({ ...d, name: e.target.value }))
                }
                disabled={isCreating}
                autoFocus
                style={inputStyle}
              />
            </div>

            <div>
              <label style={labelStyle} htmlFor="create-workspace-preset">
                {t("workspace.create.preset") || "Preset"}
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
                {t("workspace.create.language") || "Language"}
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
                  color: "var(--color-danger, #f87171)",
                  fontSize: "0.75rem",
                }}
              >
                {createError}
              </div>
            )}
          </div>

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
              {t("workspace.create.cancel") || "Cancel"}
            </button>
            <button
              type="submit"
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
        </form>
      </div>
    </div>
  );
}
