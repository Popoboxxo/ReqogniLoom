/**
 * TraceLinksForm — Extracted form component for trace link creation.
 *
 * REQ-L1-040 Phase 2 — Unified ModalDialogBase pattern.
 * REQ-L2-RF-006 — Traceability management.
 *
 * Manages trace link creation with multi-artifact source/target selection
 * and LinkType grouping validation.
 */

import React, { useState, useCallback, useEffect, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useWorkspace } from "../../context/WorkspaceContext";
import { tracelinksApi } from "../../api/tracelinks";
import { requirementsApi } from "../../api/requirements";
import { architectureApi } from "../../api/architecture";
import { testcasesApi } from "../../api/testcases";
import { artifactsApi } from "../../api/artifacts";
import { ModalDialogBase, SHARED_STYLES } from "../RequirementsList/ModalDialogBase";
import type {
  Artifact,
  LinkType,
  TraceLink,
  Requirement,
  ArchitectureElement,
} from "../../types";

interface TraceLinkFormState {
  sourceId: string;
  targetId: string;
  linkType: LinkType;
}

interface TraceLinksListProps {
  items: TraceLink[];
  titles: Record<string, string>;
}

// Canonical link_type order (REQ-L2-RF-006 — predictable section order)
const LINK_TYPE_ORDER: LinkType[] = [
  "parent-child",
  "derives-from",
  "satisfies",
  "verifies",
  "implements",
  "refines",
];

function formatId(id: string): string {
  return `${id.slice(0, 8)}…`;
}

function renderEndpoint(id: string, titles: Record<string, string>): string {
  const title = titles[id];
  return title ? `${title} (${formatId(id)})` : formatId(id);
}

function artifactLabel(a: Artifact, titles: Record<string, string>): string {
  const title = titles[a.id];
  if (title) return `${a.artifact_type}: ${title} (${formatId(a.id)})`;
  return `${a.artifact_type} (${formatId(a.id)})`;
}

function groupByLinkType(links: TraceLink[]): Record<string, TraceLink[]> {
  const grouped: Record<string, TraceLink[]> = {};
  for (const link of links) {
    const key = link.link_type || "other";
    if (!grouped[key]) grouped[key] = [];
    grouped[key].push(link);
  }
  return grouped;
}

function orderedGroupKeys(grouped: Record<string, TraceLink[]>): string[] {
  const known = LINK_TYPE_ORDER.filter((k) => grouped[k]);
  const unknown = Object.keys(grouped)
    .filter((k) => !LINK_TYPE_ORDER.includes(k as LinkType))
    .sort();
  return [...known, ...unknown];
}

function TraceLinksList({ items, titles }: TraceLinksListProps): JSX.Element {
  const { t } = useTranslation();
  const grouped = useMemo(() => groupByLinkType(items), [items]);
  const groupKeys = useMemo(() => orderedGroupKeys(grouped), [grouped]);

  if (items.length === 0) {
    return (
      <p style={{ color: "var(--color-text-muted)", padding: "var(--space-6)" }}>
        {t("traceability.empty")}
      </p>
    );
  }

  return (
    <div
      data-testid="traceability-list"
      style={{ display: "flex", flexDirection: "column", gap: "var(--space-6)" }}
    >
      {groupKeys.map((linkType) => {
        const groupLinks = grouped[linkType];
        return (
          <section
            key={linkType}
            data-testid="tracelink-group"
            data-link-type={linkType}
            style={{
              background: "var(--color-surface)",
              borderRadius: "var(--radius-lg)",
              boxShadow: "var(--shadow-card)",
              overflow: "hidden",
            }}
          >
            <header
              style={{
                background: "var(--color-surface-raised)",
                padding: "var(--space-3) var(--space-4)",
                borderBottom: "1px solid var(--color-border)",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
              }}
            >
              <h3
                style={{
                  margin: 0,
                  fontSize: "var(--font-size-lg)",
                  fontWeight: 600,
                  color: "var(--color-text)",
                }}
              >
                {linkType}
              </h3>
              <span style={{ fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)" }}>
                {groupLinks.length}
              </span>
            </header>
            <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
              {groupLinks.map((link) => (
                <li
                  key={link.id}
                  data-testid="tracelink-item"
                  data-link-type={link.link_type}
                  style={{
                    padding: "var(--space-3) var(--space-4)",
                    borderBottom: "1px solid var(--color-border)",
                    display: "flex",
                    alignItems: "center",
                    gap: "var(--space-3)",
                    fontSize: "var(--font-size-base)",
                    color: "var(--color-text)",
                  }}
                >
                  <span data-testid="tracelink-source">{renderEndpoint(link.source_id, titles)}</span>
                  <span
                    aria-hidden="true"
                    style={{ color: "var(--color-text-muted)", fontWeight: 500 }}
                  >
                    →
                  </span>
                  <span
                    data-testid="tracelink-type"
                    style={{
                      fontSize: "var(--font-size-sm)",
                      background: "#eef",
                      padding: "2px 8px",
                      borderRadius: "var(--radius-full)",
                      color: "#2c5282",
                      fontWeight: 500,
                    }}
                  >
                    {link.link_type}
                  </span>
                  <span
                    aria-hidden="true"
                    style={{ color: "var(--color-text-muted)", fontWeight: 500 }}
                  >
                    →
                  </span>
                  <span data-testid="tracelink-target">{renderEndpoint(link.target_id, titles)}</span>
                </li>
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}

export function TraceLinksForm(): JSX.Element {
  const { t } = useTranslation();
  const { activeWorkspace } = useWorkspace();
  const [items, setItems] = useState<TraceLink[]>([]);
  const [titles, setTitles] = useState<Record<string, string>>({});
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const [formData, setFormData] = useState<TraceLinkFormState>({
    sourceId: "",
    targetId: "",
    linkType: "satisfies",
  });

  // Load trace links and resolve titles
  const loadList = useCallback(async (): Promise<void> => {
    if (!activeWorkspace) {
      setItems([]);
      setTitles({});
      setArtifacts([]);
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    setError(null);
    try {
      const [linksResp, reqResp, archResp, tcResp, artifactsResp] = await Promise.all([
        tracelinksApi.list(activeWorkspace.id),
        requirementsApi.list(activeWorkspace.id),
        architectureApi.list(activeWorkspace.id),
        testcasesApi.list(activeWorkspace.id),
        artifactsApi.list(activeWorkspace.id),
      ]);

      const newTitles: Record<string, string> = {};
      for (const r of reqResp.results as Requirement[]) {
        newTitles[r.id] = r.title || t("editor.untitled");
      }
      for (const el of archResp.results as ArchitectureElement[]) {
        newTitles[el.id] = el.title || t("editor.untitled");
      }
      for (const tc of tcResp.results) {
        newTitles[tc.id] = tc.title || t("editor.untitled");
      }

      setItems(linksResp.results as TraceLink[]);
      setTitles(newTitles);
      setArtifacts(artifactsResp.results as Artifact[]);
    } catch (err: unknown) {
      const status = (err as { status?: number })?.status;
      if (status === 404) {
        setItems([]);
        setTitles({});
        setArtifacts([]);
        return;
      }
      const msg = (err as { error?: { message?: string } })?.error?.message ?? String(err);
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  }, [activeWorkspace, t]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      if (!cancelled) {
        await loadList();
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [loadList]);

  const resetForm = useCallback((): void => {
    setFormData({ sourceId: "", targetId: "", linkType: "satisfies" });
    setFormError(null);
  }, []);

  const handleSubmit = useCallback(
    async (e: React.FormEvent<HTMLFormElement>): Promise<void> => {
      e.preventDefault();
      if (!activeWorkspace) return;

      if (!formData.sourceId) {
        setFormError(t("traceability.sourceRequired"));
        return;
      }
      if (!formData.targetId) {
        setFormError(t("traceability.targetRequired"));
        return;
      }
      if (formData.sourceId === formData.targetId) {
        setFormError(t("traceability.sameEndpoints"));
        return;
      }

      setIsSubmitting(true);
      setFormError(null);
      try {
        await tracelinksApi.create({
          source_id: formData.sourceId,
          target_id: formData.targetId,
          link_type: formData.linkType,
        });
        setShowCreate(false);
        resetForm();
        await loadList();
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
        setFormError(msg);
      } finally {
        setIsSubmitting(false);
      }
    },
    [activeWorkspace, formData, t, resetForm, loadList]
  );

  const handleCancel = useCallback((): void => {
    setShowCreate(false);
    resetForm();
  }, [resetForm]);

  if (isLoading) {
    return (
      <p role="status" style={{ color: "var(--color-text-muted)", padding: "var(--space-4)" }}>
        {t("loading")}
      </p>
    );
  }

  if (error) {
    return (
      <div role="alert" style={{ color: "var(--color-danger)", padding: "var(--space-4)" }}>
        {error}
        <button onClick={loadList} style={SHARED_STYLES.primaryButton}>
          {t("actions.reload")}
        </button>
      </div>
    );
  }

  const hasArtifacts = artifacts.length > 0;

  return (
    <div>
      <ModalDialogBase
        title={t("nav.traceability")}
        isOpen={showCreate}
        onToggle={() => setShowCreate(!showCreate)}
        onSubmit={handleSubmit}
        onCancel={handleCancel}
        error={formError}
        isSubmitting={isSubmitting}
        itemCount={items.length}
        testIdPrefix="tracelink"
        buttonTestIdPrefix="tracelink"
      >
        <div>
          <label htmlFor="tracelink-source" style={SHARED_STYLES.label}>
            {t("traceability.source")} *
          </label>
          <select
            id="tracelink-source"
            data-testid="tracelink-source-select"
            value={formData.sourceId}
            onChange={(e) => setFormData((prev) => ({ ...prev, sourceId: e.target.value }))}
            disabled={!hasArtifacts || isSubmitting}
            style={SHARED_STYLES.input}
            required
          >
            <option value="">
              {hasArtifacts ? "—" : t("traceability.noArtifacts")}
            </option>
            {artifacts.map((a) => (
              <option key={a.id} value={a.id}>
                {artifactLabel(a, titles)}
              </option>
            ))}
          </select>

          <label htmlFor="tracelink-target" style={SHARED_STYLES.label}>
            {t("traceability.target")} *
          </label>
          <select
            id="tracelink-target"
            data-testid="tracelink-target-select"
            value={formData.targetId}
            onChange={(e) => setFormData((prev) => ({ ...prev, targetId: e.target.value }))}
            disabled={!hasArtifacts || isSubmitting}
            style={SHARED_STYLES.input}
            required
          >
            <option value="">
              {hasArtifacts ? "—" : t("traceability.noArtifacts")}
            </option>
            {artifacts.map((a) => (
              <option key={a.id} value={a.id}>
                {artifactLabel(a, titles)}
              </option>
            ))}
          </select>

          <label htmlFor="tracelink-type" style={SHARED_STYLES.label}>
            {t("traceability.linkType")} *
          </label>
          <select
            id="tracelink-type"
            data-testid="tracelink-type-select"
            value={formData.linkType}
            onChange={(e) =>
              setFormData((prev) => ({
                ...prev,
                linkType: e.target.value as LinkType,
              }))
            }
            disabled={isSubmitting}
            style={SHARED_STYLES.input}
            required
          >
            {LINK_TYPE_ORDER.map((lt) => (
              <option key={lt} value={lt}>
                {lt}
              </option>
            ))}
          </select>
        </div>
      </ModalDialogBase>

      <TraceLinksList items={items} titles={titles} />
    </div>
  );
}

export default TraceLinksForm;
