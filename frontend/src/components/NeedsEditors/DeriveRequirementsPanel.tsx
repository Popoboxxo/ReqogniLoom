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
 *   3. "Accept" persists the selected drafts via requirementsApi.create and
 *      links each one back to the source need with a 'derives-from' TraceLink
 *      (SE: Req --derives-from--> Need).
 *
 * data-testid is set on every interactive element (E2E convention).
 */
import type { CSSProperties } from "react";
import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";

import { requirementsApi } from "../../api/requirements";
import { tracelinksApi } from "../../api/tracelinks";
import type { DerivedRequirementDraft } from "../../api/stakeholder-need";
import { Spinner } from "../shared/Spinner/Spinner";

export interface DeriveRequirementsPanelProps {
  workspaceId: string;
  /** Artifact id of the source need — the TraceLink target. */
  needArtifactId: string;
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
  workspaceId,
  needArtifactId,
  drafts,
  onAccepted,
  onDiscard,
}: DeriveRequirementsPanelProps): JSX.Element {
  const { t } = useTranslation();

  const [rows, setRows] = useState<DraftRow[]>(() =>
    drafts.map((d) => ({ ...d, selected: true }))
  );
  const [isAccepting, setIsAccepting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // UI-33 (Systemaudit 2026-08-27 AP-5): simple progress tracking for the
  // sequential accept loop — previously the whole multi-second operation
  // showed a single static spinner with no indication of how far it had
  // gotten, on top of the silent-partial-failure gap fixed below.
  const [acceptProgress, setAcceptProgress] = useState<{ done: number; total: number } | null>(
    null,
  );

  const updateRow = useCallback((index: number, patch: Partial<DraftRow>) => {
    setRows((prev) => prev.map((r, i) => (i === index ? { ...r, ...patch } : r)));
  }, []);

  const selectedCount = rows.filter((r) => r.selected && r.title.trim()).length;

  const handleAccept = useCallback(async () => {
    const selected = rows.filter((r) => r.selected && r.title.trim());
    if (selected.length === 0) return;
    setIsAccepting(true);
    setError(null);
    setAcceptProgress({ done: 0, total: selected.length });
    let createdCount = 0;
    try {
      // Sequential on purpose: each requirement must exist before its
      // 'derives-from' link is written, and the backend applies per-artifact
      // versioning we do not want to race.
      for (const row of selected) {
        let created: { id: string } | null = null;
        try {
          created = await requirementsApi.create({
            workspace_id: workspaceId,
            title: row.title.trim(),
            description: row.description,
          });
          await tracelinksApi.create({
            source_id: created.id,
            target_id: needArtifactId,
            link_type: "derives-from",
          });
        } catch (rowErr) {
          // UI-33: a mid-loop failure previously stopped silently with a
          // generic "derive failed" message, giving no indication that some
          // drafts were already persisted, and — if it was the TraceLink
          // step that threw — left the in-flight draft's Requirement
          // orphaned (created but never linked back to the Need). Report
          // exactly how many succeeded and best-effort roll back the orphan
          // before surfacing the error, then stop instead of silently
          // abandoning the remaining drafts.
          if (created) {
            try {
              await requirementsApi.delete(created.id);
            } catch {
              // Best-effort only — the partial-failure message below
              // already tells the user to check manually.
            }
          }
          const apiErr = rowErr as { error?: { message?: string } };
          const baseMessage = apiErr?.error?.message ?? t("needs.deriveFailed");
          setError(
            createdCount > 0
              ? t("deriveRequirements.partialFailure", {
                  created: createdCount,
                  total: selected.length,
                  message: baseMessage,
                  defaultValue: `${createdCount} of ${selected.length} requirements were created, then: ${baseMessage}`,
                })
              : baseMessage,
          );
          if (createdCount > 0) onAccepted?.(createdCount);
          return;
        }
        createdCount += 1;
        setAcceptProgress({ done: createdCount, total: selected.length });
      }
      onAccepted?.(createdCount);
    } finally {
      setIsAccepting(false);
      setAcceptProgress(null);
    }
  }, [rows, workspaceId, needArtifactId, onAccepted, t]);

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
            <Spinner
              label={
                acceptProgress
                  ? t("deriveRequirements.acceptingProgress", {
                      done: acceptProgress.done,
                      total: acceptProgress.total,
                      defaultValue: `Creating ${acceptProgress.done}/${acceptProgress.total}...`,
                    })
                  : t("deriveRequirements.accepting")
              }
            />
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
