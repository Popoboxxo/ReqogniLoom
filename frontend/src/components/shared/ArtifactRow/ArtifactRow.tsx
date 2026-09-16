/**
 * ARCH-L1-001 ReactFrontend — <ArtifactRow> (UI concept ch. 12.3 / 12.4).
 *
 * The artifact list row. Issue #807 changed the reading order: the **title
 * leads** and the identifier becomes a clearly-labelled *secondary*
 * reference on the line below (`ID <short-id>`), because #932 settled that
 * `uid` is a read-only *import* key, not an auto-generated readable
 * identifier — for artifacts without an imported uid the only stable handle
 * is the opaque UUID prefix, and leading with that hash made the list a hash
 * register instead of a work instrument. The status stays top-right
 * (colour-coded, the *only* colour-coded element per row per ch. 3.3/8.1);
 * version sits outside it, further right, and only from v2 on (ch. 12.4 —
 * "v1" on every row is noise).
 *
 * Issue #804 adds an optional, compact SE-attribute line (`attributes`): a
 * labelled chip row below the identifier for the classification a reviewer
 * needs at a glance (category, V-model level, verification method, …). It is
 * deliberately a single, non-wrapping line so the row keeps a predictable
 * height for `shared/WorkspaceTree`'s virtualized lists.
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

import { useTranslation } from "react-i18next";

import { ArtifactId } from "../ArtifactId";
import { LevelBadge } from "../LevelBadge";
import { StatusBadge } from "../StatusBadge";
import { VersionBadge } from "../VersionBadge";
import type { BadgeVariant } from "../../../utils/statusBadge";
import styles from "./ArtifactRow.module.css";

/**
 * One compact secondary attribute on the row's meta line (issue #804).
 * Entries whose `value` is empty are skipped by `<ArtifactRow>`, so callers
 * can build the list declaratively from the API payload without pre-filtering.
 */
export interface ArtifactRowAttribute {
  /** Translated attribute label, e.g. "Kategorie". */
  label: string;
  /** Rendered right of the label. */
  value?: string | number | null;
  /** Native tooltip; defaults to `"{label}: {value}"`. */
  title?: string;
}

export interface ArtifactRowProps {
  /** Semantic identifier (`uid`). Falls back to `idFallback` when empty. */
  id?: string | null;
  /** Shown when `id` is empty, e.g. the first 8 chars of the UUID. */
  idFallback?: string | null;
  /**
   * Visible label in front of the identifier (issue #807), so a short hash
   * reads as a clearly-labelled reference rather than the artifact's name.
   * Defaults to the translated `artifactId.shortLabel` ("ID"); pass `null` to
   * render the identifier unlabelled.
   */
  idLabel?: string | null;
  /** Tree depth / level, rendered as `L{level}` via `<LevelBadge>`. */
  level?: number | null;
  /** Explicit level/type label, takes precedence over `level`. */
  levelLabel?: string | null;
  /**
   * Spelled-out meaning of `levelLabel`/`level`, e.g. "System Requirement
   * (SyReq)" for the "SR" abbreviation (issue #169 — short codes without a
   * legend). Rendered as a native tooltip and exposed to screen readers.
   */
  levelTitle?: string;
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
  /**
   * Compact SE attributes (issue #804). Rendered as a labelled chip line
   * below the identifier; empty values are skipped.
   */
  attributes?: ArtifactRowAttribute[];
  selected?: boolean;
  onClick?: () => void;
  testId?: string;
}

export function ArtifactRow({
  id,
  idFallback,
  idLabel,
  level,
  levelLabel,
  levelTitle,
  title,
  status,
  statusLabel,
  badgeVariant,
  version,
  versionIsCurrent = true,
  attributes,
  selected = false,
  onClick,
  testId = "artifact-row",
}: ArtifactRowProps): JSX.Element {
  const { t } = useTranslation();
  // `undefined` keeps the translated default; `null` explicitly opts out.
  const resolvedIdLabel =
    idLabel === undefined ? t("artifactId.shortLabel", "ID") : idLabel;
  const visibleAttributes = (attributes ?? []).filter(
    (attr) => attr.value != null && String(attr.value).trim() !== "",
  );

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
      {/* Issue #807: the title leads — it is the artifact's name, the hash is
          not. Status/version stay top-right, outside the shrinking title. */}
      <div className={styles.topLine}>
        <div className={styles.title} title={title}>
          {title}
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
      <div className={styles.identity}>
        {/* Copy-to-clipboard is a standalone interaction (ch. 12.4) that
            must not also trigger row selection. */}
        <span className={styles.idGroup} onClick={(e) => e.stopPropagation()}>
          {resolvedIdLabel != null && resolvedIdLabel !== "" && (
            <span className={styles.idLabel}>{resolvedIdLabel}</span>
          )}
          <ArtifactId value={id} fallback={idFallback} testId={`${testId}-id`} />
        </span>
        <LevelBadge
          level={level}
          label={levelLabel}
          title={levelTitle}
          testId={`${testId}-level`}
        />
      </div>
      {visibleAttributes.length > 0 && (
        <ul className={styles.attributes} data-testid={`${testId}-attributes`}>
          {visibleAttributes.map((attr) => (
            <li
              key={attr.label}
              className={styles.attribute}
              data-testid={`${testId}-attribute`}
              title={attr.title ?? `${attr.label}: ${String(attr.value)}`}
            >
              <span className={styles.attributeLabel}>{attr.label}</span>
              <span className={styles.attributeValue}>{String(attr.value)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

ArtifactRow.displayName = "ArtifactRow";
