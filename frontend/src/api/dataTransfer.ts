/**
 * ARCH-L1-001 ReactFrontend — data-transfer API client (P8).
 *
 * Wraps the P5/P6 snapshot endpoints and the P7 checked-restore endpoint:
 *   POST /api/v1/workspaces/{id}/export/snapshot/
 *   POST /api/v1/workspaces/{id}/import/snapshot/
 *   POST /api/v1/admin/restore/
 *
 * Auth flows via the httpOnly session cookie (REQ-052); every write carries
 * the CSRF token from the `csrftoken` cookie and the active Accept-Language.
 */

import { readCookie } from "./client";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Minimal shape needed to render counts — the full document is opaque to the UI. */
export interface SnapshotDocument {
  format_version?: string;
  workspace?: { id?: string; name?: string };
  entities?: Record<string, unknown[]>;
  relations?: Record<string, unknown[]>;
  [key: string]: unknown;
}

export interface SnapshotImportResult {
  success: boolean;
  workspace_id: string;
  created: number;
  updated: number;
  skipped: number;
  reconciled: number;
  dry_run: boolean;
  warnings: string[];
  id_map: Record<string, string>;
}

export interface RestorePlan {
  dry_run: boolean;
  backup_id: string;
  format_version: string;
  checksum_verified: boolean;
  target_tenant: string | null;
  target_workspace: string | null;
  restored_tables: string[];
  rows_per_table: Record<string, number>;
  loaddata: boolean;
}

export interface RestoreResult {
  backup_id: string;
  started_at: string | null;
  completed_at: string | null;
  restored_tables: string[];
  rows_per_table: Record<string, number>;
  dry_run: boolean;
  format_version: string;
  target_tenant: string | null;
  target_workspace: string | null;
  checksum_verified: boolean;
  warnings: string[];
  plan: RestorePlan | null;
}

function headers(): Record<string, string> {
  const result: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "application/json",
    "Accept-Language": document.documentElement.lang || "en",
  };
  const csrf = readCookie("csrftoken");
  if (csrf) result["X-CSRFToken"] = csrf;
  return result;
}

async function parseBody(resp: Response): Promise<Record<string, unknown>> {
  try {
    return (await resp.json()) as Record<string, unknown>;
  } catch {
    return {};
  }
}

function messageOf(body: Record<string, unknown>, fallback: string): string {
  const error = body.error as { message?: string } | undefined;
  const detail = body.detail;
  return error?.message ?? (typeof detail === "string" ? detail : fallback);
}

// ---------------------------------------------------------------------------
// Snapshot export / import
// ---------------------------------------------------------------------------

/**
 * Export a versioned full snapshot of the given workspace.
 * The returned document can be handed straight back to `importSnapshot`.
 */
export async function exportSnapshot(
  workspaceId: string
): Promise<SnapshotDocument> {
  const resp = await fetch(
    `/api/v1/workspaces/${workspaceId}/export/snapshot/`,
    { method: "POST", headers: headers(), credentials: "same-origin" }
  );
  const body = await parseBody(resp);
  if (!resp.ok) {
    throw new Error(messageOf(body, `Snapshot export failed (HTTP ${resp.status})`));
  }
  return body as unknown as SnapshotDocument;
}

export interface SnapshotImportOptions {
  /** Existing workspace to import into. Omit together with newWorkspaceName to use the route workspace. */
  targetWorkspaceId?: string;
  /** When set without targetWorkspaceId, a new workspace is created. */
  newWorkspaceName?: string;
  /** Preview only — no writes (D5). */
  dryRun?: boolean;
  /** version-guard (default) or admin-only update / reconcile_status. */
  conflictMode?: string;
}

/** Import a snapshot into an existing or newly created workspace. */
export async function importSnapshot(
  workspaceId: string,
  snapshot: SnapshotDocument,
  options: SnapshotImportOptions = {}
): Promise<SnapshotImportResult> {
  const body: Record<string, unknown> = { snapshot };
  if (options.targetWorkspaceId) body.target_workspace_id = options.targetWorkspaceId;
  if (options.newWorkspaceName) body.new_workspace_name = options.newWorkspaceName;
  if (options.dryRun) body.dry_run = true;
  if (options.conflictMode) body.conflict_mode = options.conflictMode;

  const resp = await fetch(
    `/api/v1/workspaces/${workspaceId}/import/snapshot/`,
    {
      method: "POST",
      headers: headers(),
      credentials: "same-origin",
      body: JSON.stringify(body),
    }
  );
  const parsed = await parseBody(resp);
  if (!resp.ok) {
    throw new Error(messageOf(parsed, `Snapshot import failed (HTTP ${resp.status})`));
  }
  return parsed as unknown as SnapshotImportResult;
}

// ---------------------------------------------------------------------------
// Checked restore (P7)
// ---------------------------------------------------------------------------

export interface RestoreOptions {
  backupId: string;
  dryRun?: boolean;
  targetTenant?: string;
  targetWorkspace?: string;
}

/** Run a checked restore (captcha is supplied by the caller after confirmation). */
export async function restoreBackup(
  options: RestoreOptions,
  confirmationText: string
): Promise<RestoreResult> {
  const body: Record<string, unknown> = {
    backup_id: options.backupId,
    confirmation_text: confirmationText,
    dry_run: Boolean(options.dryRun),
  };
  if (options.targetTenant) body.target_tenant = options.targetTenant;
  if (options.targetWorkspace) body.target_workspace = options.targetWorkspace;

  const resp = await fetch("/api/v1/admin/restore/", {
    method: "POST",
    headers: headers(),
    credentials: "same-origin",
    body: JSON.stringify(body),
  });
  const parsed = await parseBody(resp);
  if (!resp.ok) {
    throw new Error(messageOf(parsed, `Restore failed (HTTP ${resp.status})`));
  }
  return (parsed.restore ?? parsed) as RestoreResult;
}

/** Download a snapshot document as a JSON file in the browser. */
export function downloadSnapshot(snapshot: SnapshotDocument, filename: string): void {
  const blob = new Blob([JSON.stringify(snapshot, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export const dataTransferApi = {
  exportSnapshot,
  importSnapshot,
  restoreBackup,
  downloadSnapshot,
};
