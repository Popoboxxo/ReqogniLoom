/**
 * ARCH-L1-001 ReactFrontend — Requirements query/mutation hooks.
 *
 * leaf_id: COMP-RF-003 (RequirementEditors)
 * req_id:  REQ-L3-RF003-001 (Inline-Editing),
 *          REQ-L3-RF003-004 (Editor-Performance < 500ms)
 *
 * TanStack Query wrapper around requirementsApi + tracelinksApi, replacing
 * the hand-rolled fetch/loading/error state in useRequirementData.
 */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { requirementsApi } from "../api/requirements";
import { tracelinksApi } from "../api/tracelinks";
import type { Requirement, TraceLink, UUID } from "../types";

export const requirementKeys = {
  all: ["requirements"] as const,
  lists: () => [...requirementKeys.all, "list"] as const,
  list: (workspaceId: UUID) => [...requirementKeys.lists(), workspaceId] as const,
  details: () => [...requirementKeys.all, "detail"] as const,
  detail: (id: UUID) => [...requirementKeys.details(), id] as const,
};

export function useRequirementsList(workspaceId: UUID | undefined) {
  return useQuery({
    queryKey: requirementKeys.list(workspaceId ?? ""),
    queryFn: () => requirementsApi.listAll(workspaceId as UUID),
    enabled: !!workspaceId,
  });
}

export interface RequirementDetail {
  requirement: Requirement;
  upstreamLinks: TraceLink[];
  downstreamLinks: TraceLink[];
  linkedTitles: Record<string, string>;
}

async function fetchRequirementDetail(
  workspaceId: UUID,
  id: UUID
): Promise<RequirementDetail> {
  const requirement = await requirementsApi.get(id);
  const links = await tracelinksApi.listForArtifact(workspaceId, requirement.id);
  const upstreamLinks = links.results.filter((l) => l.target_id === requirement.id);
  const downstreamLinks = links.results.filter((l) => l.source_id === requirement.id);

  const linkedIds = new Set<string>();
  upstreamLinks.forEach((l) => linkedIds.add(l.source_id));
  downstreamLinks.forEach((l) => linkedIds.add(l.target_id));

  const linkedTitles: Record<string, string> = {};
  await Promise.all(
    Array.from(linkedIds).map(async (linkedId) => {
      try {
        const linkedReq = await requirementsApi.get(linkedId);
        linkedTitles[linkedId] = linkedReq.title || "(untitled)";
      } catch {
        linkedTitles[linkedId] = `(${linkedId.slice(0, 8)})`;
      }
    })
  );

  return { requirement, upstreamLinks, downstreamLinks, linkedTitles };
}

export function useRequirementDetail(
  workspaceId: UUID | undefined,
  id: UUID | undefined
) {
  return useQuery({
    queryKey: requirementKeys.detail(id ?? ""),
    queryFn: () => fetchRequirementDetail(workspaceId as UUID, id as UUID),
    enabled: !!workspaceId && !!id,
  });
}

export function useCreateRequirement() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: Parameters<typeof requirementsApi.create>[0]) =>
      requirementsApi.create(data),
    onSuccess: (created) => {
      void queryClient.invalidateQueries({
        queryKey: requirementKeys.list(created.workspace_id),
      });
    },
  });
}

export function useUpdateRequirement() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      data,
    }: {
      id: UUID;
      data: Parameters<typeof requirementsApi.update>[1];
    }) => requirementsApi.update(id, data),
    onSuccess: (updated) => {
      void queryClient.invalidateQueries({
        queryKey: requirementKeys.detail(updated.id),
      });
      void queryClient.invalidateQueries({
        queryKey: requirementKeys.list(updated.workspace_id),
      });
    },
  });
}

export function useDeleteRequirement() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id }: { id: UUID; workspaceId: UUID }) =>
      requirementsApi.delete(id),
    onSuccess: (_result, variables) => {
      void queryClient.invalidateQueries({
        queryKey: requirementKeys.list(variables.workspaceId),
      });
      queryClient.removeQueries({ queryKey: requirementKeys.detail(variables.id) });
    },
  });
}
