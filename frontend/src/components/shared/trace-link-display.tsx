/**
 * TraceLinkDisplay — shared trace-link row renderer (REQ-002).
 *
 * leaf_id : COMP-RF-003-TraceLinkDisplay
 * req_id  : REQ-002 (Trace-Link-Resolver — human-readable titles)
 *
 * Renders a single TraceLink row with the resolved title of the "other"
 * artifact (the endpoint that is NOT the current artifact).  Uses the
 * backend-supplied source_title / target_title fields from the API response
 * (REQ-002) so no extra round-trips are needed.
 *
 * Usage:
 *   <TraceLinkDisplay link={link} currentArtifactId={artifactId} />
 *
 * The component is intentionally stateless and has no side-effects; callers
 * own fetching and deleting.
 */
import type { CSSProperties } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { getLinkTypeLabel } from "../../constants/traceLinkLabels";
import { getArtifactRoute } from "../../utils/artifactRoutes";
import type { TraceLink, UUID } from "../../types";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface TraceLinkDisplayProps {
  /** The trace link to display. */
  link: TraceLink;
  /** ID of the current artifact — used to determine which endpoint is "other". */
  currentArtifactId: UUID;
  /** Called when the user clicks the delete button. Optional. */
  onDelete?: (linkId: UUID) => void;
  /** Extra inline styles for the container li element. */
  style?: CSSProperties;
  /** data-testid prefix (defaults to "trace-link-display"). */
  testIdPrefix?: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Derive the SPA route for the "other" endpoint.
 * Delegates to getArtifactRoute which accepts PascalCase backend artifact_type
 * values (Requirement, ArchitectureElement, TestCase, …) as well as camelCase
 * ArtifactKind aliases — falls back to /requirements when unknown.
 */
function resolveRoute(artifactId: UUID, artifactType: string | undefined): string {
  return getArtifactRoute(artifactType ?? "requirement", artifactId);
}

/**
 * Resolve the display label and route for the "other" endpoint.
 * Priority:
 *   1. Backend-supplied title (source_title / target_title from REQ-002 API)
 *   2. Truncated UUID prefix as last-resort fallback
 */
function resolveOtherEndpoint(
  link: TraceLink,
  currentArtifactId: UUID
): { title: string; route: string; otherId: UUID } {
  const isSource = link.source_id === currentArtifactId;
  const otherId = isSource ? link.target_id : link.source_id;
  const backendTitle = isSource ? link.target_title : link.source_title;
  const artifactType = isSource ? link.target_type : link.source_type;

  const title =
    backendTitle && backendTitle.length > 0
      ? backendTitle
      : `${otherId.slice(0, 8)}…`;

  const route = resolveRoute(otherId, artifactType);

  return { title, route, otherId };
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const containerStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "var(--space-2)",
  padding: "var(--space-2) var(--space-3)",
  background: "var(--color-surface-raised)",
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-md)",
  marginBottom: "var(--space-2)",
  fontSize: "var(--font-size-sm)",
  color: "var(--color-text)",
  listStyle: "none",
};

const badgeStyle: CSSProperties = {
  fontSize: "0.7rem",
  background: "var(--color-badge-draft)",
  color: "var(--color-badge-draft-text)",
  padding: "2px 6px",
  borderRadius: "var(--radius-full)",
  flexShrink: 0,
};

const linkButtonStyle: CSSProperties = {
  fontFamily: "monospace",
  background: "none",
  border: "none",
  padding: 0,
  color: "var(--color-primary)",
  cursor: "pointer",
  textDecoration: "underline",
  fontSize: "0.85rem",
  overflow: "hidden",
  textOverflow: "ellipsis",
  whiteSpace: "nowrap",
};

const titleSpanStyle: CSSProperties = {
  fontSize: "0.85rem",
  color: "var(--color-text)",
  overflow: "hidden",
  textOverflow: "ellipsis",
  whiteSpace: "nowrap",
};

const deleteButtonStyle: CSSProperties = {
  marginLeft: "auto",
  background: "none",
  border: "none",
  color: "var(--color-danger)",
  cursor: "pointer",
  fontSize: "1rem",
  lineHeight: 1,
  flexShrink: 0,
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * Shared trace-link row component (REQ-002).
 *
 * Displays link_type badge + resolved title for the "other" endpoint.
 * If the backend already provides source_title/target_title, uses them
 * directly; otherwise falls back to the truncated UUID prefix.
 */
export function TraceLinkDisplay({
  link,
  currentArtifactId,
  onDelete,
  style,
  testIdPrefix = "trace-link-display",
}: TraceLinkDisplayProps): JSX.Element {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { title, route } = resolveOtherEndpoint(link, currentArtifactId);

  return (
    <li
      data-testid={`${testIdPrefix}-item`}
      style={{ ...containerStyle, ...style }}
    >
      <span
        data-testid={`${testIdPrefix}-badge`}
        style={badgeStyle}
      >
        {getLinkTypeLabel(link.link_type)}
      </span>

      {route ? (
        <button
          type="button"
          data-testid={`${testIdPrefix}-title`}
          onClick={() => navigate(route)}
          style={linkButtonStyle}
          title={title}
        >
          {title}
        </button>
      ) : (
        <span
          data-testid={`${testIdPrefix}-title`}
          style={titleSpanStyle}
          title={title}
        >
          {title}
        </span>
      )}

      {onDelete && (
        <button
          type="button"
          data-testid={`${testIdPrefix}-delete`}
          onClick={() => onDelete(link.id)}
          style={deleteButtonStyle}
          title={t("actions.delete")}
          aria-label={t("actions.delete")}
        >
          ×
        </button>
      )}
    </li>
  );
}
