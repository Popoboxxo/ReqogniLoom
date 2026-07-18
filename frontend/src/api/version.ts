/**
 * ARCH-L1-001 ReactFrontend — deployed build/version metadata API.
 *
 * leaf_id: COMP-RF-001 (NavigationShell — sidebar build indicator)
 *
 * Wraps the public endpoint:
 *   GET /api/v1/version/ — commit SHA (full + short) and build time.
 */

import { apiClient } from "./client";

export interface VersionInfo {
  /** Human-facing release version from the root VERSION file (e.g. "0.2.0"). */
  app_version: string;
  commit: string;
  commit_short: string;
  build_time: string | null;
}

export const versionApi = {
  /** GET /api/v1/version/ — public, no auth required. */
  async getVersion(): Promise<VersionInfo> {
    return apiClient.get<VersionInfo>("/version/");
  },
};
