import type { GlossaryReferenceResolution, GlossaryTerm } from "../../types";
import styles from "./GlossaryTooltip.module.css";

interface GlossaryTooltipProps {
  termText: string;
  /** Legacy `@Term` payload (pre-#1266 inline glossary mention). */
  termData?: GlossaryTerm;
  /**
   * #1266: resolved `[[glossary:<uuid>@<rev>]]` reference metadata. When set,
   * the mark shows the resolved version and flags version drift.
   */
  reference?: GlossaryReferenceResolution;
}

/**
 * Highlighted, hoverable glossary mark.
 *
 * Two shapes share one component so the tooltip styling stays in one place:
 * the legacy `@Term` mention (definition only) and the version-bound reference
 * token (definition + resolved version + drift marker).
 */
export function GlossaryTooltip({
  termText,
  termData,
  reference,
}: GlossaryTooltipProps): JSX.Element {
  const version = reference?.resolved_revision;
  const definition = reference?.definition ?? termData?.definition ?? "";
  const title = reference && version ? `${definition} (v${version})` : definition;

  const className = reference?.drift
    ? `${styles.term} ${styles.drift}`
    : styles.term;

  return (
    <span
      className={className}
      title={title}
      data-testid={reference ? "glossary-reference-mark" : undefined}
      data-drift={reference ? (reference.drift ? "true" : "false") : undefined}
      data-version={version}
    >
      {reference ? termText : `@${termText}`}
      {reference && version ? <sup className={styles.version}>v{version}</sup> : null}
    </span>
  );
}
