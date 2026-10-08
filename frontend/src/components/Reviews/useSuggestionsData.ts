/**
 * ARCH-L1-001 ReactFrontend — Suggestions inbox data hook (ADR-019 / #1155).
 *
 * leaf_id: COMP-RF-SUG-001 (SuggestionsInbox)
 * req_id:  ADR-019 (generischer Vorschlags-Lebenszyklus, WP6),
 *          #1155 Aspekt 2
 *
 * TanStack Query data-fetching for the persisted suggestion inbox: the open
 * suggestions of the active workspace plus the accept/reject mutations. The
 * hook is mounted only while the ReviewsView "suggestions" mode is active, so
 * the query costs nothing in the historical review/proposals queues.
 *
 * Accept/reject both invalidate the list on success so a decided suggestion
 * drops out of the inbox without a manual refresh (the backend only lists
 * `open` rows for the default filter).
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  acceptSuggestion,
  listSuggestions,
  rejectSuggestion,
  type Suggestion,
  type SuggestionKind,
  type SuggestionStatus,
} from "../../api/suggestions";
import { useWorkspace } from "../../context/WorkspaceContext";
import { extractErrorMessage } from "../../api/client";

export const suggestionKeys = {
  all: ["suggestions"] as const,
  // `kind` is part of the key: the server filters on it, so two consumers with
  // different kinds must not share one cache entry (FE review round 2, F1).
  // `kind ?? null` keeps "no kind filter" a distinct, stable key part.
  list: (
    workspaceId: string,
    status: SuggestionStatus,
    kind?: SuggestionKind,
  ) => ["suggestions", "list", workspaceId, status, kind ?? null] as const,
};

export interface UseSuggestionsDataParams {
  /** Status filter; defaults to the inbox's "open" rows. */
  status?: SuggestionStatus;
  /** Optional kind filter (all kinds when omitted). */
  kind?: SuggestionKind;
}

export interface SuggestionsData {
  suggestions: Suggestion[];
  isLoading: boolean;
  error: string | null;
  /** Accept by id; resolves to the decided suggestion. */
  accept: (id: string) => Promise<Suggestion>;
  /** Reject by id with an optional reason. */
  reject: (id: string, reason?: string) => Promise<Suggestion>;
  /** True while an accept/reject request is in flight. */
  isActing: boolean;
}

export function useSuggestionsData(
  params: UseSuggestionsDataParams = {},
): SuggestionsData {
  const { status = "open", kind } = params;
  const { activeWorkspace } = useWorkspace();
  const workspaceId = activeWorkspace?.id;
  const queryClient = useQueryClient();

  const listQuery = useQuery({
    queryKey: suggestionKeys.list(workspaceId ?? "", status, kind),
    queryFn: () =>
      listSuggestions({ workspaceId: workspaceId as string, status, kind }),
    enabled: !!workspaceId,
  });

  const invalidate = async (): Promise<void> => {
    if (!workspaceId) return;
    await queryClient.invalidateQueries({
      queryKey: suggestionKeys.list(workspaceId, status, kind),
    });
  };

  const acceptMutation = useMutation({
    mutationFn: (id: string) => acceptSuggestion(id),
    onSuccess: invalidate,
  });
  const rejectMutation = useMutation({
    mutationFn: ({ id, reason }: { id: string; reason?: string }) =>
      rejectSuggestion(id, reason),
    onSuccess: invalidate,
  });

  return {
    suggestions: listQuery.data?.results ?? [],
    isLoading: !!workspaceId && listQuery.isLoading,
    error: listQuery.error ? extractErrorMessage(listQuery.error) : null,
    accept: (id) => acceptMutation.mutateAsync(id),
    reject: (id, reason) => rejectMutation.mutateAsync({ id, reason }),
    isActing: acceptMutation.isPending || rejectMutation.isPending,
  };
}
