/**
 * ARCH-L1-001 ReactFrontend — Document query hooks (Plan F F2-T8, ADR-026).
 *
 * One cache key family for the list + detail reads and the four write paths,
 * so a successful mutation refreshes both panels without each call site
 * re-deriving invalidation rules.
 */

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";

import { documentsApi } from "../api/documents";
import type {
  DocumentCreatePayload,
  DocumentTransitionOptions,
  DocumentTransitionResult,
  DocumentTransitionsResponse,
  DocumentUpdatePayload,
} from "../api/documents";
import type { Document, DocumentReading, UUID } from "../types";

export const documentKeys = {
  all: ["documents"] as const,
  list: (workspaceId: UUID, includeDeleted: boolean) =>
    ["documents", "list", workspaceId, includeDeleted] as const,
  detail: (id: UUID) => ["documents", "detail", id] as const,
  reading: (workspaceId: UUID | undefined, id: UUID | undefined) =>
    ["documents", "reading", workspaceId ?? "", id ?? ""] as const,
  transitions: (id: UUID) => ["documents", "transitions", id] as const,
};

/** Workspace document list, soft-deleted rows only when requested (G1.5 V4). */
export function useDocuments(
  workspaceId: UUID | undefined,
  includeDeleted = false,
  enabled = true
): UseQueryResult<Document[], Error> {
  return useQuery({
    queryKey: documentKeys.list(workspaceId ?? "", includeDeleted),
    queryFn: () => documentsApi.listAll(workspaceId as UUID, includeDeleted),
    enabled: enabled && !!workspaceId,
  });
}

/** One document. A soft-deleted document still resolves with `status=outdated`. */
export function useDocument(id: UUID | undefined): UseQueryResult<Document, Error> {
  return useQuery({
    queryKey: documentKeys.detail(id ?? ""),
    queryFn: () => documentsApi.get(id as UUID),
    enabled: !!id,
  });
}

/**
 * The chaptered reading object of one document (R4, plan
 * 2026-11-15-document-view-on-document.md).
 *
 * `staleTime: 0` is deliberate: the surface shows the document's current
 * state, never a cache snapshot. `workspaceId` only participates in the cache
 * key (the endpoint itself is workspace-agnostic), so switching workspace can
 * never serve another workspace's reading object.
 */
export function useDocumentReading(
  documentId: UUID | undefined,
  workspaceId?: UUID
): UseQueryResult<DocumentReading, Error> {
  return useQuery({
    queryKey: documentKeys.reading(workspaceId, documentId),
    queryFn: () => documentsApi.readingView(documentId as UUID),
    enabled: !!documentId,
    staleTime: 0,
  });
}

/** Current workflow state + allowed transitions for one document. */
export function useDocumentTransitions(
  id: UUID | undefined
): UseQueryResult<DocumentTransitionsResponse, Error> {
  return useQuery({
    queryKey: documentKeys.transitions(id ?? ""),
    queryFn: () => documentsApi.transitions(id as UUID),
    enabled: !!id,
  });
}

export interface CreateDocumentVariables {
  payload: DocumentCreatePayload;
}

export function useCreateDocument(
  workspaceId: UUID | undefined,
  includeDeleted = false
): UseMutationResult<Document, Error, CreateDocumentVariables> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ payload }) => documentsApi.create(payload),
    onSuccess: (created) => {
      queryClient.setQueryData(documentKeys.detail(created.id), created);
      if (workspaceId) {
        void queryClient.invalidateQueries({
          queryKey: documentKeys.list(workspaceId, includeDeleted),
        });
      }
    },
  });
}

export interface UpdateDocumentVariables {
  id: UUID;
  payload: DocumentUpdatePayload;
  expectedVersion?: number;
}

export function useUpdateDocument(
  workspaceId: UUID | undefined,
  includeDeleted = false
): UseMutationResult<Document, Error, UpdateDocumentVariables> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload, expectedVersion }) =>
      documentsApi.update(id, payload, expectedVersion),
    onSuccess: (updated) => {
      queryClient.setQueryData(documentKeys.detail(updated.id), updated);
      if (workspaceId) {
        void queryClient.invalidateQueries({
          queryKey: documentKeys.list(workspaceId, includeDeleted),
        });
      }
    },
  });
}

export interface DeleteDocumentVariables {
  id: UUID;
  changeReason?: string;
}

export function useDeleteDocument(
  workspaceId: UUID | undefined,
  includeDeleted = false
): UseMutationResult<void, Error, DeleteDocumentVariables> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, changeReason }) =>
      documentsApi.delete(id, changeReason),
    onSuccess: (_data, { id }) => {
      void queryClient.invalidateQueries({
        queryKey: documentKeys.detail(id),
      });
      if (workspaceId) {
        void queryClient.invalidateQueries({
          queryKey: documentKeys.list(workspaceId, includeDeleted),
        });
      }
    },
  });
}

export function useReactivateDocument(
  workspaceId: UUID | undefined,
  includeDeleted = false
): UseMutationResult<{ document: Document }, Error, UUID> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: UUID) => documentsApi.reactivate(id),
    onSuccess: (response) => {
      queryClient.setQueryData(
        documentKeys.detail(response.document.id),
        response.document
      );
      if (workspaceId) {
        void queryClient.invalidateQueries({
          queryKey: documentKeys.list(workspaceId, includeDeleted),
        });
      }
    },
  });
}

export interface TransitionDocumentVariables {
  id: UUID;
  targetState: string;
  options?: DocumentTransitionOptions;
}

export function useTransitionDocument(
  workspaceId: UUID | undefined,
  includeDeleted = false
): UseMutationResult<
  DocumentTransitionResult,
  Error,
  TransitionDocumentVariables
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, targetState, options }) =>
      documentsApi.transition(id, targetState, options),
    onSuccess: (result) => {
      queryClient.setQueryData(
        documentKeys.detail(result.document.id),
        result.document
      );
      void queryClient.invalidateQueries({
        queryKey: documentKeys.transitions(result.document.id),
      });
      if (workspaceId) {
        void queryClient.invalidateQueries({
          queryKey: documentKeys.list(workspaceId, includeDeleted),
        });
      }
    },
  });
}
