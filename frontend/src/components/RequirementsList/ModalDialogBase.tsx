/**
 * ModalDialogBase — Unified form pattern for AdrList, RiskList, IssueList.
 *
 * Extracted from REQ-L1-040 (SE Masks Unification Phase 1).
 * Provides standardized form layout, styling, and state management patterns.
 *
 * Generic component supporting arbitrary field configurations and submit handlers.
 */

import { useTranslation } from "react-i18next";

// Shared style constants — unified across all entity types
export const SHARED_STYLES = {
  input: {
    width: "100%",
    padding: "var(--space-2) var(--space-3)",
    borderRadius: "var(--radius-md)",
    border: "1px solid var(--color-border)",
    fontSize: "var(--font-size-sm)",
    background: "var(--color-surface)",
    color: "var(--color-text)",
    fontFamily: "var(--font-sans)",
    boxSizing: "border-box" as const,
  },
  label: {
    fontWeight: 600 as const,
    fontSize: "var(--font-size-sm)",
    color: "var(--color-text)",
    display: "block" as const,
    marginBottom: "var(--space-1)",
  },
  primaryButton: {
    background: "var(--color-primary)",
    color: "white",
    border: "none",
    borderRadius: "var(--radius-md)",
    padding: "var(--space-2) var(--space-4)",
    fontSize: "var(--font-size-sm)",
    fontWeight: 600 as const,
    cursor: "pointer",
  } as React.CSSProperties,
};

export interface ModalDialogBaseProps {
  /** Dialog title (e.g., "ADRs", "Risks", "Issues") */
  title: string;

  /** Whether the create form is visible */
  isOpen: boolean;

  /** Toggle form visibility */
  onToggle: () => void;

  /** Form content — rendered between form tag and footer buttons */
  children: React.ReactNode;

  /** Submit handler — receives form event */
  onSubmit: (e: React.FormEvent<HTMLFormElement>) => Promise<void>;

  /** Cancel handler — hides form and resets state */
  onCancel: () => void;

  /** Error message to display in alert */
  error?: string | null;

  /** Whether submit is in progress */
  isSubmitting?: boolean;

  /** List of items (for empty state check) */
  itemCount: number;

  /** Form test ID prefix (e.g., "adr" → "adr-create-form") */
  testIdPrefix: string;

  /** Button test ID prefix (e.g., "adr" → "adr-create-btn") */
  buttonTestIdPrefix: string;

  /** Custom label for "New" button (defaults to "New {entityKey}") */
  newButtonLabel?: string;
}

/**
 * ModalDialogBase — Renders the standard form layout and structure.
 *
 * Usage:
 * ```tsx
 * <ModalDialogBase
 *   title="ADRs"
 *   entityKey="adrs"
 *   isOpen={showCreate}
 *   onToggle={() => setShowCreate(!showCreate)}
 *   onSubmit={handleSubmit}
 *   onCancel={handleCancel}
 *   error={formError}
 *   itemCount={items.length}
 *   testIdPrefix="adr"
 *   buttonTestIdPrefix="adr"
 * >
 *   <div>
 *     <label htmlFor="adr-title">Title</label>
 *     <input id="adr-title" value={title} onChange={...} />
 *   </div>
 * </ModalDialogBase>
 * ```
 */
export function ModalDialogBase({
  title,
  isOpen,
  onToggle,
  children,
  onSubmit,
  onCancel,
  error,
  isSubmitting = false,
  itemCount,
  testIdPrefix,
  buttonTestIdPrefix,
  newButtonLabel,
}: ModalDialogBaseProps): JSX.Element {
  const { t } = useTranslation();

  const buttonLabel = newButtonLabel || `+ ${t("actions.new")} ${title}`;

  return (
    <div>
      {/* Header with title and toggle button */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginTop: 0,
          marginBottom: "var(--space-6)",
        }}
      >
        <h2
          style={{
            fontSize: "var(--font-size-2xl)",
            fontWeight: 700,
            color: "var(--color-text)",
            margin: 0,
          }}
        >
          {title}
        </h2>
        <button
          type="button"
          data-testid={`${buttonTestIdPrefix}-create-btn`}
          onClick={onToggle}
          style={SHARED_STYLES.primaryButton}
        >
          {isOpen ? t("actions.cancel") : buttonLabel}
        </button>
      </div>

      {/* Conditional form rendering */}
      {isOpen && (
        <form
          data-testid={`${testIdPrefix}-create-form`}
          onSubmit={(e) => void onSubmit(e)}
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "var(--space-3)",
            padding: "var(--space-4)",
            marginBottom: "var(--space-4)",
            background: "var(--color-surface-raised)",
            border: "1px solid var(--color-border)",
            borderRadius: "var(--radius-lg)",
          }}
        >
          {/* Form fields injected via children */}
          {children}

          {/* Error display */}
          {error && (
            <p
              role="alert"
              style={{
                color: "var(--color-danger)",
                fontSize: "var(--font-size-sm)",
                margin: 0,
              }}
            >
              {error}
            </p>
          )}

          {/* Form buttons */}
          <div style={{ display: "flex", gap: "var(--space-2)", justifyContent: "flex-end" }}>
            <button
              type="button"
              data-testid={`${testIdPrefix}-cancel-btn`}
              onClick={onCancel}
              disabled={isSubmitting}
              style={{
                background: "var(--color-surface)",
                color: "var(--color-text)",
                border: "1px solid var(--color-border)",
                borderRadius: "var(--radius-md)",
                padding: "var(--space-2) var(--space-4)",
                fontSize: "var(--font-size-sm)",
                fontWeight: 600,
                cursor: isSubmitting ? "not-allowed" : "pointer",
              }}
            >
              {t("actions.cancel")}
            </button>
            <button
              type="submit"
              data-testid={`${testIdPrefix}-save-btn`}
              disabled={isSubmitting}
              style={{
                ...SHARED_STYLES.primaryButton,
                opacity: isSubmitting ? 0.6 : 1,
                cursor: isSubmitting ? "not-allowed" : "pointer",
              }}
            >
              {isSubmitting ? t("actions.saving") : t("actions.save")}
            </button>
          </div>
        </form>
      )}

      {/* Empty state — rendered outside form for proper layout */}
      {itemCount === 0 && !isOpen && (
        <p
          style={{
            fontSize: "var(--font-size-base)",
            color: "var(--color-text-muted)",
            padding: "var(--space-6)",
            background: "var(--color-surface-raised)",
            borderRadius: "var(--radius-lg)",
            border: "1px dashed var(--color-border)",
          }}
        >
          {t("editor.empty")}
        </p>
      )}
    </div>
  );
}

export default ModalDialogBase;
