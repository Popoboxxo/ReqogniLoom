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
import { useNavigate } from "react-router-dom";

import { useDerivationChain } from "../shared/TraceSpine";
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
  derivationChain: ReturnType<typeof useDerivationChain>;
  isChainArtifactOpenable: (artifact: ChainArtifact) => boolean;
  handleOpenChainArtifact: (artifact: ChainArtifact) => void;
  detailScrollRef: RefObject<HTMLDivElement | null>;
  focusInspectorHeading: () => void;
  focusSpine: () => void;
}

export function useArchitectureInspector({
  element,
  elements,
}: UseArchitectureInspectorOptions): UseArchitectureInspectorResult {
  const navigate = useNavigate();

  // Feed the ArtifactInspector with the current version (REQ-L2-RF-035).
  const currentVersion = useMemo(() => buildCurrentVersion(element), [element]);

  // The trace graph is keyed by Artifact id, the detail routes take the
  // domain-entity id. For architecture the mapping is available locally
  // (the exhaustive element list carries both).
  const derivationChain = useDerivationChain(
    element?.artifact_id ?? element?.id ?? null,
    'ArchitectureElement',
    element?.level ?? 0,
    { architectureElements: elements, enabled: !!element },
  );

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

  const handleOpenChainArtifact = useCallback(
    (artifact: ChainArtifact): void => {
      const elementId = archElementByArtifactId.get(artifact.id);
      if (artifact.artifactType === 'ArchitectureElement' && elementId) {
        navigate(`/architecture/${elementId}`);
      }
    },
    [archElementByArtifactId, navigate],
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
      .querySelector<HTMLElement>('[data-testid="trace-spine-station-button"]')
      ?.focus();
  }, []);

  return {
    currentVersion,
    derivationChain,
    isChainArtifactOpenable,
    handleOpenChainArtifact,
    detailScrollRef,
    focusInspectorHeading,
    focusSpine,
  };
}
