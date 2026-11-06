/**
 * ARCH-L1-001 ReactFrontend — connection-view state (P3 Tasks 3.2–3.4, V10/B9).
 *
 * One hook owns everything the three renderers share:
 *
 * - the filter state lives in the URL (round-trips across reloads, survives
 *   switching the view), never in component state;
 * - the flat `allocation-view` read object is fetched through React Query;
 * - the requirement/element split and the two UI-only quick filters
 *   (`Gesperrt`, `Befunde`) are applied client-side because the committed
 *   read object exposes those two flags per row but has no server filter for
 *   them.
 *
 * The pure (de)serializers are exported so they can be tested without a
 * router or a network mock.
 */

import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import {
  allocationViewApi,
  type AllocationRow,
  type AllocationViewQuery,
} from "../../api/allocation-view";
import { loadGroupsWithMembers } from "../../api/groups";
import { asError } from "../../queries/query-error";
import { useWorkspace } from "../../context/WorkspaceContext";

/** The four renderers: P3's three plus the P5 card graph. */
export type ConnectionViewMode = "tree" | "two-column" | "matrix" | "graph";

export const CONNECTION_VIEW_MODES: readonly ConnectionViewMode[] = [
  "tree",
  "two-column",
  "matrix",
  "graph",
];

/** Default client-side window for the matrix. */
export const DEFAULT_PAGE_SIZE = 50;

/**
 * The read object paginates the *combined* requirement+element list; elements
 * are appended after requirements, so a small page would contain no element
 * rows at all and the tree/matrix would lose their columns. The renderers
 * therefore read the maximum page and window the matrix client-side.
 */
export const SERVER_PAGE_SIZE = 500;

export interface ConnectionFilters {
  /** `allocated=false` is the "Nicht allokiert" quick filter. */
  allocated?: boolean;
  /** `open=true` is the "Offen" quick filter (server-side). */
  open?: boolean;
  /** UI-only quick filter over `row.locked`. */
  locked?: boolean;
  /** UI-only quick filter over `row.findings`. */
  hasFindings?: boolean;
  intent?: string;
  tier?: string;
  type?: string;
  category?: string;
  state?: string;
  elementSubtree?: string;
  q?: string;
  /**
   * P6 Task 6.3: id of a visual group. The committed read object has no group
   * filter, so membership is fetched separately and matched client-side over
   * `row.artifact_id`.
   */
  group?: string;
  /** 1-based client-side matrix window. */
  page: number;
  pageSize: number;
}

function readBoolean(raw: string | null): boolean | undefined {
  if (raw === "true") return true;
  if (raw === "false") return false;
  return undefined;
}

/** Parse the connection view's filter state out of a `URLSearchParams`. */
export function parseConnectionSearch(
  params: URLSearchParams
): ConnectionFilters {
  const page = Number.parseInt(params.get("page") ?? "1", 10);
  const pageSize = Number.parseInt(
    params.get("page_size") ?? String(DEFAULT_PAGE_SIZE),
    10
  );
  return {
    allocated: readBoolean(params.get("allocated")),
    open: readBoolean(params.get("open")),
    locked: readBoolean(params.get("locked")),
    hasFindings: readBoolean(params.get("has_findings")),
    intent: params.get("intent") || undefined,
    tier: params.get("tier") || undefined,
    type: params.get("type") || undefined,
    category: params.get("category") || undefined,
    state: params.get("state") || undefined,
    elementSubtree: params.get("element_subtree") || undefined,
    q: params.get("q") || undefined,
    group: params.get("group") || undefined,
    page: Number.isFinite(page) && page > 0 ? page : 1,
    pageSize:
      Number.isFinite(pageSize) && pageSize > 0
        ? Math.min(pageSize, SERVER_PAGE_SIZE)
        : DEFAULT_PAGE_SIZE,
  };
}

/**
 * Serialize filter state into the URL. `view` is deliberately not part of the
 * filter object — it is orthogonal (switching the renderer must never reset a
 * filter), so the caller composes it separately.
 */
export function buildConnectionSearch(
  filters: ConnectionFilters
): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.allocated !== undefined) {
    params.set("allocated", String(filters.allocated));
  }
  if (filters.open) params.set("open", "true");
  if (filters.locked) params.set("locked", "true");
  if (filters.hasFindings) params.set("has_findings", "true");
  if (filters.intent) params.set("intent", filters.intent);
  if (filters.tier) params.set("tier", filters.tier);
  if (filters.type) params.set("type", filters.type);
  if (filters.category) params.set("category", filters.category);
  if (filters.state) params.set("state", filters.state);
  if (filters.elementSubtree) {
    params.set("element_subtree", filters.elementSubtree);
  }
  if (filters.q) params.set("q", filters.q);
  if (filters.group) params.set("group", filters.group);
  if (filters.page > 1) params.set("page", String(filters.page));
  if (filters.pageSize !== DEFAULT_PAGE_SIZE) {
    params.set("page_size", String(filters.pageSize));
  }
  return params;
}

/** Only the filters the committed backend accepts go over the wire. */
export function filtersToQuery(
  filters: ConnectionFilters
): AllocationViewQuery {
  const query: AllocationViewQuery = {
    page_size: SERVER_PAGE_SIZE,
    offset: 0,
  };
  if (filters.allocated !== undefined) query.allocated = filters.allocated;
  if (filters.open !== undefined) query.open = filters.open;
  if (filters.intent) query.intent = filters.intent;
  if (filters.tier) query.tier = filters.tier;
  if (filters.type) query.type = filters.type;
  if (filters.category) query.category = filters.category;
  if (filters.state) query.state = filters.state;
  if (filters.elementSubtree) query.element_subtree = filters.elementSubtree;
  if (filters.q) query.q = filters.q;
  // `filters.group` is deliberately not forwarded: group membership is a
  // client-side join, the read object accepts no group parameter.
  return query;
}

/** Parse the selected renderer from the URL; `Baum` is the default. */
export function parseConnectionView(params: URLSearchParams): ConnectionViewMode {
  const raw = params.get("view");
  if (raw === "two-column" || raw === "matrix" || raw === "graph") return raw;
  return "tree";
}

/** Whether a row passes the two client-side quick filters. */
export function rowMatchesClientFilters(
  row: AllocationRow,
  filters: ConnectionFilters
): boolean {
  if (row.kind !== "requirement") return true;
  if (filters.locked && row.locked === null) return false;
  if (filters.hasFindings && row.findings.length === 0) return false;
  return true;
}

/** Fractional `sort_key` first (ASCII order), then title as a stable tie-break. */
export function compareRows(a: AllocationRow, b: AllocationRow): number {
  const keyA = a.sort_key ?? "";
  const keyB = b.sort_key ?? "";
  if (keyA !== keyB) return keyA < keyB ? -1 : 1;
  return a.title.localeCompare(b.title);
}

export const allocationViewKeys = {
  all: ["allocation-view"] as const,
  rows: (workspaceId: string | null, query: AllocationViewQuery) =>
    [...allocationViewKeys.all, "rows", workspaceId, query] as const,
  elements: (workspaceId: string | null) =>
    [...allocationViewKeys.all, "elements", workspaceId] as const,
  groups: (workspaceId: string | null) =>
    [...allocationViewKeys.all, "groups", workspaceId] as const,
};

/** One group option of the filter bar. */
export interface ConnectionGroupOption {
  id: string;
  title: string;
}

export interface UseAllocationViewResult {
  workspaceId: string | null;
  view: ConnectionViewMode;
  filters: ConnectionFilters;
  /** Requirements after the client-side quick filters, sorted by `sort_key`. */
  requirements: AllocationRow[];
  /** Requirements before the two client-side quick filters (filter options). */
  allRequirements: AllocationRow[];
  /** Full element catalogue (independent of the active filters). */
  elements: AllocationRow[];
  /** P6: groups offered by the `group` filter (empty when none exist). */
  groups: ConnectionGroupOption[];
  meta: {
    total: number;
    unallocated: number;
    locked: number;
    findings: number;
  };
  isLoading: boolean;
  isFetching: boolean;
  error: Error | null;
  setView: (view: ConnectionViewMode) => void;
  setFilters: (patch: Partial<ConnectionFilters>) => void;
  resetFilters: () => void;
  setPage: (page: number) => void;
}

export function useAllocationView(): UseAllocationViewResult {
  const { activeWorkspace } = useWorkspace();
  const workspaceId = activeWorkspace?.id ?? null;
  const [searchParams, setSearchParams] = useSearchParams();

  const filters = useMemo(
    () => parseConnectionSearch(searchParams),
    [searchParams]
  );
  const view = parseConnectionView(searchParams);
  const query = useMemo(() => filtersToQuery(filters), [filters]);

  const rowsQuery = useQuery({
    queryKey: allocationViewKeys.rows(workspaceId, query),
    queryFn: () => allocationViewApi.view(workspaceId as string, query),
    enabled: Boolean(workspaceId),
  });

  const elementsQuery = useQuery({
    queryKey: allocationViewKeys.elements(workspaceId),
    queryFn: () =>
      allocationViewApi.view(workspaceId as string, {
        page_size: SERVER_PAGE_SIZE,
        offset: 0,
      }),
    enabled: Boolean(workspaceId),
  });

  // P6 Task 6.3: groups + membership. A failed read degrades to "no groups"
  // (the filter and the card field simply stay empty) instead of blocking the
  // connection view.
  const groupsQuery = useQuery({
    queryKey: allocationViewKeys.groups(workspaceId),
    queryFn: () => loadGroupsWithMembers(workspaceId as string),
    enabled: Boolean(workspaceId),
    staleTime: 60 * 1000,
  });

  const groups = useMemo(
    (): ConnectionGroupOption[] =>
      (groupsQuery.data ?? []).map((group) => ({
        id: group.id,
        title: group.title,
      })),
    [groupsQuery.data]
  );

  /** Requirement artifact id -> names of the groups it belongs to. */
  const groupNamesByArtifact = useMemo(() => {
    const map = new Map<string, string>();
    for (const group of groupsQuery.data ?? []) {
      for (const member of group.members) {
        const previous = map.get(member.requirement_artifact_id);
        map.set(
          member.requirement_artifact_id,
          previous ? `${previous}, ${group.title}` : group.title
        );
      }
    }
    return map;
  }, [groupsQuery.data]);

  /** Membership set of the active group filter (empty when none is active). */
  const groupMemberArtifactIds = useMemo((): Set<string> => {
    if (!filters.group) return new Set<string>();
    const group = (groupsQuery.data ?? []).find(
      (candidate) => candidate.id === filters.group
    );
    if (!group) return new Set<string>();
    return new Set(group.members.map((member) => member.requirement_artifact_id));
  }, [filters.group, groupsQuery.data]);

  const allRows = useMemo(
    () => rowsQuery.data?.results ?? [],
    [rowsQuery.data]
  );

  const allRequirements = useMemo(
    () =>
      allRows
        .filter((row) => row.kind === "requirement")
        .slice()
        .sort(compareRows),
    [allRows]
  );

  const requirements = useMemo(() => {
    const filtered = allRequirements.filter((row) =>
      rowMatchesClientFilters(row, filters)
    );
    // P6: the group filter is a client-side membership join (no server
    // parameter exists on the committed read object).
    if (!filters.group) return filtered;
    return filtered.filter((row) => groupMemberArtifactIds.has(row.artifact_id));
  }, [allRequirements, filters, groupMemberArtifactIds]);

  /**
   * P6 Task 6.3: the read object's `group` field is not populated by the
   * backend yet. Where membership data is available, fill it with the group
   * name(s) so the card field "group" shows a name instead of "—"; when there
   * is nothing to resolve the original value wins.
   */
  const requirementsWithGroup = useMemo(
    () =>
      requirements.map((row) => {
        const groupName = groupNamesByArtifact.get(row.artifact_id);
        return groupName ? { ...row, group: groupName } : row;
      }),
    [requirements, groupNamesByArtifact]
  );

  const elements = useMemo(() => {
    const fromCatalog =
      elementsQuery.data?.results.filter((row) => row.kind === "element") ?? [];
    const source = fromCatalog.length
      ? fromCatalog
      : allRows.filter((row) => row.kind === "element");
    return source.slice().sort(compareRows);
  }, [elementsQuery.data, allRows]);

  const setFilters = useCallback(
    (patch: Partial<ConnectionFilters>) => {
      setSearchParams(
        (previous) => {
          const current = parseConnectionSearch(previous);
          const next: ConnectionFilters = {
            ...current,
            ...patch,
            // Every filter change restarts the matrix window; an explicit
            // `page` in the patch (paging) wins.
            page: patch.page ?? 1,
          };
          const params = buildConnectionSearch(next);
          const mode = parseConnectionView(previous);
          if (mode !== "tree") params.set("view", mode);
          return params;
        },
        { replace: true }
      );
    },
    [setSearchParams]
  );

  const setView = useCallback(
    (nextView: ConnectionViewMode) => {
      setSearchParams(
        (previous) => {
          const params = new URLSearchParams(previous);
          if (nextView === "tree") params.delete("view");
          else params.set("view", nextView);
          return params;
        },
        { replace: true }
      );
    },
    [setSearchParams]
  );

  const resetFilters = useCallback(() => {
    setSearchParams(
      (previous) => {
        const params = buildConnectionSearch({
          page: 1,
          pageSize: parseConnectionSearch(previous).pageSize,
        });
        const mode = parseConnectionView(previous);
        if (mode !== "tree") params.set("view", mode);
        return params;
      },
      { replace: true }
    );
  }, [setSearchParams]);

  const setPage = useCallback(
    (page: number) => {
      setFilters({ page: Math.max(1, page) });
    },
    [setFilters]
  );

  const meta = rowsQuery.data?.meta ?? {
    total: 0,
    unallocated: 0,
    locked: 0,
    findings: 0,
  };

  return {
    workspaceId,
    view,
    filters,
    requirements: requirementsWithGroup,
    allRequirements,
    elements,
    groups,
    meta: {
      total: meta.total,
      unallocated: meta.unallocated,
      locked: meta.locked,
      findings: meta.findings,
    },
    isLoading: rowsQuery.isLoading,
    isFetching: rowsQuery.isFetching,
    error: rowsQuery.error ? asError(rowsQuery.error) : null,
    setView,
    setFilters,
    resetFilters,
    setPage,
  };
}
