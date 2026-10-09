/**
 * ARCH-L1-001 ReactFrontend — Derive Requirements Panel (REQ-L2-AI-001/002).
 *
 * Human-in-the-loop review step for the StakeholderNeed -> SystemRequirement
 * derivation, modelled on DeriveTestCasePanel (SysEng 2.0 N5):
 *
 *   1. The caller asks the backend for drafts
 *      (POST /needs/{id}/derive-requirements/) — nothing is persisted there.
 *   2. This panel shows every draft as an editable, selectable row so the user
 *      can correct or drop proposals before anything is written.
 *   3. "Accept" hands the selected drafts to the server in ONE call
 *      (POST /needs/{id}/derive-requirements/accept/, issue #1095). The server
 *      creates each Requirement through the `ai_proposal_service` authoring
 *      seam — so the artefact is born `proposed`, lands in the pending-review
 *      queue and carries the `ai_elicit`/`origin` markers — and writes the
 *      `derives-from` TraceLink back to this need itself (SE: Req
 *      --derives-from--> Need).
 *
 * Why the client no longer persists (issue #1095 / #1089): it used to call
 * `requirementsApi.create` from a `user` principal and then build the
 * TraceLink by hand. `initial_state_for` seeds "proposed" only for an `agent`
 * principal, which the auth layer decides — a human pressing the button holds
 * a Bearer token — so every accepted draft became a plain `draft`: the row
 * existed, the panel reported success, and nobody was ever shown it for
 * approval. The whole batch is also atomic server-side, which removes the
 * per-row rollback/partial-failure bookkeeping this panel used to carry.
 *
 * data-testid is set on every interactive element (E2E convention).
 */
import type { CSSProperties } from "react";
import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";

import type { DerivedRequirementDraft } from "../../api/stakeholder-need";
import { stakeholderNeedApi } from "../../api/stakeholder-need";
import { Spinner } from "../shared/Spinner/Spinner";

export interface DeriveRequirementsPanelProps {
  /**
   * PK of the source need. Both derivation endpoints resolve it via
   * `StakeholderNeedService.get` — the artifact id is NOT accepted here (it
   * is only what TraceLinkService stores as the link target, and the server
   * writes that link itself since #1095).
   */
  needId: string;
  drafts: DerivedRequirementDraft[];
  /** Called with the number of persisted requirements after a successful accept. */
  onAccepted?: (count: number) => void;
  /** Called when the user discards the proposals. */
  onDiscard?: () => void;
}

interface DraftRow extends DerivedRequirementDraft {
  selected: boolean;
}

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
  row: {
    display: "flex",
    flexDirection: "column",
    gap: "var(--space-2)",
    padding: "var(--space-3)",
    border: "1px solid var(--color-border)",
    borderRadius: "var(--radius-sm)",
  },
  rowHeader: {
    display: "flex",
    alignItems: "center",
    gap: "var(--space-2)",
  },
  input: {
    flex: 1,
    padding: "var(--space-2) var(--space-3)",
    border: "1px solid var(--color-border)",
    borderRadius: "var(--radius-sm)",
    background: "var(--color-surface-raised)",
    color: "var(--color-text)",
  },
  textarea: {
    padding: "var(--space-2) var(--space-3)",
    border: "1px solid var(--color-border)",
    borderRadius: "var(--radius-sm)",
    background: "var(--color-surface-raised)",
    color: "var(--color-text)",
    minHeight: "4rem",
    resize: "vertical",
  },
  error: {
    background: "var(--color-badge-danger-bg)",
    color: "var(--color-badge-danger-text)",
    borderRadius: "var(--radius-sm)",
    padding: "var(--space-2) var(--space-3)",
  },
  actions: { display: "flex", gap: "var(--space-3)", flexWrap: "wrap" },
  muted: { color: "var(--color-text-muted)", fontSize: "var(--font-size-sm)" },
};

export function DeriveRequirementsPanel({
  needId,
  drafts,
  onAccepted,
  onDiscard,
}: DeriveRequirementsPanelProps): JSX.Element {
  const { t } = useTranslation();

  const [rows, setRows] = useState<DraftRow[]>(() =>
    drafts.map((d) => ({ ...d, selected: true }))
  );
  // One in-flight flag for the whole batch: the server persists the selected
  // drafts in a single transaction, so there is no per-row progress to report
  // and no partially-persisted state to roll back (#1095).
  const [isAccepting, setIsAccepting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const updateRow = useCallback((index: number, patch: Partial<DraftRow>) => {
    setRows((prev) => prev.map((r, i) => (i === index ? { ...r, ...patch } : r)));
  }, []);

  const selectedCount = rows.filter((r) => r.selected && r.title.trim()).length;

  const handleAccept = useCallback(async () => {
    const selected = rows.filter((r) => r.selected && r.title.trim());
    if (selected.length === 0) return;
    setIsAccepting(true);
    setError(null);
    try {
      const result = await stakeholderNeedApi.acceptDerivedRequirements(
        needId,
        selected.map((row) => ({
          title: row.title.trim(),
          description: row.description,
          rationale: row.rationale,
        })),
      );
      // The server always answers with a `proposal` block. When it reports that
      // no reviewable proposal was created, the artefacts are (at best) plain
      // drafts — reporting success would reproduce the #1089 gap the user just
      // tried to close, so the server's own reason is surfaced verbatim.
      if (!result.proposal?.is_proposal) {
        setError(
          t("deriveRequirements.reviewRequired", {
            reason: result.proposal?.reason || t("needs.deriveFailed"),
          }),
        );
        return;
      }
      onAccepted?.(result.count);
    } catch (err) {
      const apiErr = err as { error?: { message?: string } };
      setError(apiErr?.error?.message ?? t("needs.deriveFailed"));
    } finally {
      setIsAccepting(false);
    }
  }, [rows, needId, onAccepted, t]);

  return (
    <section style={styles.panel} data-testid="derive-requirements-panel">
      <header style={styles.header}>
        <strong>{t("deriveRequirements.title")}</strong>
        <span style={styles.muted} data-testid="derive-requirements-count">
          {t("deriveRequirements.selectedCount", {
            selected: selectedCount,
            total: rows.length,
          })}
        </span>
      </header>

      {/* #1095: says up front what accepting does — the drafts become an AI
          proposal in the pending-review queue, not a silently-written draft
          that nobody is ever shown (the #1089 half of the same defect). */}
      <span style={styles.muted} data-testid="derive-requirements-accepted-hint">
        {t("deriveRequirements.acceptedHint")}
      </span>

      {error && (
        <div style={styles.error} role="alert" data-testid="derive-requirements-error">
          {error}
        </div>
      )}

      {rows.map((row, i) => (
        <div key={i} style={styles.row} data-testid={`derive-requirements-draft-${i}`}>
          <div style={styles.rowHeader}>
            <input
              type="checkbox"
              checked={row.selected}
              disabled={isAccepting}
              onChange={(e) => updateRow(i, { selected: e.target.checked })}
              aria-label={t("deriveRequirements.selectDraft", { index: i + 1 })}
              data-testid={`derive-requirements-select-${i}`}
            />
            <input
              type="text"
              value={row.title}
              disabled={isAccepting}
              onChange={(e) => updateRow(i, { title: e.target.value })}
              style={styles.input}
              data-testid={`derive-requirements-title-${i}`}
            />
          </div>
          <textarea
            value={row.description}
            disabled={isAccepting}
            onChange={(e) => updateRow(i, { description: e.target.value })}
            style={styles.textarea}
            data-testid={`derive-requirements-description-${i}`}
          />
          {row.rationale && (
            <span style={styles.muted} data-testid={`derive-requirements-rationale-${i}`}>
              {t("deriveRequirements.rationale")}: {row.rationale}
            </span>
          )}
        </div>
      ))}

      <div style={styles.actions}>
        <button
          type="button"
          onClick={() => void handleAccept()}
          disabled={isAccepting || selectedCount === 0}
          data-testid="derive-requirements-accept"
        >
          {isAccepting ? (
            <Spinner label={t("deriveRequirements.accepting")} />
          ) : (
            t("deriveRequirements.accept")
          )}
        </button>
        <button
          type="button"
          onClick={onDiscard}
          disabled={isAccepting}
          data-testid="derive-requirements-discard"
        >
          {t("deriveRequirements.discard")}
        </button>
      </div>
    </section>
  );
}
