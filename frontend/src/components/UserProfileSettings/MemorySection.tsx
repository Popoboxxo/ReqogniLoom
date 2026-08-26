/**
 * ARCH-L1-001 ReactFrontend — MemorySection (UserProfileSettings).
 *
 * leaf_id: COMP-RF-006 (UserProfileSettings — user-owned data controls)
 *
 * Memory Admin UI Phase 4 (spec 2026-08-26): GDPR-style self-service erasure
 * control for the authenticated user's OWN UserTenantMemory rows — never
 * WorkspaceMemory, which is team-owned and stays exclusively under the
 * System-Admin "Memory" tab (MemoryAdminService, Phase 1). No admin gate:
 * any authenticated user, no role required (mirrors ApiKeysSection).
 */

import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  memorySelfServiceApi,
  type MemorySelfServiceOverview,
} from "../../api/memory-self-service";

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

const cardStyle: React.CSSProperties = {
  boxShadow: "var(--shadow-card)",
  borderRadius: "var(--radius-lg)",
  padding: "var(--space-4)",
  background: "var(--color-surface-raised)",
  marginBottom: "var(--space-4)",
  border: "1px solid var(--color-border)",
};

const dangerButtonStyle: React.CSSProperties = {
  background: "var(--color-danger)",
  color: "white",
  border: "none",
  borderRadius: "var(--radius-md)",
  padding: "var(--space-1) var(--space-3)",
  fontSize: "var(--font-size-sm)",
  fontWeight: 600,
  cursor: "pointer",
};

const EMPTY_OVERVIEW: MemorySelfServiceOverview = {
  entry_count: 0,
  last_updated_at: null,
};

export function MemorySection(): JSX.Element {
  const { t } = useTranslation();
  const [overview, setOverview] = useState<MemorySelfServiceOverview>(EMPTY_OVERVIEW);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  const load = useCallback(async (): Promise<void> => {
    setIsLoading(true);
    setError(null);
    try {
      const result = await memorySelfServiceApi.get();
      setOverview(result);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const handleDelete = useCallback(async (): Promise<void> => {
    if (
      !window.confirm(
        t(
          "memorySelfService.deleteConfirm",
          "Delete ALL of your own memory entries? This removes everything the AI has remembered about you and cannot be undone."
        )
      )
    ) {
      return;
    }
    setIsDeleting(true);
    setError(null);
    try {
      await memorySelfServiceApi.deleteAll();
      setOverview(EMPTY_OVERVIEW);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setIsDeleting(false);
    }
  }, [t]);

  return (
    <section style={sectionStyle} data-testid="memory-self-service-section">
      <h2
        style={{
          ...headingStyle,
          fontSize: "var(--font-size-xl)",
          marginBottom: "var(--space-2)",
        }}
      >
        {t("memorySelfService.title", "Mein Memory")}
      </h2>
      <p
        style={{
          fontSize: "var(--font-size-sm)",
          color: "var(--color-text-muted)",
          marginTop: 0,
          marginBottom: "var(--space-5)",
        }}
      >
        {t(
          "memorySelfService.hint",
          "Das KI-Langzeitgedächtnis speichert Kontext über dich, um Antworten zu personalisieren. Du kannst deine eigenen Einträge jederzeit vollständig löschen."
        )}
      </p>

      {error && (
        <p
          role="alert"
          data-testid="memory-self-service-error"
          style={{
            color: "var(--color-danger)",
            fontSize: "var(--font-size-sm)",
          }}
        >
          {error}
        </p>
      )}

      {isLoading ? (
        <div style={cardStyle}>
          <p
            role="status"
            data-testid="memory-self-service-loading"
            style={{ color: "var(--color-text-muted)", margin: 0 }}
          >
            {t("loading", "Loading...")}
          </p>
        </div>
      ) : (
        <div style={cardStyle}>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "flex-start",
              marginBottom: "var(--space-3)",
            }}
          >
            <div>
              <p
                style={{
                  margin: "0 0 var(--space-1) 0",
                  fontSize: "var(--font-size-sm)",
                  color: "var(--color-text-muted)",
                }}
              >
                {t("memorySelfService.countLabel", "Gespeicherte Einträge")}:{" "}
                <span
                  data-testid="memory-self-service-count"
                  style={{ fontWeight: 700, color: "var(--color-text)" }}
                >
                  {overview.entry_count}
                </span>
              </p>
              <p
                style={{
                  margin: 0,
                  fontSize: "var(--font-size-sm)",
                  color: "var(--color-text-muted)",
                }}
              >
                {t("memorySelfService.lastUpdatedLabel", "Zuletzt aktualisiert")}:{" "}
                <span data-testid="memory-self-service-last-updated">
                  {formatDate(overview.last_updated_at)}
                </span>
              </p>
              {overview.entry_count === 0 && (
                <p
                  data-testid="memory-self-service-empty"
                  style={{
                    margin: "var(--space-2) 0 0 0",
                    fontSize: "var(--font-size-sm)",
                    color: "var(--color-text-muted)",
                  }}
                >
                  {t("memorySelfService.empty", "Noch keine Memory-Einträge vorhanden.")}
                </p>
              )}
            </div>
            <button
              type="button"
              data-testid="memory-self-service-delete-btn"
              onClick={() => void handleDelete()}
              disabled={overview.entry_count === 0 || isDeleting}
              style={{
                ...dangerButtonStyle,
                opacity: overview.entry_count === 0 || isDeleting ? 0.5 : 1,
                cursor:
                  overview.entry_count === 0
                    ? "not-allowed"
                    : isDeleting
                      ? "wait"
                      : "pointer",
              }}
            >
              {isDeleting ? "…" : t("memorySelfService.deleteButton", "Mein Memory löschen")}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
