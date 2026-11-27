/**
 * ARCH-L1-001 ReactFrontend — Search API.
 *
 * leaf_id: COMP-RF-001 (NavigationShell — global search bar)
 * req_id:  REQ-L1-020 (Full-text search), REQ-L3-SEARCH-001..009
 *
 * Wraps /api/v1/search/ endpoint backed by COMP-AS-010 SearchService.
 */

import { apiClient } from "./client";
import type { UUID } from "../types";

export interface SearchHit {
  id: UUID;
  artifact_type: "Requirement" | "ArchitectureElement" | "TestCase" | "Adr" | "Risk" | "Issue" | "StakeholderNeed";
  title: string;
  description: string;
  relevance_score: number;
  workspace_id: UUID;
  /** Workflow state of the hit (issue #1098 / search lifecycle). */
  status?: string;
  /** True when the hit is soft-deleted / outdated. */
  outdated?: boolean;
}

export interface SearchResponse {
  results: SearchHit[];
  total_count: number;
  page: number;
  limit: number;
  query: string;
}

/**
 * Issue #1971: upper bound for a global-search query.
 *
 * The request line `GET /search/?q=…` is part of the URL, so an unbounded
 * query eventually trips the HTTP server / Vite proxy's request-line limit
 * (~10k characters here) with a 414 — long before the search backend can
 * answer. Keeping the constant next to the request that would fail lets the
 * input (`maxLength`) and this client agree on one number. The UI shows a
 * visible hint when it enforces the bound, so a truncated query is never
 * silently substituted for what the user typed.
 */
export const MAX_SEARCH_QUERY_LENGTH = 2000;

export const searchApi = {
  search(
    query: string,
    workspaceId: UUID,
    options: { type?: string[]; page?: number; limit?: number; includeOutdated?: boolean } = {}
  ): Promise<SearchResponse> {
    const params = new URLSearchParams();
    // Defence in depth: callers other than the bounded input must not be able
    // to produce a 414 either. Normal queries are far below this limit and are
    // passed through byte-for-byte.
    params.set("q", query.slice(0, MAX_SEARCH_QUERY_LENGTH));
    params.set("workspace_id", workspaceId);
    if (options.type && options.type.length > 0) {
      for (const t of options.type) {
        params.append("type", t);
      }
    }
    if (options.page !== undefined) {
      params.set("page", String(options.page));
    }
    if (options.limit !== undefined) {
      params.set("limit", String(options.limit));
    }
    // Outdated hits are hidden by default; an explicit opt-in is required
    // (the backend answers 400 for a non-boolean value).
    if (options.includeOutdated) {
      params.set("include_outdated", "true");
    }
    return apiClient.get<SearchResponse>(`/search/?${params.toString()}`);
  },
};
