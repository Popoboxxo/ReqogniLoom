/**
 * ARCH-L1-001 ReactFrontend — deployed build/version metadata API.
 *
 * leaf_id: COMP-RF-001 (NavigationShell — sidebar build indicator)
 *
 * Wraps the public endpoint:
 *   GET /api/v1/version/ — app version and truncated (7-char) commit SHA.
 *
 * #74: the full commit SHA and build timestamp are intentionally NOT part of
 * this public, unauthenticated response (they'd let an attacker pinpoint the
 * exact deployed revision/build time) — do not add them back here.
 */

import { apiClient } from "./client";

export interface VersionInfo {
  /** Human-facing release version from the root VERSION file (e.g. "0.2.0"). */
  app_version: string;
  commit_short: string;
}

export const versionApi = {
  /** GET /api/v1/version/ — public, no auth required. */
  async getVersion(): Promise<VersionInfo> {
    return apiClient.get<VersionInfo>("/version/");
  },
};
