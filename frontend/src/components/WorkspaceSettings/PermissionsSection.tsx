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
 * NOTE: the backend exposes no user directory endpoint, so the user is
 * addressed by UUID (copy from the admin panel or the auth/me response).
 */

import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  itemPermissionsApi,
  type ItemPermission,
  type ItemPermissionLevel,
} from "../../api/item-permissions";
import { artifactsApi } from "../../api/artifacts";
import type { Artifact, UUID } from "../../types";

function extractErrorMessage(err: unknown): string {
  const e = err as { error?: { message?: string }; message?: string };
  return e?.error?.message ?? e?.message ?? String(err);
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
  background: "var(--color-bg)",
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-md)",
  padding: "var(--space-2) var(--space-3)",
  color: "var(--color-text)",
  fontSize: "var(--font-size-sm)",
  boxSizing: "border-box",
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
        <input
          data-testid="permission-user-input"
          type="text"
          value={grantUserId}
          onChange={(e) => setGrantUserId(e.target.value)}
          placeholder={t("permissions.userPlaceholder", "User ID (UUID)")}
          disabled={isGranting}
          style={{ ...inputStyle, flex: 1, minWidth: "220px" }}
        />
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
        <input
          data-testid="permission-filter-input"
          type="text"
          value={filterUserId}
          onChange={(e) => setFilterUserId(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") void loadPermissions(filterUserId);
          }}
          placeholder={t(
            "permissions.filterPlaceholder",
            "Show rules for user ID (UUID)…"
          )}
          style={{ ...inputStyle, flex: 1 }}
        />
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
                <td style={{ ...tdStyle, fontFamily: "monospace" }}>
                  {perm.user_id.slice(0, 8)}…
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
                        ? "rgba(220,38,38,0.12)"
                        : "rgba(79,110,247,0.12)",
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
