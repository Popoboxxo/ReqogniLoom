/**
 * ARCH-L1-001 ReactFrontend — MainGoalPanel (REQ-L2-TE-020).
 *
 * Shows the currently approved (Freigegeben) MainGoal of a workspace and lets
 * an editor produce a new draft either
 *   - via LLM aggregation of the workspace's approved Goals, or
 *   - by authoring it manually (`mainGoalApi.createManual`),
 * and then approve that draft.
 *
 * AI-toggle behaviour (design spec 6): the generate entry point stays VISIBLE
 * even when the workspace's AI toggle is off. The backend answers with an
 * explicit "AI generation is disabled for this workspace" error, which is
 * surfaced here — the button is deliberately not hidden client-side, so the
 * user learns why it is unavailable instead of the feature silently vanishing.
 *
 * UI concept rollout: identity row (StatusBadge + VersionBadge) above the
 * content, an empty state that offers the next step instead of reporting a
 * condition (ch. 3.5 / 12.7), and action labels that name the result
 * (ch. 14.2).
 *
 * Issue #238: the panel also offers the archive move, which it did not have
 * at all before — a MainGoal could be created and approved but never retired.
 * It is driven by the generic `/main-goals/{id}/transitions/` contract
 * (`workflowTransitionsApi`, which already lists `main-goal`), so a workspace
 * with a customised MainGoal state machine (ADR-06) gets its own moves rather
 * than a hardcoded "Archiviert".
 *
 * Issue #219: `onActiveChange` reports the MainGoal the panel is currently
 * showing so the page can mount the `<ArtifactInspector>` beside it — the
 * panel itself must not, because the inspector is a sibling of the whole
 * detail column, not of this card.
 */

import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { extractErrorMessage } from "../../api/client";
import { mainGoalApi } from "../../api/main-goal";
import { workflowTransitionsApi } from "../../api/workflow-transitions";
import type { WorkflowAllowedTransition } from "../../api/workflow-transitions";
import { StatusBadge } from "../shared/StatusBadge";
import { VersionBadge } from "../shared/VersionBadge";
import { ArchiveConfirmDialog } from "./ArchiveConfirmDialog";
import { isArchiveTransition, isDraftState } from "./goal-workflow";
import type { MainGoal, UUID } from "../../types";

interface MainGoalPanelProps {
  workspaceId: UUID;
  aiEnabled: boolean;
  /**
   * Reports the MainGoal currently on screen (the draft while one exists,
   * otherwise the approved one, `null` when there is neither). Issue #219 —
   * the page uses it as the inspector's subject.
   */
  onActiveChange?: (mainGoal: MainGoal | null) => void;
}

const sectionStyle: React.CSSProperties = {
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-md)",
  background: "var(--color-surface-raised)",
  padding: "var(--space-4)",
};

const bodyStyle: React.CSSProperties = {
  margin: 0,
  maxWidth: "var(--measure)",
  fontSize: "var(--font-size-base)",
  lineHeight: "var(--leading-relaxed)",
  color: "var(--color-text)",
  whiteSpace: "pre-wrap",
};

export function MainGoalPanel({
  workspaceId,
  aiEnabled,
  onActiveChange,
}: MainGoalPanelProps): JSX.Element {
  const { t } = useTranslation();
  const [current, setCurrent] = useState<MainGoal | null>(null);
  const [draft, setDraft] = useState<MainGoal | null>(null);
  const [manualContent, setManualContent] = useState("");
  const [manualOpen, setManualOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [archiveTransition, setArchiveTransition] =
    useState<WorkflowAllowedTransition | null>(null);
  const [archivePending, setArchivePending] = useState<WorkflowAllowedTransition | null>(
    null,
  );

  useEffect(() => {
    let cancelled = false;
    // Review round 2, finding 1: the panel is rendered without a `key` in
    // `GoalsPage` (workspace switches do not remount it), so a workspace
    // change re-runs this effect with new props but leaves whatever `draft`/
    // `error` state the PREVIOUS workspace left behind on screen until this
    // fetch resolves — an approve button bound to another workspace's draft
    // id, and a stale error banner. Clear both up front, before the first
    // `await`, so switching to a workspace with neither shows neither.
    setDraft(null);
    setError(null);
    void (async () => {
      let approved: MainGoal | null = null;
      try {
        // "No approved main goal yet" is an empty result, not an error
        // (ch. 13.3): the endpoint answers 200 with an empty body, so
        // normalise undefined to null and let the empty state speak.
        approved = (await mainGoalApi.current(workspaceId)) ?? null;
      } catch (err) {
        if (!cancelled) setError(extractErrorMessage(err));
        return;
      }
      if (cancelled) return;
      setCurrent(approved);

      // Issue #221 finding 6: before this, `draft` was only ever set by
      // handleGenerate/handleCreateManual/handleApprove — a page refresh
      // after generating or authoring a draft made the Approve control
      // unreachable for the rest of that draft's life, even though the
      // backend still had it. Re-derive it from the workspace's full
      // version chain: the newest row that is neither approved nor
      // archived AND newer than the currently approved row (so an older,
      // abandoned draft below the current version never resurfaces and
      // outranks it). A failed lookup degrades quietly, same contract as
      // the archive-transitions lookup below — the approved MainGoal above
      // already rendered.
      try {
        const versions = await mainGoalApi.list(workspaceId);
        if (cancelled || !Array.isArray(versions)) return;
        const approvedSeq = approved?.sequence_number ?? -1;
        const pendingDraft = versions
          .filter(
            (mg) => mg.sequence_number > approvedSeq && isDraftState(mg.status),
          )
          .sort((a, b) => b.sequence_number - a.sequence_number)[0];
        // Review round 2, recommendation 4: if the user generated/authored
        // their own fresh draft while this hydration fetch was still in
        // flight, a late-arriving `pendingDraft` here must not clobber it
        // with an older one — keep whatever is already on screen.
        if (pendingDraft) setDraft((prev) => prev ?? pendingDraft);
      } catch {
        // no-op — see comment above.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [workspaceId]);

  // The artifact on screen: a fresh draft takes precedence over the approved
  // version, because that is what the user is working on.
  const active = draft ?? current;

  useEffect(() => {
    onActiveChange?.(active);
  }, [active, onActiveChange]);

  // Which moves the WorkflowEngine currently allows for the approved main
  // goal. A 404 (no workflow configured) or 403 (role gate) degrades to "no
  // archive button" rather than an error banner — same contract GoalDetail
  // uses for Goal.
  useEffect(() => {
    const target = current;
    if (!target) {
      setArchiveTransition(null);
      return undefined;
    }
    let cancelled = false;
    void (async () => {
      try {
        const resp = await workflowTransitionsApi.getTransitions("main-goal", target.id);
        if (cancelled) return;
        const allowed = Array.isArray(resp?.allowed_transitions)
          ? resp.allowed_transitions
          : [];
        setArchiveTransition(
          allowed.find((tr) => isArchiveTransition(tr.target_state)) ?? null,
        );
      } catch {
        if (!cancelled) setArchiveTransition(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [current]);

  const handleGenerate = async (): Promise<void> => {
    setError(null);
    try {
      setDraft(await mainGoalApi.generate(workspaceId));
    } catch (err) {
      setError(extractErrorMessage(err));
    }
  };

  const handleCreateManual = async (): Promise<void> => {
    setError(null);
    try {
      setDraft(await mainGoalApi.createManual(workspaceId, manualContent));
      setManualContent("");
      setManualOpen(false);
    } catch (err) {
      setError(extractErrorMessage(err));
    }
  };

  const handleApprove = async (id: string): Promise<void> => {
    setError(null);
    try {
      // The backend returns the FULLY serialized MainGoal (including
      // `content`), so this can replace the panel state directly.
      const approved = await mainGoalApi.approve(id);
      setCurrent(approved);
      setDraft(null);
    } catch (err) {
      setError(extractErrorMessage(err));
    }
  };

  const handleArchive = useCallback(
    async (transition: WorkflowAllowedTransition): Promise<void> => {
      const target = current;
      if (!target) return;
      setError(null);
      try {
        // Issue #221 finding 1 — same computed-string scope boundary as
        // `GoalsPage.runTransition`: see the comment there for why this
        // does not (yet) prompt for a real reason.
        await workflowTransitionsApi.transition(
          "main-goal",
          target.id,
          transition.target_state,
          transition.requires_change_reason
            ? t("goals.transitionReason", {
                state: transition.target_state,
                defaultValue: `Statuswechsel nach ${transition.target_state}.`,
              })
            : "",
        );
        // `MainGoalService.get_current()` returns the NEWEST `Freigegeben`
        // row, which is not necessarily `null` after archiving: e.g. v1
        // approved, then v2 generated+approved, then v2 archived leaves v1
        // (still `Freigegeben`) as the current one. Re-fetch instead of
        // assuming "none approved" so the panel, the inspector, and the
        // backend agree. This also re-derives `archiveTransition` for the
        // new current row via the effect keyed on `current`.
        const refreshed = await mainGoalApi.current(workspaceId);
        setCurrent(refreshed ?? null);
      } catch (err) {
        setError(extractErrorMessage(err));
      }
    },
    [current, t, workspaceId],
  );

  // Issue #238 finding 2: the dialog closes BEFORE the request starts (same
  // pattern as `GoalsPage.confirmArchive`), so a doubled click on the confirm
  // button cannot fire a second `transitions/` request — the button is gone
  // by the time the first request is even in flight.
  const confirmArchive = useCallback((): void => {
    if (!archivePending) return;
    const transition = archivePending;
    setArchivePending(null);
    void handleArchive(transition);
  }, [archivePending, handleArchive]);

  const archiveLabel = archiveTransition
    ? t(`goals.transition.${archiveTransition.target_state}`, {
        defaultValue: archiveTransition.target_state,
      })
    : "";

  return (
    <div data-testid="main-goal-panel" style={sectionStyle}>
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "var(--space-2)",
          marginBottom: "var(--space-3)",
        }}
      >
        <h2
          style={{
            margin: 0,
            fontSize: "var(--font-size-xl)",
            lineHeight: "var(--leading-tight)",
            letterSpacing: "var(--tracking-tight)",
            fontWeight: "var(--weight-semibold)",
            color: "var(--color-text)",
          }}
        >
          {t("goals.mainGoal", "Haupt-Ziel")}
        </h2>
        {current && (
          <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
            <StatusBadge status={current.status} testId="main-goal-status" />
            <VersionBadge version={current.sequence_number} hideWhenFirst />
          </div>
        )}
      </div>

      {error && (
        <p
          data-testid="main-goal-error"
          role="alert"
          style={{
            color: "var(--color-danger)",
            fontSize: "var(--font-size-sm)",
            marginTop: 0,
          }}
        >
          {error}
        </p>
      )}

      {current ? (
        <p style={bodyStyle}>{current.content}</p>
      ) : (
        <div data-testid="main-goal-empty">
          <p
            style={{
              margin: 0,
              fontSize: "var(--font-size-lg)",
              fontWeight: "var(--weight-semibold)",
              color: "var(--color-text)",
            }}
          >
            {t("goals.mainGoalNone", "Noch kein Haupt-Ziel freigegeben.")}
          </p>
          <p
            style={{
              margin: "var(--space-2) 0 0",
              maxWidth: "var(--measure)",
              fontSize: "var(--font-size-sm)",
              lineHeight: "var(--leading-normal)",
              color: "var(--color-text-muted)",
            }}
          >
            {t(
              "goals.mainGoalNoneHint",
              "Das Haupt-Ziel fasst die freigegebenen Ziele des Workspace zusammen.",
            )}
          </p>
        </div>
      )}

      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "var(--space-2)",
          marginTop: "var(--space-4)",
        }}
      >
        <button
          type="button"
          className="btn-secondary"
          data-testid="main-goal-generate-button"
          onClick={() => void handleGenerate()}
          title={
            aiEnabled
              ? undefined
              : t(
                  "goals.generateDisabledHint",
                  "KI-Generierung ist für diesen Workspace deaktiviert.",
                )
          }
        >
          {t("goals.generate", "Haupt-Ziel per KI erzeugen")}
        </button>
        <button
          type="button"
          className="btn-secondary"
          data-testid="main-goal-manual-toggle-button"
          aria-expanded={manualOpen}
          onClick={() => {
            setError(null);
            setManualOpen((open) => !open);
          }}
        >
          {manualOpen
            ? t("goals.manualCancel", "Eingabe abbrechen")
            : t("goals.manualOpen", "Haupt-Ziel selbst schreiben")}
        </button>
        {/*
            The archive move — the only way to retire a MainGoal, since
            MainGoals cannot be deleted (see goal-workflow.ts). Only shown
            when the WorkflowEngine actually allows it for the caller. */}
        {current && archiveTransition && (
          <button
            type="button"
            className="btn-danger"
            data-testid="main-goal-archive-button"
            onClick={() => {
              setError(null);
              setArchivePending(archiveTransition);
            }}
          >
            {archiveLabel}
          </button>
        )}
      </div>

      {manualOpen && (
        <form
          data-testid="main-goal-manual-form"
          onSubmit={(e) => {
            e.preventDefault();
            void handleCreateManual();
          }}
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "var(--space-2)",
            marginTop: "var(--space-3)",
          }}
        >
          <label
            htmlFor="main-goal-manual"
            style={{
              fontSize: "var(--font-size-sm)",
              fontWeight: "var(--weight-semibold)",
              color: "var(--color-text)",
            }}
          >
            {t("goals.manualPlaceholder", "Haupt-Ziel")}
          </label>
          <textarea
            id="main-goal-manual"
            data-testid="main-goal-manual-input"
            value={manualContent}
            rows={5}
            onChange={(e) => setManualContent(e.target.value)}
            style={{
              padding: "var(--space-2) var(--space-3)",
              borderRadius: "var(--radius-md)",
              border: "1px solid var(--color-border)",
              background: "var(--color-surface)",
              color: "var(--color-text)",
              fontFamily: "var(--font-sans)",
              fontSize: "var(--font-size-sm)",
              lineHeight: "var(--leading-normal)",
              resize: "vertical",
            }}
          />
          <div style={{ display: "flex", justifyContent: "flex-end" }}>
            <button
              type="submit"
              className="btn-primary"
              data-testid="main-goal-manual-create-button"
            >
              {t("goals.manualCreate", "Entwurf anlegen")}
            </button>
          </div>
        </form>
      )}

      {draft && (
        <div
          data-testid="main-goal-draft"
          style={{
            marginTop: "var(--space-4)",
            padding: "var(--space-3)",
            borderRadius: "var(--radius-md)",
            border: "1px dashed var(--color-border-hover)",
            background: "var(--color-surface)",
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "var(--space-2)",
              marginBottom: "var(--space-2)",
            }}
          >
            <StatusBadge status={draft.status} testId="main-goal-draft-status" />
            <VersionBadge version={draft.sequence_number} hideWhenFirst />
          </div>
          <p style={bodyStyle}>{draft.content}</p>
          <button
            type="button"
            className="btn-primary"
            data-testid="main-goal-approve-button"
            style={{ marginTop: "var(--space-3)" }}
            onClick={() => void handleApprove(draft.id)}
          >
            {t("goals.approve", "Freigeben")}
          </button>
        </div>
      )}

      {archivePending && current && (
        <ArchiveConfirmDialog
          testId="main-goal-archive-dialog"
          itemLabel={t("goals.mainGoal", "Haupt-Ziel")}
          confirmLabel={archiveLabel}
          onConfirm={confirmArchive}
          onCancel={() => setArchivePending(null)}
        />
      )}
    </div>
  );
}
