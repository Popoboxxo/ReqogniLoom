/**
 * ARCH-L1-001 ReactFrontend — <ArtifactRow> (UI concept ch. 12.3 / 12.4).
 *
 * The two-line artifact list row: identity (id + level/type) on the top
 * line, title on the line below — the eye scans for the id when skimming,
 * for the title when reading, and both need their own line (ch. 12.3).
 * Status sits top-right (colour-coded, the *only* colour-coded element per
 * row per ch. 3.3/8.1); version sits outside it, further right, and only
 * from v2 on (ch. 12.4 — "v1" on every row is noise).
 *
 * Selection is shown by a full-row background plus a 3px left edge accent
 * in `--color-primary` — never by text colour (ch. 12.3). This mirrors the
 * selection mechanic `shared/WorkspaceTree`'s `TreeRow` already uses, so a
 * list row and a tree row read as the same interaction language.
 *
 * Composed entirely from the ch. 12.4 identity building blocks
 * (`ArtifactId`, `LevelBadge`, `StatusBadge`, `VersionBadge`) — this
 * component owns layout only, no artifact-type-specific knowledge. Any
 * artifact list (Goals, ADRs, Risks, Issues, TestCases, Requirements, ...)
 * can render its rows with it.
 */

import { ArtifactId } from "../ArtifactId";
import { LevelBadge } from "../LevelBadge";
import { StatusBadge } from "../StatusBadge";
import { VersionBadge } from "../VersionBadge";
import type { BadgeVariant } from "../../../utils/statusBadge";
import styles from "./ArtifactRow.module.css";

export interface ArtifactRowProps {
  /** Semantic identifier (`uid`). Falls back to `idFallback` when empty. */
  id?: string | null;
  /** Shown when `id` is empty, e.g. the first 8 chars of the UUID. */
  idFallback?: string | null;
  /** Tree depth / level, rendered as `L{level}` via `<LevelBadge>`. */
  level?: number | null;
  /** Explicit level/type label, takes precedence over `level`. */
  levelLabel?: string | null;
  title: string;
  /**
   * Workflow status. Optional: some artifact types (ICD, Diagram) carry no
   * status at list-fetch time — a lazily-loaded, per-artifact WorkflowEngine
   * mirror only appears once the detail view fetches it. When omitted, the
   * status badge is not rendered instead of showing an empty pill.
   */
  status?: string;
  /** Optional override for the rendered status label. */
  statusLabel?: string;
  badgeVariant?: BadgeVariant | null;
  /** Rendered as `v{version}`; hidden below v2 (ch. 12.4). */
  version?: number | string | null;
  versionIsCurrent?: boolean;
  selected?: boolean;
  onClick?: () => void;
  testId?: string;
}

export function ArtifactRow({
  id,
  idFallback,
  level,
  levelLabel,
  title,
  status,
  statusLabel,
  badgeVariant,
  version,
  versionIsCurrent = true,
  selected = false,
  onClick,
  testId = "artifact-row",
}: ArtifactRowProps): JSX.Element {
  return (
    <div
      data-testid={testId}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      aria-selected={onClick ? selected : undefined}
      className={`${styles.root} ${selected ? styles.selected : ""}`}
      onClick={onClick}
      onKeyDown={
        onClick
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onClick();
              }
            }
          : undefined
      }
    >
      <div className={styles.topLine}>
        <div className={styles.identity}>
          {/* Copy-to-clipboard is a standalone interaction (ch. 12.4) that
              must not also trigger row selection. */}
          <span onClick={(e) => e.stopPropagation()}>
            <ArtifactId value={id} fallback={idFallback} testId={`${testId}-id`} />
          </span>
          <LevelBadge level={level} label={levelLabel} testId={`${testId}-level`} />
        </div>
        <div className={styles.meta}>
          {status != null && (
            <StatusBadge
              status={status}
              label={statusLabel}
              badgeVariant={badgeVariant}
              testId={`${testId}-status`}
            />
          )}
          {version != null && (
            <VersionBadge version={version} isCurrent={versionIsCurrent} hideWhenFirst />
          )}
        </div>
      </div>
      <div className={styles.title} title={title}>
        {title}
      </div>
    </div>
  );
}

ArtifactRow.displayName = "ArtifactRow";
