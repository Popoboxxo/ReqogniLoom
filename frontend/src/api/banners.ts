/**
 * ARCH-L1-001 ReactFrontend — System & Workspace Banners API.
 *
 * leaf_id: COMP-RF-001 (NavigationShell scope)
 *
 * Wraps:
 *   GET/PUT /api/v1/admin/banners/global/          — System-Admin only
 *   GET/PUT /api/v1/workspaces/{id}/banner/         — Workspace-Admin or System-Admin
 *   GET     /api/v1/public/banners/login/           — unauthenticated
 *
 * A GET returning no configured banner resolves to `null` here (the
 * backend returns 204 No Content, which `apiClient.get` treats as an
 * empty successful response — this wrapper normalises that to `null` so
 * callers never have to special-case an empty object).
 */

import { apiClient } from "./client";
import type { UUID } from "../types";

export type BannerLevel = "neutral" | "info" | "warning" | "critical";

export interface Banner {
  id: UUID;
  scope: "global" | "workspace";
  workspace_id: UUID | null;
  level: BannerLevel;
  message: string;
  enabled: boolean;
  dismissible: boolean;
  show_on_login_page: boolean;
  updated_at: string | null;
}

export interface BannerWritePayload {
  level: BannerLevel;
  message: string;
  enabled: boolean;
  dismissible: boolean;
}

export interface GlobalBannerWritePayload extends BannerWritePayload {
  show_on_login_page: boolean;
}

export interface LoginBanner {
  level: BannerLevel;
  message: string;
  dismissible: boolean;
}

export const bannersApi = {
  /** GET /api/v1/admin/banners/global/ — System-Admin only. */
  async getGlobal(): Promise<Banner | null> {
    const data = await apiClient.get<Banner | null>("/admin/banners/global/");
    return data ?? null;
  },

  /** PUT /api/v1/admin/banners/global/ — System-Admin only. */
  async putGlobal(payload: GlobalBannerWritePayload): Promise<Banner> {
    return apiClient.put<Banner>("/admin/banners/global/", payload);
  },

  /** GET /api/v1/workspaces/{workspaceId}/banner/ — any authenticated member. */
  async getWorkspace(workspaceId: UUID): Promise<Banner | null> {
    const data = await apiClient.get<Banner | null>(
      `/workspaces/${workspaceId}/banner/`
    );
    return data ?? null;
  },

  /** PUT /api/v1/workspaces/{workspaceId}/banner/ — Workspace-Admin or System-Admin. */
  async putWorkspace(workspaceId: UUID, payload: BannerWritePayload): Promise<Banner> {
    return apiClient.put<Banner>(`/workspaces/${workspaceId}/banner/`, payload);
  },

  /** GET /api/v1/public/banners/login/ — unauthenticated, used pre-login. */
  async getLoginBanner(): Promise<LoginBanner | null> {
    const data = await apiClient.get<LoginBanner | null>("/public/banners/login/");
    return data ?? null;
  },
};
