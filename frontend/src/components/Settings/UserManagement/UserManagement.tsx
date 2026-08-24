/**
 * ARCH-L1-001 ReactFrontend — UserManagement (multi-user management design spec).
 *
 * leaf_id: COMP-RF-001 (NavigationShell — Settings scope)
 * req_id:  multi-user management design spec (Task 12)
 *
 * Tenant-admin-only admin surface: list/create/activate/deactivate users of
 * the caller's tenant and grant/revoke the tenant-admin role. Consumes
 * `usersApi` (Task 11) exclusively — no direct model access, no new RBAC
 * concept invented client-side.
 *
 * Gating: `useAuth().isTenantAdmin` (backed by the `is_tenant_admin` field
 * this task added to `/api/v1/auth/{login,refresh,me}/`, mirroring how
 * `WorkspaceSettings`/`SystemSettings` gate on the workspace `admin` role).
 * This is UX-only — the real enforcement is server-side
 * (`UserViewSet`/`AuthorizationService.is_tenant_admin`, Task 7-9); a
 * non-admin who somehow reaches this component still gets 403s from every
 * `usersApi` call.
 *
 * `LastAdminError` (409, `error: "LAST_ADMIN"`): the backend
 * (`user_management_views.py`'s `_err()`) returns a FLAT
 * `{error, message}` body, and `apiClient.apiFetch` (client.ts) throws that
 * body directly for a non-2xx response — NOT an axios-style
 * `{response: {status, data}}` wrapper. `message` is a fixed-format English
 * sentence ("Cannot complete this action: it would leave {scope}
 * {identifier} with no active admin."); `parseLastAdminMessage` below
 * extracts `{scope, identifier}` from it so the UI can render the
 * LOCALIZED `settings.userManagement.lastAdminError` copy (DE/EN) instead
 * of always leaking the backend's English sentence into a German UI.
 *
 * Styling follows the CSS-Module convention (Dialog/Goals precedent) rather
 * than WorkspaceSettings.tsx's legacy inline object-literal style props —
 * see `UserManagement.module.css` and the UI concept ratchet
 * (frontend/src/test/ui-ratchet.test.ts), which freezes the project-wide
 * inline-style-prop count and fails on any net increase.
 */
import { useState, useEffect, useCallback, useRef } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../../context/AuthContext";
import { usersApi, type ManagedUser } from "../../../api/users";
import { Dialog } from "../../shared/Dialog";
import { PageHeader } from "../../shared/PageHeader";
import styles from "./UserManagement.module.css";

// ---------------------------------------------------------------------------
// LAST_ADMIN error handling
// ---------------------------------------------------------------------------

interface ApiErrorBody {
  error: string;
  message: string;
}

function isLastAdminError(err: unknown): err is ApiErrorBody {
  const candidate = err as Partial<ApiErrorBody> | null | undefined;
  return (
    !!candidate &&
    typeof candidate === "object" &&
    candidate.error === "LAST_ADMIN" &&
    typeof candidate.message === "string"
  );
}

function extractMessage(err: unknown): string | null {
  const candidate = err as { message?: unknown } | null | undefined;
  return candidate && typeof candidate === "object" && typeof candidate.message === "string"
    ? candidate.message
    : null;
}

// Matches `LastAdminError.__init__`'s fixed message format
// (backend/auth_tenancy/services/authorization.py): "Cannot complete this
// action: it would leave {scope} {identifier} with no active admin."
const LAST_ADMIN_MESSAGE_RE = /leave (workspace|tenant) (\S+) with no active admin/i;

function parseLastAdminMessage(message: string): { scope: string; identifier: string } | null {
  const match = message.match(LAST_ADMIN_MESSAGE_RE);
  if (!match) return null;
  const [, scope, identifier] = match;
  return { scope: scope.charAt(0).toUpperCase() + scope.slice(1), identifier };
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function UserManagement(): JSX.Element {
  const { t } = useTranslation();
  // Keep the latest `t` in a ref so the data-loading/action callbacks below
  // do not depend on it directly (mirrors CreateTraceLinkDialog.tsx): a
  // language switch — or an unstable test-only i18next mock that returns a
  // fresh `t` closure on every render — would otherwise give `reload`/
  // `handleApiError`/`handleCreate` a new identity every render, re-firing
  // the load-on-mount effect in an infinite loop.
  const tRef = useRef(t);
  tRef.current = t;
  const { isTenantAdmin } = useAuth();

  const [users, setUsers] = useState<ManagedUser[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Create-user dialog state
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [createUsername, setCreateUsername] = useState("");
  const [createEmail, setCreateEmail] = useState("");
  const [createPassword, setCreatePassword] = useState("");
  const [createError, setCreateError] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);

  const reload = useCallback(async (): Promise<void> => {
    setIsLoading(true);
    try {
      const list = await usersApi.list();
      setUsers(list);
    } catch {
      setError(tRef.current("errors.generic"));
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    // Never fires the tenant-admin-guarded list request for a non-admin —
    // it would only ever 403 (server-side enforcement, this gate is UX only).
    if (!isTenantAdmin) return;
    void reload();
  }, [isTenantAdmin, reload]);

  const handleApiError = useCallback((err: unknown): void => {
    if (isLastAdminError(err)) {
      const parsed = parseLastAdminMessage(err.message);
      setError(
        parsed
          ? tRef.current("settings.userManagement.lastAdminError", {
              scope: parsed.scope,
              identifier: parsed.identifier,
            })
          : err.message
      );
      return;
    }
    setError(extractMessage(err) ?? tRef.current("errors.generic"));
  }, []);

  const handleToggleActive = useCallback(
    async (u: ManagedUser): Promise<void> => {
      setError(null);
      try {
        if (u.is_active) {
          await usersApi.deactivate(u.id);
        } else {
          await usersApi.activate(u.id);
        }
        await reload();
      } catch (err) {
        handleApiError(err);
      }
    },
    [reload, handleApiError]
  );

  const handleToggleTenantAdmin = useCallback(
    async (u: ManagedUser): Promise<void> => {
      setError(null);
      try {
        if (u.is_tenant_admin) {
          await usersApi.revokeTenantAdmin(u.id);
        } else {
          await usersApi.grantTenantAdmin(u.id);
        }
        await reload();
      } catch (err) {
        handleApiError(err);
      }
    },
    [reload, handleApiError]
  );

  const resetCreateForm = useCallback((): void => {
    setCreateUsername("");
    setCreateEmail("");
    setCreatePassword("");
    setCreateError(null);
  }, []);

  const handleCreate = useCallback(async (): Promise<void> => {
    setIsCreating(true);
    setCreateError(null);
    try {
      await usersApi.create({
        username: createUsername.trim(),
        email: createEmail.trim(),
        password: createPassword,
      });
      setShowCreateDialog(false);
      resetCreateForm();
      await reload();
    } catch (err) {
      setCreateError(extractMessage(err) ?? tRef.current("settings.userManagement.createFailed"));
    } finally {
      setIsCreating(false);
    }
  }, [createUsername, createEmail, createPassword, reload, resetCreateForm]);

  const canSubmitCreate =
    createUsername.trim().length > 0 && createEmail.trim().length > 0 && createPassword.length > 0;

  if (!isTenantAdmin) {
    return (
      <div className={styles.gatePage} data-testid="user-management">
        <PageHeader title={t("nav.userManagement", "User Management")} />
        <p data-testid="user-management-tenant-admin-only" className={styles.gateMessage}>
          {t("settings.userManagement.tenantAdminOnly")}
        </p>
      </div>
    );
  }

  return (
    <div className={styles.page} data-testid="user-management">
      <PageHeader
        title={t("settings.userManagement.title")}
        summary={t("settings.userManagement.summary", { count: users.length })}
        primaryAction={{
          label: `+ ${t("users.newUser")}`,
          onClick: () => {
            resetCreateForm();
            setShowCreateDialog(true);
          },
          testId: "user-management-create-btn",
        }}
      />

      <section className={styles.card}>
        {isLoading ? (
          <p>{t("loading")}</p>
        ) : (
          <table data-testid="user-management-table" className={styles.table}>
            <thead>
              <tr className={styles.tableHeadRow}>
                <th className={styles.th}>{t("settings.userManagement.username")}</th>
                <th className={styles.th}>{t("settings.userManagement.email")}</th>
                <th className={styles.th}>{t("settings.userManagement.status")}</th>
                <th className={styles.th}>{t("settings.userManagement.tenantAdmin")}</th>
                <th className={styles.th} />
              </tr>
            </thead>
            <tbody>
              {users.length === 0 && (
                <tr>
                  <td colSpan={5} className={styles.emptyCell}>
                    {t("settings.userManagement.noUsers")}
                  </td>
                </tr>
              )}
              {users.map((u) => (
                <tr key={u.id} data-testid={`user-management-row-${u.id}`} className={styles.row}>
                  <td className={styles.td}>{u.username}</td>
                  <td className={styles.td}>{u.email}</td>
                  <td className={styles.td}>
                    {u.is_active ? t("settings.userManagement.active") : t("settings.userManagement.inactive")}
                  </td>
                  <td className={styles.td}>{u.is_tenant_admin ? "✓" : "—"}</td>
                  <td className={styles.tdActions}>
                    <button
                      type="button"
                      data-testid={`user-management-toggle-active-${u.id}`}
                      onClick={() => void handleToggleActive(u)}
                      className={styles.actionButton}
                    >
                      {u.is_active ? t("settings.userManagement.deactivate") : t("settings.userManagement.activate")}
                    </button>
                    <button
                      type="button"
                      data-testid={`user-management-toggle-admin-${u.id}`}
                      onClick={() => void handleToggleTenantAdmin(u)}
                      className={styles.actionButton}
                    >
                      {u.is_tenant_admin
                        ? t("settings.userManagement.revokeTenantAdmin")
                        : t("settings.userManagement.grantTenantAdmin")}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {error && (
        <p role="alert" data-testid="user-management-error" className={styles.error}>
          {error}
        </p>
      )}

      {showCreateDialog && (
        <Dialog
          title={t("settings.userManagement.createUser")}
          onClose={() => {
            setShowCreateDialog(false);
            resetCreateForm();
          }}
          testId="user-management-create-dialog"
          footer={
            <div className={styles.dialogFooter}>
              <button
                type="button"
                data-testid="user-management-create-cancel"
                className="btn-secondary"
                onClick={() => {
                  setShowCreateDialog(false);
                  resetCreateForm();
                }}
                disabled={isCreating}
              >
                {t("actions.cancel")}
              </button>
              <button
                type="submit"
                form="user-management-create-form"
                data-testid="user-management-create-submit"
                className="btn-primary"
                disabled={isCreating || !canSubmitCreate}
              >
                {isCreating ? t("actions.creating") : t('actions.create', 'Erstellen')}
              </button>
            </div>
          }
        >
          <form
            id="user-management-create-form"
            className={styles.formGrid}
            onSubmit={(e) => {
              e.preventDefault();
              void handleCreate();
            }}
          >
            <div>
              <label htmlFor="user-management-create-username" className={styles.label}>
                {t("settings.userManagement.username")}
              </label>
              <input
                id="user-management-create-username"
                data-testid="user-management-create-username"
                value={createUsername}
                onChange={(e) => setCreateUsername(e.target.value)}
                className={styles.input}
                disabled={isCreating}
              />
            </div>
            <div>
              <label htmlFor="user-management-create-email" className={styles.label}>
                {t("settings.userManagement.email")}
              </label>
              <input
                id="user-management-create-email"
                data-testid="user-management-create-email"
                type="email"
                value={createEmail}
                onChange={(e) => setCreateEmail(e.target.value)}
                className={styles.input}
                disabled={isCreating}
              />
            </div>
            <div>
              <label htmlFor="user-management-create-password" className={styles.label}>
                {t("settings.userManagement.password")}
              </label>
              <input
                id="user-management-create-password"
                data-testid="user-management-create-password"
                type="password"
                value={createPassword}
                onChange={(e) => setCreatePassword(e.target.value)}
                className={styles.input}
                disabled={isCreating}
              />
            </div>
            {createError && (
              <p role="alert" data-testid="user-management-create-error" className={styles.formError}>
                {createError}
              </p>
            )}
          </form>
        </Dialog>
      )}
    </div>
  );
}

UserManagement.displayName = "UserManagement";
