/**
 * ARCH-L1-001 ReactFrontend — Admin Ops (Disaster Recovery) API.
 *
 * leaf_id: COMP-RF-001 (NavigationShell — WorkspaceSettings scope)
 * req_id:  REQ-L1-046 (Disaster Recovery: Backup / Restore)
 *
 * Wraps the admin-only endpoints:
 *   GET  /api/v1/admin/backups/   — list backups (newest first)
 *   POST /api/v1/admin/backups/   — create a backup
 *   POST /api/v1/admin/restore/   — restore from a backup (captcha "RESTORE")
 */

import { apiClient } from "./client";
import type { UUID } from "../types";

export type BackupStatusValue = "pending" | "running" | "completed" | "failed";
export type BackupTypeValue = "full" | "partial";

export interface BackupMetadata {
  id: UUID;
  status: string;
  backup_type: string;
  file_path: string;
  file_size_bytes: number | null;
  checksum_sha256: string | null;
  error_message: string;
  metadata: Record<string, unknown>;
  completed_at: string | null;
  is_restorable: boolean;
  created_at: string | null;
  created_by: UUID | null;
}

export interface RestoreResult {
  backup_id: UUID;
  started_at: string | null;
  completed_at: string | null;
  restored_tables: string[];
  rows_per_table: Record<string, number>;
}

/** Captcha text the backend requires for a restore (REQ-L1-046). */
export const RESTORE_CONFIRMATION_TEXT = "RESTORE";

export const adminOpsApi = {
  /** GET /api/v1/admin/backups/ — admin-only backup listing. */
  async listBackups(params?: {
    status?: BackupStatusValue;
    backupType?: BackupTypeValue;
    limit?: number;
    offset?: number;
  }): Promise<BackupMetadata[]> {
    const query = new URLSearchParams();
    if (params?.status) query.set("status", params.status);
    if (params?.backupType) query.set("backup_type", params.backupType);
    if (params?.limit !== undefined) query.set("limit", String(params.limit));
    if (params?.offset !== undefined) query.set("offset", String(params.offset));
    const qs = query.toString();
    const resp = await apiClient.get<{ backups: BackupMetadata[] }>(
      `/admin/backups/${qs ? `?${qs}` : ""}`
    );
    return resp.backups;
  },

  /** POST /api/v1/admin/backups/ — create a backup (admin-only). */
  async createBackup(data?: {
    reason?: string;
    backup_type?: BackupTypeValue;
  }): Promise<BackupMetadata> {
    const resp = await apiClient.post<{ backup: BackupMetadata }>(
      "/admin/backups/",
      data ?? {}
    );
    return resp.backup;
  },

  /**
   * POST /api/v1/admin/restore/ — restore from a backup (admin-only).
   * The backend validates ``confirmation_text === "RESTORE"`` as a captcha.
   */
  async restore(data: {
    backup_id: UUID;
    confirmation_text: string;
    restore_type?: BackupTypeValue;
  }): Promise<RestoreResult> {
    const resp = await apiClient.post<{ restore: RestoreResult }>(
      "/admin/restore/",
      data
    );
    return resp.restore;
  },
};
