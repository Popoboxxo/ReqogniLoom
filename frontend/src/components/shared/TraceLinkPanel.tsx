import React, { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { TraceLink, LinkType, UUID, Requirement, ArchitectureElement, TestCase } from "../../types";
import { tracelinksApi } from "../../api/tracelinks";
import { requirementsApi } from "../../api/requirements";
import { architectureApi } from "../../api/architecture";
import { testcasesApi } from "../../api/testcases";
import { resolveArtifactRef, type ArtifactRef } from "../../api/artifactRefs";
import { ALL_LINK_TYPES, getLinkTypeLabel } from "../../constants/traceLinkLabels";

const inputStyle: React.CSSProperties = {
  width: "100%",
  fontSize: "var(--font-size-base)",
  padding: "var(--space-2) var(--space-3)",
  marginBottom: "var(--space-2)",
  boxSizing: "border-box",
  background: "var(--color-surface)",
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-md)",
  color: "var(--color-text)",
  fontFamily: "var(--font-sans)",
};

const labelStyle: React.CSSProperties = {
  fontWeight: 600,
  display: "block",
  marginBottom: "var(--space-1)",
  color: "var(--color-text)",
  fontSize: "var(--font-size-sm)",
};

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
  const [showForm, setShowForm] = useState(false);
  
  const [targetId, setTargetId] = useState<string>("");
  const [linkType, setLinkType] = useState<LinkType>("derives-from");
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [architectureElements, setArchitectureElements] = useState<ArchitectureElement[]>([]);
  const [testCases, setTestCases] = useState<TestCase[]>([]);
  const [refsById, setRefsById] = useState<Record<UUID, ArtifactRef>>({});

  const loadLinks = async () => {
    setLoading(true);
    try {
      const res = await tracelinksApi.listForArtifact(workspaceId, artifactId);
      setLinks(res.results);

      const linkedIds = new Set<UUID>();
      res.results.forEach((l) => {
        linkedIds.add(l.source_id);
        linkedIds.add(l.target_id);
      });
      const refEntries = await Promise.all(
        Array.from(linkedIds).map(
          async (id) => {
             try {
                const ref = await resolveArtifactRef(id);
                return [id, ref] as const;
             } catch {
                return [id, { title: id, route: "" }] as const;
             }
          }
        )
      );
      setRefsById(Object.fromEntries(refEntries));
    } catch (err) {
      console.error("Failed to load trace links", err);
    } finally {
      setLoading(false);
    }
  };

  const loadOptions = async () => {
    try {
      const [reqs, archs, tcs] = await Promise.all([
        requirementsApi.listAll(workspaceId).catch(() => []),
        architectureApi.listAll(workspaceId).catch(() => []),
        testcasesApi.list(workspaceId).then(r => r.results).catch(() => []),
      ]);
      setRequirements(reqs);
      setArchitectureElements(archs);
      setTestCases(tcs);
    } catch (err) {
      console.error("Failed to load target options", err);
    }
  };

  useEffect(() => {
    if (workspaceId && artifactId) {
      loadLinks();
    }
  }, [workspaceId, artifactId]);

  const handleOpenForm = () => {
    loadOptions();
    setShowForm(true);
  };

  const submitForm = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!targetId) {
      setSubmitError(t("traceability.targetRequired", "Target artifact is required"));
      return;
    }
    setIsSubmitting(true);
    setSubmitError(null);
    try {
      await tracelinksApi.create({
        source_id: artifactId,
        target_id: targetId,
        link_type: linkType,
      });
      setShowForm(false);
      setTargetId("");
      loadLinks();
    } catch (err: any) {
      setSubmitError(err?.error?.message || String(err));
    } finally {
      setIsSubmitting(false);
    }
  };

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
            background: "var(--color-badge-draft)",
            color: "var(--color-badge-draft-text)",
            padding: "2px 6px",
            borderRadius: "var(--radius-full)",
          }}
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

  const otherRequirements = requirements.filter((r) => r.id !== artifactId);
  const otherArchitectureElements = architectureElements.filter((a) => a.id !== artifactId);
  const otherTestCases = testCases.filter((t) => t.id !== artifactId);

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
        {!showForm && (
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
            <button className="btn-primary" onClick={handleOpenForm}>
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
        )}
      </div>

      {showForm && (
        <form onSubmit={submitForm} style={{ marginBottom: "var(--space-4)", padding: "var(--space-4)", background: "var(--color-surface-raised)", borderRadius: "var(--radius-md)", border: "1px solid var(--color-border)" }}>
          <label style={labelStyle}>{t("traceability.target")}</label>
          <select
            value={targetId}
            onChange={(e) => setTargetId(e.target.value)}
            disabled={isSubmitting}
            style={inputStyle}
          >
            <option value="">{t("editor.selectOption", "Select Option")} --</option>
            {otherRequirements.length > 0 && (
              <optgroup label={t("traceability.requirementsGroup", "Requirements")}>
                {otherRequirements.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.title || "Untitled"}
                  </option>
                ))}
              </optgroup>
            )}
            {otherArchitectureElements.length > 0 && (
              <optgroup label={t("traceability.architectureGroup", "Architecture")}>
                {otherArchitectureElements.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.title || "Untitled"}
                  </option>
                ))}
              </optgroup>
            )}
            {otherTestCases.length > 0 && (
              <optgroup label={t("traceability.testCasesGroup", "Test Cases")}>
                {otherTestCases.map((tc) => (
                  <option key={tc.id} value={tc.id}>
                    {tc.title || "Untitled"}
                  </option>
                ))}
              </optgroup>
            )}
          </select>

          <label style={labelStyle}>{t("traceability.linkType")}</label>
          <select
            value={linkType}
            onChange={(e) => setLinkType(e.target.value as LinkType)}
            disabled={isSubmitting}
            style={inputStyle}
          >
            {ALL_LINK_TYPES.map((lt) => (
              <option key={lt} value={lt}>
                {getLinkTypeLabel(lt)}
              </option>
            ))}
          </select>

          {submitError && (
            <p style={{ color: "var(--color-danger)", fontSize: "var(--font-size-sm)", margin: "var(--space-2) 0" }}>
              {submitError}
            </p>
          )}

          <div style={{ display: "flex", justifyContent: "flex-end", gap: "var(--space-2)", marginTop: "var(--space-3)" }}>
            <button
              type="button"
              className="btn-ghost"
              onClick={() => setShowForm(false)}
              disabled={isSubmitting}
            >
              {t("actions.cancel")}
            </button>
            <button
              type="submit"
              className="btn-primary"
              disabled={isSubmitting || !targetId}
            >
              {isSubmitting ? t("actions.saving", "Saving...") : t("traceability.submit", "Create Link")}
            </button>
          </div>
        </form>
      )}

      {loading && !showForm && (
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
