/**
 * ArtifactInspector — barrel export.
 *
 * leaf_id: COMP-RF-014 (ArtifactInspector)
 * req_id:  REQ-L2-RF-034..037
 *
 * Pages import from this module to avoid reaching into the
 * individual files (e.g. `import { RightSidebar } from
 * "components/shared/ArtifactInspector"`).
 *
 * Named exports only — no default export (project coding convention).
 */
export { RightSidebar } from "./RightSidebar";
export type { RightSidebarProps } from "./RightSidebar";

export { VersionPanel } from "./VersionPanel";
export type { VersionPanelProps } from "./VersionPanel";

export { DiffPanel } from "./DiffPanel";
export type { DiffPanelProps } from "./DiffPanel";

export { TracePanel } from "./TracePanel";
export type { TracePanelProps } from "./TracePanel";

export { ALL_LINK_TYPES, DIFF_SUPPORTED_KINDS } from "./types";
export type {
  ArtifactKind,
  BaselineSummary,
  LinkType,
  TraceLinkRow,
  VersionRef,
} from "./types";
