/**
 * RequirementEditors — trace spine + inspector focus (S3.2 WP-5).
 *
 * Extracted verbatim from `RequirementEditors.tsx`: the current-version anchor,
 * the derivation chain and its resolve-endpoint-backed open handler, and the
 * two programmatic focus targets (issue #1762/M1). The shell must not know the
 * detail area's DOM, so these targets live in the route; grouping them with
 * the spine keeps that single responsibility in one module.
 */

import { useCallback, useMemo, useRef } from "react";
import type { RefObject } from "react";

import type { Requirement } from "../../types";
import { buildCurrentVersion } from "./requirement-editors.logic";

export interface UseRequirementInspectorOptions {
  requirement: Requirement | null | undefined;
}

export interface UseRequirementInspectorResult {
  currentVersion: ReturnType<typeof buildCurrentVersion>;
  detailScrollRef: RefObject<HTMLDivElement | null>;
  focusInspectorHeading: () => void;
  focusSpine: () => void;
}

export function useRequirementInspector({
  requirement,
}: UseRequirementInspectorOptions): UseRequirementInspectorResult {
  const currentVersion = useMemo(
    () => buildCurrentVersion(requirement),
    [requirement],
  );

  // #1762 (M1): the inspector's programmatic focus targets. Both live here in
  // the route, not in the shell, because the shell must not know the detail
  // area's DOM (it only receives `coveredRef` for the `inert` bracket).
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
    detailScrollRef,
    focusInspectorHeading,
    focusSpine,
  };
}
