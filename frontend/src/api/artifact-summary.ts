/**
 * AI summary of one artifact and its visible trace neighbours (Issue #1792, S2).
 *
 * Consumes the S1 endpoint
 * `GET /api/v1/artifacts/{artifact_id}/summary/?refresh=&depth=`.
 *
 * The endpoint answers **200 for every outcome**, including the four
 * degradations. A rejected promise therefore means transport, authentication
 * or authorisation trouble only — never "this artifact has no summary". The
 * degradation is reported in the payload (`degraded` + `degraded_reason`) and
 * has to stay visible in the UI (spec §9/E11).
 *
 * No retry, no fallback text: the panel owns the loading/error states, this
 * module only maps the wire form.
 */

import { apiClient } from "./client";
import type { UUID } from "../types";

/**
 * The closed degradation vocabulary of spec §9/E11. Kept as a runtime tuple so
 * an unknown value from a newer backend can be recognised and mapped to
 * `null` instead of leaking an untyped string into the UI.
 */
export const SUMMARY_DEGRADED_REASONS = [
  "budget_exhausted",
  "provider_unavailable",
  "stale",
  "disabled",
] as const;

export type SummaryDegradedReason = (typeof SUMMARY_DEGRADED_REASONS)[number];

/** Wire format returned by the backend (snake_case). */
interface ArtifactSummaryWire {
  artifact_id: string;
  artifact_type: string;
  summary: string | null;
  degraded: boolean;
  degraded_reason: string | null;
  cache_hit: boolean;
  trace_depth: number;
  neighbour_count: number;
  omitted_neighbours: number;
  generated_at: string;
}

export interface ArtifactSummary {
  artifactId: UUID;
  artifactType: string;
  /** Generated free text — `null` on every degraded answer. */
  summary: string | null;
  degraded: boolean;
  /** Closed enum, `null` when the answer is not degraded. */
  degradedReason: SummaryDegradedReason | null;
  cacheHit: boolean;
  /** Trace hops that went into the prompt (1 or 2, backend-clamped). */
  traceDepth: number;
  /** Visible neighbours included in the prompt (capped). */
  neighbourCount: number;
  /** Visible neighbours that did not fit into the cap. */
  omittedNeighbours: number;
  generatedAt: string;
}

export interface FetchArtifactSummaryOptions {
  /** Regenerate instead of serving a cached answer (default false). */
  refresh?: boolean;
  /** Trace hops to include, 1 or 2. Out-of-range values are clamped server-side. */
  depth?: number;
}

function toDegradedReason(raw: string | null): SummaryDegradedReason | null {
  if (raw === null) return null;
  return (SUMMARY_DEGRADED_REASONS as readonly string[]).includes(raw)
    ? (raw as SummaryDegradedReason)
    : null;
}

function toArtifactSummary(wire: ArtifactSummaryWire): ArtifactSummary {
  return {
    artifactId: wire.artifact_id,
    artifactType: wire.artifact_type,
    summary: wire.summary,
    degraded: wire.degraded,
    degradedReason: toDegradedReason(wire.degraded_reason),
    cacheHit: wire.cache_hit,
    traceDepth: wire.trace_depth,
    neighbourCount: wire.neighbour_count,
    omittedNeighbours: wire.omitted_neighbours,
    generatedAt: wire.generated_at,
  };
}

/**
 * Fetch the on-demand summary for one backing generic Artifact UUID.
 *
 * `refresh: true` asks the backend to regenerate even when a cached answer for
 * the same content exists; the initial call deliberately leaves it off so the
 * cache can answer.
 */
export async function fetchArtifactSummary(
  artifactId: UUID,
  options: FetchArtifactSummaryOptions = {},
): Promise<ArtifactSummary> {
  const params = new URLSearchParams();
  if (options.refresh) params.set("refresh", "true");
  if (typeof options.depth === "number") params.set("depth", String(options.depth));
  const query = params.toString();

  const wire = await apiClient.get<ArtifactSummaryWire>(
    `/artifacts/${artifactId}/summary/${query ? `?${query}` : ""}`,
  );
  return toArtifactSummary(wire);
}

// ---------------------------------------------------------------------------
// Stored per-scope summaries (issue #1793 / S6, surface in S8)
// ---------------------------------------------------------------------------

/** Wire form of one persisted summary scope (spec §6.6). */
interface StoredSummaryWire {
  workspace_id: string;
  summary_kind: string;
  artifact_type: string | null;
  artifact_id: string | null;
  text: string | null;
  reason: string | null;
  stale: boolean;
  item_count: number;
  status: string | null;
  provider: string | null;
  model: string | null;
  token_usage: number | null;
  trigger: string | null;
  generated_at: string | null;
  updated_at: string | null;
}

interface StoredSummaryRefreshWire extends StoredSummaryWire {
  outcome: string;
}

interface WorkspaceSummaryListWire {
  workspace_id: string;
  summaries: StoredSummaryWire[];
  count: number;
  truncated: boolean;
  limit: number;
}

export interface StoredSummary {
  workspaceId: UUID;
  /** `type_roster` for a workspace/type stand, `artifact` for a single item. */
  summaryKind: string;
  artifactType: string | null;
  artifactId: string | null;
  /** Generated free text; `null` when the scope has never produced one. */
  text: string | null;
  /** Closed enum (E11). `null` for a scope that was never summarised. */
  reason: SummaryDegradedReason | null;
  stale: boolean;
  itemCount: number;
  status: string | null;
  provider: string | null;
  model: string | null;
  tokenUsage: number | null;
  trigger: string | null;
  generatedAt: string | null;
  updatedAt: string | null;
}

export interface WorkspaceSummaryList {
  workspaceId: UUID;
  summaries: StoredSummary[];
  count: number;
  truncated: boolean;
  limit: number;
}

export interface RefreshedTypeSummary extends StoredSummary {
  /** `summarized | skipped:<reason> | failed` — the manual run's verdict. */
  outcome: string;
}

function toStoredSummary(wire: StoredSummaryWire): StoredSummary {
  return {
    workspaceId: wire.workspace_id,
    summaryKind: wire.summary_kind,
    artifactType: wire.artifact_type,
    artifactId: wire.artifact_id,
    text: wire.text,
    reason: toDegradedReason(wire.reason),
    stale: wire.stale,
    itemCount: wire.item_count,
    status: wire.status,
    provider: wire.provider,
    model: wire.model,
    tokenUsage: wire.token_usage,
    trigger: wire.trigger,
    generatedAt: wire.generated_at,
    updatedAt: wire.updated_at,
  };
}

/**
 * Every stored type stand of one workspace (read-only, free).
 *
 * Types that were never summarised are simply absent from the list — the
 * caller renders its own "nothing yet" state instead of inventing a reason.
 */
export async function fetchWorkspaceSummaries(
  workspaceId: UUID,
): Promise<WorkspaceSummaryList> {
  const wire = await apiClient.get<WorkspaceSummaryListWire>(
    `/workspaces/${workspaceId}/summaries/`,
  );
  return {
    workspaceId: wire.workspace_id,
    summaries: wire.summaries.map(toStoredSummary),
    count: wire.count,
    truncated: wire.truncated,
    limit: wire.limit,
  };
}

/**
 * The stored stand of one artifact type. A never-summarised type answers the
 * empty payload (`text: null`, `itemCount: 0`, `reason: null`), never a 404.
 */
export async function fetchTypeSummary(
  workspaceId: UUID,
  artifactType: string,
): Promise<StoredSummary> {
  const wire = await apiClient.get<StoredSummaryWire>(
    `/workspaces/${workspaceId}/summaries/${encodeURIComponent(artifactType)}/`,
  );
  return toStoredSummary(wire);
}

/**
 * One manual run of a type stand. Requires a write role; every brake of the
 * periodic sweep (switch, budget, agent key, throttle) stays in force, so a
 * refused run still resolves with `outcome: "skipped:<reason>"`.
 */
export async function refreshTypeSummary(
  workspaceId: UUID,
  artifactType: string,
): Promise<RefreshedTypeSummary> {
  const wire = await apiClient.post<StoredSummaryRefreshWire>(
    `/workspaces/${workspaceId}/summaries/${encodeURIComponent(artifactType)}/refresh/`,
    {},
  );
  return { ...toStoredSummary(wire), outcome: wire.outcome };
}
