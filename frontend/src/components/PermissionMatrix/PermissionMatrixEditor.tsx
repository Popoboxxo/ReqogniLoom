/**
 * REQ-181/182 — PermissionMatrixEditor: shared editable 4-role × 6-capability
 * boolean grid. Used by both the global Permission Defaults editor (SCR-206
 * Card 1) and the workspace override editor (SCR-202 Card 2), parameterized only
 * by the ``onSave`` target the parent binds.
 *
 * The shape is CLOSED — exactly the 4 roles as rows and 6 capabilities as
 * columns — so a malformed matrix is impossible to produce from the UI (it
 * always renders and sends the full grid). No new design-system primitive:
 * reuses the ``permissions-table`` th/td look and ``primaryButtonStyle``.
 */

import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  CAPABILITY_KEYS,
  ROLE_KEYS,
  normalizeMatrix,
  type CapabilityKey,
  type PermissionMatrix,
  type RoleKey,
} from "../../api/permission-defaults";

interface PermissionMatrixEditorProps {
  /** Current effective matrix (pre-fills the grid). */
  value: PermissionMatrix;
  /** Persist the full matrix. Rejects → surfaced by the parent via ``error``. */
  onSave: (matrix: PermissionMatrix) => Promise<void> | void;
  onCancel?: () => void;
  saving?: boolean;
  error?: string | null;
  savedOk?: boolean;
  /** Prefix for data-testids so multiple editors on one page stay distinct. */
  testIdPrefix?: string;
}

const thStyle: React.CSSProperties = {
  textAlign: "center",
  padding: "var(--space-2) var(--space-2)",
  fontSize: "var(--font-size-xs)",
  fontWeight: 600,
  color: "var(--color-text-muted)",
  textTransform: "uppercase",
  letterSpacing: "0.03em",
  borderBottom: "1px solid var(--color-border)",
};

const tdStyle: React.CSSProperties = {
  padding: "var(--space-2) var(--space-2)",
  fontSize: "var(--font-size-sm)",
  color: "var(--color-text)",
  borderBottom: "1px solid var(--color-border)",
  textAlign: "center",
  verticalAlign: "middle",
};

const primaryButtonStyle: React.CSSProperties = {
  background: "var(--color-primary)",
  color: "white",
  border: "none",
  borderRadius: "var(--radius-md)",
  padding: "var(--space-2) var(--space-4)",
  fontSize: "var(--font-size-sm)",
  fontWeight: 600,
  cursor: "pointer",
};

const cancelButtonStyle: React.CSSProperties = {
  background: "transparent",
  color: "var(--color-text-muted)",
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-md)",
  padding: "var(--space-2) var(--space-4)",
  fontSize: "var(--font-size-sm)",
  cursor: "pointer",
};

function matricesEqual(a: PermissionMatrix, b: PermissionMatrix): boolean {
  return ROLE_KEYS.every((role) =>
    CAPABILITY_KEYS.every((cap) => a[role][cap] === b[role][cap])
  );
}

export function PermissionMatrixEditor({
  value,
  onSave,
  onCancel,
  saving = false,
  error,
  savedOk = false,
  testIdPrefix = "permission-matrix",
}: PermissionMatrixEditorProps): JSX.Element {
  const { t } = useTranslation();
  const normalized = useMemo(() => normalizeMatrix(value), [value]);
  const [draft, setDraft] = useState<PermissionMatrix>(normalized);

  // Re-sync when the source matrix changes (e.g. after a reset/refetch).
  useEffect(() => {
    setDraft(normalizeMatrix(value));
  }, [value]);

  const dirty = !matricesEqual(draft, normalized);

  const toggle = (role: RoleKey, cap: CapabilityKey): void => {
    setDraft((prev) => ({
      ...prev,
      [role]: { ...prev[role], [cap]: !prev[role][cap] },
    }));
  };

  return (
    <div data-testid={testIdPrefix}>
      <div style={{ overflowX: "auto" }}>
        <table
          data-testid={`${testIdPrefix}-table`}
          style={{ width: "100%", borderCollapse: "collapse", minWidth: "520px" }}
        >
          <thead>
            <tr>
              <th style={{ ...thStyle, textAlign: "left" }} scope="col">
                {t("permissionMatrix.roleColumn")}
              </th>
              {CAPABILITY_KEYS.map((cap) => (
                <th key={cap} style={thStyle} scope="col" title={cap}>
                  {t("permissionMatrix.capability." + cap)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {ROLE_KEYS.map((role) => (
              <tr key={role} data-testid={`${testIdPrefix}-row-${role}`}>
                <th
                  scope="row"
                  style={{
                    ...tdStyle,
                    textAlign: "left",
                    fontWeight: 600,
                    textTransform: "capitalize",
                  }}
                >
                  {role}
                </th>
                {CAPABILITY_KEYS.map((cap) => (
                  <td key={cap} style={tdStyle}>
                    <input
                      type="checkbox"
                      checked={draft[role][cap]}
                      onChange={() => toggle(role, cap)}
                      disabled={saving}
                      aria-label={`${role}, ${cap}`}
                      data-testid={`${testIdPrefix}-cell-${role}-${cap}`}
                    />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {error && (
        <p
          role="alert"
          data-testid={`${testIdPrefix}-error`}
          style={{
            color: "var(--color-danger)",
            fontSize: "var(--font-size-sm)",
            marginTop: "var(--space-2)",
          }}
        >
          {error}
        </p>
      )}
      {savedOk && !dirty && (
        <p
          data-testid={`${testIdPrefix}-saved`}
          style={{
            // Theming phase 2, checkpoint 3: dropped the raw-hex var()
            // fallback that used to sit here — --color-success is always
            // defined in tokens.css, so the fallback was unreachable dead
            // code, not a real color choice.
            color: "var(--color-success)",
            fontSize: "var(--font-size-sm)",
            marginTop: "var(--space-2)",
          }}
        >
          {t("actions.saved")}
        </p>
      )}

      <div
        style={{
          display: "flex",
          gap: "var(--space-2)",
          marginTop: "var(--space-3)",
        }}
      >
        <button
          type="button"
          data-testid={`${testIdPrefix}-save`}
          onClick={() => void onSave(draft)}
          disabled={saving || !dirty}
          style={{
            ...primaryButtonStyle,
            opacity: saving || !dirty ? 0.5 : 1,
            cursor: saving || !dirty ? "not-allowed" : "pointer",
          }}
        >
          {saving ? "…" : t("actions.save")}
        </button>
        {onCancel && (
          <button
            type="button"
            data-testid={`${testIdPrefix}-cancel`}
            onClick={onCancel}
            disabled={saving}
            style={cancelButtonStyle}
          >
            {t("actions.cancel")}
          </button>
        )}
      </div>
    </div>
  );
}
