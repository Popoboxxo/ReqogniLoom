/**
 * ARCH-L1-001 ReactFrontend — CSV / ReqIF Import API client.
 *
 * leaf_id: COMP-RF-001 (NavigationShell — API layer)
 * req_id:  REQ-L0-013 (CSV-Bulk-Import),
 *          REQ-L2-AS-014 (CSV Bulk Import),
 *          REQ-L2-RF-016 (Frontend CSV import UI),
 *          REQ-147 (ReqIF 1.2 import, COMP-AS-008b)
 *
 * Wraps POST /api/v1/workspaces/{id}/import/csv/ and
 * POST /api/v1/workspaces/{id}/import/reqif/ endpoints.
 * Uses multipart/form-data for file upload.
 */

import { readCookie } from "./client";
import type { UUID } from "../types";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type EntityType = "Requirement" | "ArchitectureElement" | "TestCase";

export interface ImportRowError {
  row_number: number;
  field: string;
  message: string;
}

export interface ImportResult {
  success: boolean;
  imported_count: number;
  skipped_count: number;
  status: "ok" | "validation_error" | "rollback";
  errors: ImportRowError[];
}

// REQ-147: ReqIF 1.2 import.

export interface ReqifEntityError {
  identifier: string;
  message: string;
}

export interface ReqifEntityReport {
  created: number;
  updated: number;
  skipped: number;
  errors: ReqifEntityError[];
}

export interface ReqifImportResult {
  success: boolean;
  dry_run: boolean;
  needs: ReqifEntityReport;
  requirements: ReqifEntityReport;
  relations: ReqifEntityReport;
  warnings: string[];
}

// ---------------------------------------------------------------------------
// API
// ---------------------------------------------------------------------------

export const importApi = {
  /**
   * Upload a CSV file and import rows into the workspace.
   *
   * @param workspaceId - Target workspace UUID.
   * @param file - CSV file (RFC 4180, UTF-8).
   * @param entityType - Entity type to import.
   * @returns ImportResult with counts and per-row errors.
   */
  async importCsv(
    workspaceId: UUID,
    file: File,
    entityType: EntityType
  ): Promise<ImportResult> {
    // Auth flows via the httpOnly cookie (REQ-052); this POST additionally
    // carries the CSRF token from the csrftoken cookie.
    const headers: Record<string, string> = {};
    const lang = document.documentElement.lang || "en";
    headers["Accept-Language"] = lang;
    const csrf = readCookie("csrftoken");
    if (csrf) headers["X-CSRFToken"] = csrf;

    const formData = new FormData();
    formData.append("file", file);
    formData.append("entity_type", entityType);

    const resp = await fetch(
      `/api/v1/workspaces/${workspaceId}/import/csv/`,
      {
        method: "POST",
        headers,
        credentials: "same-origin",
        body: formData,
      }
    );

    let body: ImportResult | { error?: { message?: string } };
    try {
      body = await resp.json();
    } catch {
      body = { error: { message: `HTTP ${resp.status}` } };
    }

    if (!resp.ok) {
      const errMsg =
        (body as { error?: { message?: string } })?.error?.message ??
        `Import failed (HTTP ${resp.status})`;
      throw new Error(errMsg);
    }

    return body as ImportResult;
  },

  /**
   * Upload a ReqIF 1.2 file and import Needs/Requirements/TraceLinks into
   * the workspace (REQ-147).
   *
   * @param workspaceId - Target workspace UUID.
   * @param file - ReqIF 1.2 XML file (.reqif / .xml, UTF-8).
   * @param dryRun - When true, runs the full pipeline and rolls it back;
   *   the returned report reflects what a real import would do.
   * @returns ReqifImportResult with per-entity-kind counts and warnings.
   */
  async importReqif(
    workspaceId: UUID,
    file: File,
    dryRun = false
  ): Promise<ReqifImportResult> {
    // Auth flows via the httpOnly cookie (REQ-052); this POST additionally
    // carries the CSRF token from the csrftoken cookie.
    const headers: Record<string, string> = {};
    const lang = document.documentElement.lang || "en";
    headers["Accept-Language"] = lang;
    const csrf = readCookie("csrftoken");
    if (csrf) headers["X-CSRFToken"] = csrf;

    const formData = new FormData();
    formData.append("file", file);

    const query = dryRun ? "?dry_run=true" : "";
    const resp = await fetch(
      `/api/v1/workspaces/${workspaceId}/import/reqif/${query}`,
      {
        method: "POST",
        headers,
        credentials: "same-origin",
        body: formData,
      }
    );

    let body: ReqifImportResult | { error?: { message?: string } };
    try {
      body = await resp.json();
    } catch {
      body = { error: { message: `HTTP ${resp.status}` } };
    }

    if (!resp.ok) {
      const errMsg =
        (body as { error?: { message?: string } })?.error?.message ??
        `ReqIF import failed (HTTP ${resp.status})`;
      throw new Error(errMsg);
    }

    return body as ReqifImportResult;
  },
};
