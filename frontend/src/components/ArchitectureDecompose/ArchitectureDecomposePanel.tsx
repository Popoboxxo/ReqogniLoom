/**
 * ARCH-L1-001 ReactFrontend — Architecture Decompose Panel (SysEng 2.0 N1).
 *
 * UMSETZUNGSPLAN_SYSENG_2.0.md §3.1 + §4 Phase 4a ("KI-Copilot", Draft-Staging).
 *
 * Human-in-the-loop copilot for `architecture.decompose`:
 *   1. "Generate" asks the backend to propose a decomposition draft for the
 *      selected ArchitectureElement (child elements + one derived requirement
 *      each + the internal decomposes / derives-from / allocated-to links).
 *      Nothing is persisted — the draft lives in this component's state.
 *   2. The draft is shown diff-style (every node is an "added" entry, analogous
 *      to the ArtifactDiff feature) so the user can review it before writing.
 *   3. "Commit" sends the reviewed draft back; the backend persists it in one
 *      transaction and rolls back entirely on any failure (including an
 *      SE-Auditor violation, surfaced here as a 422 with findings).
 *
 * data-testid is set on every interactive element (E2E convention).
 */

import type { CSSProperties } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { architectureDecomposeApi } from "../../api/architectureDecompose";
import type {
  CommitResult,
  DecompositionDraft,
  DraftNode,
} from "../../api/architectureDecompose";
import { extractErrorMessage } from "../../api/client";
import { promptVariablesApi } from "../../api/prompt-variables";

/**
 * Used only when the variable catalog cannot be read (e.g. a non-admin user
 * whose token cannot list prompt variables). Matches the backend factory
 * defaults so the panel behaves identically either way.
 */
const FALLBACK_MAX_BREADTH = 5;
const FALLBACK_MAX_DEPTH = 3;

/** Read one int-valued config variable out of a catalog listing. */
function capFromCatalog(
  variables: { name: string; effective_value: unknown }[],
  name: string,
  fallback: number
): number {
  const found = variables.find((v) => v.name === name);
  const value = Number(found?.effective_value);
  return Number.isFinite(value) && value >= 1 ? value : fallback;
}

export interface ArchitectureDecomposePanelProps {
  workspaceId: string;
  element: { id: string; title: string };
  /** Called after a successful commit (e.g. to refresh the architecture tree). */
  onCommitted?: (result: CommitResult) => void;
}

type Phase = "idle" | "generating" | "review" | "committing" | "done";

const styles: Record<string, CSSProperties> = {
  panel: {
    display: "flex",
    flexDirection: "column",
    gap: "var(--space-4)",
    padding: "var(--space-5)",
    background: "var(--color-surface)",
    border: "1px solid var(--color-border)",
    borderRadius: "var(--radius-lg)",
    color: "var(--color-text)",
  },
  controls: {
    display: "flex",
    gap: "var(--space-3)",
    alignItems: "flex-end",
    flexWrap: "wrap",
  },
  field: { display: "flex", flexDirection: "column", gap: "var(--space-1)" },
  numberInput: { width: "5rem", padding: "var(--space-1) var(--space-2)" },
  node: {
    borderLeft: "3px solid var(--color-success)",
    background: "var(--color-badge-success-bg)",
    color: "var(--color-badge-success-text)",
    borderRadius: "var(--radius-sm)",
    padding: "var(--space-2) var(--space-3)",
  },
  linkTag: {
    display: "inline-block",
    fontSize: "var(--font-size-xs)",
    background: "var(--color-badge-info-bg)",
    color: "var(--color-badge-info-text)",
    borderRadius: "var(--radius-full)",
    padding: "0 var(--space-2)",
    marginRight: "var(--space-2)",
  },
  banner: {
    background: "var(--color-badge-warning-bg)",
    color: "var(--color-badge-warning-text)",
    borderRadius: "var(--radius-sm)",
    padding: "var(--space-2) var(--space-3)",
    fontSize: "var(--font-size-sm)",
  },
  error: {
    background: "var(--color-badge-danger-bg)",
    color: "var(--color-badge-danger-text)",
    borderRadius: "var(--radius-sm)",
    padding: "var(--space-2) var(--space-3)",
  },
  success: {
    background: "var(--color-badge-success-bg)",
    color: "var(--color-badge-success-text)",
    borderRadius: "var(--radius-sm)",
    padding: "var(--space-3)",
  },
  actions: { display: "flex", gap: "var(--space-3)", flexWrap: "wrap" },
  muted: { color: "var(--color-text-muted)", fontSize: "var(--font-size-sm)" },
};

/** Indent a node by its recursion depth (derived from the dotted temp_id). */
function nodeDepth(node: DraftNode): number {
  return (node.temp_id.match(/\./g) || []).length;
}

export function ArchitectureDecomposePanel({
  workspaceId,
  element,
  onCommitted,
}: ArchitectureDecomposePanelProps): JSX.Element {
  const { t } = useTranslation();

  const [phase, setPhase] = useState<Phase>("idle");
  const [maxBreadth, setMaxBreadth] = useState<number>(FALLBACK_MAX_BREADTH);
  const [maxDepth, setMaxDepth] = useState<number>(FALLBACK_MAX_DEPTH);
  const [draft, setDraft] = useState<DecompositionDraft | null>(null);
  const [result, setResult] = useState<CommitResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const busy = phase === "generating" || phase === "committing";

  // Defaults come from the variable catalog (spec §4) rather than hard-coded
  // 2/1, so a workspace that raised its caps sees them here too. A failure is
  // silent on purpose: the fallbacks equal the backend factory values, so the
  // panel stays usable instead of blocking on an admin-only read.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const catalog = await promptVariablesApi.list(workspaceId);
        if (cancelled) return;
        setMaxBreadth(
          capFromCatalog(catalog.variables, "max_breadth", FALLBACK_MAX_BREADTH)
        );
        setMaxDepth(
          capFromCatalog(catalog.variables, "max_depth", FALLBACK_MAX_DEPTH)
        );
      } catch {
        // Keep the fallbacks.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [workspaceId]);

  const handleGenerate = useCallback(async () => {
    setError(null);
    setResult(null);
    setPhase("generating");
    try {
      const next = await architectureDecomposeApi.generate(
        workspaceId,
        element.id,
        { maxBreadth, maxDepth }
      );
      setDraft(next);
      setPhase("review");
    } catch (err) {
      setError(extractErrorMessage(err));
      setPhase("idle");
    }
  }, [workspaceId, element.id, maxBreadth, maxDepth]);

  const handleCommit = useCallback(async () => {
    if (!draft) return;
    setError(null);
    setPhase("committing");
    try {
      const committed = await architectureDecomposeApi.commit(workspaceId, draft);
      setResult(committed);
      setDraft(null);
      setPhase("done");
      onCommitted?.(committed);
    } catch (err) {
      setError(extractErrorMessage(err));
      setPhase("review");
    }
  }, [workspaceId, draft, onCommitted]);

  const handleDiscard = useCallback(() => {
    setDraft(null);
    setError(null);
    setPhase("idle");
  }, []);

  const nodeCount = draft?.nodes.length ?? 0;
  const linkEstimate = useMemo(() => nodeCount * 3, [nodeCount]);

  return (
    <section style={styles.panel} data-testid="arch-decompose-panel">
      <div style={styles.controls}>
        <label style={styles.field}>
          <span style={styles.muted}>{t("archDecompose.maxBreadth")}</span>
          <input
            type="number"
            min={1}
            value={maxBreadth}
            disabled={busy}
            onChange={(e) => setMaxBreadth(Number(e.target.value))}
            style={styles.numberInput}
            data-testid="arch-decompose-breadth"
          />
        </label>
        <label style={styles.field}>
          <span style={styles.muted}>{t("archDecompose.maxDepth")}</span>
          <input
            type="number"
            min={1}
            value={maxDepth}
            disabled={busy}
            onChange={(e) => setMaxDepth(Number(e.target.value))}
            style={styles.numberInput}
            data-testid="arch-decompose-depth"
          />
        </label>
        <button
          type="button"
          onClick={handleGenerate}
          disabled={busy}
          data-testid="arch-decompose-generate"
        >
          {phase === "generating"
            ? t("archDecompose.generating")
            : t("archDecompose.generate")}
        </button>
      </div>

      <p style={styles.muted} data-testid="arch-decompose-caps-hint">
        {t("archDecompose.capsHint")}
      </p>

      {error && (
        <div style={styles.error} role="alert" data-testid="arch-decompose-error">
          {error}
        </div>
      )}

      {draft && (
        <div data-testid="arch-decompose-draft">
          {draft.degraded && (
            <div style={styles.banner} data-testid="arch-decompose-degraded">
              {t("archDecompose.degraded")}
            </div>
          )}
          <p style={styles.muted} data-testid="arch-decompose-summary">
            {t("archDecompose.summary", {
              elements: nodeCount,
              requirements: nodeCount,
              links: linkEstimate,
            })}
          </p>
          <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
            {draft.nodes.map((node) => (
              <li
                key={node.temp_id}
                style={{
                  ...styles.node,
                  marginLeft: `calc(${nodeDepth(node)} * var(--space-4))`,
                }}
                data-testid={`arch-decompose-node-${node.temp_id}`}
              >
                <div>
                  <span style={styles.linkTag}>+ {node.element_type}</span>
                  <strong>{node.title}</strong>
                </div>
                {node.description && <div>{node.description}</div>}
                <div style={styles.muted}>
                  {t("archDecompose.derivedRequirement")}: {node.requirement.title}
                </div>
                <div>
                  <span style={styles.linkTag}>allocated-to</span>
                  <span style={styles.linkTag}>decomposes</span>
                  <span style={styles.linkTag}>derives-from</span>
                </div>
              </li>
            ))}
          </ul>
          <div style={styles.actions}>
            <button
              type="button"
              onClick={handleCommit}
              disabled={busy}
              data-testid="arch-decompose-commit"
            >
              {phase === "committing"
                ? t("archDecompose.committing")
                : t("archDecompose.commit")}
            </button>
            <button
              type="button"
              onClick={handleDiscard}
              disabled={busy}
              data-testid="arch-decompose-discard"
            >
              {t("archDecompose.discard")}
            </button>
          </div>
        </div>
      )}

      {result && (
        <div style={styles.success} data-testid="arch-decompose-result">
          <div>
            {t("archDecompose.committed", {
              elements: result.counts.elements,
              requirements: result.counts.requirements,
              links: result.counts.links,
            })}
          </div>
          <div style={styles.muted}>
            {t("archDecompose.verified")}: {result.verified_rules.join(", ")}
          </div>
        </div>
      )}
    </section>
  );
}
