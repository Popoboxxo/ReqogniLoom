import { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { TraceLink, UUID } from "../../types";
import { tracelinksApi } from "../../api/tracelinks";
import { resolveArtifactRef, type ArtifactRef } from "../../api/artifactRefs";
import { getLinkTypeLabel } from "../../constants/traceLinkLabels";
import { CreateTraceLinkDialog } from "./CreateTraceLinkDialog";


interface TraceLinkPanelProps {
  workspaceId: string;
  artifactId: string;
  onDerive?: () => void;
  isDeriving?: boolean;
}

export function TraceLinkPanel({
  workspaceId,
  artifactId,
  onDerive,
  isDeriving,
}: TraceLinkPanelProps): JSX.Element {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [links, setLinks] = useState<TraceLink[]>([]);
  const [loading, setLoading] = useState(false);
  // REQ-005: unified CreateTraceLinkDialog replaces the old inline form
  const [showDialog, setShowDialog] = useState(false);
  const [refsById, setRefsById] = useState<Record<UUID, ArtifactRef>>({});

  const loadLinks = async () => {
    setLoading(true);
    try {
      const res = await tracelinksApi.listForArtifact(workspaceId, artifactId);
      setLinks(res.results);

      // REQ-002: build refsById from backend-supplied titles first. For any
      // endpoint that still lacks a title (legacy API response), fall back to
      // resolveArtifactRef (2 extra HTTP calls per artifact). This keeps the
      // panel functional against older backend versions.
      const refsFromBackend: Record<UUID, ArtifactRef> = {};
      res.results.forEach((l) => {
        if (l.source_title && l.source_title.length > 0) {
          refsFromBackend[l.source_id] = {
            title: l.source_title,
            route: l.source_type
              ? `/${l.source_type.toLowerCase().replace("architectureelement", "architecture").replace("testcase", "testcases").replace("stakeholderneed", "needs")}/${l.source_id}`
              : "",
          };
        }
        if (l.target_title && l.target_title.length > 0) {
          refsFromBackend[l.target_id] = {
            title: l.target_title,
            route: l.target_type
              ? `/${l.target_type.toLowerCase().replace("architectureelement", "architecture").replace("testcase", "testcases").replace("stakeholderneed", "needs")}/${l.target_id}`
              : "",
          };
        }
      });

      // For IDs not resolved via backend titles, fall back to resolveArtifactRef.
      const unresolvedIds = new Set<UUID>();
      res.results.forEach((l) => {
        if (!refsFromBackend[l.source_id]) unresolvedIds.add(l.source_id);
        if (!refsFromBackend[l.target_id]) unresolvedIds.add(l.target_id);
      });

      const fallbackEntries = await Promise.all(
        Array.from(unresolvedIds).map(async (id) => {
          try {
            const ref = await resolveArtifactRef(id);
            return [id, ref] as const;
          } catch {
            return [id, { title: id, route: "" }] as const;
          }
        })
      );

      setRefsById({
        ...Object.fromEntries(fallbackEntries),
        ...refsFromBackend, // backend titles take precedence
      });
    } catch (err) {
      console.error("Failed to load trace links", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (workspaceId && artifactId) {
      loadLinks();
    }
  }, [workspaceId, artifactId]);

  const handleDelete = async (linkId: UUID) => {
    try {
      await tracelinksApi.delete(linkId);
      loadLinks();
    } catch (err) {
      console.error("Delete tracelink failed:", err);
    }
  };

  const upstream = links.filter((l) => l.target_id === artifactId);
  const downstream = links.filter((l) => l.source_id === artifactId);

  const renderLinkItem = (trace: TraceLink, otherId: string) => {
    const label = refsById[otherId]?.title || otherId.slice(0, 8);
    const route = refsById[otherId]?.route;
    return (
      <li
        key={trace.id}
        style={{
          background: "var(--color-surface-raised)",
          border: "1px solid var(--color-border)",
          padding: "var(--space-2) var(--space-3)",
          borderRadius: "var(--radius-md)",
          display: "flex",
          gap: "var(--space-3)",
          alignItems: "center",
          marginBottom: "var(--space-2)",
        }}
      >
        <span
          style={{
            fontSize: "0.7rem",
            background: "var(--color-badge-info-bg)",
            color: "var(--color-badge-info-text)",
            padding: "2px 6px",
            borderRadius: "var(--radius-full)",
            fontWeight: 600,
            whiteSpace: "nowrap",
          }}
          data-testid={`trace-type-${trace.link_type}`}
          title={getLinkTypeLabel(trace.link_type)}
        >
          {getLinkTypeLabel(trace.link_type)}
        </span>
        {route ? (
          <button
             type="button"
             onClick={() => navigate(route)}
             style={{
               fontFamily: "monospace",
               background: "none",
               border: "none",
               padding: 0,
               color: "var(--color-primary)",
               cursor: "pointer",
               textDecoration: "underline",
               fontSize: "0.85rem"
             }}
          >
            {label}
          </button>
        ) : (
          <span style={{ fontSize: "0.85rem", color: "var(--color-text)", fontFamily: "monospace" }}>{label}</span>
        )}
        <button
          onClick={() => void handleDelete(trace.id)}
          style={{
            marginLeft: "auto",
            background: "none",
            border: "none",
            color: "var(--color-danger)",
            cursor: "pointer",
            fontSize: "1rem",
            lineHeight: 1,
          }}
          title={t("actions.delete")}
        >
          ×
        </button>
      </li>
    );
  };

  return (
    <div
      style={{
        marginTop: "var(--space-6)",
        padding: "var(--space-4)",
        background: "var(--color-surface)",
        borderRadius: "var(--radius-lg)",
        border: "1px solid var(--color-border)",
        boxShadow: "var(--shadow-card)",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "var(--space-4)",
        }}
      >
        <h3 style={{ margin: 0, fontSize: "1.1rem" }}>{t("tracelinks.panelTitle", "Trace Links")}</h3>
        <div style={{ display: "flex", gap: "var(--space-2)" }}>
          {onDerive && (
            <button
              className="btn-primary"
              onClick={onDerive}
              disabled={isDeriving}
              style={{
                background: "linear-gradient(135deg, #4f6ef7, #8e2de2)",
              }}
            >
              ✨ {isDeriving ? t("actions.deriving", "Ableiten...") : t("actions.derive", "Ableiten")}
            </button>
          )}
          {/* REQ-005: unified CreateTraceLinkDialog opens as modal (no layout shift) */}
          <button
            className="btn-primary"
            data-testid="trace-link-panel-open-dialog"
            onClick={() => setShowDialog(true)}
          >
            {t("actions.newLink", "Neuen Link erstellen")}
          </button>
          <a
            href="/traceability"
            className="btn-secondary"
            onClick={(e) => { e.preventDefault(); navigate('/traceability'); }}
            style={{ textDecoration: "none" }}
          >
            {t("actions.showAll", "Alle anzeigen")}
          </a>
        </div>
      </div>

      {/* Unified create dialog (REQ-005) */}
      <CreateTraceLinkDialog
        workspaceId={workspaceId}
        sourceId={artifactId}
        isOpen={showDialog}
        onClose={() => setShowDialog(false)}
        onCreated={() => { setShowDialog(false); loadLinks(); }}
      />

      {loading && (
        <p style={{ color: "var(--color-text-muted)", fontSize: "var(--font-size-sm)" }}>{t("loading")}</p>
      )}

      {!loading && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-4)" }}>
          {/* Upstream */}
          <div>
            <h4 style={{ margin: "0 0 var(--space-2) 0", fontSize: "0.9rem", color: "var(--color-text-muted)" }}>
              {t("tracelinks.upstream", "Upstream (Parent)")}
            </h4>
            {upstream.length === 0 && (
              <p style={{ color: "var(--color-text-muted)", fontSize: "0.85rem", margin: 0 }}>
                {t("tracelinks.empty", "Keine Links vorhanden.")}
              </p>
            )}
            <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
              {upstream.map((trace) => renderLinkItem(trace, trace.source_id))}
            </ul>
          </div>

          {/* Downstream */}
          <div>
            <h4 style={{ margin: "0 0 var(--space-2) 0", fontSize: "0.9rem", color: "var(--color-text-muted)" }}>
              {t("tracelinks.downstream", "Downstream (Child)")}
            </h4>
            {downstream.length === 0 && (
              <p style={{ color: "var(--color-text-muted)", fontSize: "0.85rem", margin: 0 }}>
                {t("tracelinks.empty", "Keine Links vorhanden.")}
              </p>
            )}
            <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
              {downstream.map((trace) => renderLinkItem(trace, trace.target_id))}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}
