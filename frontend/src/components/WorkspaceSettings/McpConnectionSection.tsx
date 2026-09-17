/**
 * ARCH-L1-001 ReactFrontend — McpConnectionSection (WorkspaceSettings).
 *
 * Read-only connection card that carries everything a developer needs to point
 * an MCP client (Claude Desktop, Claude Code, …) at *this* workspace:
 *
 *   - workspace name and workspace UUID,
 *   - both MCP transport endpoints (HTTP + SSE), derived from the current
 *     origin — the SPA is served behind the same nginx/Vite proxy that also
 *     forwards ``/mcp/`` to Django, so ``window.location.origin`` is the
 *     address the browser (and therefore any client on the same host) uses,
 *   - the header-based authentication contract (``X-API-Key`` /
 *     ``Authorization: Bearer``) with an in-app link to the Personal Access
 *     Token management in the profile page,
 *   - a ready-to-paste ``mcpServers`` config snippet.
 *
 * Why the workspace id is shown so prominently: an API key is a *personal*,
 * workspace-independent credential (see UserProfileSettings/ApiKeysSection).
 * It identifies the user and the tenant, never the workspace. Almost every MCP
 * tool therefore declares ``workspace_id`` as a required parameter
 * (mcp_server/tools/*.py), so the client has to supply it explicitly on each
 * ``tools/call``.
 *
 * The section is purely informational — it neither creates nor mutates
 * anything, and needs no backend endpoint of its own.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

/** MCP transport paths as mounted in backend/reqogniloom/urls.py. */
const MCP_HTTP_PATH = "/mcp/";
const MCP_SSE_PATH = "/mcp/sse/";

/** Plaintext prefix of a ReqogniLoom API key (auth_tenancy/services/authentication.py). */
const API_KEY_PREFIX = "reqlo_";

const CONFIRMATION_MS = 1500;

// --- Styles (named constants, not inline literals — UI ratchet Task 7.4) ---

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

const tightHintStyle: React.CSSProperties = {
  ...hintStyle,
  margin: "0 0 var(--space-2) 0",
};

const fieldStyle: React.CSSProperties = {
  marginBottom: "var(--space-4)",
};

const fieldLabelStyle: React.CSSProperties = {
  display: "block",
  marginBottom: "var(--space-2)",
  fontWeight: 600,
  fontSize: "var(--font-size-sm)",
  color: "var(--color-text)",
};

const valueRowStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "var(--space-2)",
};

const multilineValueRowStyle: React.CSSProperties = {
  ...valueRowStyle,
  alignItems: "flex-start",
};

const valueStyle: React.CSSProperties = {
  flex: 1,
  minWidth: 0,
  background: "var(--color-surface-raised)",
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-md)",
  padding: "var(--space-2) var(--space-3)",
  fontFamily: "var(--font-mono)",
  fontSize: "var(--font-size-sm)",
  color: "var(--color-text)",
  userSelect: "all",
  whiteSpace: "nowrap",
  overflowX: "auto",
};

const multilineValueStyle: React.CSSProperties = {
  ...valueStyle,
  whiteSpace: "pre",
};

const copyButtonStyle: React.CSSProperties = {
  appearance: "none",
  border: "1px solid var(--color-border)",
  background: "var(--color-surface)",
  color: "var(--color-text)",
  borderRadius: "var(--radius-md)",
  padding: "var(--space-2) var(--space-3)",
  fontSize: "var(--font-size-sm)",
  cursor: "pointer",
  whiteSpace: "nowrap",
};

const linkStyle: React.CSSProperties = {
  fontSize: "var(--font-size-sm)",
  color: "var(--color-primary)",
};

export interface McpConnectionSectionProps {
  workspaceId: string;
  workspaceName: string;
  /** Test seam: overrides the origin used to build the endpoint URLs. */
  origin?: string;
}

interface CopyableValueProps {
  label: string;
  value: string;
  /** Accessible name for the copy button, e.g. "Copy workspace ID". */
  copyLabel: string;
  testId: string;
  multiline?: boolean;
}

/**
 * A labelled, monospaced value with a copy-to-clipboard button.
 *
 * Mirrors the clipboard handling of `shared/ArtifactId` (optional-chained
 * `navigator.clipboard`, transient confirmation, unmount-safe timer).
 * `ArtifactId` itself is deliberately not reused here: its accessible name is
 * hardcoded to "Bezeichner … kopieren" with no per-instance override, which
 * would mislabel URLs and config snippets for screen-reader users.
 */
function CopyableValue({
  label,
  value,
  copyLabel,
  testId,
  multiline = false,
}: CopyableValueProps): JSX.Element {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    },
    [],
  );

  const handleCopy = useCallback(() => {
    if (!value) return;
    // navigator.clipboard is undefined on insecure origins and in jsdom —
    // a failed copy must never break the surrounding view.
    const write = navigator.clipboard?.writeText?.(value);
    // Unlike `ArtifactId`, an absent Clipboard API must NOT report success:
    // this panel exists to be copied from, so a false "Copied" would make a
    // user paste a stale value. `undefined` means the call never happened.
    if (write === undefined) return;
    Promise.resolve(write)
      .then(() => {
        setCopied(true);
        if (timerRef.current) clearTimeout(timerRef.current);
        timerRef.current = setTimeout(() => setCopied(false), CONFIRMATION_MS);
      })
      .catch(() => {
        /* clipboard unavailable — the value stays selectable by hand */
      });
  }, [value]);

  return (
    <div style={fieldStyle}>
      <div style={fieldLabelStyle}>{label}</div>
      <div style={multiline ? multilineValueRowStyle : valueRowStyle}>
        <code
          data-testid={`${testId}-value`}
          style={multiline ? multilineValueStyle : valueStyle}
        >
          {value}
        </code>
        <button
          type="button"
          data-testid={testId}
          onClick={handleCopy}
          aria-label={copyLabel}
          title={copyLabel}
          style={copyButtonStyle}
        >
          {copied
            ? t("settings.mcp.copied", "Kopiert")
            : t("settings.mcp.copy", "Kopieren")}
        </button>
      </div>
    </div>
  );
}

export function McpConnectionSection({
  workspaceId,
  workspaceName,
  origin,
}: McpConnectionSectionProps): JSX.Element {
  const { t } = useTranslation();

  const baseOrigin =
    origin ?? (typeof window !== "undefined" ? window.location.origin : "");
  const httpEndpoint = `${baseOrigin}${MCP_HTTP_PATH}`;
  const sseEndpoint = `${baseOrigin}${MCP_SSE_PATH}`;

  const configSnippet = JSON.stringify(
    {
      mcpServers: {
        reqogniloom: {
          url: sseEndpoint,
          headers: { "X-API-Key": `${API_KEY_PREFIX}…` },
        },
      },
    },
    null,
    2,
  );

  return (
    <section style={cardStyle} data-testid="mcp-connection-section">
      <h3 style={headingStyle}>{t("settings.mcp.title", "MCP-Verbindung")}</h3>
      <p style={hintStyle}>
        {t(
          "settings.mcp.hint",
          "Alle Angaben, die ein MCP-Client (z. B. Claude Desktop oder Claude Code) benötigt, um sich mit diesem Workspace zu verbinden.",
        )}
      </p>

      <CopyableValue
        label={t("settings.mcp.workspaceName", "Workspace-Name")}
        value={workspaceName}
        copyLabel={t(
          "settings.mcp.copyWorkspaceName",
          "Workspace-Namen kopieren",
        )}
        testId="mcp-copy-workspace-name"
      />

      <CopyableValue
        label={t("settings.mcp.workspaceId", "Workspace-ID")}
        value={workspaceId}
        copyLabel={t("settings.mcp.copyWorkspaceId", "Workspace-ID kopieren")}
        testId="mcp-copy-workspace-id"
      />
      <p style={hintStyle} data-testid="mcp-workspace-id-hint">
        {t(
          "settings.mcp.workspaceIdHint",
          "Der API-Key ist personen- und mandantengebunden, nicht workspace-gebunden. Fast alle MCP-Tools verlangen daher workspace_id als expliziten Parameter bei jedem tools/call.",
        )}
      </p>

      <CopyableValue
        label={t("settings.mcp.httpEndpoint", "MCP-Endpunkt (HTTP)")}
        value={httpEndpoint}
        copyLabel={t("settings.mcp.copyHttpEndpoint", "HTTP-Endpunkt kopieren")}
        testId="mcp-copy-http-endpoint"
      />

      <CopyableValue
        label={t("settings.mcp.sseEndpoint", "MCP-Endpunkt (SSE)")}
        value={sseEndpoint}
        copyLabel={t("settings.mcp.copySseEndpoint", "SSE-Endpunkt kopieren")}
        testId="mcp-copy-sse-endpoint"
      />

      <div style={fieldStyle}>
        <div style={fieldLabelStyle}>
          {t("settings.mcp.auth", "Authentifizierung")}
        </div>
        <p style={tightHintStyle}>
          {t(
            "settings.mcp.authHint",
            "Der API-Key muss als Header gesendet werden — X-API-Key: reqlo_… oder Authorization: Bearer reqlo_…. Ein api_key-Query-Parameter wird bewusst nicht unterstützt.",
          )}
        </p>
        <Link
          to="/profile"
          data-testid="mcp-personal-access-tokens-link"
          style={linkStyle}
        >
          {t(
            "settings.mcp.tokenLink",
            "Personal Access Token im Profil erstellen",
          )}
        </Link>
      </div>

      <CopyableValue
        label={t("settings.mcp.configExample", "Beispiel-Konfiguration")}
        value={configSnippet}
        copyLabel={t(
          "settings.mcp.copyConfigExample",
          "Beispiel-Konfiguration kopieren",
        )}
        testId="mcp-copy-config"
        multiline
      />
    </section>
  );
}
