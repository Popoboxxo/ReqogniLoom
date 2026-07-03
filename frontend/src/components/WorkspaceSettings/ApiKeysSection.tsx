/**
 * ARCH-L1-001 ReactFrontend — ApiKeysSection (WorkspaceSettings).
 *
 * leaf_id: COMP-RF-001 (NavigationShell scope — Workspace-Konfigurations-UI)
 * req_id:  REQ-L3-AT001-003 (API key lifecycle: create / list / revoke)
 *
 * Manages the authenticated user's API keys:
 *   - list (metadata only)
 *   - create (plaintext shown exactly ONCE with copy-me warning)
 *   - revoke (immediate)
 */

import React, { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  apiKeysApi,
  type ApiKeyCreateResult,
  type ApiKeyMetadata,
} from "../../api/api-keys";

function extractErrorMessage(err: unknown): string {
  const e = err as { error?: { message?: string }; message?: string };
  return e?.error?.message ?? e?.message ?? String(err);
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

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
  fontSize: "var(--font-size-base)",
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

export function ApiKeysSection(): JSX.Element {
  const { t } = useTranslation();
  const [keys, setKeys] = useState<ApiKeyMetadata[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [newKeyName, setNewKeyName] = useState("");
  const [isCreating, setIsCreating] = useState(false);
  const [createdKey, setCreatedKey] = useState<ApiKeyCreateResult | null>(null);
  const [revokingId, setRevokingId] = useState<string | null>(null);

  const load = useCallback(async (): Promise<void> => {
    setIsLoading(true);
    setError(null);
    try {
      const list = await apiKeysApi.list();
      setKeys(list);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const handleCreate = useCallback(async (): Promise<void> => {
    if (!newKeyName.trim()) return;
    setIsCreating(true);
    setError(null);
    try {
      const result = await apiKeysApi.create(newKeyName.trim());
      setCreatedKey(result);
      setNewKeyName("");
      await load();
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setIsCreating(false);
    }
  }, [newKeyName, load]);

  const handleRevoke = useCallback(
    async (id: string): Promise<void> => {
      if (
        !window.confirm(
          t(
            "apiKeys.revokeConfirm",
            "Revoke this API key? Clients using it will lose access immediately."
          )
        )
      ) {
        return;
      }
      setRevokingId(id);
      setError(null);
      try {
        await apiKeysApi.revoke(id);
        if (createdKey?.id === id) setCreatedKey(null);
        await load();
      } catch (err) {
        setError(extractErrorMessage(err));
      } finally {
        setRevokingId(null);
      }
    },
    [createdKey, load, t]
  );

  return (
    <section style={sectionStyle} data-testid="api-keys-section">
      <h3 style={headingStyle}>{t("apiKeys.title", "API Keys")}</h3>
      <p
        style={{
          fontSize: "var(--font-size-sm)",
          color: "var(--color-text-muted)",
          marginTop: 0,
          marginBottom: "var(--space-3)",
        }}
      >
        {t(
          "apiKeys.hint",
          "API keys authenticate MCP and REST clients (X-API-Key header). The key value is shown exactly once after creation."
        )}
      </p>

      {/* Create form */}
      <div
        style={{
          display: "flex",
          gap: "var(--space-3)",
          marginBottom: "var(--space-4)",
        }}
      >
        <input
          data-testid="api-key-name-input"
          type="text"
          value={newKeyName}
          onChange={(e) => setNewKeyName(e.target.value)}
          placeholder={t("apiKeys.namePlaceholder", "Key label (e.g. ci-pipeline)")}
          disabled={isCreating}
          style={{ ...inputStyle, flex: 1 }}
        />
        <button
          type="button"
          data-testid="api-key-create-btn"
          onClick={() => void handleCreate()}
          disabled={isCreating || !newKeyName.trim()}
          style={{
            ...primaryButtonStyle,
            opacity: isCreating || !newKeyName.trim() ? 0.5 : 1,
            cursor: isCreating || !newKeyName.trim() ? "not-allowed" : "pointer",
          }}
        >
          {isCreating ? "…" : `+ ${t("actions.create", "Create")}`}
        </button>
      </div>

      {/* One-time plaintext display */}
      {createdKey && (
        <div
          data-testid="api-key-plaintext-box"
          role="alert"
          style={{
            background: "var(--color-surface-raised)",
            border: "1px solid var(--color-warning, #f59e0b)",
            borderRadius: "var(--radius-md)",
            padding: "var(--space-3)",
            marginBottom: "var(--space-4)",
          }}
        >
          <p
            style={{
              margin: "0 0 var(--space-2) 0",
              fontWeight: 600,
              fontSize: "var(--font-size-sm)",
              color: "var(--color-text)",
            }}
          >
            {t(
              "apiKeys.plaintextWarning",
              "Save this key now — it will not be shown again."
            )}
          </p>
          <div style={{ display: "flex", gap: "var(--space-2)", alignItems: "center" }}>
            <code
              data-testid="api-key-plaintext"
              style={{
                fontFamily: "monospace",
                fontSize: "var(--font-size-sm)",
                background: "var(--color-bg)",
                padding: "var(--space-1) var(--space-2)",
                borderRadius: "var(--radius-sm)",
                wordBreak: "break-all",
                flex: 1,
              }}
            >
              {createdKey.plaintext}
            </code>
            <button
              type="button"
              data-testid="api-key-copy-btn"
              onClick={() => {
                void navigator.clipboard?.writeText(createdKey.plaintext);
              }}
              style={{
                ...primaryButtonStyle,
                padding: "var(--space-1) var(--space-3)",
              }}
            >
              {t("actions.copy", "Copy")}
            </button>
            <button
              type="button"
              onClick={() => setCreatedKey(null)}
              style={{
                background: "transparent",
                color: "var(--color-text-muted)",
                border: "1px solid var(--color-border)",
                borderRadius: "var(--radius-md)",
                padding: "var(--space-1) var(--space-3)",
                fontSize: "var(--font-size-sm)",
                cursor: "pointer",
              }}
            >
              {t("actions.dismiss", "Dismiss")}
            </button>
          </div>
        </div>
      )}

      {error && (
        <p
          role="alert"
          data-testid="api-keys-error"
          style={{
            color: "var(--color-danger)",
            fontSize: "var(--font-size-sm)",
          }}
        >
          {error}
        </p>
      )}

      {/* Key list */}
      {isLoading ? (
        <p role="status" style={{ color: "var(--color-text-muted)" }}>
          {t("loading", "Loading...")}
        </p>
      ) : keys.length === 0 ? (
        <p
          data-testid="api-keys-empty"
          style={{
            color: "var(--color-text-muted)",
            fontSize: "var(--font-size-sm)",
          }}
        >
          {t("apiKeys.empty", "No API keys yet.")}
        </p>
      ) : (
        <table
          data-testid="api-keys-table"
          style={{ width: "100%", borderCollapse: "collapse" }}
        >
          <thead>
            <tr>
              <th style={thStyle}>{t("apiKeys.name", "Name")}</th>
              <th style={thStyle}>{t("apiKeys.created", "Created")}</th>
              <th style={thStyle}>{t("apiKeys.lastUsed", "Last used")}</th>
              <th style={thStyle}>{t("apiKeys.status", "Status")}</th>
              <th style={thStyle} />
            </tr>
          </thead>
          <tbody>
            {keys.map((key) => (
              <tr key={key.id} data-testid={`api-key-row-${key.id}`}>
                <td style={tdStyle}>{key.name}</td>
                <td style={tdStyle}>{formatDate(key.created_at)}</td>
                <td style={tdStyle}>{formatDate(key.last_used_at)}</td>
                <td style={tdStyle}>
                  <span
                    style={{
                      display: "inline-block",
                      padding: "1px var(--space-2)",
                      borderRadius: "var(--radius-full)",
                      fontSize: "var(--font-size-xs)",
                      fontWeight: 600,
                      background: key.revoked
                        ? "var(--color-surface-raised)"
                        : "rgba(22,163,74,0.12)",
                      color: key.revoked
                        ? "var(--color-text-muted)"
                        : "var(--color-success, #16a34a)",
                    }}
                  >
                    {key.revoked
                      ? t("apiKeys.revoked", "revoked")
                      : t("apiKeys.active", "active")}
                  </span>
                </td>
                <td style={{ ...tdStyle, textAlign: "right" }}>
                  {!key.revoked && (
                    <button
                      type="button"
                      data-testid={`api-key-revoke-${key.id}`}
                      onClick={() => void handleRevoke(key.id)}
                      disabled={revokingId === key.id}
                      style={{
                        background: "transparent",
                        color: "var(--color-danger)",
                        border: "1px solid var(--color-danger)",
                        borderRadius: "var(--radius-md)",
                        padding: "var(--space-1) var(--space-3)",
                        fontSize: "var(--font-size-sm)",
                        cursor: revokingId === key.id ? "wait" : "pointer",
                        opacity: revokingId === key.id ? 0.6 : 1,
                      }}
                    >
                      {t("apiKeys.revoke", "Revoke")}
                    </button>
                  )}
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
