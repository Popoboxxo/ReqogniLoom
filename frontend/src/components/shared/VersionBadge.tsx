import React from "react";
import { useTranslation } from "react-i18next";

interface VersionBadgeProps {
  version: number | string;
  isCurrent?: boolean;
}

export function VersionBadge({ version, isCurrent = true }: VersionBadgeProps): JSX.Element {
  const { t } = useTranslation();
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
        background: isCurrent ? "var(--color-primary)" : "var(--color-text-muted)",
        color: "white",
        fontSize: "var(--font-size-xs)",
        fontWeight: 600,
        textTransform: "uppercase",
        letterSpacing: "0.05em",
        verticalAlign: "middle",
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
