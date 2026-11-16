/**
 * Task 4.9 — React Query hook for the table rows
 * (plan 2026-11-04-tabellenansicht-s4).
 *
 * The table query is server-side; the hook keeps `filters`/`sort`/`page` in
 * the key so a change refetches, and disables retries for a missing endpoint
 * (a slice-1-less deployment must degrade to an empty state, not a retry
 * loop).
 */

import { useQuery } from "@tanstack/react-query";

import { tableApi, type TableFilters, type SortTerm } from "../api/table-views";
import type { UUID } from "../types";

export const TABLE_PAGE_SIZE = 50;

export const tableKeys = {
  all: ["table-rows"] as const,
  rows: (workspaceId: string, itemType: string) =>
    [...tableKeys.all, workspaceId, itemType] as const,
};

export function useTableRows(
  workspaceId: string | undefined,
  itemType: string,
  filters: TableFilters,
  sort: SortTerm[],
  page: number
) {
  return useQuery({
    queryKey: [
      ...tableKeys.rows(workspaceId ?? "", itemType),
      { filters, sort, page },
    ],
    queryFn: () =>
      tableApi.query({
        workspace_id: workspaceId as UUID,
        item_type: itemType,
        filters,
        sort,
        page,
        page_size: TABLE_PAGE_SIZE,
      }),
    enabled: !!workspaceId,
    retry: false,
  });
}
