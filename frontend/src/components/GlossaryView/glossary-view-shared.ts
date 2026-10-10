/**
 * ARCH-L1-001 ReactFrontend — GlossaryView shared helpers.
 *
 * leaf_id: COMP-RF-GLOSSARY
 * req_id:  REQ-006 (C9 glossary trace links, C10 synonym linking)
 *
 * Pure glossary list logic (workspace/global filter, status filter, search,
 * sort) plus the C10 synonym-link lookup — extracted from the formerly
 * monolithic GlossaryView so the view keeps only state wiring and
 * composition. Predicates and ordering are unchanged.
 */

import type { GlossaryTerm } from "../../types";

export type FilterMode = "" | "workspace" | "global";

// GESAMTTEST_BERICHT_2026-08-21.md §6 "Glossar-Toolbar-Lücke": every sibling
// artifact list (Adr/Risk/Issue/...) offers a lifecycle-status filter and a
// sort dropdown via ListToolbar — Glossary only had the workspace/global
// filter. Mirrors ArchitectureEditors.tsx's ARCH_LIFECYCLE_STATUSES (same
// status vocabulary — #831 renamed the Glossary wire key from
// `lifecycle_status` to the artifact-consistent `status`; "deleted" is
// excluded since deleted terms are already hidden from the loaded list — see
// the GlossaryTerm type's own comment in types/index.ts).
export const GLOSSARY_LIFECYCLE_STATUSES = ["active", "outdated", "deprecated"] as const;

export type SortKey = "default" | "term" | "status" | "updated";

export function sortTerms(list: GlossaryTerm[], sortKey: SortKey): GlossaryTerm[] {
  const sorted = [...list];
  switch (sortKey) {
    case "term":
      sorted.sort((a, b) => a.term.localeCompare(b.term));
      break;
    case "status":
      sorted.sort(
        (a, b) =>
          (a.status ?? "active").localeCompare(b.status ?? "active") ||
          a.term.localeCompare(b.term),
      );
      break;
    case "updated":
      sorted.sort((a, b) => (b.updated_at || "").localeCompare(a.updated_at || ""));
      break;
  }
  return sorted;
}

export interface GlossaryListFilter {
  searchTerm: string;
  filterMode: FilterMode;
  statusFilter: string;
  workspaceId?: string;
}

/**
 * Workspace/global + status + free-text filter over the loaded term list —
 * the same three predicates GlossaryView applies before sorting.
 */
export function filterTerms(terms: GlossaryTerm[], filter: GlossaryListFilter): GlossaryTerm[] {
  const query = filter.searchTerm.toLowerCase();
  return terms.filter((term) => {
    const matchesSearch =
      term.term.toLowerCase().includes(query) ||
      term.definition.toLowerCase().includes(query);

    let matchesMode = true;
    if (filter.filterMode === "workspace") {
      matchesMode = term.workspace_id === filter.workspaceId;
    } else if (filter.filterMode === "global") {
      matchesMode = term.workspace_id === null;
    }

    const matchesStatus = !filter.statusFilter || (term.status ?? "active") === filter.statusFilter;

    return matchesSearch && matchesMode && matchesStatus;
  });
}

/**
 * C10 (REQ-006): case-insensitive lookup of term text -> GlossaryTerm, used to
 * detect when a free-text synonym already matches an existing entry (i.e. is
 * "linked" in the normalized-text sense — no dedicated backend link field
 * exists for GlossaryTerm, see GlossarySynonyms' onLinkSynonym).
 */
export function buildSynonymLinkIndex(terms: GlossaryTerm[]): Map<string, GlossaryTerm> {
  const map = new Map<string, GlossaryTerm>();
  terms.forEach((term) => map.set(term.term.trim().toLowerCase(), term));
  return map;
}

/** Resolve a synonym text to the entry it is linked to (never the entry itself). */
export function resolveSynonymLink(
  index: Map<string, GlossaryTerm>,
  synonym: string,
  selfId: string,
): GlossaryTerm | null {
  const match = index.get(synonym.trim().toLowerCase());
  return match && match.id !== selfId ? match : null;
}
