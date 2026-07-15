/**
 * ARCH-L1-001 ReactFrontend — CSV/ReqIF Export API client.
 *
 * leaf_id: COMP-RF-001 (NavigationShell — API layer)
 * req_id:  REQ-L3-EXP-002 (CSV export, COMP-AS-008),
 *          C7 (frontend-feedback Cluster C — Import/Export MVP),
 *          REQ-146 (ReqIF 1.2 export, COMP-AS-008)
 *
 * Wraps GET /api/v1/workspaces/{id}/export/csv/ and
 * GET /api/v1/workspaces/{id}/export/reqif/ and triggers a browser download
 * of the returned file.
 */

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
    // Auth flows via the httpOnly cookie (REQ-052) — send credentials, no header.
    const headers: Record<string, string> = {};
    const lang = document.documentElement.lang || "en";
    headers["Accept-Language"] = lang;

    const resp = await fetch(
      `/api/v1/workspaces/${workspaceId}/export/csv/?entity_type=${encodeURIComponent(entityType)}`,
      { method: "GET", headers, credentials: "same-origin" }
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

  /**
   * Fetch a ReqIF 1.2 export for the given workspace (StakeholderNeeds,
   * Requirements, TraceLinks) and trigger a browser download (REQ-146).
   *
   * @param workspaceId - Source workspace UUID.
   */
  async downloadReqif(workspaceId: UUID): Promise<void> {
    // Auth flows via the httpOnly cookie (REQ-052) — send credentials, no header.
    const headers: Record<string, string> = {};
    const lang = document.documentElement.lang || "en";
    headers["Accept-Language"] = lang;

    const resp = await fetch(`/api/v1/workspaces/${workspaceId}/export/reqif/`, {
      method: "GET",
      headers,
      credentials: "same-origin",
    });

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
    // Prefer the server-provided filename (Content-Disposition:
    // attachment; filename="<workspace-slug>.reqif") but fall back to a
    // generic name if the header is missing or malformed.
    let filename = "export.reqif";
    const disposition = resp.headers.get("Content-Disposition");
    if (disposition) {
      const match = /filename="?([^";]+)"?/i.exec(disposition);
      if (match?.[1]) {
        filename = match[1];
      }
    }
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    link.click();
    URL.revokeObjectURL(link.href);
  },
};
