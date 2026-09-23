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
import { Spinner } from "../shared/Spinner/Spinner";
import styles from "./PermissionMatrixEditor.module.css";

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

  // UI-40: unlike the Requirement/Need/TestCase forms (issue #672), this
  // editor is not embedded in a SplitView with in-app entity-to-entity
  // navigation to guard — its two hosts (Global Permission Defaults /
  // workspace override settings) are standalone settings pages. The
  // realistic loss path here is a tab close/reload with pending checkbox
  // edits, so this mirrors the same `beforeunload` guard already
  // established for `useGraphAutosave` (DiagramGraphEditor), registered
  // only while `dirty` is true.
  useEffect(() => {
    if (!dirty) return undefined;

    function handleBeforeUnload(event: BeforeUnloadEvent): void {
      event.preventDefault();
      event.returnValue = "";
    }

    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [dirty]);

  const toggle = (role: RoleKey, cap: CapabilityKey): void => {
    setDraft((prev) => ({
      ...prev,
      [role]: { ...prev[role], [cap]: !prev[role][cap] },
    }));
  };

  return (
    <div data-testid={testIdPrefix}>
      <div className={styles.scrollX}>
        <table data-testid={`${testIdPrefix}-table`} className={styles.table}>
          <thead>
            <tr>
              <th className={styles.th + " " + styles.thLeft} scope="col">
                {t("permissionMatrix.roleColumn")}
              </th>
              {CAPABILITY_KEYS.map((cap) => (
                <th key={cap} className={styles.th} scope="col" title={cap}>
                  {t("permissionMatrix.capability." + cap)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {ROLE_KEYS.map((role) => (
              <tr key={role} data-testid={`${testIdPrefix}-row-${role}`}>
                <th scope="row" className={styles.td + " " + styles.tdRole}>
                  {role}
                </th>
                {CAPABILITY_KEYS.map((cap) => (
                  <td key={cap} className={styles.td}>
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
        <p role="alert" data-testid={`${testIdPrefix}-error`} className={styles.errorText}>
          {error}
        </p>
      )}
      {savedOk && !dirty && (
        <p data-testid={`${testIdPrefix}-saved`} className={styles.savedText}>
          {t("actions.saved")}
        </p>
      )}

      <div className={styles.actions}>
        <button
          type="button"
          data-testid={`${testIdPrefix}-save`}
          onClick={() => void onSave(draft)}
          disabled={saving || !dirty}
          className={
            styles.primaryButton +
            " " +
            (saving || !dirty ? styles.primaryDisabled : styles.primaryEnabled)
          }
        >
          {saving ? <Spinner label={t("actions.saving")} /> : t("actions.save")}
        </button>
        {onCancel && (
          <button
            type="button"
            data-testid={`${testIdPrefix}-cancel`}
            onClick={onCancel}
            disabled={saving}
            className={styles.cancelButton}
          >
            {t("actions.cancel")}
          </button>
        )}
      </div>
    </div>
  );
}
