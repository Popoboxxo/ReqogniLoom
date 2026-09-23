/**
 * ARCH-L1-001 ReactFrontend — ApiKeysSection (UserProfileSettings).
 *
 * leaf_id: COMP-RF-006 (UserProfileSettings — Personal Access Token management)
 * req_id:  REQ-L2-RF-027 (User-Profile Dialog für PAT-Verwaltung),
 *          REQ-L3-RF006-001 (Token-Liste und UI-Controls),
 *          REQ-L3-AT001-003 (API key lifecycle: create / list / revoke)
 *
 * Manages the authenticated user's Personal Access Tokens, workspace-independent:
 *   - list (metadata only)
 *   - create (plaintext shown exactly ONCE with copy-me warning)
 *   - revoke (immediate)
 */

import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  apiKeysApi,
  type ApiKeyCreateResult,
  type ApiKeyMetadata,
} from "../../api/api-keys";
import { ConfirmDialog } from "../shared/ConfirmDialog";
import styles from "./ApiKeysSection.module.css";

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

export function ApiKeysSection(): JSX.Element {
  const { t } = useTranslation();
  const [keys, setKeys] = useState<ApiKeyMetadata[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [newKeyName, setNewKeyName] = useState("");
  const [isCreating, setIsCreating] = useState(false);
  const [createdKey, setCreatedKey] = useState<ApiKeyCreateResult | null>(null);
  const [revokingId, setRevokingId] = useState<string | null>(null);
  // UI-20: unified on the shared ConfirmDialog instead of window.confirm.
  const [pendingRevokeId, setPendingRevokeId] = useState<string | null>(null);

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
    [createdKey, load]
  );

  const confirmRevoke = useCallback((): void => {
    if (!pendingRevokeId) return;
    const id = pendingRevokeId;
    setPendingRevokeId(null);
    void handleRevoke(id);
  }, [pendingRevokeId, handleRevoke]);

  return (
    <section className={styles.section} data-testid="api-keys-section">
      <h2 className={styles.title}>
        {t("apiKeys.title", "Persönliche API-Tokens")}
      </h2>
      <p className={styles.hint}>
        {t(
          "apiKeys.hint",
          "API keys authenticate MCP and REST clients (X-API-Key header). The key value is shown exactly once after creation."
        )}
      </p>

      {/* Create form card */}
      <div className={styles.card}>
        <h3 className={styles.subheading}>
          {t("apiKeys.createNew", "Neuen Token erstellen")}
        </h3>
        <div className={styles.createRow}>
          <input
            data-testid="api-key-name-input"
            type="text"
            value={newKeyName}
            onChange={(e) => setNewKeyName(e.target.value)}
            placeholder={t("apiKeys.namePlaceholder", "Key label (e.g. ci-pipeline)")}
            disabled={isCreating}
            className={styles.nameInput}
          />
          <button
            type="button"
            data-testid="api-key-create-btn"
            onClick={() => void handleCreate()}
            disabled={isCreating || !newKeyName.trim()}
            className={`${styles.primaryButton} ${
              isCreating || !newKeyName.trim()
                ? styles.primaryButtonDisabled
                : styles.primaryButtonEnabled
            }`}
          >
            {isCreating ? "…" : `+ ${t("actions.new")} ${t("apiKeys.newKeyLabel")}`}
          </button>
        </div>
      </div>

      {/* One-time plaintext display */}
      {createdKey && (
        <div
          data-testid="api-key-plaintext-box"
          role="alert"
          className={styles.plaintextBox}
        >
          <p className={styles.plaintextWarning}>
            {t(
              "apiKeys.plaintextWarning",
              "Save this key now — it will not be shown again."
            )}
          </p>
          <div className={styles.plaintextRow}>
            <code
              data-testid="api-key-plaintext"
              className={styles.plaintextCode}
            >
              {createdKey.plaintext}
            </code>
            <button
              type="button"
              data-testid="api-key-copy-btn"
              onClick={() => {
                void navigator.clipboard?.writeText(createdKey.plaintext);
              }}
              className={styles.copyButton}
            >
              {t("actions.copy", "Copy")}
            </button>
            <button
              type="button"
              data-testid="api-key-dismiss"
              onClick={() => setCreatedKey(null)}
              className={styles.dismissButton}
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
          className={styles.errorText}
        >
          {error}
        </p>
      )}

      {/* Key list */}
      {isLoading ? (
        <div className={styles.card}>
          <p role="status" className={styles.loadingText}>
            {t("loading", "Loading...")}
          </p>
        </div>
      ) : keys.length === 0 ? (
        <div className={styles.card}>
          <p
            data-testid="api-keys-empty"
            className={styles.emptyText}
          >
            {t("apiKeys.empty", "Noch keine API-Tokens vorhanden. Erstelle einen neuen Token oben, um Clients zu authentifizieren.")}
          </p>
        </div>
      ) : (
        <div
          data-testid="api-keys-list"
          className={styles.keyList}
        >
          {keys.map((key) => (
            <div
              key={key.id}
              data-testid={`api-key-row-${key.id}`}
              className={styles.keyRow}
            >
              <div className={styles.keyHeader}>
                <div>
                  <p className={styles.keyName}>
                    {key.name}
                  </p>
                  <div className={styles.keyMeta}>
                    <span>
                      {t("apiKeys.created", "Created")}: {formatDate(key.created_at)}
                    </span>
                    <span>
                      {t("apiKeys.lastUsed", "Last used")}: {formatDate(key.last_used_at)}
                    </span>
                  </div>
                </div>
                <span
                  className={`${styles.statusBadge} ${
                    key.revoked ? styles.statusBadgeRevoked : styles.statusBadgeActive
                  }`}
                >
                  {key.revoked
                    ? t("apiKeys.revoked", "revoked")
                    : t("apiKeys.active", "active")}
                </span>
              </div>
              {!key.revoked && (
                <div className={styles.revokeRow}>
                  <button
                    type="button"
                    data-testid={`api-key-revoke-${key.id}`}
                    onClick={() => setPendingRevokeId(key.id)}
                    disabled={revokingId === key.id}
                    className={`${styles.dangerButton} ${
                      revokingId === key.id
                        ? styles.dangerButtonDisabled
                        : styles.dangerButtonEnabled
                    }`}
                  >
                    {revokingId === key.id ? "…" : t("apiKeys.revoke", "Revoke")}
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {pendingRevokeId && (
        <ConfirmDialog
          title={t("apiKeys.revoke", "Revoke")}
          message={t(
            "apiKeys.revokeConfirm",
            "Revoke this API key? Clients using it will lose access immediately."
          )}
          confirmLabel={t("apiKeys.revoke", "Revoke")}
          onConfirm={confirmRevoke}
          onCancel={() => setPendingRevokeId(null)}
          testId="api-key-revoke-confirm"
        />
      )}
    </section>
  );
}
