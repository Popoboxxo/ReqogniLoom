/**
 * ArchitectureEditors — trace spine + inspector focus (S3.2 WP-5).
 *
 * Extracted verbatim from `ArchitectureEditors.tsx`: the current-version
 * anchor, the local Artifact→element id mapping, the spine's openability and
 * open handler, and the two programmatic focus targets (issue #1762/M3). The
 * shell must not know the detail area's DOM, so these targets live in the
 * route; grouping them with the spine keeps that single responsibility in one
 * module.
 */

import { useCallback, useMemo, useRef } from "react";
import type { RefObject } from "react";

import type { ChainArtifact } from "../shared/TraceSpine";
import type { ArchitectureElement } from "../../types";
import {
  buildCurrentVersion,
  buildElementIdByArtifactId,
} from "./architecture-editors.logic";

export interface UseArchitectureInspectorOptions {
  element: ArchitectureElement | null | undefined;
  elements: ArchitectureElement[];
}

export interface UseArchitectureInspectorResult {
  currentVersion: ReturnType<typeof buildCurrentVersion>;
  isChainArtifactOpenable: (artifact: ChainArtifact) => boolean;
  detailScrollRef: RefObject<HTMLDivElement | null>;
  focusInspectorHeading: () => void;
  focusSpine: () => void;
}

export function useArchitectureInspector({
  element,
  elements,
}: UseArchitectureInspectorOptions): UseArchitectureInspectorResult {
  // Feed the ArtifactInspector with the current version (REQ-L2-RF-035).
  const currentVersion = useMemo(() => buildCurrentVersion(element), [element]);

  // The trace graph is keyed by Artifact id, the detail routes take the
  // domain-entity id. For architecture the mapping is available locally
  // (the exhaustive element list carries both), so the footer receives this
  // as its host-side `isOpenable` check.
  const archElementByArtifactId = useMemo(
    () => buildElementIdByArtifactId(elements),
    [elements],
  );

  const isChainArtifactOpenable = useCallback(
    (artifact: ChainArtifact): boolean =>
      artifact.artifactType === 'ArchitectureElement' &&
      archElementByArtifactId.has(artifact.id),
    [archElementByArtifactId],
  );

  // #1762 (M3, mirrors M2): the inspector's programmatic focus targets live in
  // the route, not in the shell — the shell must not know the detail area's DOM
  // (it only receives `coveredRef` for the `inert` bracket).
  const detailScrollRef = useRef<HTMLDivElement | null>(null);

  const focusInspectorHeading = useCallback((): void => {
    document.getElementById('inspector-heading')?.focus();
  }, []);

  // Spec §2.3 rule 1: the Links tab's summary line jumps into the spine. The
  // spine is a separate flex zone now, so this is the one place that knows its
  // first station.
  const focusSpine = useCallback((): void => {
    document
      .querySelector<HTMLElement>('[data-testid="trace-footer-station"]')
      ?.focus();
  }, []);

  return {
    currentVersion,
    isChainArtifactOpenable,
    detailScrollRef,
    focusInspectorHeading,
    focusSpine,
  };
}
