/**
 * ARCH-L1-001 ReactFrontend — CSV Export API client.
 *
 * leaf_id: COMP-RF-001 (NavigationShell — API layer)
 * req_id:  REQ-L3-EXP-002 (CSV export, COMP-AS-008),
 *          C7 (frontend-feedback Cluster C — Import/Export MVP)
 *
 * Wraps GET /api/v1/workspaces/{id}/export/csv/ endpoint and triggers a
 * browser download of the returned CSV file.
 */

import { getAuthToken } from "./client";
import type { UUID } from "../types";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type ExportEntityType = "Requirement" | "StakeholderNeed" | "ArchitectureElement";

// ---------------------------------------------------------------------------
// API
// ---------------------------------------------------------------------------

export const exportApi = {
  /**
   * Fetch a CSV export for the given workspace + entity type and trigger a
   * browser download.
   *
   * @param workspaceId - Source workspace UUID.
   * @param entityType - Entity type to export.
   */
  async downloadCsv(workspaceId: UUID, entityType: ExportEntityType): Promise<void> {
    const token = getAuthToken();
    const headers: Record<string, string> = {};
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
    const lang = document.documentElement.lang || "en";
    headers["Accept-Language"] = lang;

    const resp = await fetch(
      `/api/v1/workspaces/${workspaceId}/export/csv/?entity_type=${encodeURIComponent(entityType)}`,
      { method: "GET", headers }
    );

    if (!resp.ok) {
      let message = `Export failed (HTTP ${resp.status})`;
      try {
        const body = (await resp.json()) as { error?: { message?: string } };
        message = body?.error?.message ?? message;
      } catch {
        // ignore — fall back to default message
      }
      throw new Error(message);
    }

    const blob = await resp.blob();
    const filename = `export_${entityType.toLowerCase()}.csv`;
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    link.click();
    URL.revokeObjectURL(link.href);
  },
};
