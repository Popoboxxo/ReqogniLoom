/**
 * ARCH-L1-001 ReactFrontend — TraceabilityPanel.
 *
 * leaf_id: COMP-RF-003 (RequirementEditors)
 * req_id:  REQ-L3-RF003-003 (TraceabilityPanel — Upstream/Downstream Links),
 *          REQ-L2-RF-006 (Traceability-Anzeige)
 */

import React from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import type { TraceLink } from "../../types";

interface TraceabilityPanelProps {
  upstreamLinks: TraceLink[];
  downstreamLinks: TraceLink[];
}

function LinkItem({ link }: { link: TraceLink }): JSX.Element {
  const navigate = useNavigate();

  const handleClick = (): void => {
    // Navigate to the linked artifact (requirement)
    navigate(`/requirements/${link.source_id}`);
  };

  return (
    <li
      style={{
        padding: "0.3rem 0",
        borderBottom: "1px solid #eee",
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
      }}
    >
      <span style={{ fontFamily: "monospace", fontSize: "0.8rem" }}>
        {link.source_id.slice(0, 8)}…
      </span>
      <span
        style={{
          fontSize: "0.75rem",
          background: "#eef",
          padding: "0.1rem 0.4rem",
          borderRadius: "4px",
        }}
      >
        {link.link_type}
      </span>
      <button
        onClick={handleClick}
        style={{ fontSize: "0.75rem", cursor: "pointer" }}
      >
        →
      </button>
    </li>
  );
}

export function TraceabilityPanel({
  upstreamLinks,
  downstreamLinks,
}: TraceabilityPanelProps): JSX.Element {
  const { t } = useTranslation();

  return (
    <aside
      data-testid="traceability-panel"
      style={{
        borderLeft: "1px solid #ddd",
        paddingLeft: "1rem",
        minWidth: "200px",
      }}
    >
      <h4 style={{ margin: "0 0 0.5rem" }}>{t("traceability.upstream")}</h4>
      {upstreamLinks.length === 0 ? (
        <p style={{ fontSize: "0.85rem", color: "#888" }}>
          {t("traceability.none")}
        </p>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {upstreamLinks.map((l) => (
            <LinkItem key={l.id} link={l} />
          ))}
        </ul>
      )}

      <h4 style={{ margin: "1rem 0 0.5rem" }}>{t("traceability.downstream")}</h4>
      {downstreamLinks.length === 0 ? (
        <p style={{ fontSize: "0.85rem", color: "#888" }}>
          {t("traceability.none")}
        </p>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {downstreamLinks.map((l) => (
            <LinkItem key={l.id} link={l} />
          ))}
        </ul>
      )}
    </aside>
  );
}
