/**
 * ARCH-L1-001 ReactFrontend — WorkItem query hooks (Plan F F3-T9, #1374).
 *
 * One cache-key family for the document-scoped list, the resume read and the
 * item detail/transitions, so a write refreshes every panel that shows the
 * work state without each call site re-deriving invalidation rules.
 */

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";

import { workItemsApi } from "../api/workItems";
import type {
  WorkItemCreatePayload,
  WorkItemTransitionOptions,
  WorkItemUpdatePayload,
} from "../api/workItems";
import type {
  UUID,
  WorkItem,
  WorkItemResume,
  WorkItemTransitionResult,
  WorkItemTransitionsResponse,
} from "../types";

export const workItemKeys = {
  all: ["work-items"] as const,
  list: (workspaceId: UUID, documentId: UUID | undefined, includeDeleted: boolean) =>
    ["work-items", "list", workspaceId, documentId ?? "", includeDeleted] as const,
  detail: (id: UUID) => ["work-items", "detail", id] as const,
  transitions: (id: UUID) => ["work-items", "transitions", id] as const,
  resume: (workspaceId: UUID, documentId: UUID) =>
    ["work-items", "resume", workspaceId, documentId] as const,
};

/** Items of one document, ordered `(ordinal, id)` by the service (G2.1). */
export function useWorkItems(
  workspaceId: UUID | undefined,
  documentId: UUID | undefined,
  includeDeleted = false,
  enabled = true
): UseQueryResult<WorkItem[], Error> {
  return useQuery({
    queryKey: workItemKeys.list(workspaceId ?? "", documentId, includeDeleted),
    queryFn: () =>
      workItemsApi.listAll(
        workspaceId as UUID,
        documentId as UUID,
        includeDeleted
      ),
    enabled: enabled && !!workspaceId && !!documentId,
  });
}

/** One item. A soft-deleted item still resolves with `status=outdated`. */
export function useWorkItem(
  id: UUID | undefined
): UseQueryResult<WorkItem, Error> {
  return useQuery({
    queryKey: workItemKeys.detail(id ?? ""),
    queryFn: () => workItemsApi.get(id as UUID),
    enabled: !!id,
  });
}

/** Current workflow state + allowed moves for one item. */
export function useWorkItemTransitions(
  id: UUID | undefined
): UseQueryResult<WorkItemTransitionsResponse, Error> {
  return useQuery({
    queryKey: workItemKeys.transitions(id ?? ""),
    queryFn: () => workItemsApi.transitions(id as UUID),
    enabled: !!id,
  });
}

/** Newest checkpoint + every open item of a document (`work_item.resume`). */
export function useWorkItemResume(
  workspaceId: UUID | undefined,
  documentId: UUID | undefined,
  enabled = true
): UseQueryResult<WorkItemResume, Error> {
  return useQuery({
    queryKey: workItemKeys.resume(workspaceId ?? "", documentId ?? ""),
    queryFn: () =>
      workItemsApi.resume(workspaceId as UUID, documentId as UUID),
    enabled: enabled && !!workspaceId && !!documentId,
  });
}

function useInvalidateWorkItems(
  workspaceId: UUID | undefined,
  documentId: UUID | undefined,
  includeDeleted: boolean
): (id?: UUID) => void {
  const queryClient = useQueryClient();
  return (id?: UUID) => {
    if (workspaceId && documentId) {
      void queryClient.invalidateQueries({
        queryKey: workItemKeys.list(workspaceId, documentId, includeDeleted),
      });
      void queryClient.invalidateQueries({
        queryKey: workItemKeys.resume(workspaceId, documentId),
      });
    }
    if (id) {
      void queryClient.invalidateQueries({
        queryKey: workItemKeys.detail(id),
      });
      void queryClient.invalidateQueries({
        queryKey: workItemKeys.transitions(id),
      });
    }
  };
}

export interface CreateWorkItemVariables {
  payload: WorkItemCreatePayload;
}

export function useCreateWorkItem(
  workspaceId: UUID | undefined,
  documentId: UUID | undefined,
  includeDeleted = false
): UseMutationResult<WorkItem, Error, CreateWorkItemVariables> {
  const queryClient = useQueryClient();
  const invalidate = useInvalidateWorkItems(
    workspaceId,
    documentId,
    includeDeleted
  );
  return useMutation({
    mutationFn: ({ payload }) => workItemsApi.create(payload),
    onSuccess: (created) => {
      queryClient.setQueryData(workItemKeys.detail(created.id), created);
      invalidate(created.id);
    },
  });
}

export interface UpdateWorkItemVariables {
  id: UUID;
  payload: WorkItemUpdatePayload;
  expectedVersion?: number;
}

export function useUpdateWorkItem(
  workspaceId: UUID | undefined,
  documentId: UUID | undefined,
  includeDeleted = false
): UseMutationResult<WorkItem, Error, UpdateWorkItemVariables> {
  const queryClient = useQueryClient();
  const invalidate = useInvalidateWorkItems(
    workspaceId,
    documentId,
    includeDeleted
  );
  return useMutation({
    mutationFn: ({ id, payload, expectedVersion }) =>
      workItemsApi.update(id, payload, expectedVersion),
    onSuccess: (updated) => {
      queryClient.setQueryData(workItemKeys.detail(updated.id), updated);
      invalidate(updated.id);
    },
  });
}

export interface DeleteWorkItemVariables {
  id: UUID;
  changeReason?: string;
}

export function useDeleteWorkItem(
  workspaceId: UUID | undefined,
  documentId: UUID | undefined,
  includeDeleted = false
): UseMutationResult<void, Error, DeleteWorkItemVariables> {
  const invalidate = useInvalidateWorkItems(
    workspaceId,
    documentId,
    includeDeleted
  );
  return useMutation({
    mutationFn: ({ id, changeReason }) =>
      workItemsApi.delete(id, changeReason),
    onSuccess: (_data, { id }) => invalidate(id),
  });
}

export function useReactivateWorkItem(
  workspaceId: UUID | undefined,
  documentId: UUID | undefined,
  includeDeleted = false
): UseMutationResult<{ work_item: WorkItem }, Error, UUID> {
  const queryClient = useQueryClient();
  const invalidate = useInvalidateWorkItems(
    workspaceId,
    documentId,
    includeDeleted
  );
  return useMutation({
    mutationFn: (id: UUID) => workItemsApi.reactivate(id),
    onSuccess: (response) => {
      queryClient.setQueryData(
        workItemKeys.detail(response.work_item.id),
        response.work_item
      );
      invalidate(response.work_item.id);
    },
  });
}

export interface TransitionWorkItemVariables {
  id: UUID;
  targetState: string;
  options?: WorkItemTransitionOptions;
}

export function useTransitionWorkItem(
  workspaceId: UUID | undefined,
  documentId: UUID | undefined,
  includeDeleted = false
): UseMutationResult<
  WorkItemTransitionResult,
  Error,
  TransitionWorkItemVariables
> {
  const queryClient = useQueryClient();
  const invalidate = useInvalidateWorkItems(
    workspaceId,
    documentId,
    includeDeleted
  );
  return useMutation({
    mutationFn: ({ id, targetState, options }) =>
      workItemsApi.transition(id, targetState, options),
    onSuccess: (result) => {
      queryClient.setQueryData(
        workItemKeys.detail(result.work_item.id),
        result.work_item
      );
      invalidate(result.work_item.id);
    },
  });
}
