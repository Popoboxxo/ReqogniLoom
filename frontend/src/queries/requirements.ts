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
import { resolveArtifactRefs } from "../api/artifactRefs";
import type { Requirement, TraceLink, UUID } from "../types";

export const requirementKeys = {
  all: ["requirements"] as const,
  lists: () => [...requirementKeys.all, "list"] as const,
  list: (workspaceId: UUID) => [...requirementKeys.lists(), workspaceId] as const,
  details: () => [...requirementKeys.all, "detail"] as const,
  detail: (id: UUID) => [...requirementKeys.details(), id] as const,
};

/**
 * GH-443: `includeDeleted` opts into soft-deleted (`status === "outdated"`)
 * requirements. It is part of the query key — the two variants are different
 * result sets and must not share a cache entry — but appended *after*
 * `requirementKeys.list(workspaceId)`, so the existing
 * `invalidateQueries({ queryKey: requirementKeys.list(ws) })` calls still match
 * both by prefix.
 */
export function useRequirementsList(
  workspaceId: UUID | undefined,
  includeDeleted = false,
) {
  return useQuery({
    queryKey: [...requirementKeys.list(workspaceId ?? ""), { includeDeleted }],
    queryFn: () =>
      requirementsApi.listAll(workspaceId as UUID, { includeDeleted }),
    enabled: !!workspaceId,
  });
}

export interface RequirementDetail {
  requirement: Requirement;
  upstreamLinks: TraceLink[];
  downstreamLinks: TraceLink[];
  linkedTitles: Record<string, string>;
  linkedRoutes: Record<string, string>;
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

  // Linked artifacts are not always Requirements — satisfies/verifies/implements
  // links can point at ArchitectureElements or TestCases too (REQ-L1-003).
  //
  // #414: these ids are TraceLink endpoints, i.e. **Artifact** ids, while the
  // routes handed to the editor take domain-entity ids. resolveArtifactRefs
  // bridges the two spaces in a single batched request; resolving them per id
  // (and treating an Artifact id as an entity id) is what produced the 404s.
  const linkedTitles: Record<string, string> = {};
  const linkedRoutes: Record<string, string> = {};
  const linkedRefs = await resolveArtifactRefs(Array.from(linkedIds));
  for (const [linkedId, ref] of Object.entries(linkedRefs)) {
    linkedTitles[linkedId] = ref.title;
    linkedRoutes[linkedId] = ref.route;
  }

  return { requirement, upstreamLinks, downstreamLinks, linkedTitles, linkedRoutes };
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
    mutationFn: ({ id, changeReason }: { id: UUID; workspaceId: UUID; changeReason?: string }) =>
      requirementsApi.delete(id, changeReason),
    onSuccess: (_result, variables) => {
      void queryClient.invalidateQueries({
        queryKey: requirementKeys.list(variables.workspaceId),
      });
      // GH-443: the detail cache entry is *removed*, not invalidated. The
      // requirement still resolves after the soft-delete, so an invalidate
      // would refetch it and leave a deleted item rendered in the detail pane.
      queryClient.removeQueries({ queryKey: requirementKeys.detail(variables.id) });
    },
  });
}

/** GH-443: undo a soft-delete and refresh both list variants + the detail. */
export function useReactivateRequirement() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id }: { id: UUID; workspaceId: UUID }) =>
      requirementsApi.reactivate(id),
    onSuccess: (_result, variables) => {
      void queryClient.invalidateQueries({
        queryKey: requirementKeys.list(variables.workspaceId),
      });
      void queryClient.invalidateQueries({
        queryKey: requirementKeys.detail(variables.id),
      });
    },
  });
}
