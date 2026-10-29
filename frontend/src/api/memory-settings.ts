/**
 * ARCH-L1-001 ReactFrontend — AI Long-Term Memory settings API (Spec
 * 2026-08-24, Task 11; Plan A T-A1-3/T-A1-7 slot policy).
 *
 * Wraps:
 *   GET/PUT /api/v1/workspaces/{workspaceId}/memory-settings/  — any workspace
 *     member may GET; editor+ may PUT `enabled`, admin is required for the
 *     policy fields (`disabled_slots`, `allow_user_opt_out`).
 *
 * A workspace with no settings row yet returns `{ enabled: true }` (the
 * memory feature defaults ON — see backend `WorkspaceMemorySettingsView`
 * docstring), so callers never have to special-case a missing row.
 *
 * Plan A T-A1-3 made the payload additive (backend
 * `WorkspaceMemorySettingsResponseSerializer`):
 *
 *   `disabled_slots`          stored WORKSPACE level, the editable source of
 *                             truth — exactly what a PUT writes.
 *   `allow_user_opt_out`      stored WORKSPACE level (the key's only level).
 *   `effective_disabled_slots` merged value the injection policy applies
 *                             (global ∪ workspace ∪ caller's user level).
 *                             Read-only, display only — never written back.
 *   `available_slots`         derived slot catalogue, sorted by name; a
 *                             `hard_off` slot can never receive memory, so the
 *                             UI renders it disabled instead of offering a
 *                             value the writer rejects.
 */

import { apiClient } from "./client";
import type { UUID } from "../types";

/** One entry of `available_slots` (backend `WorkspaceMemorySlotSerializer`). */
export interface MemorySlot {
  /** Slot name, e.g. `testcase_derive` or `interview.chat_turn`. */
  name: string;
  /** `true` = the slot can never receive memory (HARD_OFF, Plan A T-A1-1). */
  hard_off: boolean;
}

export interface MemorySettings {
  enabled: boolean;
  /** Stored workspace level — the value a PUT round-trips. */
  disabled_slots: string[];
  /** Stored workspace level. */
  allow_user_opt_out: boolean;
  /** Merged value the injection policy applies (read-only). */
  effective_disabled_slots: string[];
  /** Derived slot catalogue, sorted by name. */
  available_slots: MemorySlot[];
}

/**
 * Body of `PUT …/memory-settings/` — partial (backend
 * `WorkspaceMemorySettingsWriteSerializer`): an omitted field is left
 * unchanged, `null` resets that level to the registry default.
 */
export interface MemorySettingsUpdate {
  enabled?: boolean;
  disabled_slots?: string[] | null;
  allow_user_opt_out?: boolean | null;
}

export const memorySettingsApi = {
  /** GET /api/v1/workspaces/{workspaceId}/memory-settings/ — any workspace member. */
  async get(workspaceId: UUID): Promise<MemorySettings> {
    return apiClient.get<MemorySettings>(`/workspaces/${workspaceId}/memory-settings/`);
  },

  /**
   * PUT /api/v1/workspaces/{workspaceId}/memory-settings/ — editor
   * (`enabled`) or admin (policy fields). Only the supplied fields change.
   */
  async update(workspaceId: UUID, update: MemorySettingsUpdate): Promise<MemorySettings> {
    return apiClient.put<MemorySettings>(
      `/workspaces/${workspaceId}/memory-settings/`,
      update
    );
  },
};
