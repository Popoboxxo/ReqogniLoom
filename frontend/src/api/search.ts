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
}

export interface SearchResponse {
  results: SearchHit[];
  total_count: number;
  page: number;
  limit: number;
  query: string;
}

export const searchApi = {
  search(
    query: string,
    workspaceId: UUID,
    options: { type?: string[]; page?: number; limit?: number } = {}
  ): Promise<SearchResponse> {
    const params = new URLSearchParams();
    params.set("q", query);
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
    return apiClient.get<SearchResponse>(`/search/?${params.toString()}`);
  },
};
