import { useState, useEffect, type CSSProperties } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { TraceLink, UUID, type LinkType } from "../../types";
import { tracelinksApi } from "../../api/tracelinks";
import { resolveArtifactRef, type ArtifactRef } from "../../api/artifactRefs";
import { getLinkTypeLabel } from "../../constants/traceLinkLabels";
import { CreateTraceLinkDialog } from "./CreateTraceLinkDialog";
import { ConfirmDialog } from "./ConfirmDialog";
import { useWorkspace } from "../../context/WorkspaceContext";
import { extractErrorMessage } from "../../api/client";


interface TraceLinkPanelProps {
  workspaceId: string;
  artifactId: string;
  onDerive?: () => void;
  isDeriving?: boolean;
}

/**
 * UI-P3: badge marking a link whose far endpoint was soft-deleted. Such links
 * are retained by the backend on purpose (audit trail), so they keep arriving
 * from `GET /tracelinks/` and previously rendered as ordinary, live links.
 * Named constant rather than an inline literal — see `src/test/ui-ratchet.test.ts`.
 */
const outdatedBadgeStyle: CSSProperties = {
  fontSize: "0.7rem",
  background: "var(--color-badge-neutral-bg)",
  color: "var(--color-badge-neutral-text)",
  padding: "2px 6px",
  borderRadius: "var(--radius-full)",
  fontWeight: 600,
  whiteSpace: "nowrap",
};

/** Muted, struck-through label for a soft-deleted endpoint. */
const outdatedLabelStyle: CSSProperties = {
  fontSize: "0.85rem",
  color: "var(--color-text-muted)",
  fontFamily: "monospace",
  textDecoration: "line-through",
};

export function TraceLinkPanel({
  workspaceId,
  artifactId,
  onDerive,
  isDeriving,
}: TraceLinkPanelProps): JSX.Element {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { activeWorkspace } = useWorkspace();
  const [links, setLinks] = useState<TraceLink[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // REQ-005: unified CreateTraceLinkDialog replaces the old inline form
  const [showDialog, setShowDialog] = useState(false);
  const [refsById, setRefsById] = useState<Record<UUID, ArtifactRef>>({});
  // UI-09 (systemaudit 2026-08-29, Bug 1): deleting a trace link is
  // destructive and irreversible — require explicit confirmation, matching
  // the pattern already used in ReqTraceLinkPanel.tsx.
  const [pendingDeleteLinkId, setPendingDeleteLinkId] = useState<UUID | null>(null);

  const loadLinks = async () => {
    setLoading(true);
    setError(null);
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
      //
      // #512: only the *other* endpoint of a link is ever rendered
      // (renderLinkItem takes `otherId`), and only the other endpoint is
      // reliably an Artifact id. GET /tracelinks/?artifact_id=<id> echoes the
      // requested id back verbatim as this link's own endpoint
      // (rest_api/views.py::_neighbor_to_dict) — and the editors pass their
      // *entity* id (ArchitectureElement.id, not .artifact_id), which the
      // backend resolves internally but does not translate in the response.
      // Resolving that endpoint therefore meant a
      // GET /api/v1/artifacts/<entity-id>/ that 404s on every panel load, for
      // a title that is never displayed. Resolve only what is rendered.
      const unresolvedIds = new Set<UUID>();
      res.results.forEach((l) => {
        const otherId = l.source_id === artifactId ? l.target_id : l.source_id;
        if (!refsFromBackend[otherId]) unresolvedIds.add(otherId);
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
      setError(extractErrorMessage(err) || t("tracelinks.loadFailed", "Trace links could not be loaded."));
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
      setError(null);
      await tracelinksApi.delete(linkId);
      loadLinks();
    } catch (err) {
      console.error("Delete tracelink failed:", err);
      setError(extractErrorMessage(err) || t("tracelinks.deleteFailed", "Trace link could not be deleted."));
    }
  };

  const confirmDeleteLink = async () => {
    if (!pendingDeleteLinkId) return;
    const linkId = pendingDeleteLinkId;
    setPendingDeleteLinkId(null);
    await handleDelete(linkId);
  };

  const upstream = links.filter((l) => l.target_id === artifactId);
  const downstream = links.filter((l) => l.source_id === artifactId);

  /**
   * UI-P3: is the *far* endpoint of this link soft-deleted?
   *
   * The panel classifies a link by comparing against the raw `artifactId` it
   * queried with (see the #512 endpoint-echo contract in
   * `rest_api/views.py::TraceLinkViewSet.list`), so the far side is the source
   * for an upstream link and the target for a downstream one.
   */
  const isOtherEndpointOutdated = (trace: TraceLink): boolean =>
    trace.target_id === artifactId
      ? (trace.source_is_outdated ?? false)
      : (trace.target_is_outdated ?? false);

  // Links to soft-deleted artifacts stay visible (audit trail) but must not
  // inflate the "how many live relations does this artifact have" counters.
  const liveUpstreamCount = upstream.filter((l) => !isOtherEndpointOutdated(l)).length;
  const liveDownstreamCount = downstream.filter((l) => !isOtherEndpointOutdated(l)).length;

  const renderLinkItem = (trace: TraceLink, otherId: string) => {
    const label = refsById[otherId]?.title || otherId.slice(0, 8);
    const route = refsById[otherId]?.route;
    const isOutdated = isOtherEndpointOutdated(trace);
    return (
      <li
        key={trace.id}
        data-testid={isOutdated ? `trace-link-outdated-${trace.id}` : undefined}
        style={{
          background: "var(--color-surface-raised)",
          border: "1px solid var(--color-border)",
          padding: "var(--space-2) var(--space-3)",
          borderRadius: "var(--radius-md)",
          display: "flex",
          gap: "var(--space-3)",
          alignItems: "center",
          marginBottom: "var(--space-2)",
          opacity: isOutdated ? 0.65 : 1,
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
        {isOutdated ? (
          // The artifact is soft-deleted: every detail route filters outdated
          // rows out, so linking there would only produce a 404. Render a dead,
          // struck-through label plus an explicit badge instead.
          <>
            <span data-testid={`trace-link-label-${trace.id}`} style={outdatedLabelStyle}>
              {label}
            </span>
            <span
              data-testid={`trace-link-outdated-badge-${trace.id}`}
              style={outdatedBadgeStyle}
              title={t(
                "tracelinks.outdatedHint",
                "Das verknüpfte Artefakt wurde gelöscht. Der Link bleibt für den Audit-Trail erhalten."
              )}
            >
              {t("tracelinks.outdated", "Gelöscht")}
            </span>
          </>
        ) : route ? (
          <button
             type="button"
             data-testid={`trace-link-open-${trace.id}`}
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
          data-testid={`trace-link-delete-${trace.id}`}
          onClick={() => setPendingDeleteLinkId(trace.id)}
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
              data-testid="trace-link-derive-btn"
              onClick={onDerive}
              disabled={isDeriving}
              style={{
                background:
                  "linear-gradient(135deg, var(--color-gradient-ai-start), var(--color-gradient-ai-end))",
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
        defaultLinkType={(activeWorkspace?.default_link_type as LinkType) || 'derives-from'}
      />

      {error && (
        <p
          role="alert"
          data-testid="trace-link-panel-error"
          style={{ color: "var(--color-danger)", fontSize: "var(--font-size-sm)", marginBottom: "var(--space-3)" }}
        >
          {error}
        </p>
      )}

      {loading && (
        <p style={{ color: "var(--color-text-muted)", fontSize: "var(--font-size-sm)" }}>{t("loading")}</p>
      )}

      {!loading && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-4)" }}>
          {/* Upstream / Incoming */}
          <div>
            <h4 style={{ margin: "0 0 var(--space-2) 0", fontSize: "0.9rem", color: "var(--color-text-muted)" }}>
              {t("tracelinks.upstream", "Incoming")} {liveUpstreamCount > 0 && <span data-testid="trace-link-upstream-count" style={{ fontSize: "0.8rem", color: "var(--color-badge-info-text)", background: "var(--color-badge-info-bg)", borderRadius: "var(--radius-full)", padding: "2px 6px", marginLeft: "4px" }}>{liveUpstreamCount}</span>}
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

          {/* Downstream / Outgoing */}
          <div>
            <h4 style={{ margin: "0 0 var(--space-2) 0", fontSize: "0.9rem", color: "var(--color-text-muted)" }}>
              {t("tracelinks.downstream", "Outgoing")} {liveDownstreamCount > 0 && <span data-testid="trace-link-downstream-count" style={{ fontSize: "0.8rem", color: "var(--color-badge-info-text)", background: "var(--color-badge-info-bg)", borderRadius: "var(--radius-full)", padding: "2px 6px", marginLeft: "4px" }}>{liveDownstreamCount}</span>}
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

      {pendingDeleteLinkId && (
        <ConfirmDialog
          title={t("traceability.deleteConfirmTitle", "TraceLink löschen")}
          message={t(
            "traceability.deleteConfirmMessage",
            "Diesen TraceLink löschen? Diese Aktion kann nicht rückgängig gemacht werden."
          )}
          confirmLabel={t("actions.delete", "Löschen")}
          onConfirm={() => void confirmDeleteLink()}
          onCancel={() => setPendingDeleteLinkId(null)}
          testId="tracelink-panel-delete-confirm"
        />
      )}
    </div>
  );
}
