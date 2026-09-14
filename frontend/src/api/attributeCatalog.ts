/**
 * ARCH-L1-001 ReactFrontend — Central attribute catalog API (WS5 #942).
 *
 * Wraps `/api/v1/attribute-catalog/…`: the item-type-independent, per-tenant
 * template library from spec section 8. Every route is admin-gated server-side
 * (`attribute_catalog_views._require_admin`), so the UI only offers these
 * calls behind an admin gate — this module makes no permission decision of
 * its own.
 *
 * `definition` is the catalog's normalized `kind: "extended"` attribute block
 * — the same shape `AttributeSpec` publishes everywhere else. `addToDefinition`
 * is an explicit one-shot copy, never a binding: applying an entry writes a
 * snapshot into a definition and later edits to the entry do not reach it.
 */

import { apiClient } from "./client";
import type { UUID, WorkspacePreset } from "../types";
import type {
  AttributeItemType,
  AttributeSpec,
  GlobalAttributeDefinition,
  OnCollision,
  ResolvedAttributeDefinition,
} from "./attribute-definitions";

/** `{de, en}` metadata block on a catalog entry. */
export interface CatalogLocalizedText {
  de: string;
  en: string;
}

export interface AttributeCatalogEntry {
  id: UUID;
  name: string;
  /** Normalized extended attribute block — the reusable template. */
  definition: AttributeSpec;
  category: string;
  tags: string[];
  label: CatalogLocalizedText;
  help_text: CatalogLocalizedText;
  origin: string;
  deprecated: boolean;
  version: number;
  created_at: string;
  modified_at: string;
}

/** Everything `createEntry` accepts (server generates id/version/timestamps). */
export interface CatalogEntryInput {
  name: string;
  definition: AttributeSpec;
  category?: string;
  tags?: string[];
  label?: CatalogLocalizedText;
  help_text?: CatalogLocalizedText;
  origin?: string;
}

/** List/search filters; `query` is the name substring, `tags` are ANDed. */
export interface CatalogListFilters {
  query?: string;
  category?: string;
  tags?: string[];
  /** Default `false` — deprecated entries are hidden unless asked for. */
  includeDeprecated?: boolean;
}

export interface AddToDefinitionInput {
  item_type: AttributeItemType;
  /** Global scope: exactly one of `preset` / `workspace_id` must be set. */
  preset?: WorkspacePreset;
  workspace_id?: UUID;
  on_collision?: OnCollision;
}

export interface AddToDefinitionResult {
  /** The updated definition (workspace or global shape, matching the scope). */
  definition: ResolvedAttributeDefinition | GlobalAttributeDefinition;
  catalog_entry_id: string;
  on_collision: OnCollision;
}

/** One entry inside an exported catalog document (no storage metadata). */
export type CatalogEntryDocument = Omit<
  AttributeCatalogEntry,
  "id" | "version" | "created_at" | "modified_at"
>;

export interface AttributeCatalogDocument {
  schema_version: number;
  document_type: string;
  entries: CatalogEntryDocument[];
}

export interface CatalogImportResult {
  created: number;
  updated: number;
  total: number;
}

function appendFilters(params: URLSearchParams, filters?: CatalogListFilters): void {
  if (filters?.query) params.set("query", filters.query);
  if (filters?.category) params.set("category", filters.category);
  for (const tag of filters?.tags ?? []) params.append("tag", tag);
  if (filters?.includeDeprecated) params.set("include_deprecated", "true");
}

function withQuery(base: string, params: URLSearchParams): string {
  const query = params.toString();
  return query ? `${base}?${query}` : base;
}

export const attributeCatalogApi = {
  /** `GET /attribute-catalog/` — list entries (optionally filtered). */
  async listEntries(filters?: CatalogListFilters): Promise<AttributeCatalogEntry[]> {
    const params = new URLSearchParams();
    appendFilters(params, filters);
    const raw = await apiClient.get<{ entries: AttributeCatalogEntry[] }>(
      withQuery("/attribute-catalog/", params)
    );
    return raw.entries;
  },

  /**
   * `GET /attribute-catalog/search/` — name/category/tag search. The backend
   * rejects an empty query, so callers use `listEntries` for the unfiltered
   * view and this only once there is a term.
   */
  async searchEntries(
    query: string,
    filters?: Omit<CatalogListFilters, "query">
  ): Promise<AttributeCatalogEntry[]> {
    const params = new URLSearchParams({ q: query });
    appendFilters(params, filters);
    const raw = await apiClient.get<{ entries: AttributeCatalogEntry[] }>(
      withQuery("/attribute-catalog/search/", params)
    );
    return raw.entries;
  },

  getEntry(entryId: UUID): Promise<AttributeCatalogEntry> {
    return apiClient.get<AttributeCatalogEntry>(
      `/attribute-catalog/${encodeURIComponent(entryId)}/`
    );
  },

  createEntry(input: CatalogEntryInput): Promise<AttributeCatalogEntry> {
    return apiClient.post<AttributeCatalogEntry>("/attribute-catalog/", input);
  },

  /** Partial update — omitted keys are left untouched by the server. */
  updateEntry(
    entryId: UUID,
    patch: Partial<CatalogEntryInput> & { deprecated?: boolean }
  ): Promise<AttributeCatalogEntry> {
    return apiClient.patch<AttributeCatalogEntry>(
      `/attribute-catalog/${encodeURIComponent(entryId)}/`,
      patch
    );
  },

  deprecateEntry(entryId: UUID, deprecated = true): Promise<AttributeCatalogEntry> {
    return apiClient.post<AttributeCatalogEntry>(
      `/attribute-catalog/${encodeURIComponent(entryId)}/deprecate/`,
      { deprecated }
    );
  },

  /**
   * `POST /attribute-catalog/{id}/add-to-definition/` — copy the entry's block
   * into the target definition, resolving name collisions via the definition
   * service's `skip`/`overwrite`/`rename` merge.
   */
  addToDefinition(
    entryId: UUID,
    input: AddToDefinitionInput
  ): Promise<AddToDefinitionResult> {
    const body: Record<string, unknown> = {
      item_type: input.item_type,
      on_collision: input.on_collision ?? "skip",
    };
    if (input.preset) body.preset = input.preset;
    if (input.workspace_id) body.workspace_id = input.workspace_id;
    return apiClient.post<AddToDefinitionResult>(
      `/attribute-catalog/${encodeURIComponent(entryId)}/add-to-definition/`,
      body
    );
  },

  exportCatalog(includeDeprecated = true): Promise<AttributeCatalogDocument> {
    const params = new URLSearchParams();
    if (includeDeprecated) params.set("include_deprecated", "true");
    return apiClient.get<AttributeCatalogDocument>(
      withQuery("/attribute-catalog/export/", params)
    );
  },

  importCatalog(
    document: AttributeCatalogDocument,
    onCollision: OnCollision = "skip"
  ): Promise<CatalogImportResult> {
    return apiClient.post<CatalogImportResult>(
      `/attribute-catalog/import/?on_collision=${onCollision}`,
      document
    );
  },
};
