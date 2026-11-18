/**
 * ArchitectureEditors — pure view helpers (S3.2 WP-5 split by cohesion).
 *
 * Extracted verbatim from `ArchitectureEditors.tsx`: the list filter, the tree
 * node/summary builders, the two id maps used by reparenting and the trace
 * spine, the current-version anchor and the AI-action descriptor list. They are
 * plain functions of their inputs (the translator is injected), so they can be
 * unit-tested without mounting the route; the component keeps the hooks, the
 * action callbacks and all JSX.
 *
 * No behaviour change: bodies, defaults and ordering are the ones that used to
 * live in the component.
 */

import type { TFunction } from "i18next";
import type { ArchitectureElement } from "../../types";
import type { WorkspaceTreeNode } from "../shared/WorkspaceTree";
import type { LockMap } from "../../api/locks";
import type { VersionRef } from "../shared/ArtifactInspector";
import type { AiActionDescriptor } from "../shared/AiActions";

// REQ-175: ArchitectureElement.lifecycle_status values (see types/index.ts).
// 'deleted' is intentionally omitted — deleted elements are hidden in
// normal views (REQ-006).
export const ARCH_LIFECYCLE_STATUSES = ['active', 'outdated', 'deprecated'] as const;

/** Filter elements by search and lifecycle status (the client-side half of the list toolbar). */
export function filterElements(
  elements: ArchitectureElement[],
  listSearch: string,
  statusFilter: string,
): ArchitectureElement[] {
  const q = listSearch.trim().toLowerCase();
  return elements.filter((el) => {
    if (statusFilter && (el.lifecycle_status ?? 'active') !== statusFilter) {
      return false;
    }
    if (!q) return true;
    return (
      el.title.toLowerCase().includes(q) ||
      Boolean(el.uid && el.uid.toLowerCase().includes(q))
    );
  });
}

/** Convert the filtered domain rows into the tree's display nodes. */
export function buildTreeNodes(
  filteredElements: ArchitectureElement[],
  locks: LockMap,
  t: TFunction,
): WorkspaceTreeNode[] {
  return filteredElements.map((el) => ({
    id: el.id,
    name: el.title || t('editor.untitled'),
    // Issue #932: show the readable local uid in the tree, not just in search.
    identifier: el.uid,
    parentId: el.parent_id ?? null,
    level: el.level != null ? `L${el.level}` : 'L0',
    outdated:
      el.lifecycle_status === 'outdated' || el.lifecycle_status === 'deprecated',
    // P4.4: workflow lock — disables drag, Alt+↑/↓ and "Move…" for this row.
    locked: locks[el.id] ? { state: locks[el.id] } : null,
  }));
}

/** UI concept ch. 12.1: always-visible summary line. */
export function buildArchSummary(
  elements: ArchitectureElement[],
  t: TFunction,
): string {
  // `lifecycle_status` defaults to 'active' server-side, so an absent value
  // counts as active here too.
  const active = elements.filter(
    (el) => (el.lifecycle_status ?? 'active') === 'active',
  ).length;
  return [
    t('arch.summary', { count: elements.length, defaultValue: `${elements.length}` }),
    t('arch.activeSuffix', { count: active, defaultValue: `${active} active` }),
  ].join(' · ');
}

/** Element id → backing Artifact id (with an identity fallback). */
export function buildArtifactIdMap(
  elements: ArchitectureElement[],
): Map<string, string> {
  return new Map<string, string>(
    elements.map((el) => [el.id, el.artifact_id ?? el.id]),
  );
}

/**
 * Artifact id → element id, with the element id itself as an additional key.
 * The trace graph is keyed by Artifact id while detail routes take the domain
 * entity id; architecture has the mapping locally (the exhaustive element
 * list carries both).
 */
export function buildElementIdByArtifactId(
  elements: ArchitectureElement[],
): Map<string, string> {
  const map = new Map<string, string>();
  for (const el of elements) {
    if (el.artifact_id) map.set(el.artifact_id, el.id);
    map.set(el.id, el.id);
  }
  return map;
}

/** Resolve a tree node id to the Artifact id the move endpoint expects. */
export function resolveArtifactId(
  map: Map<string, string>,
  nodeId: string | null,
): string | null {
  return nodeId === null ? null : (map.get(nodeId) ?? nodeId);
}

/** Feed the ArtifactInspector with the current version row. */
export function buildCurrentVersion(
  element: ArchitectureElement | null | undefined,
): VersionRef | undefined {
  if (!element) return undefined;
  return {
    version: element.version,
    label: `v${element.version}`,
    createdAt: element.updated_at ?? element.created_at,
    baselineIds: [],
  };
}

/** The route's AI-action set: decompose + element-scoped risk derivation. */
export function buildAiActions(
  element: ArchitectureElement | null | undefined,
  t: TFunction,
  openDecomposePanel: () => void,
  openRiskDialog: () => void | Promise<void>,
  riskLoading: boolean,
): AiActionDescriptor[] {
  if (!element) return [];
  return [
    {
      label: t("archDecompose.trigger"),
      hint: t("archDecompose.triggerHint"),
      onClick: openDecomposePanel,
      testId: "arch-decompose-btn",
    },
    {
      label: t("aiDerivation.riskAction"),
      hint: t("aiActions.hint"),
      onClick: () => void openRiskDialog(),
      disabled: riskLoading,
      testId: "arch-derive-risks-btn",
    },
  ];
}
