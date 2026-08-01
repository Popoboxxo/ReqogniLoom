/**
 * ARCH-L1-001 ReactFrontend — <VersionBadge> (UI concept ch. 12.4).
 *
 * The release state is the second-most important piece of information on an
 * artifact (ch. 2) — but it is *not* a workflow status, so it renders
 * neutral. It used to be filled with `--color-primary`, which put a third
 * meaning on the colour channel next to type and status (ch. 8.1).
 *
 * The current/superseded distinction is kept, now carried by border weight
 * and emphasis instead of hue, so it survives the "colour belongs to state"
 * rule (ch. 3.3) without losing information in the version timeline.
 */

import { useTranslation } from "react-i18next";

interface VersionBadgeProps {
  version: number | string;
  isCurrent?: boolean;
  /**
   * UI concept ch. 12.4: in list rows the badge only appears from version 2
   * — "v1" on every row is noise. Detail headers and the version timeline
   * keep showing it, hence opt-in rather than default.
   */
  hideWhenFirst?: boolean;
}

export function VersionBadge({
  version,
  isCurrent = true,
  hideWhenFirst = false,
}: VersionBadgeProps): JSX.Element | null {
  const { t } = useTranslation();

  if (hideWhenFirst && Number(version) <= 1) return null;

  return (
    <span
      data-testid="version-badge"
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        marginLeft: "var(--space-2)",
        padding: "2px 8px",
        borderRadius: "var(--radius-sm)",
        background: "var(--color-badge-neutral-bg)",
        border: `1px solid ${isCurrent ? "var(--color-border-hover)" : "transparent"}`,
        color: "var(--color-badge-neutral-text)",
        opacity: isCurrent ? 1 : 0.7,
        fontFamily: "var(--font-mono)",
        fontSize: "var(--font-size-xs)",
        fontWeight: isCurrent ? "var(--weight-semibold)" : "var(--weight-regular)",
        fontVariantNumeric: "tabular-nums",
        letterSpacing: "var(--tracking-normal)",
        verticalAlign: "middle",
        whiteSpace: "nowrap",
      }}
      title={isCurrent ? t("icds.current", "Current Version") : t("icds.superseded", "Superseded Version")}
    >
      v{version}
    </span>
  );
}

interface TimelineEntry {
  version_number: number | string;
  is_current: boolean;
  created_at: string | null;
}

interface VersionTimelineProps {
  timeline: TimelineEntry[];
  formatDate?: (iso: string | null | undefined) => string;
}

export function VersionTimeline({ timeline, formatDate = (iso) => iso ? new Date(iso).toLocaleString() : "—" }: VersionTimelineProps): JSX.Element {
  const { t } = useTranslation();
  if (!timeline || timeline.length === 0) {
    return <p style={{ color: "var(--color-text-muted)", fontSize: "var(--font-size-sm)", margin: 0 }}>—</p>;
  }
  return (
    <ol
      style={{
        listStyle: "none",
        padding: 0,
        margin: 0,
        borderLeft: "2px solid var(--color-border)",
        paddingLeft: "var(--space-4)",
      }}
    >
      {timeline
        .slice()
        .reverse()
        .map((entry) => (
          <li
            key={entry.version_number}
            style={{
              position: "relative",
              paddingBottom: "var(--space-3)",
            }}
          >
            <span
              aria-hidden="true"
              style={{
                position: "absolute",
                left: "-22px",
                top: "4px",
                width: "10px",
                height: "10px",
                borderRadius: "var(--radius-full)",
                background: entry.is_current ? "var(--color-primary)" : "var(--color-text-muted)",
              }}
            />
            <div style={{ fontWeight: 600, color: "var(--color-text)", fontSize: "var(--font-size-sm)", display: "flex", alignItems: "center" }}>
              {t("icds.versionBadge", { n: entry.version_number })}
              <VersionBadge version={entry.version_number} isCurrent={entry.is_current} />
            </div>
            <div style={{ color: "var(--color-text-muted)", fontSize: "var(--font-size-xs)", marginTop: "4px" }}>
              {formatDate(entry.created_at)}
            </div>
          </li>
        ))}
    </ol>
  );
}
