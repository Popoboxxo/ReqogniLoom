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
import { useCallback, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { architectureDecomposeApi } from "../../api/architectureDecompose";
import type {
  CommitResult,
  DecompositionDraft,
  DraftNode,
} from "../../api/architectureDecompose";
import { extractErrorMessage } from "../../api/client";

export interface ArchitectureDecomposePanelProps {
  workspaceId: string;
  element: { id: string; title: string };
  /** Called after a successful commit (e.g. to refresh the architecture tree). */
  onCommitted?: (result: CommitResult) => void;
  /** Called when the user closes the panel. */
  onClose?: () => void;
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
  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    gap: "var(--space-3)",
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
  onClose,
}: ArchitectureDecomposePanelProps): JSX.Element {
  const { t } = useTranslation();

  const [phase, setPhase] = useState<Phase>("idle");
  const [breadth, setBreadth] = useState<number>(2);
  const [depth, setDepth] = useState<number>(1);
  const [draft, setDraft] = useState<DecompositionDraft | null>(null);
  const [result, setResult] = useState<CommitResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const busy = phase === "generating" || phase === "committing";

  const handleGenerate = useCallback(async () => {
    setError(null);
    setResult(null);
    setPhase("generating");
    try {
      const next = await architectureDecomposeApi.generate(
        workspaceId,
        element.id,
        { breadth, depth }
      );
      setDraft(next);
      setPhase("review");
    } catch (err) {
      setError(extractErrorMessage(err));
      setPhase("idle");
    }
  }, [workspaceId, element.id, breadth, depth]);

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
      <header style={styles.header}>
        <div>
          <strong>{t("archDecompose.title")}</strong>
          <div style={styles.muted} data-testid="arch-decompose-element-title">
            {element.title}
          </div>
        </div>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            data-testid="arch-decompose-close"
          >
            {t("archDecompose.close")}
          </button>
        )}
      </header>

      <div style={styles.controls}>
        <label style={styles.field}>
          <span style={styles.muted}>{t("archDecompose.breadth")}</span>
          <input
            type="number"
            min={1}
            max={5}
            value={breadth}
            disabled={busy}
            onChange={(e) => setBreadth(Number(e.target.value))}
            style={styles.numberInput}
            data-testid="arch-decompose-breadth"
          />
        </label>
        <label style={styles.field}>
          <span style={styles.muted}>{t("archDecompose.depth")}</span>
          <input
            type="number"
            min={1}
            max={3}
            value={depth}
            disabled={busy}
            onChange={(e) => setDepth(Number(e.target.value))}
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
