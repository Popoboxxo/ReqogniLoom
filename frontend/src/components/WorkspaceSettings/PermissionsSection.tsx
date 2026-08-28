/**
 * ARCH-L1-001 ReactFrontend — PermissionsSection (WorkspaceSettings).
 *
 * leaf_id: COMP-RF-001 (NavigationShell scope — Workspace-Konfigurations-UI)
 * req_id:  REQ-L1-039 (ItemPermission CRUD, COMP-AT-005)
 *
 * Admin-only section (parent gates rendering on the admin role) for
 * workspace item permissions:
 *   - list rules for a given user (the backend requires a user_id filter)
 *   - grant a rule (user, optional artifact, level read/write/none)
 *   - revoke a rule
 *
 * The subject user is chosen from the workspace member directory
 * (GET /workspaces/{id}/members/, REQ-014) via a searchable dropdown that
 * resolves the user_id automatically — no more copy-pasting raw UUIDs.
 *
 * This member directory (also rendered below as a "Workspace Members" table,
 * multi-user management design spec §5 Task 13) additionally exposes
 * suspend/reactivate role actions for workspace-admins, extending the
 * pre-existing GET-only `WorkspaceMembersView` with
 * `workspaceMembersApi.suspendRole`/`reactivateRole` (Task 11). Button
 * visibility here is UX only — real enforcement stays server-side
 * (`WorkspaceMemberRoleTransitionView`, `AuthorizationService.suspend_role`/
 * `reactivate_role`).
 *
 * `LAST_ADMIN` (409) handling mirrors `UserManagement.tsx` (Task 12): the
 * backend (`rest_workspace_members.py`'s `_err()`) returns a FLAT
 * `{error, message}` body and `apiClient.apiFetch` throws that body
 * directly for a non-2xx response — NOT an axios-style
 * `{response: {status, data}}` wrapper.
 *
 * `GET /members/` only returns a member's ACTIVE (non-suspended) roles
 * (`AuthorizationService.list_workspace_members` filters
 * `suspended_at__isnull=True`) — a role vanishes from the list the moment
 * it is suspended, and a member with zero remaining active roles vanishes
 * entirely. `suspendedRoleSnapshots` below keeps a client-side, session-only
 * memory of roles suspended through this UI so the just-suspended role (and
 * its member row, if it would otherwise disappear) stays visible with a
 * "Reactivate" action — a deliberate frontend-only workaround, not a
 * backend change: `GET /members/` intentionally stays active-only for its
 * original purpose (the item-permission picker above must never offer a
 * suspended member).
 */

import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  itemPermissionsApi,
  type ItemPermission,
  type ItemPermissionLevel,
} from "../../api/item-permissions";
import {
  workspaceMembersApi,
  type WorkspaceMember,
} from "../../api/workspace-members";
import { artifactsApi } from "../../api/artifacts";
import type { Artifact, UUID } from "../../types";

function extractErrorMessage(err: unknown): string {
  const e = err as { error?: { message?: string }; message?: string };
  return e?.error?.message ?? e?.message ?? String(err);
}

// ---------------------------------------------------------------------------
// LAST_ADMIN error handling (mirrors UserManagement.tsx, Task 12)
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

function memberRoleKey(userId: string, role: string): string {
  return `${userId}::${role}`;
}

const LEVELS: ItemPermissionLevel[] = ["read", "write", "none"];

const sectionStyle: React.CSSProperties = {
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

const inputStyle: React.CSSProperties = {
  background: "var(--color-surface)",
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-md)",
  padding: "var(--space-2) var(--space-3)",
  color: "var(--color-text)",
  fontSize: "var(--font-size-sm)",
  boxSizing: "border-box",
};

const primaryButtonStyle: React.CSSProperties = {
  background: "var(--color-primary)",
  color: "var(--color-on-primary)",
  border: "none",
  borderRadius: "var(--radius-md)",
  padding: "var(--space-2) var(--space-4)",
  fontSize: "var(--font-size-sm)",
  fontWeight: 600,
  cursor: "pointer",
};

// Workspace-members roster styles (Task 13). Hoisted to module-level
// constants — referenced via `style={constName}` (single-brace) rather than
// an inline double-brace object literal — per the UI-concept ratchet guard
// (`frontend/src/test/ui-ratchet.test.ts`), which freezes the project-wide
// count of inline-style-object-literal usages and fails on any net increase.
const membersSectionStyle: React.CSSProperties = { marginBottom: "var(--space-4)" };

const membersHeadingStyle: React.CSSProperties = {
  fontSize: "var(--font-size-md)",
  fontWeight: 600,
  color: "var(--color-text)",
  margin: "0 0 var(--space-2) 0",
};

const membersErrorStyle: React.CSSProperties = {
  color: "var(--color-danger)",
  fontSize: "var(--font-size-sm)",
};

const membersEmptyStyle: React.CSSProperties = {
  color: "var(--color-text-muted)",
  fontSize: "var(--font-size-sm)",
};

const membersTableStyle: React.CSSProperties = { width: "100%", borderCollapse: "collapse" };

const roleChipWrapperStyle: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: "var(--space-1)",
  marginRight: "var(--space-3)",
};

const roleLabelActiveStyle: React.CSSProperties = {
  fontSize: "var(--font-size-xs)",
  fontWeight: 600,
  color: "var(--color-text)",
  textDecoration: "none",
};

const roleLabelSuspendedStyle: React.CSSProperties = {
  ...roleLabelActiveStyle,
  color: "var(--color-text-muted)",
  textDecoration: "line-through",
};

const roleActionBaseStyle: React.CSSProperties = {
  background: "transparent",
  borderRadius: "var(--radius-md)",
  padding: "1px var(--space-2)",
  fontSize: "var(--font-size-xs)",
  cursor: "pointer",
  opacity: 1,
};

const suspendActionStyle: React.CSSProperties = {
  ...roleActionBaseStyle,
  color: "var(--color-danger)",
  border: "1px solid var(--color-danger)",
};

const suspendActionPendingStyle: React.CSSProperties = {
  ...suspendActionStyle,
  cursor: "wait",
  opacity: 0.6,
};

const reactivateActionStyle: React.CSSProperties = {
  ...roleActionBaseStyle,
  color: "var(--color-primary)",
  border: "1px solid var(--color-primary)",
};

const reactivateActionPendingStyle: React.CSSProperties = {
  ...reactivateActionStyle,
  cursor: "wait",
  opacity: 0.6,
};

export interface PermissionsSectionProps {
  workspaceId: UUID;
}

export function PermissionsSection({
  workspaceId,
}: PermissionsSectionProps): JSX.Element {
  const { t } = useTranslation();

  const [filterUserId, setFilterUserId] = useState("");
  const [permissions, setPermissions] = useState<ItemPermission[]>([]);
  const [hasLoaded, setHasLoaded] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Grant form state
  const [grantUserId, setGrantUserId] = useState("");
  const [grantArtifactId, setGrantArtifactId] = useState("");
  const [grantLevel, setGrantLevel] = useState<ItemPermissionLevel>("read");
  const [isGranting, setIsGranting] = useState(false);

  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [revokingId, setRevokingId] = useState<string | null>(null);

  const [members, setMembers] = useState<WorkspaceMember[]>([]);

  // Workspace-members roster (Task 13): suspend/reactivate role actions.
  const [membersError, setMembersError] = useState<string | null>(null);
  const [pendingRoleKey, setPendingRoleKey] = useState<string | null>(null);
  // Session-only memory of roles suspended through this UI, keyed by
  // `memberRoleKey(user_id, role)` — see the file-level doc comment above
  // for why this exists (GET /members/ is active-roles-only).
  const [suspendedRoleSnapshots, setSuspendedRoleSnapshots] = useState<
    Record<string, WorkspaceMember>
  >({});

  // Load artifact options for the optional artifact-scoped rule.
  useEffect(() => {
    let cancelled = false;
    artifactsApi
      .list(workspaceId)
      .then((resp) => {
        if (!cancelled) setArtifacts(resp.results);
      })
      .catch(() => {
        /* artifact options are a convenience — non-fatal */
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId]);

  // Load the workspace member directory for the user picker (REQ-014).
  useEffect(() => {
    let cancelled = false;
    workspaceMembersApi
      .list(workspaceId)
      .then((rows) => {
        if (!cancelled) setMembers(rows);
      })
      .catch((err) => {
        if (!cancelled) setError(extractErrorMessage(err));
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId]);

  const memberLabel = useCallback((m: WorkspaceMember): string => {
    const roles = m.roles.length > 0 ? ` [${m.roles.join(", ")}]` : "";
    return `${m.display_name} · ${m.email}${roles}`;
  }, []);

  const loadPermissions = useCallback(
    async (userId: string): Promise<void> => {
      if (!userId.trim()) return;
      setIsLoading(true);
      setError(null);
      try {
        const rows = await itemPermissionsApi.list(workspaceId, userId.trim());
        setPermissions(rows);
        setHasLoaded(true);
      } catch (err) {
        setError(extractErrorMessage(err));
        setPermissions([]);
      } finally {
        setIsLoading(false);
      }
    },
    [workspaceId]
  );

  const handleGrant = useCallback(async (): Promise<void> => {
    if (!grantUserId.trim()) {
      setError(t("permissions.userRequired", "User ID is required."));
      return;
    }
    setIsGranting(true);
    setError(null);
    try {
      await itemPermissionsApi.grant(workspaceId, {
        user_id: grantUserId.trim(),
        artifact_id: grantArtifactId || null,
        permission_level: grantLevel,
      });
      // Refresh the list for the user the rule was granted to.
      setFilterUserId(grantUserId.trim());
      await loadPermissions(grantUserId.trim());
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setIsGranting(false);
    }
  }, [workspaceId, grantUserId, grantArtifactId, grantLevel, loadPermissions, t]);

  const handleRevoke = useCallback(
    async (permissionId: string): Promise<void> => {
      if (
        !window.confirm(
          t("permissions.revokeConfirm", "Revoke this permission rule?")
        )
      ) {
        return;
      }
      setRevokingId(permissionId);
      setError(null);
      try {
        await itemPermissionsApi.revoke(workspaceId, permissionId);
        if (filterUserId.trim()) {
          await loadPermissions(filterUserId);
        } else {
          setPermissions((prev) => prev.filter((p) => p.id !== permissionId));
        }
      } catch (err) {
        setError(extractErrorMessage(err));
      } finally {
        setRevokingId(null);
      }
    },
    [workspaceId, filterUserId, loadPermissions, t]
  );

  const loadMembers = useCallback(async (): Promise<void> => {
    try {
      const rows = await workspaceMembersApi.list(workspaceId);
      setMembers(rows);
    } catch (err) {
      setMembersError(extractErrorMessage(err));
    }
  }, [workspaceId]);

  const handleMembersApiError = useCallback(
    (err: unknown): void => {
      if (isLastAdminError(err)) {
        const parsed = parseLastAdminMessage(err.message);
        setMembersError(
          parsed
            ? t(
                "permissions.members.lastAdminError",
                "Cannot complete this action: {{scope}} {{identifier}} would have no active admin left.",
                { scope: parsed.scope, identifier: parsed.identifier }
              )
            : err.message
        );
        return;
      }
      setMembersError(extractErrorMessage(err));
    },
    [t]
  );

  const handleSuspendRole = useCallback(
    async (member: WorkspaceMember, role: string): Promise<void> => {
      const key = memberRoleKey(member.user_id, role);
      setMembersError(null);
      setPendingRoleKey(key);
      try {
        await workspaceMembersApi.suspendRole(workspaceId, member.user_id, role);
        // Snapshot the member as it looked right before suspension so the
        // row/role stays visible (with a Reactivate action) even if the
        // refetch below drops it from the active-only roster.
        setSuspendedRoleSnapshots((prev) => ({ ...prev, [key]: member }));
        await loadMembers();
      } catch (err) {
        handleMembersApiError(err);
      } finally {
        setPendingRoleKey(null);
      }
    },
    [workspaceId, loadMembers, handleMembersApiError]
  );

  const handleReactivateRole = useCallback(
    async (member: WorkspaceMember, role: string): Promise<void> => {
      const key = memberRoleKey(member.user_id, role);
      setMembersError(null);
      setPendingRoleKey(key);
      try {
        await workspaceMembersApi.reactivateRole(workspaceId, member.user_id, role);
        setSuspendedRoleSnapshots((prev) => {
          const next = { ...prev };
          delete next[key];
          return next;
        });
        await loadMembers();
      } catch (err) {
        handleMembersApiError(err);
      } finally {
        setPendingRoleKey(null);
      }
    },
    [workspaceId, loadMembers, handleMembersApiError]
  );

  // Merge the live (active-only) roster with any session-suspended
  // snapshots so a member whose last active role was just suspended does
  // not vanish before the admin can reactivate it.
  const memberById = new Map(members.map((m) => [m.user_id, m]));
  const ghostMembers = Object.values(suspendedRoleSnapshots).filter(
    (m) => !memberById.has(m.user_id)
  );
  const dedupedGhosts = Array.from(
    new Map(ghostMembers.map((m) => [m.user_id, m])).values()
  );
  const displayMembers = [...members, ...dedupedGhosts];

  const rolesForDisplay = useCallback(
    (member: WorkspaceMember): string[] => {
      const live = memberById.get(member.user_id)?.roles ?? [];
      const suspended = Object.entries(suspendedRoleSnapshots)
        .filter(([key]) => key.startsWith(`${member.user_id}::`))
        .map(([key]) => key.slice(`${member.user_id}::`.length));
      return Array.from(new Set([...live, ...suspended]));
    },
    // memberById is derived fresh from `members` every render; depend on
    // `members` directly instead so this callback's identity tracks it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [members, suspendedRoleSnapshots]
  );

  const isRoleSuspended = useCallback(
    (member: WorkspaceMember, role: string): boolean => {
      const key = memberRoleKey(member.user_id, role);
      const live = memberById.get(member.user_id)?.roles ?? [];
      return key in suspendedRoleSnapshots && !live.includes(role);
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [members, suspendedRoleSnapshots]
  );

  return (
    <section style={sectionStyle} data-testid="permissions-section">
      <h3 style={headingStyle}>
        {t("permissions.title", "Item Permissions")}
      </h3>
      <p
        style={{
          fontSize: "var(--font-size-sm)",
          color: "var(--color-text-muted)",
          marginTop: 0,
          marginBottom: "var(--space-3)",
        }}
      >
        {t(
          "permissions.hint",
          "Per-user access rules for this workspace. A rule without an artifact applies workspace-wide; level 'none' is an explicit deny."
        )}
      </p>

      {/* Workspace members roster — suspend/reactivate role actions (Task 13) */}
      <div data-testid="workspace-members-section" style={membersSectionStyle}>
        <h4 style={membersHeadingStyle}>
          {t("permissions.members.title", "Workspace Members")}
        </h4>

        {membersError && (
          <p role="alert" data-testid="workspace-members-error" style={membersErrorStyle}>
            {membersError}
          </p>
        )}

        {displayMembers.length === 0 ? (
          <p data-testid="workspace-members-empty" style={membersEmptyStyle}>
            {t("permissions.members.empty", "No workspace members.")}
          </p>
        ) : (
          <table data-testid="workspace-members-table" style={membersTableStyle}>
            <thead>
              <tr>
                <th style={thStyle}>{t("permissions.members.member", "Member")}</th>
                <th style={thStyle}>{t("permissions.members.roles", "Roles")}</th>
              </tr>
            </thead>
            <tbody>
              {displayMembers.map((m) => (
                <tr key={m.user_id} data-testid={`workspace-member-row-${m.user_id}`}>
                  <td style={tdStyle}>{memberLabel(m)}</td>
                  <td style={tdStyle}>
                    {rolesForDisplay(m).map((role) => {
                      const key = memberRoleKey(m.user_id, role);
                      const suspended = isRoleSuspended(m, role);
                      const isPending = pendingRoleKey === key;
                      return (
                        <span
                          key={role}
                          data-testid={`workspace-member-role-${m.user_id}-${role}`}
                          style={roleChipWrapperStyle}
                        >
                          <span style={suspended ? roleLabelSuspendedStyle : roleLabelActiveStyle}>
                            {role}
                          </span>
                          {suspended ? (
                            <button
                              type="button"
                              data-testid={`workspace-member-reactivate-${m.user_id}-${role}`}
                              onClick={() => void handleReactivateRole(m, role)}
                              disabled={isPending}
                              style={isPending ? reactivateActionPendingStyle : reactivateActionStyle}
                            >
                              {t("permissions.members.reactivate", "Reactivate")}
                            </button>
                          ) : (
                            <button
                              type="button"
                              data-testid={`workspace-member-suspend-${m.user_id}-${role}`}
                              onClick={() => void handleSuspendRole(m, role)}
                              disabled={isPending}
                              style={isPending ? suspendActionPendingStyle : suspendActionStyle}
                            >
                              {t("permissions.members.suspend", "Suspend")}
                            </button>
                          )}
                        </span>
                      );
                    })}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Grant form */}
      <div
        data-testid="permission-grant-form"
        style={{
          display: "flex",
          gap: "var(--space-2)",
          flexWrap: "wrap",
          alignItems: "center",
          marginBottom: "var(--space-4)",
          padding: "var(--space-3)",
          background: "var(--color-surface-raised)",
          borderRadius: "var(--radius-md)",
        }}
      >
        <select
          data-testid="permission-user-input"
          value={grantUserId}
          onChange={(e) => setGrantUserId(e.target.value)}
          disabled={isGranting || members.length === 0}
          style={{ ...inputStyle, flex: 1, minWidth: "220px" }}
        >
          <option value="">
            {members.length === 0
              ? t("permissions.noMembers", "No workspace members")
              : t("permissions.selectUser", "Select a member…")}
          </option>
          {members.map((m) => (
            <option key={m.user_id} value={m.user_id}>
              {memberLabel(m)}
            </option>
          ))}
        </select>
        <select
          data-testid="permission-artifact-select"
          value={grantArtifactId}
          onChange={(e) => setGrantArtifactId(e.target.value)}
          disabled={isGranting}
          style={inputStyle}
        >
          <option value="">
            {t("permissions.workspaceWide", "Workspace-wide (all artifacts)")}
          </option>
          {artifacts.map((a) => (
            <option key={a.id} value={a.id}>
              {a.artifact_type} — {a.id.slice(0, 8)}…
            </option>
          ))}
        </select>
        <select
          data-testid="permission-level-select"
          value={grantLevel}
          onChange={(e) => setGrantLevel(e.target.value as ItemPermissionLevel)}
          disabled={isGranting}
          style={inputStyle}
        >
          {LEVELS.map((lvl) => (
            <option key={lvl} value={lvl}>
              {lvl}
            </option>
          ))}
        </select>
        <button
          type="button"
          data-testid="permission-grant-btn"
          onClick={() => void handleGrant()}
          disabled={isGranting || !grantUserId.trim()}
          style={{
            ...primaryButtonStyle,
            opacity: isGranting || !grantUserId.trim() ? 0.5 : 1,
            cursor: isGranting || !grantUserId.trim() ? "not-allowed" : "pointer",
          }}
        >
          {isGranting ? "…" : `+ ${t("permissions.grant", "Grant")}`}
        </button>
      </div>

      {/* Filter / list */}
      <div
        style={{
          display: "flex",
          gap: "var(--space-2)",
          marginBottom: "var(--space-3)",
        }}
      >
        <select
          data-testid="permission-filter-input"
          value={filterUserId}
          onChange={(e) => {
            const value = e.target.value;
            setFilterUserId(value);
            if (value) void loadPermissions(value);
          }}
          disabled={members.length === 0}
          style={{ ...inputStyle, flex: 1 }}
        >
          <option value="">
            {members.length === 0
              ? t("permissions.noMembers", "No workspace members")
              : t("permissions.filterSelect", "Show rules for member…")}
          </option>
          {members.map((m) => (
            <option key={m.user_id} value={m.user_id}>
              {memberLabel(m)}
            </option>
          ))}
        </select>
        <button
          type="button"
          data-testid="permission-load-btn"
          onClick={() => void loadPermissions(filterUserId)}
          disabled={isLoading || !filterUserId.trim()}
          style={{
            ...primaryButtonStyle,
            background: "var(--color-surface)",
            color: "var(--color-primary)",
            border: "1px solid var(--color-primary)",
            opacity: isLoading || !filterUserId.trim() ? 0.5 : 1,
          }}
        >
          {isLoading ? "…" : t("permissions.load", "Load rules")}
        </button>
      </div>

      {error && (
        <p
          role="alert"
          data-testid="permissions-error"
          style={{
            color: "var(--color-danger)",
            fontSize: "var(--font-size-sm)",
          }}
        >
          {error}
        </p>
      )}

      {hasLoaded && permissions.length === 0 && !isLoading && (
        <p
          data-testid="permissions-empty"
          style={{
            color: "var(--color-text-muted)",
            fontSize: "var(--font-size-sm)",
          }}
        >
          {t("permissions.empty", "No permission rules for this user.")}
        </p>
      )}

      {permissions.length > 0 && (
        <table
          data-testid="permissions-table"
          style={{ width: "100%", borderCollapse: "collapse" }}
        >
          <thead>
            <tr>
              <th style={thStyle}>{t("permissions.user", "User")}</th>
              <th style={thStyle}>{t("permissions.artifact", "Artifact")}</th>
              <th style={thStyle}>{t("permissions.level", "Level")}</th>
              <th style={thStyle} />
            </tr>
          </thead>
          <tbody>
            {permissions.map((perm) => (
              <tr key={perm.id} data-testid={`permission-row-${perm.id}`}>
                <td style={tdStyle}>
                  {members.find((m) => m.user_id === perm.user_id)
                    ?.display_name ?? `${perm.user_id.slice(0, 8)}…`}
                </td>
                <td style={{ ...tdStyle, fontFamily: "monospace" }}>
                  {perm.artifact_id
                    ? `${perm.artifact_id.slice(0, 8)}…`
                    : t("permissions.workspaceWideShort", "workspace-wide")}
                </td>
                <td style={tdStyle}>
                  <span
                    style={{
                      display: "inline-block",
                      padding: "1px var(--space-2)",
                      borderRadius: "var(--radius-full)",
                      fontSize: "var(--font-size-xs)",
                      fontWeight: 600,
                      background: perm.is_explicit_deny
                        ? "rgba(var(--color-danger-rgb), 0.12)"
                        : "rgba(var(--color-primary-rgb), 0.12)",
                      color: perm.is_explicit_deny
                        ? "var(--color-danger)"
                        : "var(--color-primary)",
                    }}
                  >
                    {perm.permission_level}
                  </span>
                </td>
                <td style={{ ...tdStyle, textAlign: "right" }}>
                  <button
                    type="button"
                    data-testid={`permission-revoke-${perm.id}`}
                    onClick={() => void handleRevoke(perm.id)}
                    disabled={revokingId === perm.id}
                    style={{
                      background: "transparent",
                      color: "var(--color-danger)",
                      border: "1px solid var(--color-danger)",
                      borderRadius: "var(--radius-md)",
                      padding: "var(--space-1) var(--space-3)",
                      fontSize: "var(--font-size-sm)",
                      cursor: revokingId === perm.id ? "wait" : "pointer",
                      opacity: revokingId === perm.id ? 0.6 : 1,
                    }}
                  >
                    {t("permissions.revoke", "Revoke")}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

const thStyle: React.CSSProperties = {
  textAlign: "left",
  padding: "var(--space-2) var(--space-3)",
  fontSize: "var(--font-size-xs)",
  fontWeight: 600,
  color: "var(--color-text-muted)",
  textTransform: "uppercase",
  letterSpacing: "0.05em",
  borderBottom: "1px solid var(--color-border)",
};

const tdStyle: React.CSSProperties = {
  padding: "var(--space-2) var(--space-3)",
  fontSize: "var(--font-size-sm)",
  color: "var(--color-text)",
  borderBottom: "1px solid var(--color-border)",
  verticalAlign: "middle",
};
