/**
 * ARCH-L1-001 ReactFrontend — SE-Auditor "Modify" target resolution (#451).
 *
 * An audit finding names its subjects by **Artifact** id (`Finding.artifact_ids`,
 * `backend/traceability/audit/types.py`), but the SPA's editor routes take the
 * **domain-entity** id (`/requirements/<Requirement.id>`, see
 * `NavigationShell.tsx` + `useRequirementData`). That mismatch — the same
 * artifact-id-vs-entity-id gap that produced issues #413/#415/#416 — is why the
 * dashboard could not offer a working "Modify" action and rendered a permanently
 * disabled button instead.
 *
 * `GET /api/v1/traceability/resolve/` (REQ-L2-TE-019, Task 3.2a) closes exactly
 * that gap for all nine artifact-backed types, so this hook batch-resolves every
 * artifact id referenced by the current findings and hands the dashboard a ready
 * `artifactId -> route` map.
 *
 * Contract details that shape the implementation:
 *   - The endpoint rejects a batch larger than `RESOLVE_BATCH_LIMIT` with a 400
 *     (verified live against the dev stack) and `traceabilityApi.resolve`
 *     silently truncates. A workspace can easily produce four-digit finding
 *     counts, so ids are chunked here rather than passed through in one go.
 *   - `resolved: false` is a normal answer, not an error (dangling artifact, or
 *     a type without a backing domain row). Those ids are cached as "no target"
 *     so the UI renders no action at all instead of a dead control.
 *   - Results are cached across re-runs: adopting one finding must not re-resolve
 *     the other several hundred.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { traceabilityApi } from "../../api/traceability";
import { RESOLVE_BATCH_LIMIT } from "../../api/tracelinks";
import { getArtifactRoute } from "../../utils/artifactRoutes";
import type { AuditFinding } from "../../api/audit";
import type { UUID } from "../../types";

/** A resolved, navigable editor target for one artifact id. */
export interface FindingTarget {
  artifactId: UUID;
  /** Backend entity type ("Requirement", "ArchitectureElement", ...). */
  entityType: string;
  /** SPA route of the entity's editor, e.g. `/requirements/<entity id>`. */
  route: string;
}

/** `artifactId -> target`, or `null` for an id that has no editor route. */
export type FindingTargetMap = Readonly<Record<string, FindingTarget | null>>;

/** Split `ids` into chunks the resolve endpoint accepts in a single request. */
function chunk(ids: readonly string[], size: number): string[][] {
  const out: string[][] = [];
  for (let i = 0; i < ids.length; i += size) out.push(ids.slice(i, i + size));
  return out;
}

/**
 * Resolve every artifact id referenced by `findings` to an editor route.
 *
 * Ids already resolved in an earlier run are never requested again; a failed
 * request marks its ids as "no target" rather than retrying forever, so a
 * backend hiccup degrades to the read-only rendering instead of a request loop.
 */
export function useFindingTargets(findings: readonly AuditFinding[]): FindingTargetMap {
  const [targets, setTargets] = useState<Record<string, FindingTarget | null>>({});
  // Mirror of `targets` for the effect, so "which ids are still missing?" does
  // not have to put `targets` into the dependency list (which would re-run the
  // effect on every resolution and re-request in a loop).
  const knownRef = useRef<Record<string, FindingTarget | null>>({});

  // A stable, order-independent key — the findings array gets a new identity on
  // every audit run and after every Adopt, but its id set usually does not.
  const idsKey = useMemo(() => {
    const ids = new Set<string>();
    for (const finding of findings) {
      for (const id of finding.artifact_ids) if (id) ids.add(id);
    }
    return [...ids].sort().join(",");
  }, [findings]);

  useEffect(() => {
    const ids = idsKey ? idsKey.split(",") : [];
    const missing = ids.filter((id) => !(id in knownRef.current));
    if (missing.length === 0) return;

    let cancelled = false;
    const batches = chunk(missing, RESOLVE_BATCH_LIMIT);

    void Promise.all(
      batches.map((batch) =>
        traceabilityApi
          .resolve(batch as UUID[])
          // A failed batch must not drop the whole page into an error state —
          // the findings themselves are still valid and readable.
          .catch(() => [])
      )
    ).then((responses) => {
      if (cancelled) return;
      // Start from "no target" for every requested id so a missing or failed
      // response is cached too and never re-requested.
      const resolved: Record<string, FindingTarget | null> = {};
      for (const id of missing) resolved[id] = null;
      for (const entry of responses.flat()) {
        if (!entry.resolved || !entry.entity_type || !entry.entity_id) continue;
        resolved[entry.artifact_id] = {
          artifactId: entry.artifact_id,
          entityType: entry.entity_type,
          route: getArtifactRoute(entry.entity_type, entry.entity_id),
        };
      }
      knownRef.current = { ...knownRef.current, ...resolved };
      setTargets((prev) => ({ ...prev, ...resolved }));
    });

    return () => {
      cancelled = true;
    };
  }, [idsKey]);

  return targets;
}

/**
 * Pick the target a finding's "Modify" action should navigate to.
 *
 * `artifact_ids[0]` is the finding's subject for every rule that reports more
 * than one id (e.g. ARCH-003 reports `(requirement, child element, parent
 * element)`), so the first resolvable id is the correct landing place; later
 * ids are only fallbacks for a subject whose artifact no longer resolves.
 */
export function primaryTarget(
  finding: AuditFinding,
  targets: FindingTargetMap
): FindingTarget | null {
  for (const id of finding.artifact_ids) {
    const target = targets[id];
    if (target) return target;
  }
  return null;
}
