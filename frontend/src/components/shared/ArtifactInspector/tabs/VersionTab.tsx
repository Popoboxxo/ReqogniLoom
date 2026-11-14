/**
 * ArtifactInspector — "Version" tab (issue #1762, M1).
 *
 * Presentation wrapper: the tab area is the existing VersionPanel in
 * `variant="tab"` (no own heading, no own live region — the shell owns both,
 * spec §2.1/§5.3). Its data contract is unchanged.
 */

import { VersionPanel } from "../VersionPanel";
import type { ArtifactKind, VersionRef } from "../types";

export interface VersionTabProps {
  kind: ArtifactKind;
  entityId: string | number;
  currentVersion: VersionRef | undefined;
  onSwitch: (version: number) => void;
  onCompare: (a: number, b: number) => void;
}

export function VersionTab(props: VersionTabProps): JSX.Element {
  return <VersionPanel {...props} variant="tab" />;
}
