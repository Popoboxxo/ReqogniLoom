/**
 * ARCH-L1-001 ReactFrontend — Multi-user management API (tenant-admin scope).
 *
 * leaf_id: COMP-RF-001 (NavigationShell — Settings / User Management scope)
 * req_id:  multi-user management design spec
 *
 * Thin wrapper around the tenant-admin-guarded user lifecycle endpoints
 * (backend/rest_api/user_management_views.py):
 *   GET    /api/v1/users/                       — list users
 *   POST   /api/v1/users/                       — create user
 *   POST   /api/v1/users/{id}/activate/         — activate
 *   POST   /api/v1/users/{id}/deactivate/       — deactivate (last-admin protected)
 *   POST   /api/v1/users/{id}/tenant-admin/     — grant tenant-admin
 *   DELETE /api/v1/users/{id}/tenant-admin/     — revoke tenant-admin (last-admin protected)
 */

import { apiClient } from "./client";
import type { UUID } from "../types";

export interface ManagedUser {
  id: UUID;
  username: string;
  email: string;
  is_active: boolean;
  is_tenant_admin: boolean;
}

export interface CreateUserPayload {
  username: string;
  email: string;
  password: string;
}

export const usersApi = {
  /** List all users of the caller's tenant. Requires tenant-admin. */
  list: async (): Promise<ManagedUser[]> => {
    return apiClient.get<ManagedUser[]>("/users/");
  },

  /** Create a new user in the caller's tenant. Requires tenant-admin. */
  create: async (payload: CreateUserPayload): Promise<ManagedUser> => {
    return apiClient.post<ManagedUser>("/users/", payload);
  },

  /** Activate a deactivated user. Requires tenant-admin. */
  activate: async (id: UUID): Promise<ManagedUser> => {
    return apiClient.post<ManagedUser>(`/users/${id}/activate/`, {});
  },

  /**
   * Deactivate a user. Requires tenant-admin; rejected with a `LAST_ADMIN`
   * 409 if this would leave the tenant without an active admin.
   */
  deactivate: async (id: UUID): Promise<ManagedUser> => {
    return apiClient.post<ManagedUser>(`/users/${id}/deactivate/`, {});
  },

  /** Grant tenant-admin to a user. Requires tenant-admin. */
  grantTenantAdmin: async (id: UUID): Promise<void> => {
    return apiClient.post(`/users/${id}/tenant-admin/`, {});
  },

  /**
   * Revoke tenant-admin from a user. Requires tenant-admin; rejected with a
   * `LAST_ADMIN` 409 if this would leave the tenant without an active admin.
   */
  revokeTenantAdmin: async (id: UUID): Promise<void> => {
    return apiClient.delete(`/users/${id}/tenant-admin/`);
  },
};
