/**
 * ARCH-L1-001 ReactFrontend — ArchTraceLinkPanel.
 *
 * leaf_id: COMP-RF-004 (ArchitectureEditors)
 * req_id:  REQ-L2-RF-006 (Traceability-Anzeige),
 *          REQ-L3-RF004-003 (Verknüpfte Requirements in Seitenleiste)
 *
 * Extracted from ArchitectureEditors.tsx so it can be reused and to give the
 * data-testid a stable home. Mirrors the ReqTraceLinkPanel (RequirementEditors)
 * structure but for the architecture-element side of the link graph.
 *
 * Fix B-TR-001: This panel now offers a real source-select (all architecture
 * elements except the current one) so architects can link ANY architecture
 * element to any target — not just the currently-open one.
 */

import React, { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { tracelinksApi } from "../../api/tracelinks";
import { requirementsApi } from "../../api/requirements";
import { architectureApi } from "../../api/architecture";
import type {
  ArchitectureElement,
  LinkType,
  Requirement,
  TraceLink,
  UUID,
} from "../../types";

const ARCH_LINK_TYPES: LinkType[] = [
  "satisfies",
  "implements",
  "verifies",
  "derives-from",
];

const panelInputStyle: React.CSSProperties = {
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

const panelLabelStyle: React.CSSProperties = {
  fontWeight: 600,
  display: "block",
  marginBottom: "var(--space-1)",
  color: "var(--color-text)",
  fontSize: "var(--font-size-sm)",
};

const panelPrimaryBtn: React.CSSProperties = {
  background: "var(--color-primary)",
  color: "#ffffff",
  border: "none",
  borderRadius: "var(--radius-md)",
  padding: "var(--space-2) var(--space-4)",
  fontSize: "var(--font-size-sm)",
  fontWeight: 600,
  cursor: "pointer",
};

export interface ArchTraceLinkPanelProps {
  workspaceId: UUID;
  elementId: UUID;
}

export function ArchTraceLinkPanel({
  workspaceId,
  elementId,
}: ArchTraceLinkPanelProps): JSX.Element {
  const { t } = useTranslation();
  const [links, setLinks] = useState<TraceLink[]>([]);
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [architectureElements, setArchitectureElements] = useState<
    ArchitectureElement[]
  >([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState<boolean>(false);
  const [sourceId, setSourceId] = useState<string>(elementId);
  const [targetId, setTargetId] = useState<string>("");
  const [linkType, setLinkType] = useState<LinkType>("satisfies");
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState<number>(0);

  // Keep the source-id default in sync if the parent swaps the active element.
  useEffect(() => {
    setSourceId(elementId);
  }, [elementId]);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setError(null);

    async function load(): Promise<void> {
      try {
        const [linksResp, allReqs, allArch] = await Promise.all([
          tracelinksApi.listForArtifact(workspaceId, elementId),
          requirementsApi.listAll(workspaceId),
          architectureApi.listAll(workspaceId),
        ]);
        if (cancelled) return;
        setLinks(linksResp.results);
        setRequirements(allReqs);
        setArchitectureElements(allArch);
      } catch (err: unknown) {
        if (cancelled) return;
        const msg =
          (err as { error?: { message?: string } })?.error?.message ??
          String(err);
        setError(msg);
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [workspaceId, elementId, reloadKey]);

  const requirementsById: Record<UUID, Requirement> = useMemo(() => {
    const m: Record<UUID, Requirement> = {};
    for (const r of requirements) m[r.id] = r;
    return m;
  }, [requirements]);

  const archById: Record<UUID, ArchitectureElement> = useMemo(() => {
    const m: Record<UUID, ArchitectureElement> = {};
    for (const a of architectureElements) m[a.id] = a;
    return m;
  }, [architectureElements]);

  // The source-select lists all arch elements except the currently-open one
  // (linking the element to itself is rejected by the backend).
  const otherArchElements = useMemo(
    () => architectureElements.filter((a) => a.id !== elementId),
    [architectureElements, elementId]
  );

  function openForm(): void {
    setSourceId(elementId);
    setTargetId("");
    setLinkType("satisfies");
    setSubmitError(null);
    setShowForm(true);
  }

  function cancelForm(): void {
    setShowForm(false);
    setSubmitError(null);
  }

  async function submitForm(
    e: React.FormEvent<HTMLFormElement>
  ): Promise<void> {
    e.preventDefault();
    if (!sourceId) {
      setSubmitError(t("traceability.sourceRequired"));
      return;
    }
    if (!targetId) {
      setSubmitError(t("traceability.targetRequired"));
      return;
    }
    setIsSubmitting(true);
    setSubmitError(null);
    try {
      await tracelinksApi.create({
        source_id: sourceId,
        target_id: targetId,
        link_type: linkType,
      });
      setShowForm(false);
      setTargetId("");
      setReloadKey((k) => k + 1);
    } catch (err: unknown) {
      const apiErr = err as {
        error?: {
          message?: string;
          details?: { field?: string; errors?: string[] }[];
        };
      };
      const baseMsg = apiErr?.error?.message;
      const firstDetail = apiErr?.error?.details?.[0];
      const detailMsg = firstDetail
        ? `${firstDetail.field ?? ""}: ${(firstDetail.errors ?? []).join(", ")}`
        : "";
      const msg = baseMsg
        ? detailMsg
          ? `${baseMsg} — ${detailMsg}`
          : baseMsg
        : String(err);
      setSubmitError(msg);
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleDelete(linkId: UUID): Promise<void> {
    try {
      await tracelinksApi.delete(linkId);
      setReloadKey((k) => k + 1);
    } catch (err: unknown) {
      console.error("Delete tracelink failed:", err);
    }
  }

  return (
    <div
      data-testid="arch-tracelink-panel"
      style={{
        marginTop: "var(--space-4)",
        background: "var(--color-surface)",
        borderRadius: "var(--radius-lg)",
        boxShadow: "var(--shadow-card)",
        padding: "var(--space-4)",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: "var(--space-3)",
        }}
      >
        <h4
          style={{
            margin: 0,
            fontSize: "var(--font-size-base)",
            fontWeight: 700,
            color: "var(--color-text)",
          }}
        >
          {t("arch.tracelinkPanelTitle")}
        </h4>
        {!showForm && (
          <button
            type="button"
            data-testid="arch-tracelink-create-btn"
            onClick={openForm}
            style={panelPrimaryBtn}
          >
            {t("traceability.create")}
          </button>
        )}
      </div>

      {showForm && (
        <form
          onSubmit={(e) => void submitForm(e)}
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "var(--space-2)",
            marginBottom: "var(--space-3)",
            padding: "var(--space-3)",
            background: "var(--color-surface-raised)",
            borderRadius: "var(--radius-md)",
            border: "1px solid var(--color-border)",
          }}
        >
          <label style={panelLabelStyle}>{t("traceability.source")}</label>
          <select
            data-testid="arch-tracelink-source-select"
            value={sourceId}
            onChange={(e) => setSourceId(e.target.value)}
            disabled={isSubmitting}
            required
            style={panelInputStyle}
          >
            <option value={elementId}>
              {(archById[elementId]?.title ?? elementId.slice(0, 8)) +
                " (this element)"}
            </option>
            {otherArchElements.map((a) => (
              <option key={a.id} value={a.id}>
                {a.title || t("editor.untitled")} ({a.element_type})
              </option>
            ))}
          </select>

          <label style={panelLabelStyle}>{t("traceability.target")}</label>
          <select
            data-testid="arch-tracelink-target-select"
            value={targetId}
            onChange={(e) => setTargetId(e.target.value)}
            disabled={isSubmitting}
            required
            style={panelInputStyle}
          >
            <option value="">
              {requirements.length === 0
                ? t("traceability.noArtifacts")
                : "—"}
            </option>
            {requirements.map((r) => (
              <option key={r.id} value={r.id}>
                {r.title || t("editor.untitled")}
              </option>
            ))}
          </select>

          <label style={panelLabelStyle}>{t("traceability.linkType")}</label>
          <select
            data-testid="arch-tracelink-type-select"
            value={linkType}
            onChange={(e) => setLinkType(e.target.value as LinkType)}
            disabled={isSubmitting}
            style={panelInputStyle}
          >
            {ARCH_LINK_TYPES.map((lt) => (
              <option key={lt} value={lt}>
                {lt}
              </option>
            ))}
          </select>

          {submitError && (
            <p
              role="alert"
              style={{
                color: "var(--color-danger)",
                fontSize: "var(--font-size-sm)",
                margin: 0,
              }}
            >
              {submitError}
            </p>
          )}

          <div
            style={{
              display: "flex",
              gap: "var(--space-2)",
              justifyContent: "flex-end",
            }}
          >
            <button
              type="button"
              data-testid="arch-tracelink-cancel-btn"
              onClick={cancelForm}
              disabled={isSubmitting}
              style={{
                background: "var(--color-surface-raised)",
                color: "var(--color-text)",
                border: "1px solid var(--color-border)",
                borderRadius: "var(--radius-md)",
                padding: "var(--space-2) var(--space-4)",
                fontSize: "var(--font-size-sm)",
                fontWeight: 600,
                cursor: isSubmitting ? "not-allowed" : "pointer",
              }}
            >
              {t("actions.cancel")}
            </button>
            <button
              type="submit"
              data-testid="arch-tracelink-save-btn"
              disabled={isSubmitting}
              style={{
                ...panelPrimaryBtn,
                opacity: isSubmitting ? 0.6 : 1,
                cursor: isSubmitting ? "not-allowed" : "pointer",
              }}
            >
              {isSubmitting
                ? t("traceability.submitting")
                : t("traceability.submit")}
            </button>
          </div>
        </form>
      )}

      {isLoading && (
        <p
          role="status"
          style={{
            color: "var(--color-text-muted)",
            fontSize: "var(--font-size-sm)",
            margin: 0,
          }}
        >
          {t("loading")}
        </p>
      )}

      {error && !isLoading && (
        <p
          role="alert"
          style={{
            color: "var(--color-danger)",
            fontSize: "var(--font-size-sm)",
            margin: 0,
          }}
        >
          {error}
        </p>
      )}

      {!isLoading && !error && links.length === 0 && (
        <p
          style={{
            fontSize: "var(--font-size-sm)",
            color: "var(--color-text-muted)",
            margin: 0,
          }}
        >
          {t("traceability.none")}
        </p>
      )}

      {!isLoading && !error && links.length > 0 && (
        <ul
          data-testid="arch-tracelink-list"
          style={{ listStyle: "none", padding: 0, margin: 0 }}
        >
          {links.map((link) => {
            const targetReq = requirementsById[link.target_id];
            const sourceEl = archById[link.source_id];
            return (
              <li
                key={link.id}
                data-testid="arch-tracelink-item"
                style={{
                  padding: "var(--space-2) var(--space-3)",
                  marginBottom: "var(--space-2)",
                  background: "var(--color-surface-raised)",
                  borderRadius: "var(--radius-md)",
                  fontSize: "var(--font-size-sm)",
                  color: "var(--color-text)",
                  display: "flex",
                  alignItems: "center",
                  gap: "var(--space-2)",
                  flexWrap: "wrap",
                }}
              >
                <span style={{ fontFamily: "monospace" }}>
                  {sourceEl?.title ?? link.source_id.slice(0, 8) + "…"}
                </span>
                <span
                  style={{
                    background: "var(--color-badge-draft)",
                    color: "var(--color-badge-draft-text)",
                    padding: "1px 6px",
                    borderRadius: "var(--radius-full)",
                    fontSize: "var(--font-size-sm)",
                  }}
                >
                  {link.link_type}
                </span>
                <span style={{ fontFamily: "monospace" }}>
                  {targetReq?.title ?? link.target_id.slice(0, 8) + "…"}
                </span>
                <button
                  type="button"
                  data-testid="arch-tracelink-delete-btn"
                  onClick={() => void handleDelete(link.id)}
                  style={{
                    marginLeft: "auto",
                    background: "none",
                    border: "none",
                    color: "var(--color-danger)",
                    cursor: "pointer",
                    fontSize: "var(--font-size-sm)",
                    fontWeight: 600,
                  }}
                  title={t("actions.delete")}
                >
                  ×
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
