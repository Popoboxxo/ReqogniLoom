/**
 * ARCH-L1-001 ReactFrontend — TraceabilityPanel.
 *
 * leaf_id: COMP-RF-003 (RequirementEditors)
 * req_id:  REQ-L3-RF003-003 (TraceabilityPanel — Upstream/Downstream Links),
 *          REQ-L2-RF-006 (Traceability-Anzeige)
 */

import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import type { TraceLink } from "../../types";

interface TraceabilityPanelProps {
  upstreamLinks: TraceLink[];
  downstreamLinks: TraceLink[];
  linkedTitles: Record<string, string>;
  linkedRoutes?: Record<string, string>;
}

interface LinkItemProps {
  link: TraceLink;
  linkedId: string;
  title: string;
  route?: string;
}

function LinkItem({ link, linkedId, title, route }: LinkItemProps): JSX.Element {
  const navigate = useNavigate();
  const { t } = useTranslation();
  // UI-05: an empty/undefined route means resolveArtifactRefs could not
  // resolve this linked artifact (lookup failure or unknown type). Do not
  // guess a Requirement route in that case — treat the entry as
  // non-navigable instead of silently jumping to the wrong artifact.
  const isNavigable = Boolean(route);

  const handleClick = (): void => {
    if (!isNavigable) return;
    // Navigate to the linked artifact — may be a Requirement, ArchitectureElement
    // or TestCase (REQ-L1-003), not necessarily another Requirement.
    navigate(route as string);
  };

  return (
    <li
      style={{
        padding: "0.3rem 0",
        borderBottom: "1px solid var(--color-border)",
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        gap: "0.5rem",
      }}
    >
      <span
        style={{
          fontSize: "0.8rem",
          flex: 1,
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
          color: "var(--color-text)",
        }}
        title={`${title} (${linkedId.slice(0, 8)}…)`}
      >
        {title}
      </span>
      <span
        style={{
          fontSize: "0.75rem",
          background: "var(--color-badge-draft)",
          color: "var(--color-badge-draft-text)",
          padding: "0.1rem 0.4rem",
          borderRadius: "4px",
          flexShrink: 0,
        }}
      >
        {link.link_type}
      </span>
      <button
        onClick={handleClick}
        disabled={!isNavigable}
        title={isNavigable ? undefined : t("traceability.unresolved")}
        // #741: the arrow glyph is the entire button content, so without an
        // aria-label the accessible name is literally "→". Names the target,
        // not the glyph, so a screen-reader user can tell the rows apart.
        aria-label={`${t("traceability.openLinked", "Verknüpftes Artefakt öffnen")}: ${title}`}
        style={{
          fontSize: "0.75rem",
          cursor: isNavigable ? "pointer" : "not-allowed",
          opacity: isNavigable ? 1 : 0.4,
          flexShrink: 0,
        }}
      >
        <span aria-hidden="true">→</span>
      </button>
    </li>
  );
}

export function TraceabilityPanel({
  upstreamLinks,
  downstreamLinks,
  linkedTitles,
  linkedRoutes,
}: TraceabilityPanelProps): JSX.Element {
  const { t } = useTranslation();

  return (
    <aside
      data-testid="traceability-panel"
      style={{
        borderLeft: "1px solid var(--color-border)",
        paddingLeft: "1rem",
        minWidth: "200px",
      }}
    >
      <h4 style={{ margin: "0 0 0.5rem" }}>{t("traceability.upstream")}</h4>
      {upstreamLinks.length === 0 ? (
        <p style={{ fontSize: "0.85rem", color: "var(--color-text-muted)" }}>
          {t("traceability.none")}
        </p>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {upstreamLinks.map((l) => (
            <LinkItem
              key={l.id}
              link={l}
              linkedId={l.source_id}
              title={linkedTitles[l.source_id] || `(${l.source_id.slice(0, 8)}…)`}
              route={linkedRoutes?.[l.source_id]}
            />
          ))}
        </ul>
      )}

      <h4 style={{ margin: "1rem 0 0.5rem" }}>{t("traceability.downstream")}</h4>
      {downstreamLinks.length === 0 ? (
        <p style={{ fontSize: "0.85rem", color: "var(--color-text-muted)" }}>
          {t("traceability.none")}
        </p>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {downstreamLinks.map((l) => (
            <LinkItem
              key={l.id}
              link={l}
              linkedId={l.target_id}
              title={linkedTitles[l.target_id] || `(${l.target_id.slice(0, 8)}…)`}
              route={linkedRoutes?.[l.target_id]}
            />
          ))}
        </ul>
      )}
    </aside>
  );
}
