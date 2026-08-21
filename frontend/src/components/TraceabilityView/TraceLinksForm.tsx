/**
 * TraceLinksForm — Extracted form component for trace link creation.
 *
 * REQ-L1-040 Phase 2 — Unified ModalDialogBase pattern.
 * REQ-L2-RF-006 — Traceability management.
 *
 * Manages trace link creation with multi-artifact source/target selection
 * and LinkType grouping validation.
 */

import { useState, useCallback, useEffect, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useWorkspace } from "../../context/WorkspaceContext";
import { tracelinksApi } from "../../api/tracelinks";
import { requirementsApi } from "../../api/requirements";
import { architectureApi } from "../../api/architecture";
import { testcasesApi } from "../../api/testcases";
import { artifactsApi } from "../../api/artifacts";
import { ModalDialogBase, SHARED_STYLES } from "../RequirementsList/ModalDialogBase";
import { allowedSeLinkTypes } from "../../utils/seLinkSemantics";
import type {
  ApiError,
  Artifact,
  LinkType,
  TraceLink,
  Requirement,
  ArchitectureElement,
  SimilarTraceLink,
} from "../../types";

interface TraceLinkFormState {
  sourceId: string;
  targetId: string;
  linkType: LinkType;
}

// REQ-L2-VS-004: state of the per-item "Find Similar" panel.
type SimilarState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "no-embedding" }
  | { status: "unavailable" }
  | { status: "error"; message: string }
  | { status: "ready"; results: SimilarTraceLink[] };

interface TraceLinksListProps {
  items: TraceLink[];
  titles: Record<string, string>;
  similarFor: string | null;
  similarState: SimilarState;
  onFindSimilar: (link: TraceLink) => void;
}

// Canonical link_type order (REQ-L2-RF-006 — predictable section order).
// Harmonized with the backend LinkType enum; uses-term is glossary-managed
// and deliberately excluded from manual link creation.
const LINK_TYPE_ORDER: LinkType[] = [
  "parent-child",
  "derives-from",
  "satisfies",
  "verifies",
  "implements",
  "refines",
  "allocated-to",
  "documents",
  "realizes",
  "traces",
  "copy-of",
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

/** REQ-L2-VS-004: inline results of a per-item trace-link similarity search. */
function SimilarTraceLinksResults({
  state,
  titles,
}: {
  state: SimilarState;
  titles: Record<string, string>;
}): JSX.Element | null {
  const { t } = useTranslation();

  if (state.status === "idle") return null;

  const noteStyle: React.CSSProperties = {
    margin: "var(--space-2) 0 0 0",
    fontSize: "var(--font-size-sm)",
    color: "var(--color-text-muted)",
  };

  if (state.status === "loading") {
    return (
      <p data-testid="similar-tracelinks-loading" style={noteStyle}>
        {t("loading", "Loading…")}
      </p>
    );
  }
  if (state.status === "no-embedding") {
    return (
      <p data-testid="similar-tracelinks-no-embedding" style={noteStyle}>
        {t(
          "traceability.similar.noEmbedding",
          "No embedding available — similarity search not possible."
        )}
      </p>
    );
  }
  if (state.status === "unavailable") {
    return (
      <p data-testid="similar-tracelinks-unavailable" style={noteStyle}>
        {t(
          "traceability.similar.unavailable",
          "Similarity search is temporarily unavailable."
        )}
      </p>
    );
  }
  if (state.status === "error") {
    return (
      <p
        role="alert"
        data-testid="similar-tracelinks-error"
        style={{ ...noteStyle, color: "var(--color-danger)" }}
      >
        {state.message}
      </p>
    );
  }
  if (state.results.length === 0) {
    return (
      <p data-testid="similar-tracelinks-empty" style={noteStyle}>
        {t("traceability.similar.empty", "No similar trace links found.")}
      </p>
    );
  }
  // Top-5 similar trace links.
  return (
    <ul
      data-testid="similar-tracelinks-results"
      style={{
        listStyle: "none",
        margin: "var(--space-2) 0 0 0",
        padding: 0,
        display: "flex",
        flexDirection: "column",
        gap: "var(--space-1)",
      }}
    >
      {state.results.slice(0, 5).map((hit) => (
        <li
          key={hit.id}
          data-testid={`similar-tracelink-${hit.id}`}
          style={{
            display: "flex",
            justifyContent: "space-between",
            gap: "var(--space-2)",
            fontSize: "var(--font-size-sm)",
            color: "var(--color-text-muted)",
            padding: "var(--space-1) var(--space-2)",
            background: "var(--color-surface-raised)",
            borderRadius: "var(--radius-md)",
          }}
        >
          <span
            style={{
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {renderEndpoint(hit.source_id, titles)} → {hit.link_type} →{" "}
            {renderEndpoint(hit.target_id, titles)}
          </span>
          <span style={{ flexShrink: 0, fontVariantNumeric: "tabular-nums" }}>
            {`${Math.round(hit.similarity_score * 100)}%`}
          </span>
        </li>
      ))}
    </ul>
  );
}

function TraceLinksList({
  items,
  titles,
  similarFor,
  similarState,
  onFindSimilar,
}: TraceLinksListProps): JSX.Element {
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
                    flexDirection: "column",
                    gap: "var(--space-2)",
                    fontSize: "var(--font-size-base)",
                    color: "var(--color-text)",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "var(--space-3)",
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
                        background: "var(--color-linktype-badge-bg)",
                        padding: "2px 8px",
                        borderRadius: "var(--radius-full)",
                        color: "var(--color-linktype-badge-text)",
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
                    <button
                      type="button"
                      data-testid={`tracelink-find-similar-${link.id}`}
                      onClick={() => onFindSimilar(link)}
                      disabled={
                        similarFor === link.id && similarState.status === "loading"
                      }
                      style={{
                        marginLeft: "auto",
                        background: "transparent",
                        color: "var(--color-primary)",
                        border: "1px solid var(--color-border)",
                        borderRadius: "var(--radius-md)",
                        padding: "2px 10px",
                        fontSize: "var(--font-size-sm)",
                        cursor: "pointer",
                      }}
                    >
                      {t("traceability.similar.findButton", "Find Similar")}
                    </button>
                  </div>
                  {similarFor === link.id && (
                    <SimilarTraceLinksResults state={similarState} titles={titles} />
                  )}
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

  // REQ-L2-VS-004: per-item semantic similarity search.
  const [similarFor, setSimilarFor] = useState<string | null>(null);
  const [similarState, setSimilarState] = useState<SimilarState>({
    status: "idle",
  });

  const handleFindSimilar = useCallback(
    async (link: TraceLink): Promise<void> => {
      setSimilarFor(link.id);
      setSimilarState({ status: "loading" });
      try {
        const results = await tracelinksApi.getSimilar(link.id, 5);
        setSimilarState({ status: "ready", results });
      } catch (err: unknown) {
        const code = (err as Partial<ApiError>)?.error?.code;
        if (code === "VALIDATION_ERROR") {
          setSimilarState({ status: "no-embedding" });
        } else if (code === "SERVICE_UNAVAILABLE") {
          setSimilarState({ status: "unavailable" });
        } else {
          const msg =
            (err as { error?: { message?: string } })?.error?.message ??
            String(err);
          setSimilarState({ status: "error", message: msg });
        }
      }
    },
    []
  );

  // SE mode: filter link types by endpoint semantics (finding F1,
  // docs/se/workspace_modes_er_model.md). dev_mode keeps the full list.
  const isSeMode = activeWorkspace?.terminology_profile === "se_mode";

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

  const artifactTypeById = useMemo(() => {
    const map: Record<string, string> = {};
    for (const a of artifacts) map[a.id] = a.artifact_type;
    return map;
  }, [artifacts]);

  const availableLinkTypes = useMemo<LinkType[]>(() => {
    if (!isSeMode) return LINK_TYPE_ORDER;
    return allowedSeLinkTypes(
      LINK_TYPE_ORDER,
      artifactTypeById[formData.sourceId],
      artifactTypeById[formData.targetId]
    );
  }, [isSeMode, artifactTypeById, formData.sourceId, formData.targetId]);

  // Keep the selected link type valid when SE filtering narrows the list.
  useEffect(() => {
    if (availableLinkTypes.length === 0) return;
    if (!availableLinkTypes.includes(formData.linkType)) {
      setFormData((prev) => ({ ...prev, linkType: availableLinkTypes[0] }));
    }
  }, [availableLinkTypes, formData.linkType]);

  const seNoValidType =
    isSeMode &&
    formData.sourceId !== "" &&
    formData.targetId !== "" &&
    availableLinkTypes.length === 0;

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
      if (seNoValidType) {
        setFormError(t("traceability.seNoValidType"));
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
    [activeWorkspace, formData, seNoValidType, t, resetForm, loadList]
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
            disabled={isSubmitting || seNoValidType}
            style={SHARED_STYLES.input}
            required
          >
            {availableLinkTypes.map((lt) => (
              <option key={lt} value={lt}>
                {lt}
              </option>
            ))}
          </select>

          {isSeMode && (
            <p
              data-testid="tracelink-se-hint"
              style={{
                marginTop: "var(--space-2)",
                fontSize: "var(--font-size-sm)",
                color: seNoValidType
                  ? "var(--color-danger)"
                  : "var(--color-text-muted)",
              }}
            >
              {seNoValidType
                ? t("traceability.seNoValidType")
                : t("traceability.seModeHint")}
            </p>
          )}
        </div>
      </ModalDialogBase>

      <TraceLinksList
        items={items}
        titles={titles}
        similarFor={similarFor}
        similarState={similarState}
        onFindSimilar={handleFindSimilar}
      />
    </div>
  );
}

export default TraceLinksForm;
