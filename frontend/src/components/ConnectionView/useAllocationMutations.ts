/**
 * ARCH-L1-001 ReactFrontend — allocation write path (P3 Tasks 3.3/3.4).
 *
 * Both mutations invalidate the whole `allocation-view` cache namespace so
 * every renderer re-reads the same authoritative rows instead of patching
 * local copies (the backend owns N:1 replacement and tier recomputation).
 *
 * `allocate` uses the atomic bulk endpoint even for a single requirement: it
 * is the committed write path that replaces an existing `allocated-to` edge,
 * which makes it equally correct for re-allocation.
 */

import { useCallback } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { allocationViewApi } from "../../api/allocation-view";
import { allocationViewKeys } from "./useAllocationView";

export interface AllocationActions {
  allocate: (requirementId: string, elementId: string) => Promise<void>;
  deallocate: (allocationTraceLinkId: string) => Promise<void>;
}

export function useAllocationMutations(): AllocationActions {
  const queryClient = useQueryClient();

  const invalidate = useCallback(() => {
    void queryClient.invalidateQueries({
      queryKey: allocationViewKeys.all,
    });
  }, [queryClient]);

  const allocateMutation = useMutation({
    mutationFn: (variables: { requirementId: string; elementId: string }) =>
      allocationViewApi.bulkAllocate([
        {
          requirement_id: variables.requirementId,
          element_id: variables.elementId,
        },
      ]),
    onSuccess: invalidate,
  });

  const deallocateMutation = useMutation({
    mutationFn: (traceLinkId: string) =>
      allocationViewApi.deallocate(traceLinkId),
    onSuccess: invalidate,
  });

  const allocate = useCallback(
    async (requirementId: string, elementId: string) => {
      await allocateMutation.mutateAsync({ requirementId, elementId });
    },
    [allocateMutation]
  );

  const deallocate = useCallback(
    async (allocationTraceLinkId: string) => {
      await deallocateMutation.mutateAsync(allocationTraceLinkId);
    },
    [deallocateMutation]
  );

  return { allocate, deallocate };
}
