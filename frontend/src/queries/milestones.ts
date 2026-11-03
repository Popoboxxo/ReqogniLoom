/**
 * ARCH-L1-001 ReactFrontend — Milestone query/mutation hooks (Plan B B6-T2).
 *
 * One list key per workspace; every mutation invalidates the milestone
 * namespace so the list (and the selected row's version) re-reads after a
 * write. The ETag/`expected_version` guard travels with the mutation
 * variables — the component forwards the version it rendered, never a
 * locally incremented counter.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  milestonesApi,
  type Milestone,
  type MilestoneCreatePayload,
  type MilestoneUpdatePayload,
} from "../api/milestones";
import type { UUID } from "../types";

export const milestoneKeys = {
  all: ["milestones"] as const,
  lists: () => [...milestoneKeys.all, "list"] as const,
  list: (workspaceId: UUID | undefined) =>
    [...milestoneKeys.lists(), workspaceId ?? ""] as const,
};

export function useMilestonesList(workspaceId: UUID | undefined) {
  return useQuery<Milestone[]>({
    queryKey: milestoneKeys.list(workspaceId),
    queryFn: async (): Promise<Milestone[]> => {
      const response = await milestonesApi.list({
        workspace_id: workspaceId as UUID,
      });
      return response.results;
    },
    enabled: Boolean(workspaceId),
  });
}

export function useCreateMilestone() {
  const queryClient = useQueryClient();
  return useMutation<Milestone, unknown, MilestoneCreatePayload>({
    mutationFn: (payload) => milestonesApi.create(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: milestoneKeys.all });
    },
  });
}

export function useUpdateMilestone() {
  const queryClient = useQueryClient();
  return useMutation<
    Milestone,
    unknown,
    { id: UUID; payload: MilestoneUpdatePayload; expectedVersion?: number }
  >({
    mutationFn: ({ id, payload, expectedVersion }) =>
      milestonesApi.update(id, payload, expectedVersion),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: milestoneKeys.all });
    },
  });
}

export function useBindMilestoneBaseline() {
  const queryClient = useQueryClient();
  return useMutation<
    Milestone,
    unknown,
    { id: UUID; baselineId: UUID; expectedVersion?: number }
  >({
    mutationFn: ({ id, baselineId, expectedVersion }) =>
      milestonesApi.bindBaseline(id, baselineId, expectedVersion),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: milestoneKeys.all });
    },
  });
}

export function useRecordMilestoneAudit() {
  const queryClient = useQueryClient();
  return useMutation<Milestone, unknown, { id: UUID; expectedVersion?: number }>({
    mutationFn: ({ id, expectedVersion }) =>
      milestonesApi.recordAudit(id, expectedVersion),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: milestoneKeys.all });
    },
  });
}
