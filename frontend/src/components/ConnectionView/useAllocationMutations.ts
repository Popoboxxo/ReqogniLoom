/**
 * ARCH-L1-001 ReactFrontend — allocation write path (P3 Tasks 3.3/3.4, P3.5).
 *
 * Every mutation invalidates the whole `allocation-view` cache namespace so
 * all renderers re-read the same authoritative rows instead of patching local
 * copies (the backend owns N:1 replacement and tier recomputation).
 *
 * `allocateBulk` is the assistant's write path: one request for the whole
 * selection, all-or-nothing on the server. `allocate` is the single-item
 * convenience wrapper used by drag/drop and the pickers.
 */

import { useCallback } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import {
  allocationViewApi,
  type BulkAllocationItem,
  type BulkAllocationResult,
} from "../../api/allocation-view";
import { allocationViewKeys } from "./useAllocationView";

export interface AllocationActions {
  allocate: (requirementId: string, elementId: string) => Promise<void>;
  allocateBulk: (
    items: BulkAllocationItem[]
  ) => Promise<BulkAllocationResult>;
  deallocate: (allocationTraceLinkId: string) => Promise<void>;
}

export function useAllocationMutations(): AllocationActions {
  const queryClient = useQueryClient();

  const invalidate = useCallback(() => {
    void queryClient.invalidateQueries({
      queryKey: allocationViewKeys.all,
    });
  }, [queryClient]);

  const bulkMutation = useMutation({
    mutationFn: (items: BulkAllocationItem[]) =>
      allocationViewApi.bulkAllocate(items),
    onSuccess: invalidate,
  });

  const deallocateMutation = useMutation({
    mutationFn: (traceLinkId: string) =>
      allocationViewApi.deallocate(traceLinkId),
    onSuccess: invalidate,
  });

  const allocateBulk = useCallback(
    async (items: BulkAllocationItem[]) => {
      return bulkMutation.mutateAsync(items);
    },
    [bulkMutation]
  );

  const allocate = useCallback(
    async (requirementId: string, elementId: string) => {
      await allocateBulk([
        { requirement_id: requirementId, element_id: elementId },
      ]);
    },
    [allocateBulk]
  );

  const deallocate = useCallback(
    async (allocationTraceLinkId: string) => {
      await deallocateMutation.mutateAsync(allocationTraceLinkId);
    },
    [deallocateMutation]
  );

  return { allocate, allocateBulk, deallocate };
}
