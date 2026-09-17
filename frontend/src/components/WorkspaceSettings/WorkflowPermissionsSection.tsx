/**
 * REQ-180/183/185 — WorkflowPermissionsSection (SCR-202, rebuilt governance tab).
 *
 * leaf_id: COMP-RF-001 (NavigationShell — Workspace-Konfigurations-UI)
 *
 * Replaces the legacy raw-artifact-id ``WorkflowsSection`` with the on-default /
 * customized model:
 *   - Card 1 "Workflow Configuration": one row per entity type showing whether
 *     the workspace workflow mirrors the global default of its preset, a link to
 *     the (unchanged) Workflow Editor, and a reset-to-default action.
 *   - Card 2 "Permission Configuration": the workspace permission-matrix override
 *     status + reset + an inline matrix editor.
 * The existing ``PermissionsSection`` (per-user ItemPermission CRUD, REQ-L1-039)
 * is rendered UNCHANGED by the parent directly below this section (REQ-182).
 */

import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { workflowsApi, type WorkflowEntityType } from "../../api/workflows";
import {
  permissionDefaultsApi,
  normalizeMatrix,
  CAPABILITY_KEYS,
  ROLE_KEYS,
  type PermissionMatrix,
  type WorkspacePermissionDefinition,
} from "../../api/permission-defaults";
import {
  WORKFLOW_ENTITY_TYPES,
  entityTypeLabel,
} from "../WorkflowEditor/constants";
import { PermissionMatrixEditor } from "../PermissionMatrix/PermissionMatrixEditor";
import { DefaultStatusBadge, ResetToDefaultButton } from "./DefaultStatusBadge";
import { ConfirmDialog } from "../shared/ConfirmDialog";
import type { UUID } from "../../types";

function extractErrorMessage(err: unknown): string {
  const e = err as { error?: { message?: string }; message?: string };
  return e?.error?.message ?? e?.message ?? String(err);
}

const cardStyle: React.CSSProperties = {
  background: "var(--color-surface)",
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-lg)",
  padding: "var(--space-5)",
  marginBottom: "var(--space-5)",
  boxShadow: "var(--shadow-card)",
};

const headingStyle: React.CSSProperties = {
  fontSize: "var(--font-size-lg)",
  fontWeight: 600,
  color: "var(--color-text)",
  margin: "0 0 var(--space-4) 0",
};

const hintStyle: React.CSSProperties = {
  fontSize: "var(--font-size-sm)",
  color: "var(--color-text-muted)",
  margin: "0 0 var(--space-4) 0",
};

const linkButtonStyle: React.CSSProperties = {
  background: "transparent",
  color: "var(--color-primary)",
  border: "none",
  padding: "var(--space-1) var(--space-2)",
  fontSize: "var(--font-size-sm)",
  cursor: "pointer",
  textDecoration: "underline",
};

interface WorkflowRowState {
  isCustomized: boolean;
  hasSource: boolean;
  loading: boolean;
  error: string | null;
  resetting: boolean;
}

const INITIAL_ROW: WorkflowRowState = {
  isCustomized: false,
  hasSource: false,
  loading: true,
  error: null,
  resetting: false,
};

export interface WorkflowPermissionsSectionProps {
  workspaceId: UUID;
}

export function WorkflowPermissionsSection({
  workspaceId,
}: WorkflowPermissionsSectionProps): JSX.Element {
  const { t } = useTranslation();
  const navigate = useNavigate();

  // ---- Card 1: per-entity-type workflow rows ----
  const [rows, setRows] = useState<Record<string, WorkflowRowState>>(() =>
    Object.fromEntries(
      WORKFLOW_ENTITY_TYPES.map((e) => [e.type, { ...INITIAL_ROW }])
    )
  );

  const loadRow = useCallback(
    async (type: WorkflowEntityType): Promise<void> => {
      setRows((prev) => ({
        ...prev,
        [type]: { ...prev[type], loading: true, error: null },
      }));
      try {
        const def = await workflowsApi.getDefinition(type, workspaceId);
        setRows((prev) => ({
          ...prev,
          [type]: {
            ...prev[type],
            loading: false,
            error: null,
            isCustomized: Boolean(def.is_customized),
            hasSource: def.source_global_id != null,
          },
        }));
      } catch (err) {
        setRows((prev) => ({
          ...prev,
          [type]: {
            ...prev[type],
            loading: false,
            error: extractErrorMessage(err),
          },
        }));
      }
    },
    [workspaceId]
  );

  useEffect(() => {
    let cancelled = false;
    for (const e of WORKFLOW_ENTITY_TYPES) {
      if (!cancelled) void loadRow(e.type);
    }
    return () => {
      cancelled = true;
    };
  }, [loadRow]);

  // UI-20: unified on the shared ConfirmDialog instead of window.confirm.
  const [pendingWorkflowReset, setPendingWorkflowReset] = useState<WorkflowEntityType | null>(null);

  const handleWorkflowReset = useCallback(
    async (type: WorkflowEntityType): Promise<void> => {
      setRows((prev) => ({
        ...prev,
        [type]: { ...prev[type], resetting: true, error: null },
      }));
      try {
        const def = await workflowsApi.resetDefinition(type, workspaceId);
        setRows((prev) => ({
          ...prev,
          [type]: {
            ...prev[type],
            resetting: false,
            isCustomized: Boolean(def.is_customized),
            hasSource: def.source_global_id != null,
          },
        }));
      } catch (err) {
        setRows((prev) => ({
          ...prev,
          [type]: {
            ...prev[type],
            resetting: false,
            error: extractErrorMessage(err),
          },
        }));
      }
    },
    [workspaceId]
  );

  const confirmWorkflowReset = useCallback((): void => {
    if (!pendingWorkflowReset) return;
    const type = pendingWorkflowReset;
    setPendingWorkflowReset(null);
    void handleWorkflowReset(type);
  }, [pendingWorkflowReset, handleWorkflowReset]);

  // ---- Card 2: workspace permission matrix ----
  const [permDef, setPermDef] = useState<WorkspacePermissionDefinition | null>(
    null
  );
  const [permLoading, setPermLoading] = useState(true);
  const [permError, setPermError] = useState<string | null>(null);
  const [permResetting, setPermResetting] = useState(false);
  const [editingMatrix, setEditingMatrix] = useState(false);
  const [savingMatrix, setSavingMatrix] = useState(false);
  const [matrixSavedOk, setMatrixSavedOk] = useState(false);

  const loadPermDef = useCallback(async (): Promise<void> => {
    setPermLoading(true);
    setPermError(null);
    try {
      const def = await permissionDefaultsApi.getWorkspace(workspaceId);
      setPermDef(def);
    } catch (err) {
      setPermError(extractErrorMessage(err));
    } finally {
      setPermLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    void loadPermDef();
  }, [loadPermDef]);

  // UI-20: unified on the shared ConfirmDialog instead of window.confirm.
  const [showPermResetConfirm, setShowPermResetConfirm] = useState(false);

  const handlePermReset = useCallback(async (): Promise<void> => {
    setPermResetting(true);
    setPermError(null);
    try {
      const def = await permissionDefaultsApi.resetWorkspace(workspaceId);
      setPermDef(def);
      setEditingMatrix(false);
    } catch (err) {
      setPermError(extractErrorMessage(err));
    } finally {
      setPermResetting(false);
    }
  }, [workspaceId]);

  const handleMatrixSave = useCallback(
    async (matrix: PermissionMatrix): Promise<void> => {
      setSavingMatrix(true);
      setPermError(null);
      setMatrixSavedOk(false);
      try {
        const def = await permissionDefaultsApi.replaceWorkspace(
          workspaceId,
          matrix
        );
        setPermDef(def);
        setMatrixSavedOk(true);
        setEditingMatrix(false);
      } catch (err) {
        setPermError(extractErrorMessage(err));
      } finally {
        setSavingMatrix(false);
      }
    },
    [workspaceId]
  );

  const matrix = permDef ? normalizeMatrix(permDef.permission_json) : null;

  return (
    <>
      {/* ---------------- Card 1: Workflow Configuration ---------------- */}
      <section style={cardStyle} data-testid="workflow-config-section">
        <h3 style={headingStyle}>
          {t("settings.workflowConfig", "Workflow Configuration")}
        </h3>
        <p style={hintStyle}>
          {t(
            "settings.workflowConfigHint",
            "Whether each entity type's workflow matches the tenant-wide global default of this workspace's preset. Edit the structure in the Workflow Editor, or reset a customized workflow back to the global default."
          )}
        </p>
        <table
          data-testid="workflow-config-table"
          style={{ width: "100%", borderCollapse: "collapse" }}
        >
          <tbody>
            {WORKFLOW_ENTITY_TYPES.map((e) => {
              const row = rows[e.type];
              return (
                <tr key={e.type} data-testid={`workflow-config-row-${e.type}`}>
                  <td
                    style={{
                      padding: "var(--space-2) var(--space-3)",
                      fontSize: "var(--font-size-sm)",
                      color: "var(--color-text)",
                      borderBottom: "1px solid var(--color-border)",
                      fontWeight: 600,
                    }}
                  >
                    {entityTypeLabel(e.type)}
                  </td>
                  <td
                    style={{
                      padding: "var(--space-2) var(--space-3)",
                      borderBottom: "1px solid var(--color-border)",
                    }}
                  >
                    {row.loading ? (
                      <span style={{ color: "var(--color-text-muted)" }}>…</span>
                    ) : row.error ? (
                      <span
                        role="alert"
                        data-testid={`workflow-config-error-${e.type}`}
                        style={{
                          color: "var(--color-danger)",
                          fontSize: "var(--font-size-xs)",
                        }}
                      >
                        {row.error}
                      </span>
                    ) : (
                      <DefaultStatusBadge
                        isCustomized={row.isCustomized}
                        hasSource={row.hasSource}
                      />
                    )}
                  </td>
                  <td
                    style={{
                      padding: "var(--space-2) var(--space-3)",
                      borderBottom: "1px solid var(--color-border)",
                      textAlign: "right",
                      whiteSpace: "nowrap",
                    }}
                  >
                    <button
                      type="button"
                      style={linkButtonStyle}
                      onClick={() => navigate(`/workflows/${e.type}`)}
                      data-testid={`workflow-config-open-${e.type}`}
                    >
                      {t("settings.openInEditor", "Open in Workflow Editor")}
                    </button>
                    <ResetToDefaultButton
                      onReset={() => setPendingWorkflowReset(e.type)}
                      disabled={!row.isCustomized || !row.hasSource}
                      busy={row.resetting}
                      ariaLabel={`Reset ${entityTypeLabel(e.type)} workflow to default`}
                      title={
                        !row.hasSource
                          ? t(
                              "settings.noGlobalSourceHint",
                              "This workspace has no linked global default — initialize one in System Settings first."
                            )
                          : undefined
                      }
                      testId={`workflow-config-reset-${e.type}`}
                    />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>

      {/* ---------------- Card 2: Permission Configuration ---------------- */}
      <section style={cardStyle} data-testid="permission-config-section">
        <h3 style={headingStyle}>
          {t("settings.permissionConfig", "Permission Configuration")}
        </h3>
        <p style={hintStyle}>
          {t(
            "settings.permissionConfigHint",
            "The workspace's role→capability permission matrix and whether it mirrors the global default or has been overridden."
          )}
        </p>

        {permLoading ? (
          <p style={{ color: "var(--color-text-muted)" }}>…</p>
        ) : permError && !permDef ? (
          <p role="alert" data-testid="permission-config-error" style={{ color: "var(--color-danger)" }}>
            {permError}
          </p>
        ) : (
          matrix && (
            <>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "var(--space-3)",
                  marginBottom: "var(--space-3)",
                }}
              >
                <DefaultStatusBadge
                  isCustomized={Boolean(permDef?.is_customized)}
                  hasSource={permDef?.source_global_id != null}
                />
                <ResetToDefaultButton
                  onReset={() => setShowPermResetConfirm(true)}
                  disabled={
                    !permDef?.is_customized || permDef?.source_global_id == null
                  }
                  busy={permResetting}
                  ariaLabel="Reset workspace permission matrix to default"
                  testId="permission-config-reset"
                />
                <button
                  type="button"
                  data-testid="permission-config-override-toggle"
                  onClick={() => {
                    setMatrixSavedOk(false);
                    setEditingMatrix((v) => !v);
                  }}
                  style={{ ...linkButtonStyle, marginLeft: "auto" }}
                >
                  {editingMatrix
                    ? t("actions.cancel", "Cancel")
                    : t("settings.overrideMatrix", "Override matrix…")}
                </button>
              </div>

              {permError && permDef && (
                <p role="alert" style={{ color: "var(--color-danger)", fontSize: "var(--font-size-sm)" }}>
                  {permError}
                </p>
              )}

              {editingMatrix ? (
                <PermissionMatrixEditor
                  value={matrix}
                  onSave={handleMatrixSave}
                  onCancel={() => setEditingMatrix(false)}
                  saving={savingMatrix}
                  savedOk={matrixSavedOk}
                  testIdPrefix="workspace-permission-matrix"
                />
              ) : (
                <ReadOnlyMatrix matrix={matrix} />
              )}
            </>
          )
        )}
      </section>

      {pendingWorkflowReset && (
        <ConfirmDialog
          title={t("settings.workflowReset", "Reset workflow")}
          message={t(
            "settings.workflowResetConfirm",
            "Reset this workflow to the current global default? Workspace-specific changes will be discarded."
          )}
          confirmLabel={t("settings.workflowReset", "Reset workflow")}
          onConfirm={confirmWorkflowReset}
          onCancel={() => setPendingWorkflowReset(null)}
          testId="workflow-config-reset-confirm"
        />
      )}

      {showPermResetConfirm && (
        <ConfirmDialog
          title={t("settings.permissionReset", "Reset permission matrix")}
          message={t(
            "settings.permissionResetConfirm",
            "Reset this workspace's permission matrix to the current global default?"
          )}
          confirmLabel={t("settings.permissionReset", "Reset permission matrix")}
          onConfirm={() => {
            setShowPermResetConfirm(false);
            void handlePermReset();
          }}
          onCancel={() => setShowPermResetConfirm(false)}
          testId="permission-config-reset-confirm"
        />
      )}
    </>
  );
}

/** Compact read-only ✓/— view of the effective matrix (SCR-202 Card 2). */
function ReadOnlyMatrix({ matrix }: { matrix: PermissionMatrix }): JSX.Element {
  const th: React.CSSProperties = {
    textAlign: "center",
    padding: "var(--space-1) var(--space-2)",
    fontSize: "var(--font-size-xs)",
    fontWeight: 600,
    color: "var(--color-text-muted)",
    textTransform: "uppercase",
    letterSpacing: "0.03em",
    borderBottom: "1px solid var(--color-border)",
  };
  const td: React.CSSProperties = {
    textAlign: "center",
    padding: "var(--space-1) var(--space-2)",
    fontSize: "var(--font-size-sm)",
    color: "var(--color-text)",
    borderBottom: "1px solid var(--color-border)",
  };
  return (
    <div style={{ overflowX: "auto" }}>
      <table
        data-testid="permission-config-readonly-table"
        style={{ width: "100%", borderCollapse: "collapse", minWidth: "520px" }}
      >
        <thead>
          <tr>
            <th style={{ ...th, textAlign: "left" }} scope="col">
              Role
            </th>
            {CAPABILITY_KEYS.map((cap) => (
              <th key={cap} style={th} scope="col">
                {cap}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {ROLE_KEYS.map((role) => (
            <tr key={role}>
              <th
                scope="row"
                style={{ ...td, textAlign: "left", fontWeight: 600, textTransform: "capitalize" }}
              >
                {role}
              </th>
              {CAPABILITY_KEYS.map((cap) => (
                <td key={cap} style={td} aria-label={`${role} ${cap} ${matrix[role][cap] ? "allowed" : "denied"}`}>
                  {matrix[role][cap] ? "✓" : "—"}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
