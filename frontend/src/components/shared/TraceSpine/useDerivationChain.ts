/**
 * ARCH-L1-001 ReactFrontend — derivation chain for <TraceSpine>.
 *
 * UI concept ch. 5. Resolves the stations around the currently opened
 * artifact from the trace graph.
 *
 * ## Why this is composed client-side
 *
 * There is no "give me the derivation chain of artifact X" endpoint, and this
 * change deliberately does not add one. The chain is therefore assembled from
 * two calls to the existing neighbourhood query
 * `GET /tracelinks/impact/?artifact_id=…&direction=incoming|outgoing`, which
 * returns every reachable artifact with its `artifact_type`, `link_type`,
 * `depth` and the `path` it was reached through.
 *
 * ## How stations are formed (ch. 5.1/5.2)
 *
 * The number of stations is NOT fixed:
 *
 *  - Stakeholder needs and requirements each form one station.
 *  - Architecture elements form one station **per real tree depth**. The
 *    depth comes from `ArchitectureElement.level`, which the backend already
 *    annotates via the CTE (`get_level()`), so a workspace with one subsystem
 *    layer shows one, and one with six shows six. No empty placeholder
 *    stations are rendered.
 *  - Test cases are NOT a station. Verification is a link type, not a level
 *    (ch. 5.1) — a test case attaches to whichever artifact it verifies, so
 *    it is counted into the verification badge of *that* artifact's station.
 *
 * ## Known limitation (documented gap)
 *
 * `impact` walks outwards from the opened artifact only. A test case that
 * verifies an ancestor but is not reachable from here is therefore not
 * counted. Attribution uses the second-to-last entry of a node's `path` —
 * the artifact the test was reached through — which is exact for the
 * ordinary `TestCase --verifies--> X` shape and approximate for longer
 * chains. Making this exact needs a per-station coverage query on the
 * backend; until then the badge is a lower bound, never an overstatement.
 */

import { useEffect, useMemo, useState } from "react";
import { tracelinksApi, type ImpactNode } from "../../../api/tracelinks";
import { extractErrorMessage } from "../../../api/client";
import type { ArchitectureElement, UUID } from "../../../types";

export const ARTIFACT_TYPE_NEED = "StakeholderNeed";
export const ARTIFACT_TYPE_REQUIREMENT = "Requirement";
export const ARTIFACT_TYPE_ARCHITECTURE = "ArchitectureElement";
export const ARTIFACT_TYPE_TESTCASE = "TestCase";

/** Link types that mean "a test case verifies this artifact". */
const VERIFICATION_LINK_TYPES = new Set(["verifies", "tests"]);

/** Relation of a station to the opened artifact (ch. 5 "Zeichensprache"). */
export type StationDirection = "origin" | "current" | "derived";

export interface ChainArtifact {
  id: UUID;
  title: string;
  uid: string | null;
  artifactType: string;
  linkType: string;
}

export interface ChainStation {
  /** Stable key, e.g. `Requirement` or `ArchitectureElement:2`. */
  key: string;
  artifactType: string;
  /** Architecture tree depth; null for types without a depth. */
  level: number | null;
  direction: StationDirection;
  /** Artifacts sitting on this station (excluding the opened one). */
  artifacts: ChainArtifact[];
  /** Test cases attributed to artifacts of this station. */
  verifications: ChainArtifact[];
  /** True for the station the opened artifact itself occupies. */
  isCurrent: boolean;
}

export interface DerivationChain {
  stations: ChainStation[];
  isLoading: boolean;
  error: string | null;
}

/** Sort weight so needs come before requirements before architecture. */
function typeRank(artifactType: string): number {
  switch (artifactType) {
    case ARTIFACT_TYPE_NEED:
      return 0;
    case ARTIFACT_TYPE_REQUIREMENT:
      return 1;
    case ARTIFACT_TYPE_ARCHITECTURE:
      return 2;
    default:
      return 3;
  }
}

function normalizeType(artifactType: string): string {
  // Backend allows sub-typing via "TestCase:unit" (normalize_artifact_type).
  return (artifactType || "").split(":", 1)[0];
}

function stationKey(artifactType: string, level: number | null): string {
  return level == null ? artifactType : `${artifactType}:${level}`;
}

interface UseDerivationChainOptions {
  /**
   * Architecture elements of the workspace, already loaded by the host view.
   * Used to resolve the real tree depth of architecture stations without a
   * second round trip.
   */
  architectureElements?: ArchitectureElement[];
  /** Depth limit for the neighbourhood walk. */
  maxDepth?: number;
  enabled?: boolean;
}

export function useDerivationChain(
  artifactId: UUID | null | undefined,
  currentArtifactType: string,
  currentLevel: number | null,
  options: UseDerivationChainOptions = {},
): DerivationChain {
  const { architectureElements = [], maxDepth = 6, enabled = true } = options;

  const [incoming, setIncoming] = useState<ImpactNode[]>([]);
  const [outgoing, setOutgoing] = useState<ImpactNode[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!artifactId || !enabled) {
      setIncoming([]);
      setOutgoing([]);
      setError(null);
      return;
    }
    let cancelled = false;
    setIsLoading(true);
    setError(null);

    // The whole call sits inside the async function on purpose: the spine is
    // an auxiliary view on top of an artifact editor and must never be able
    // to unmount its host. A synchronous throw (missing endpoint wrapper,
    // stubbed client) would escape a bare `.catch()` on Promise.all and take
    // the surrounding editor down with it.
    void (async () => {
      try {
        const [inc, out] = await Promise.all([
          tracelinksApi.impact(artifactId, { direction: "incoming", maxDepth }),
          tracelinksApi.impact(artifactId, { direction: "outgoing", maxDepth }),
        ]);
        if (cancelled) return;
        // Defensive: an unexpected envelope must not crash the detail view.
        setIncoming(Array.isArray(inc) ? inc : []);
        setOutgoing(Array.isArray(out) ? out : []);
      } catch (err: unknown) {
        if (cancelled) return;
        setIncoming([]);
        setOutgoing([]);
        setError(extractErrorMessage(err));
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [artifactId, enabled, maxDepth]);

  /** artifact id -> architecture tree depth, for station bucketing. */
  const levelByArtifactId = useMemo(() => {
    const map = new Map<string, number>();
    for (const el of architectureElements) {
      // The impact graph is keyed by Artifact id, the element list by both —
      // register whichever ids we have so lookups hit either way.
      if (el.artifact_id) map.set(el.artifact_id, el.level ?? 0);
      map.set(el.id, el.level ?? 0);
    }
    return map;
  }, [architectureElements]);

  const stations = useMemo((): ChainStation[] => {
    if (!artifactId) return [];

    const currentType = normalizeType(currentArtifactType);
    const currentKey = stationKey(
      currentType,
      currentType === ARTIFACT_TYPE_ARCHITECTURE ? currentLevel : null,
    );

    const byKey = new Map<string, ChainStation>();
    const ensure = (
      key: string,
      artifactType: string,
      level: number | null,
      direction: StationDirection,
    ): ChainStation => {
      let station = byKey.get(key);
      if (!station) {
        station = {
          key,
          artifactType,
          level,
          direction,
          artifacts: [],
          verifications: [],
          isCurrent: key === currentKey,
        };
        byKey.set(key, station);
      }
      return station;
    };

    // The opened artifact always has a station, even with no links at all.
    ensure(currentKey, currentType, currentType === ARTIFACT_TYPE_ARCHITECTURE ? currentLevel : null, "current");

    const seen = new Set<string>();
    const pendingVerifications: Array<{ node: ImpactNode; viaId: string }> = [];

    const ingest = (nodes: ImpactNode[], direction: StationDirection): void => {
      for (const node of nodes) {
        const type = normalizeType(node.artifact_type);
        if (!node.artifact_id || node.artifact_id === artifactId) continue;

        if (
          type === ARTIFACT_TYPE_TESTCASE ||
          VERIFICATION_LINK_TYPES.has((node.link_type || "").toLowerCase())
        ) {
          // Attribute to the artifact this test was reached through: the
          // second-to-last path entry, or the opened artifact for direct links.
          const path = Array.isArray(node.path) ? node.path : [];
          const viaId = path.length >= 2 ? path[path.length - 2] : artifactId;
          pendingVerifications.push({ node, viaId });
          continue;
        }

        const dedupeKey = `${node.artifact_id}:${direction}`;
        if (seen.has(dedupeKey)) continue;
        seen.add(dedupeKey);

        const level =
          type === ARTIFACT_TYPE_ARCHITECTURE
            ? levelByArtifactId.get(node.artifact_id) ?? 0
            : null;
        const key = stationKey(type, level);
        const station = ensure(key, type, level, direction);
        station.artifacts.push({
          id: node.artifact_id,
          title: node.title || "",
          uid: node.uid ?? null,
          artifactType: type,
          linkType: node.link_type || "",
        });
      }
    };

    ingest(incoming, "origin");
    ingest(outgoing, "derived");

    // Resolve which station each test case belongs to, now that all
    // non-test stations exist.
    const stationByArtifactId = new Map<string, ChainStation>();
    for (const station of byKey.values()) {
      for (const a of station.artifacts) stationByArtifactId.set(a.id, station);
    }
    const currentStation = byKey.get(currentKey);
    if (currentStation) stationByArtifactId.set(artifactId, currentStation);

    const seenVerifications = new Set<string>();
    for (const { node, viaId } of pendingVerifications) {
      const station = stationByArtifactId.get(viaId) ?? currentStation;
      if (!station) continue;
      const dedupeKey = `${station.key}:${node.artifact_id}`;
      if (seenVerifications.has(dedupeKey)) continue;
      seenVerifications.add(dedupeKey);
      station.verifications.push({
        id: node.artifact_id,
        title: node.title || "",
        uid: node.uid ?? null,
        artifactType: normalizeType(node.artifact_type),
        linkType: node.link_type || "",
      });
    }

    return [...byKey.values()].sort((a, b) => {
      const rank = typeRank(a.artifactType) - typeRank(b.artifactType);
      if (rank !== 0) return rank;
      return (a.level ?? 0) - (b.level ?? 0);
    });
  }, [
    artifactId,
    currentArtifactType,
    currentLevel,
    incoming,
    outgoing,
    levelByArtifactId,
  ]);

  return { stations, isLoading, error };
}
