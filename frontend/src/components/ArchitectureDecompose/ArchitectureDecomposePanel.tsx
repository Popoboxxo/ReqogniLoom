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
  DecomposeFinding,
  DecompositionDraft,
  DraftNode,
} from "../../api/architectureDecompose";
import { extractErrorMessage } from "../../api/client";
import { UnprocessableEntityError } from "../../api/errors";
import { promptVariablesApi } from "../../api/prompt-variables";

/**
 * Used only when the variable catalog cannot be read (e.g. a non-admin user
 * whose token cannot list prompt variables). Matches the backend factory
 * defaults so the panel behaves identically either way.
 */
const FALLBACK_MAX_BREADTH = 5;
const FALLBACK_MAX_DEPTH = 3;

/**
 * UI-40: absolute ceiling the backend enforces server-side regardless of
 * workspace config (`_ABSOLUTE_MAX_BREADTH`/`_ABSOLUTE_MAX_DEPTH` in
 * `backend/application/architecture_decompose_service.py`). The breadth/depth
 * inputs below previously had no client-side `min`/clamping, so `0` or a
 * cleared field silently produced `NaN`/`0` values that only got corrected
 * once the request reached the server.
 */
const ABSOLUTE_MAX_BREADTH = 10;
const ABSOLUTE_MAX_DEPTH = 4;
const ABSOLUTE_MIN = 1;

/**
 * UI-40: final clamp to [ABSOLUTE_MIN, cap] for a breadth/depth value —
 * never NaN, never below 1. Applied on blur and defensively again right
 * before a generate() call (so a value that never blurred, e.g. Enter-key
 * submission, still can't reach the backend as 0/NaN).
 */
function clampFinal(value: number | "", cap: number): number {
  if (value === "" || !Number.isFinite(value)) return ABSOLUTE_MIN;
  return Math.min(cap, Math.max(ABSOLUTE_MIN, Math.round(value)));
}

/**
 * UI-40: live upper-bound-only clamp while typing. Deliberately does NOT
 * enforce the minimum or reject an empty string — that would make the field
 * un-clearable (backspacing to "" to type a fresh number would immediately
 * snap back to 1, e.g. clearing "5" then typing "10" would land on "10"
 * appended to an eagerly-reinserted "1" instead). The lower bound and empty
 * state are finalized by `clampFinal` on blur.
 */
function clampWhileTyping(raw: string, cap: number): number | "" {
  if (raw === "") return "";
  const parsed = Number(raw);
  if (!Number.isFinite(parsed)) return "";
  return Math.min(cap, Math.round(parsed));
}

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
  /**
   * UI-24: fires whenever there is generated-but-not-yet-committed work that
   * an Escape/backdrop close of the surrounding dialog would silently
   * discard (an LLM-generated draft awaiting review, or a commit already in
   * flight). The host dialog uses this to interpose a confirmation instead
   * of closing straight away.
   */
  onPendingWorkChange?: (hasPendingWork: boolean) => void;
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
  // UI-40: structured per-finding error list.
  errorSummary: { margin: "0 0 var(--space-2)" },
  errorFindingsList: {
    listStyle: "none",
    padding: 0,
    margin: 0,
    display: "flex",
    flexDirection: "column",
    gap: "var(--space-1)",
  },
};

/** Indent a node by its recursion depth (derived from the dotted temp_id). */
function nodeDepth(node: DraftNode): number {
  return (node.temp_id.match(/\./g) || []).length;
}

export function ArchitectureDecomposePanel({
  workspaceId,
  element,
  onCommitted,
  onPendingWorkChange,
}: ArchitectureDecomposePanelProps): JSX.Element {
  const { t } = useTranslation();

  const [phase, setPhase] = useState<Phase>("idle");
  // UI-40: "" is a valid transient state while the user has cleared the
  // field to type a new value — clampFinal() resolves it (and any
  // out-of-range/NaN value) back to a valid int on blur and before submit.
  const [maxBreadth, setMaxBreadth] = useState<number | "">(FALLBACK_MAX_BREADTH);
  const [maxDepth, setMaxDepth] = useState<number | "">(FALLBACK_MAX_DEPTH);
  const [draft, setDraft] = useState<DecompositionDraft | null>(null);
  const [result, setResult] = useState<CommitResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  // UI-40: structured per-violation detail for a 422 commit rollback (I1-I5 /
  // SE-Auditor findings) — rendered as a list instead of the flat `error`
  // string when available.
  const [findings, setFindings] = useState<DecomposeFinding[] | null>(null);

  const busy = phase === "generating" || phase === "committing";

  // UI-24: "review" holds a generated draft that only exists client-side
  // until Commit runs; "committing" has a request in flight. Both would
  // vanish silently on an Escape/backdrop close of the host dialog.
  useEffect(() => {
    onPendingWorkChange?.(phase === "review" || phase === "committing");
  }, [phase, onPendingWorkChange]);

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
    setFindings(null);
    setResult(null);
    setPhase("generating");
    // UI-40: resolve+display the final clamped values regardless of whether
    // the input ever blurred (e.g. Enter-key submission while focused) —
    // 0/NaN must never reach the backend, even transiently.
    const resolvedBreadth = clampFinal(maxBreadth, ABSOLUTE_MAX_BREADTH);
    const resolvedDepth = clampFinal(maxDepth, ABSOLUTE_MAX_DEPTH);
    setMaxBreadth(resolvedBreadth);
    setMaxDepth(resolvedDepth);
    try {
      const next = await architectureDecomposeApi.generate(
        workspaceId,
        element.id,
        { maxBreadth: resolvedBreadth, maxDepth: resolvedDepth }
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
    setFindings(null);
    setPhase("committing");
    try {
      const committed = await architectureDecomposeApi.commit(workspaceId, draft);
      setResult(committed);
      setDraft(null);
      setPhase("done");
      onCommitted?.(committed);
    } catch (err) {
      setError(extractErrorMessage(err));
      // UI-40: a rolled-back commit (DecompositionAuditError, 422) carries
      // the offending I1-I5/SE-Auditor findings — surface them as a
      // structured list instead of only the flat summary message.
      if (err instanceof UnprocessableEntityError && err.findings?.length) {
        setFindings(err.findings as unknown as DecomposeFinding[]);
      }
      setPhase("review");
    }
  }, [workspaceId, draft, onCommitted]);

  const handleDiscard = useCallback(() => {
    setDraft(null);
    setError(null);
    setFindings(null);
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
            min={ABSOLUTE_MIN}
            max={ABSOLUTE_MAX_BREADTH}
            value={maxBreadth}
            disabled={busy}
            onChange={(e) => setMaxBreadth(clampWhileTyping(e.target.value, ABSOLUTE_MAX_BREADTH))}
            onBlur={() => setMaxBreadth((v) => clampFinal(v, ABSOLUTE_MAX_BREADTH))}
            style={styles.numberInput}
            data-testid="arch-decompose-breadth"
          />
        </label>
        <label style={styles.field}>
          <span style={styles.muted}>{t("archDecompose.maxDepth")}</span>
          <input
            type="number"
            min={ABSOLUTE_MIN}
            max={ABSOLUTE_MAX_DEPTH}
            value={maxDepth}
            disabled={busy}
            onChange={(e) => setMaxDepth(clampWhileTyping(e.target.value, ABSOLUTE_MAX_DEPTH))}
            onBlur={() => setMaxDepth((v) => clampFinal(v, ABSOLUTE_MAX_DEPTH))}
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
          {/* UI-40: previously always a single flat-text paragraph, even when
              the rollback carried multiple distinct I1-I5/SE-Auditor
              findings. Render each finding as its own list item when the
              structured detail is available; otherwise fall back to the
              summary message alone. */}
          {findings && findings.length > 0 ? (
            <>
              <p style={styles.errorSummary}>{error}</p>
              <ul
                data-testid="arch-decompose-error-findings"
                style={styles.errorFindingsList}
              >
                {findings.map((finding, i) => (
                  <li key={`${finding.rule_id}-${i}`} data-testid={`arch-decompose-error-finding-${finding.rule_id}`}>
                    <span style={styles.linkTag}>{finding.rule_id}</span>
                    {finding.message}
                  </li>
                ))}
              </ul>
            </>
          ) : (
            error
          )}
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
