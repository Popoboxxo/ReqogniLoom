/**
 * ArtifactInspector — barrel export.
 *
 * leaf_id: COMP-RF-014 (ArtifactInspector)
 * req_id:  REQ-L2-RF-034..037, REQ-L1-089, REQ-L1-095
 *
 * Pages import from this module to avoid reaching into the
 * individual files (e.g. `import { InspectorShell } from
 * "components/shared/ArtifactInspector"`).
 *
 * #1762/M8: the tabbed `InspectorShell` is the **only** inspector shell. The
 * stacked sidebar this barrel used to export alongside it is deleted — every
 * artifact route mounts the shell, so there is no second shell to keep
 * importable.
 *
 * Named exports only — no default export (project coding convention).
 */
export { InspectorShell } from "./InspectorShell";
export type { InspectorShellProps } from "./InspectorShell";

export { VersionPanel } from "./VersionPanel";
export type { VersionPanelProps } from "./VersionPanel";

export { DiffPanel } from "./DiffPanel";
export type { DiffPanelProps } from "./DiffPanel";

export { TracePanel } from "./TracePanel";
export type { TracePanelProps } from "./TracePanel";

export { CommentPanel } from "./CommentPanel";
export type { CommentPanelProps } from "./CommentPanel";

export { DIFF_SUPPORTED_KINDS } from "./types";
export type {
  ArtifactKind,
  BaselineSummary,
  LinkType,
  TraceLinkRow,
  VersionRef,
} from "./types";
