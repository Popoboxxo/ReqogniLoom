/**
 * ARCH-L1-001 ReactFrontend — generic artifact reference resolution.
 *
 * leaf_id: COMP-RF-003 (RequirementEditors), COMP-RF-004 (ArchitectureEditors)
 * req_id:  REQ-L2-RF-006 (Traceability-Anzeige), REQ-L1-003 (Traceability-Engine)
 *
 * #414: TraceLink endpoints (`source_id`/`target_id`) live in the **Artifact**
 * id space, while every SPA editor route and every `/api/v1/<entity>/<id>/`
 * detail endpoint takes the **domain-entity** id (`Requirement.id`, which is a
 * different UUID from `Requirement.artifact_id` — see
 * `persistence/models.py::Requirement.artifact`, a OneToOneField with its own
 * PK). This module used to pass the Artifact id straight through to both, so
 * every trace link produced a `404 GET /api/v1/requirements/<artifact-id>/`
 * (resp. `/architecture/...`) and then fell into the catch-all below — which is
 * why trace links rendered as inert `(1a2b3c4d…)` labels instead of navigable
 * rows, for artifacts that plainly exist.
 *
 * `GET /api/v1/traceability/resolve/` (REQ-L2-TE-019, Task 3.2a) is the
 * backend's bridge between the two id spaces and covers all nine
 * artifact-backed types. Resolving through it — rather than guessing that the
 * two ids are interchangeable — is what keeps the request and the route on the
 * entity side. Same gap, same remedy as #413/#415/#416 and
 * `components/Audit/use-finding-targets.ts`.
 */

// Both from ./traceability (which re-exports the constant) rather than pulling
// the limit out of ./tracelinks: that keeps the resolve dependency to a single
// module, so a consumer that mocks the API layer has one module to satisfy
// instead of two. Vitest raises on a missing export from a mocked module, so an
// incomplete mock is a hard failure, not a silent undefined.
import { traceabilityApi, RESOLVE_BATCH_LIMIT } from "./traceability";
import { requirementsApi } from "./requirements";
import { architectureApi } from "./architecture";
import { testcasesApi } from "./testcases";
import { adrsApi } from "./adrs";
import { ARTIFACT_ROUTE_MAP } from "../utils/artifactRoutes";
import type { UUID } from "../types";

export interface ArtifactRef {
  title: string;
  route: string;
}

/**
 * Entity types whose title can be fetched for the row label. The *route* works
 * for every type in `ARTIFACT_ROUTE_MAP` (all nine resolvable types); only the
 * display title needs a typed detail call, and these four are the types whose
 * API wrapper this module already depends on. A type outside this table still
 * gets a working, navigable route — it just falls back to the short-id label.
 */
const TITLE_FETCHERS: Record<string, (id: UUID) => Promise<{ title?: string }>> = {
  Requirement: (id) => requirementsApi.get(id),
  ArchitectureElement: (id) => architectureApi.get(id),
  TestCase: (id) => testcasesApi.get(id),
  Adr: (id) => adrsApi.get(id),
};

function shortLabel(id: UUID): string {
  return `(${id.slice(0, 8)}…)`;
}

function fallbackRef(id: UUID): ArtifactRef {
  // UI-05: a lookup failure or an unmapped artifact_type must not fake a
  // Requirement route — that silently sent users to the wrong artifact
  // (the target route "changed" depending on whether the lookup happened
  // to succeed or fail). An empty route marks the ref as "not resolvable";
  // callers (TraceLinkPanel, TraceabilityPanel) already render/must render
  // a plain, non-navigable label instead of a clickable link for it.
  return { title: shortLabel(id), route: "" };
}

/** Split `ids` into chunks the resolve endpoint accepts in a single request. */
function chunk(ids: readonly UUID[], size: number): UUID[][] {
  const out: UUID[][] = [];
  for (let i = 0; i < ids.length; i += size) out.push(ids.slice(i, i + size));
  return out;
}

/**
 * Resolve many Artifact ids to their title + editor route in one batch.
 *
 * One `/traceability/resolve/` request per `RESOLVE_BATCH_LIMIT` ids (the
 * endpoint 400s above the cap and `traceabilityApi.resolve` silently truncates,
 * so chunking here is load-bearing, not decorative), then at most one typed
 * detail call per resolved id — instead of the two-calls-per-id the previous
 * per-id implementation issued.
 *
 * Never throws and never omits a requested id: an id that cannot be resolved
 * (unknown, another tenant's, or an Artifact whose domain row was deleted —
 * all reported by the backend as `resolved: false`, which is a normal answer
 * and not an error) maps to `fallbackRef`, i.e. an explicitly non-navigable
 * entry.
 */
export async function resolveArtifactRefs(
  ids: readonly UUID[]
): Promise<Record<UUID, ArtifactRef>> {
  const unique = [...new Set(ids.filter(Boolean))];
  const refs: Record<UUID, ArtifactRef> = {};
  for (const id of unique) refs[id] = fallbackRef(id);
  if (unique.length === 0) return refs;

  const responses = await Promise.all(
    chunk(unique, RESOLVE_BATCH_LIMIT).map((batch) =>
      // A failed batch degrades to "not resolvable" for its ids rather than
      // rejecting the whole panel load.
      traceabilityApi.resolve(batch).catch(() => [])
    )
  );

  await Promise.all(
    responses.flat().map(async (entry) => {
      if (!entry.resolved || !entry.entity_type || !entry.entity_id) return;
      const routeBase = ARTIFACT_ROUTE_MAP[entry.entity_type];
      // Deliberately not `getArtifactRoute`: its unknown-type fallback is
      // "/requirements", which is exactly the faked route UI-05 forbids here.
      if (!routeBase) return;

      const entityId = entry.entity_id;
      let title = "";
      const fetchTitle = TITLE_FETCHERS[entry.entity_type];
      if (fetchTitle) {
        try {
          title = (await fetchTitle(entityId))?.title ?? "";
        } catch {
          // Title unavailable (e.g. a transient error): the route is still
          // known-good, so keep the row navigable under a short-id label
          // rather than degrading it to inert text.
          title = "";
        }
      }
      refs[entry.artifact_id] = {
        title: title || shortLabel(entry.artifact_id),
        route: `${routeBase}/${entityId}`,
      };
    })
  );

  return refs;
}

/** Resolves title + route for an arbitrary linked artifact id. Never throws. */
export async function resolveArtifactRef(id: UUID): Promise<ArtifactRef> {
  try {
    const refs = await resolveArtifactRefs([id]);
    return refs[id] ?? fallbackRef(id);
  } catch {
    return fallbackRef(id);
  }
}
