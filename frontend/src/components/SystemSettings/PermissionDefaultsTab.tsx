/**
 * REQ-181/186/187 — System Settings → Permission Defaults tab (SCR-206).
 *
 * Three stacked cards:
 *   1. Global Permission Matrix — the tenant-wide 4×6 default (full-replace via
 *      PUT). Never carries an ``enforcement_mode`` field (that is Card 2's sole
 *      concern) so a routine matrix edit can never accidentally cut over
 *      enforcement.
 *   2. Enforcement Mode — the guarded shadow↔authoritative control.
 *   3. Mismatch Review — the read-only regression-risk table.
 */

import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  permissionDefaultsApi,
  normalizeMatrix,
  type GlobalPermissionDefinition,
  type PermissionMatrix,
} from "../../api/permission-defaults";
import { PermissionMatrixEditor } from "../PermissionMatrix/PermissionMatrixEditor";
import { useToast } from "../shared/Toast/useToast";
import { EnforcementModePanel } from "./EnforcementModePanel";
import { MismatchReviewTable } from "./MismatchReviewTable";
import styles from "./PermissionDefaultsTab.module.css";

function extractErrorMessage(err: unknown): string {
  const e = err as { error?: { message?: string }; message?: string };
  return e?.error?.message ?? e?.message ?? String(err);
}

function GlobalPermissionMatrixCard(): JSX.Element {
  const { t } = useTranslation();
  const [def, setDef] = useState<GlobalPermissionDefinition | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedOk, setSavedOk] = useState(false);
  const toast = useToast();

  const load = useCallback(async (): Promise<void> => {
    setLoading(true);
    setError(null);
    try {
      const d = await permissionDefaultsApi.getGlobal();
      setDef(d);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const handleSave = useCallback(
    async (matrix: PermissionMatrix): Promise<void> => {
      setSaving(true);
      setError(null);
      setSavedOk(false);
      toast.clear();
      try {
        const updated = await permissionDefaultsApi.replaceGlobal(matrix);
        setDef(updated);
        setSavedOk(true);
        if (typeof updated.propagated_workspace_count === "number") {
          const n = updated.propagated_workspace_count;
          toast.show(
            t("systemSettings.permissionDefaults.propagatedToast", { count: n })
          );
        }
      } catch (err) {
        setError(extractErrorMessage(err));
      } finally {
        setSaving(false);
      }
    },
    []
  );

  return (
    <section className={styles.card} data-testid="global-permission-matrix-section">
      <h3 className={styles.heading}>{t("systemSettings.permissionDefaults.globalMatrixTitle")}</h3>
      <p className={styles.hint}>
        {t("systemSettings.permissionDefaults.globalMatrixHint")}
      </p>
      {loading ? (
        <p className={styles.loadingText}>…</p>
      ) : error && !def ? (
        <p role="alert" data-testid="global-matrix-error" className={styles.errorText}>
          {error}
        </p>
      ) : (
        def && (
          <>
            {toast.message && (
              <p
                data-testid="global-matrix-propagated-toast"
                role="status"
                className={styles.toast}
              >
                {toast.message}
              </p>
            )}
            <PermissionMatrixEditor
              value={normalizeMatrix(def.permission_json)}
              onSave={handleSave}
              saving={saving}
              error={error}
              savedOk={savedOk}
              testIdPrefix="global-permission-matrix"
            />
          </>
        )
      )}
    </section>
  );
}

export function PermissionDefaultsTab(): JSX.Element {
  return (
    <div data-testid="permission-defaults-tab">
      <GlobalPermissionMatrixCard />
      <EnforcementModePanel />
      <MismatchReviewTable />
    </div>
  );
}
