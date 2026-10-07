/**
 * ARCH-L1-001 ReactFrontend — ReviewsView (COMP-RF-REV-001).
 *
 * leaf_id: COMP-RF-REV-001
 * req_id:  REQ-144 (Review/Approval UI on top of the REQ-143 WorkflowEngine),
 *          REQ-L2-RF-007 (Preset-basierte Sichtbarkeit — gated by `approver_ui`),
 *          REQ-002 (Split-View Layout)
 *
 * Split-View layout with resizable divider:
 *   - Left panel: requirements currently `in_review` in the active workspace
 *     (REQ-003 ListToolbar for free-text search)
 *   - Right panel: two tabs —
 *       "Details": title/description, diff-to-previous-version (reusing the
 *         shared ArtifactDiff component), and Approve/Reject actions.
 *       "History": the append-only workflow transition log (ReviewHistoryPanel).
 *
 * Approve/Reject both delegate to the generic WorkflowEngine `transitions`
 * contract (REQ-143): "Approve" targets the `approved` state, "Reject"
 * targets `draft`. Both buttons are disabled while the transitions GET is
 * loading or when the corresponding move is not in `allowed_transitions`
 * (e.g. the caller lacks the approver role, or the workspace preset does
 * not wire an in_review -> draft/approved move).
 *
 * When the resolved transition has `signature_gate: true`, the action opens
 * SignatureDialog to collect a credential (password/TOTP) before the POST
 * is sent, instead of transitioning directly.
 *
 * Interfaces consumed:
 *   IF-RF-EXT-OUT-001 → GET  /api/v1/requirements/?workspace_id=&status=in_review
 *   IF-RF-EXT-OUT-001 → GET  /api/v1/requirements/{id}/transitions/
 *   IF-RF-EXT-OUT-001 → POST /api/v1/requirements/{id}/transitions/
 *   IF-RF-EXT-OUT-001 → GET  /api/v1/requirements/{id}/workflow-history/
 *   IF-RF-EXT-OUT-001 → GET  /api/v1/requirements/{id}/diff/, /versions/
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { SplitView } from "../SplitView/SplitView";
import { PageHeader } from "../shared/PageHeader";
import { ListToolbar } from "../shared/ListToolbar";
import { ArtifactDiff, type DiffEntityType } from "../ArtifactDiff/ArtifactDiff";
import { type AllowedTransition } from "../../api/requirements";
import {
  workflowTransitionsApi,
  type WorkflowArtifactType,
} from "../../api/workflow-transitions";
import { extractErrorMessage } from "../../api/client";
import { ForbiddenError } from "../../api/errors";
import { useReviewsData, type ReviewQueueMode } from "./useReviewsData";
import { SignatureDialog } from "./SignatureDialog";
import { ReviewHistoryPanel } from "./ReviewHistoryPanel";
import { getWorkflowStatusLabel } from "../../utils/workflowStatus";
import styles from "./ReviewsView.module.css";

// UI-34 (Systemaudit 2026-08-27 AP-5): the queue rendered every loaded item
// in one unbounded `<ul>` with no pagination controls at all. This paginates
// what `useReviewsData` already loaded (mirrors the client-side pagination
// pattern other list views use); it does not change how many items are
// fetched per page from the backend — see the caveat on `PAGE_SIZE` in the
// component below.
const REVIEWS_PAGE_SIZE = 20;

// Issue #1089: the workflow state the proposal state is injected under, in
// every non-minimal graph (backend/workflow/definition_store.py
// PROPOSED_STATE). Duplicated here as a literal on purpose — the backend
// source is not importable from the SPA bundle, and `pendingStateFor` in
// useReviewsData already pins the same literal for the queue query; a
// divergence between the two would show an origin badge for a non-proposal.
const PROPOSED_STATE = "proposed";

type ReviewTab = "details" | "history";

// REQ-168: per-type approve/reject targets. The review queue keeps the queue
// scoped to the `in_review` state, so these are the only transitions the
// Approve/Reject buttons ever attempt to resolve — but the concrete target
// state depends on the selected entity type's workflow (e.g. a risk moves to
// `mitigated`, an ADR to `accepted`). The server re-validates every move
// against the configured state machine regardless (REQ-L3-WF-004).
const REVIEW_ACTION_CONFIG: Record<
  WorkflowArtifactType,
  { approve: string; reject: string }
> = {
  requirement: { approve: "approved", reject: "draft" },
  need: { approve: "approved", reject: "draft" },
  adr: { approve: "accepted", reject: "draft" },
  "test-case": { approve: "approved", reject: "draft" },
  risk: { approve: "mitigated", reject: "open" },
  issue: { approve: "resolved", reject: "open" },
  architecture: { approve: "approved", reject: "draft" },
  // REQ-168: icd/glossary lifecycles land on the default approved/draft pair
  // until their state machines diverge; the server stays authoritative.
  icd: { approve: "approved", reject: "draft" },
  glossary: { approve: "approved", reject: "draft" },
  // REQ-173: diagrams join the review queue on the default approved/draft pair;
  // the server-side state machine stays authoritative.
  diagram: { approve: "approved", reject: "draft" },
  // Issue #372: Goal/MainGoal (workflow/definition_store.py goal_default /
  // main_goal_default) use their own "Entwurf" -> "Freigegeben" ->
  // "Archiviert" lifecycle (no draft/approved/in_review naming). The queue
  // lists items in "Entwurf" (see useReviewsData's PENDING_STATE_OVERRIDES),
  // so "approve" targets "Freigegeben"; there is no earlier state to reject
  // back to, so "reject" targets "Archiviert" (discard the draft), mirroring
  // the Entwurf -> Archiviert escape-hatch transition goal_default already
  // defines for goal.delete (issue #216).
  goal: { approve: "Freigegeben", reject: "Archiviert" },
  "main-goal": { approve: "Freigegeben", reject: "Archiviert" },
};

// REQ-168: the entity types the review queue can switch between, derived from
// the action config so both stay in lockstep as new workflow types land.
const ARTIFACT_TYPE_OPTIONS = Object.keys(
  REVIEW_ACTION_CONFIG
) as WorkflowArtifactType[];

// REQ-168: render a workflow target state / entity type as a human label
// ("mitigated" -> "Mitigated", "test-case" -> "Test Case").
function toTitleCase(value: string): string {
  return value
    .split(/[-_\s]+/)
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

// REQ-167: map the workflow artifact type to the ArtifactDiff entity kind so
// the shared diff renderer labels/routes correctly for every entity type.
const DIFF_KIND: Record<WorkflowArtifactType, DiffEntityType> = {
  requirement: "requirement",
  need: "stakeholderNeed",
  adr: "adr",
  "test-case": "testCase",
  risk: "risk",
  issue: "issue",
  architecture: "architecture",
  icd: "icd",
  glossary: "glossary",
  diagram: "diagram",
  // Issue #372: ArtifactKind (shared/ArtifactInspector/types.ts) already
  // defines "goal"/"mainGoal" diff kinds; wire them here so ArtifactDiff
  // labels/routes correctly. GH-1200 closed the backend gap this comment used
  // to flag: GoalViewSet/MainGoalViewSet now expose a `diff` action alongside
  // `versions` (ArtifactDiffService.diff_for_goal/.diff_for_main_goal), so
  // "View Diff" fetches a real field-level diff for these two types too.
  goal: "goal",
  "main-goal": "mainGoal",
};

/**
 * Confirm a list of proposals one at a time (spec §4.4, minimal bulk edit).
 *
 * Sequential on purpose: each call is a workflow transition with optimistic
 * locking and a server-side validator, and firing N of them in parallel turns
 * a partial failure into an unreadable pile of 409s. A failing item never
 * aborts the run — the caller reports both lists.
 *
 * Issue #1193: the rejected promise used to be swallowed (`catch {}`), so a
 * server rejection — e.g. a missing/invalid `change_reason`, or the item no
 * longer being in the proposal state — produced only a bare "N failed" count
 * with no cause. The optional `onError` callback surfaces the thrown value per
 * failing id so the caller can show *why* the approval did not go through.
 */
export async function bulkConfirm(
  ids: readonly string[],
  confirmOne: (id: string) => Promise<unknown>,
  onError?: (id: string, error: unknown) => void,
): Promise<{ confirmed: string[]; failed: string[] }> {
  const confirmed: string[] = [];
  const failed: string[] = [];
  for (const id of ids) {
    try {
      await confirmOne(id);
      confirmed.push(id);
    } catch (error) {
      failed.push(id);
      onError?.(id, error);
    }
  }
  return { confirmed, failed };
}

function findTransition(
  transitions: AllowedTransition[] | undefined,
  targetState: string
): AllowedTransition | undefined {
  return transitions?.find((t) => t.target_state === targetState);
}

export interface ReviewsViewProps {
  /**
   * REQ-167: the entity type whose review queue is shown. Defaults to
   * "requirement" so the existing `/reviews` route (rendered without props)
   * keeps its Requirement-only behavior.
   */
  artifactType?: WorkflowArtifactType;
}

export default function ReviewsView({
  artifactType: initialArtifactType = "requirement",
}: ReviewsViewProps = {}): JSX.Element {
  const { t } = useTranslation();
  // REQ-168: the entity type is now selectable in the list toolbar. The prop
  // seeds the initial type so callers passing an explicit type (and the
  // historical Requirement-only behavior) keep working.
  const [selectedArtifactType, setSelectedArtifactType] =
    useState<WorkflowArtifactType>(initialArtifactType);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [tab, setTab] = useState<ReviewTab>("details");
  const [showDiff, setShowDiff] = useState(false);
  const [changeReason, setChangeReason] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const [isActing, setIsActing] = useState(false);
  const [pendingTransition, setPendingTransition] = useState<AllowedTransition | null>(null);
  const [queueMode, setQueueMode] = useState<ReviewQueueMode>("review");
  const [selectedIds, setSelectedIds] = useState<readonly string[]>([]);
  const [bulkResult, setBulkResult] = useState<{ ok: number; failed: number } | null>(
    null,
  );
  // #1193: the first failure reason of the last bulk confirm, surfaced inline
  // instead of being swallowed behind a bare "N failed" count.
  const [bulkError, setBulkError] = useState<string | null>(null);

  const {
    items,
    isLoading,
    error,
    pendingProposalCount,
    proposalCountLoading,
    totalPendingCount,
    totalPendingCountLoading,
    otherTypesPendingCount,
    transitions,
    transitionsLoading,
    history,
    historyLoading,
    historyError,
    transition,
    diff,
    versions,
    refreshList,
  } = useReviewsData({
    selectedId,
    includeHistory: tab === "history",
    artifactType: selectedArtifactType,
    queueMode,
  });

  // #1089: the item open in the detail pane is an AI proposal when the
  // workflow engine says so. `proposed_by` is the actor of the newest
  // `-> "proposed"` history entry (the #904 mechanism); it is null for every
  // non-proposal item, so this single nullable field is the whole test — the
  // same one WorkflowStatusEditor already branches on, rendered here because
  // the review queue is where a reviewer decides whether to trust the content.
  //
  // Read through a local widening cast: the backend has returned `proposed_by`
  // on GET .../transitions/ since #904 (`WorkflowTransitionsMixin.transitions`
  // → `resolve_proposed_by`) and `WorkflowTransitionsResponse` in
  // `api/workflow-transitions.ts` types it, but the requirement-specific
  // `RequirementTransitions` in `api/requirements.ts` — which is what the
  // `requirement` resolver hands back — still declares only the three original
  // keys. The cast is a workaround for that gap, not a claim that the field is
  // optional: it is null-or-string by contract.
  const proposedBy = (
    transitions as { proposed_by?: string | null } | null
  )?.proposed_by;
  const proposalOrigin = useMemo(() => {
    if (queueMode !== "proposals") return null;
    if (!transitions || transitions.current_state !== PROPOSED_STATE) return null;
    return proposedBy
      ? t("workflow.proposal.hint", { agent: proposedBy })
      : t("workflow.proposal.hintUnknown");
  }, [queueMode, transitions, proposedBy, t]);

  // In proposals mode the confirm target is the graph's own initial state and
  // the discard target its reject state — both come back in
  // `transitions.allowed_transitions`, so read them rather than maintaining a
  // second per-type table that would drift from the backend graph.
  //
  // SCOPE (security review M4): `transitions` belongs to `selectedId`, the item
  // open in the DETAIL pane, so this pair is only ever valid for the detail
  // Approve/Reject buttons. It must NOT be reused for bulk actions over
  // `selectedIds` — see `confirmProposal` below, which resolves per item. The
  // `?? "draft"`/`?? "rejected"` fallbacks below are unreachable in a request:
  // with no `transitions`, `approveAllowed`/`rejectAllowed` resolve to
  // undefined and both buttons are disabled.
  const { approve: APPROVE_TARGET, reject: REJECT_TARGET } = useMemo(() => {
    if (queueMode !== "proposals") return REVIEW_ACTION_CONFIG[selectedArtifactType];
    const allowed = transitions?.allowed_transitions ?? [];
    return {
      approve: allowed.find((t) => !t.requires_change_reason)?.target_state ?? "draft",
      reject: allowed.find((t) => t.requires_change_reason)?.target_state ?? "rejected",
    };
  }, [queueMode, selectedArtifactType, transitions]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return items;
    return items.filter(
      (r) =>
        r.title.toLowerCase().includes(q) ||
        (r.uid ?? "").toLowerCase().includes(q)
    );
  }, [items, search]);

  // UI-34: page state for the queue list, reset whenever the filtered set's
  // origin changes (new search term or a different artifact type) so a page
  // number from a longer previous result set cannot point past the end of a
  // shorter one.
  const [page, setPage] = useState(1);
  const totalPages = Math.max(1, Math.ceil(filtered.length / REVIEWS_PAGE_SIZE));
  const clampedPage = Math.min(page, totalPages);
  const paged = useMemo(
    () =>
      filtered.slice(
        (clampedPage - 1) * REVIEWS_PAGE_SIZE,
        clampedPage * REVIEWS_PAGE_SIZE
      ),
    [filtered, clampedPage]
  );

  useEffect(() => {
    setPage(1);
    setSelectedIds([]);
    // Security review minor: without this the "N proposals confirmed" toast
    // survived a switch to a different artifact type or back to review mode,
    // where it describes a run against a queue that is no longer on screen.
    setBulkResult(null);
    setBulkError(null);
  }, [search, selectedArtifactType, queueMode]);

  /**
   * Confirm one proposal, resolving its target state from the item ITSELF.
   *
   * Security review M4. This used to reuse `APPROVE_TARGET`, which is derived
   * from `transitions` — the allowed transitions of the item currently open in
   * the detail pane, not of the items being bulk-confirmed. In the normal bulk
   * flow (tick checkboxes, click confirm) nothing is selected for detail at
   * all, so `transitions` was `undefined` and the target fell back to the
   * literal `"draft"`, which is not a valid target for most types
   * (adr -> `Draft`, goal -> `Entwurf`, risk -> `Identified`, issue -> `Open`)
   * — every bulk-confirm click failed.
   *
   * One GET per item is the price of correctness here: the confirm target is
   * the item's graph's own initial state, which varies by artifact type AND by
   * workspace customization, so there is no table to read it from. The run is
   * already sequential (see `bulkConfirm`).
   */
  const confirmProposal = useCallback(
    async (id: string, reason = ""): Promise<void> => {
      const detail = await workflowTransitionsApi.getTransitions(
        selectedArtifactType,
        id,
      );
      // The proposal graph gives `proposed` exactly two moves: confirm (to the
      // initial state, no change_reason) and discard (to the reject state,
      // change_reason required). Confirm is the one that needs no reason.
      const confirm = (detail?.allowed_transitions ?? []).find(
        (candidate) => !candidate.requires_change_reason,
      );
      if (!confirm) {
        // #1193: a human-readable cause, not a raw `No confirm transition
        // available for <id>` string — this message is now what the bulk
        // handler renders inline when a row cannot be confirmed.
        throw new Error(t("reviews.transitionUnavailable"));
      }
      // #1193: thread the reviewer's reason through. The confirm move does not
      // require one today, but dropping whatever the user typed previously hid
      // the case where a workspace's graph *does* require it — the server then
      // answered 400 and the caller never saw it.
      if (reason.trim()) {
        await workflowTransitionsApi.transition(
          selectedArtifactType,
          id,
          confirm.target_state,
          reason,
        );
      } else {
        // Keep the no-reason call shape byte-identical to before so existing
        // callers/tests are unaffected when there is nothing to send.
        await workflowTransitionsApi.transition(
          selectedArtifactType,
          id,
          confirm.target_state,
        );
      }
    },
    [selectedArtifactType, t],
  );

  const selected = useMemo(
    () => items.find((r) => r.id === selectedId) ?? null,
    [items, selectedId]
  );

  const handleSelect = useCallback((id: string): void => {
    setSelectedId(id);
    setTab("details");
    setShowDiff(false);
    setChangeReason("");
    setActionError(null);
    setPendingTransition(null);
  }, []);

  // REQ-168: switching the entity type reloads a different review queue, so
  // clear every selection-scoped piece of state to avoid carrying a stale
  // selection / search / reason across types.
  const handleTypeChange = useCallback((type: WorkflowArtifactType): void => {
    setSelectedArtifactType(type);
    setSelectedId(null);
    setSearch("");
    setChangeReason("");
    setTab("details");
    setShowDiff(false);
    setActionError(null);
    setPendingTransition(null);
  }, []);

  // REQ-144: shared by the direct Approve/Reject path and the signature
  // dialog's submit handler. change_reason is enforced client-side when the
  // transition requires it — the server re-validates regardless
  // (REQ-L3-WF-004).
  const runTransition = useCallback(
    async (allowed: AllowedTransition, reason: string, credential?: string): Promise<void> => {
      if (allowed.requires_change_reason && !reason.trim()) {
        setActionError(t("reviews.changeReasonRequired"));
        throw new Error("change_reason required");
      }
      setIsActing(true);
      setActionError(null);
      try {
        await transition({ targetState: allowed.target_state, changeReason: reason, credential });
        setChangeReason("");
        setPendingTransition(null);
      } catch (err: unknown) {
        if (err instanceof ForbiddenError) {
          setActionError(err.message || t("reviews.forbidden"));
        } else {
          setActionError(extractErrorMessage(err));
        }
        throw err;
      } finally {
        setIsActing(false);
      }
    },
    [t, transition]
  );

  // REQ-144: Approve/Reject first resolve the transition from the GET
  // contract (already loaded via useReviewsData). Signature-gated
  // transitions open SignatureDialog instead of transitioning directly.
  const handleAction = useCallback(
    (targetState: string): void => {
      const allowed = findTransition(transitions?.allowed_transitions, targetState);
      if (!allowed) {
        setActionError(t("reviews.transitionUnavailable"));
        return;
      }
      setActionError(null);
      if (allowed.signature_gate) {
        setPendingTransition(allowed);
        return;
      }
      void runTransition(allowed, changeReason).catch(() => {
        // Surfaced via actionError above; nothing further to do here.
      });
    },
    [transitions, runTransition, changeReason, t]
  );

  const submitSignatureDialog = useCallback(
    async (credential: string, reason: string): Promise<void> => {
      if (!pendingTransition) return;
      await runTransition(pendingTransition, reason, credential);
    },
    [pendingTransition, runTransition]
  );

  const approveAllowed = findTransition(transitions?.allowed_transitions, APPROVE_TARGET);
  const rejectAllowed = findTransition(transitions?.allowed_transitions, REJECT_TARGET);

  // REQ-168: keep the generic "Approve"/"Reject" wording for the default
  // requirement-style targets, but surface the concrete state name for types
  // whose approve/reject lands somewhere else (e.g. "Mitigated", "Accepted").
  // UI-34 (Systemaudit 2026-08-27 AP-5): this used to run the raw target
  // state through `toTitleCase` (a mechanical word-capitalizer), not through
  // the shared `getWorkflowStatusLabel` i18n-aware mapping every other
  // workflow view (AdrForm, WorkflowStatusEditor's badge, ...) already uses
  // — so e.g. a Goal's "Freigegeben" target rendered as the raw German word
  // instead of going through the same label pipeline as everywhere else.
  const approveLabel =
    APPROVE_TARGET === "approved"
      ? t("reviews.approve", "Approve")
      : getWorkflowStatusLabel(APPROVE_TARGET);
  const rejectLabel =
    REJECT_TARGET === "draft"
      ? t("reviews.reject", "Reject")
      : getWorkflowStatusLabel(REJECT_TARGET);

  // UI-34: the Approve/Reject buttons disabled themselves whenever the
  // target state was missing from `allowed_transitions` with no indication
  // why — the GET .../transitions/ contract only lists moves that ARE
  // allowed, so a disabled button could mean "still loading", "already in
  // that state", or "role/precondition denied" with no way to tell them
  // apart from the response alone. This surfaces the one case the frontend
  // *can* distinguish (already in the target state) and otherwise names the
  // two remaining possibilities together, rather than leaving the disabled
  // button unexplained.
  const buildDisabledReason = useCallback(
    (targetState: string, allowed: AllowedTransition | undefined): string | undefined => {
      if (!selected) return undefined;
      if (transitionsLoading) {
        return t("reviews.disabledLoading", "Loading available actions...");
      }
      if (allowed) return undefined;
      if (transitions && transitions.current_state === targetState) {
        return t("reviews.disabledAlreadyInState", {
          state: getWorkflowStatusLabel(targetState),
          defaultValue: `Already ${getWorkflowStatusLabel(targetState)}.`,
        });
      }
      // Reuses the existing `transitionUnavailable` copy (already shown as
      // the action-error banner on a stale click) rather than a near-
      // duplicate string, since the frontend cannot distinguish "role
      // missing" from "precondition not met" from the GET response alone.
      return t(
        "reviews.transitionUnavailable",
        "This transition is not available (role or workflow configuration)."
      );
    },
    [selected, transitionsLoading, transitions, t]
  );
  const approveDisabledReason = buildDisabledReason(APPROVE_TARGET, approveAllowed);
  const rejectDisabledReason = buildDisabledReason(REJECT_TARGET, rejectAllowed);

  const listPanel = (
    <div data-testid="reviews-list">
      <div className={styles.typeRow}>
        <label
          htmlFor="reviews-type-select"
          className={styles.typeLabel}
        >
          {t("reviews.typeLabel", "Type")}
        </label>
        <select
          id="reviews-type-select"
          data-testid="reviews-type-select"
          value={selectedArtifactType}
          onChange={(e) =>
            handleTypeChange(e.target.value as WorkflowArtifactType)
          }
          className={styles.typeSelect}
        >
          {ARTIFACT_TYPE_OPTIONS.map((type) => (
            <option key={type} value={type}>
              {t(`reviews.type.${type}`, toTitleCase(type))}
            </option>
          ))}
        </select>
        {/* #1193: the per-type filter made the page look empty while 68
            approvals were pending elsewhere. The aggregate count answers "is
            anything waiting at all?" independent of the selected type. */}
        {!totalPendingCountLoading &&
          totalPendingCount !== null &&
          totalPendingCount > 0 && (
            <span
              className={styles.totalBadge}
              data-testid="reviews-total-pending"
            >
              {t("reviews.totalPending", { count: totalPendingCount })}
            </span>
          )}
      </div>

      <label data-testid="reviews-queue-mode-toggle" className={styles.queueModeRow}>
        <input
          type="checkbox"
          data-testid="reviews-queue-mode-checkbox"
          checked={queueMode === "proposals"}
          onChange={(e) =>
            setQueueMode(e.target.checked ? "proposals" : "review")
          }
        />
        {t("workflow.proposal.queueMode")}
        {/* #1089: "3 KI-Vorschläge warten auf Prüfung". Without the number the
            toggle is an undiscoverable empty-looking switch — the reviewer has
            no way to learn that the AI left something behind without first
            clicking it. Hidden while loading or at zero, so a workspace with
            no proposals keeps the same label it always had. */}
        {proposalCountLoading ? null : pendingProposalCount > 0 ? (
          <span className={styles.queueModeCount} data-testid="reviews-proposal-count">
            {pendingProposalCount}
          </span>
        ) : null}
      </label>

      {queueMode === "proposals" && selectedIds.length > 0 && (
        <button
          type="button"
          data-testid="reviews-bulk-confirm-btn"
          disabled={isActing}
          onClick={async () => {
            setIsActing(true);
            setBulkError(null);
            // Fix F3: the state reset has to be unconditional. Previously a
            // rejected `refreshList()` threw past `setIsActing(false)`, leaving
            // the Confirm button disabled forever (nothing re-enables it).
            try {
              // #1193: collect the cause of every failed confirmation so the
              // reviewer learns *why* (e.g. a rejected `change_reason`) instead
              // of only that something failed.
              const failures: string[] = [];
              const { confirmed, failed } = await bulkConfirm(
                selectedIds,
                (id) => confirmProposal(id, changeReason),
                (_id, error) => failures.push(extractErrorMessage(error)),
              );
              setSelectedIds([]);
              setBulkResult({ ok: confirmed.length, failed: failed.length });
              setBulkError(failures.length > 0 ? failures[0] : null);
              await refreshList();
            } finally {
              setIsActing(false);
            }
          }}
        >
          {t("workflow.proposal.bulkConfirm")} ({selectedIds.length})
        </button>
      )}
      {bulkResult && (
        <p role="status" data-testid="reviews-bulk-confirm-result">
          {t("workflow.proposal.bulkConfirmDone", { count: bulkResult.ok })}
          {bulkResult.failed > 0
            ? ` — ${t("workflow.proposal.bulkConfirmFailed", { count: bulkResult.failed })}`
            : ""}
        </p>
      )}
      {/* #1193: the cause behind the "N failed" count — previously the
          rejection was swallowed entirely. */}
      {bulkError && (
        <p
          role="alert"
          data-testid="reviews-bulk-confirm-error"
          className={styles.errorText}
        >
          {t("reviews.bulkConfirmError")}: {bulkError}
        </p>
      )}

      <ListToolbar
        searchValue={search}
        onSearchChange={setSearch}
        searchPlaceholder={t("reviews.searchPlaceholder", "Search reviews...")}
        countLabel={`${filtered.length} / ${items.length}`}
        testIdPrefix="reviews"
      />

      {/* #1193: "In other types there are N open approvals" — the default
          requirement filter can legitimately be empty while the workspace has
          dozens of pending items under other types. This hint turns a silent
          empty queue into a discoverable one. */}
      {!isLoading && !error && otherTypesPendingCount > 0 && (
        <p
          data-testid="reviews-other-types-hint"
          className={styles.mutedText}
        >
          {t("reviews.otherTypesHint", { count: otherTypesPendingCount })}
        </p>
      )}

      {isLoading && (
        <p role="status" className={styles.mutedText}>
          {t("loading")}
        </p>
      )}

      {error && (
        <p role="alert" data-testid="reviews-list-error" className={styles.errorText}>
          {error}
        </p>
      )}

      {!isLoading && !error && filtered.length === 0 && (
        <p data-testid="reviews-empty" className={styles.mutedText}>
          {t("reviews.empty", "No requirements pending review.")}
        </p>
      )}

      <ul className={styles.reviewList}>
        {paged.map((r) => (
          <li key={r.id} className={styles.reviewRow}>
            {queueMode === "proposals" && (
              <input
                type="checkbox"
                data-testid={`review-select-${r.id}`}
                checked={selectedIds.includes(r.id)}
                onChange={(e) =>
                  setSelectedIds((prev) =>
                    e.target.checked
                      ? [...prev, r.id]
                      : prev.filter((id) => id !== r.id),
                  )
                }
                onClick={(e) => e.stopPropagation()}
              />
            )}
            <button
              type="button"
              data-testid={`review-list-item-${r.id}`}
              onClick={() => handleSelect(r.id)}
              className={`${styles.reviewItem} ${
                r.id === selectedId
                  ? styles.reviewItemSelected
                  : styles.reviewItemUnselected
              }`}
            >
              <div className={styles.reviewItemTitle}>{r.title}</div>
              {r.uid && (
                <div className={styles.reviewItemUid}>
                  {r.uid}
                </div>
              )}
              {/* #1089: every row in this queue is by definition in the
                  "proposed" state, so the badge is what tells the reviewer
                  *before* opening the item that the content came from the AI
                  rather than from a colleague. */}
              {queueMode === "proposals" && (
                <span
                  className={styles.proposalBadge}
                  data-testid={`review-proposal-badge-${r.id}`}
                >
                  {t("workflow.proposal.hintUnknown")}
                </span>
              )}
            </button>
          </li>
        ))}
      </ul>

      {filtered.length > REVIEWS_PAGE_SIZE && (
        <div
          data-testid="reviews-pagination"
          className={styles.paginationRow}
        >
          <button
            type="button"
            data-testid="reviews-pagination-prev"
            className="btn-secondary"
            disabled={clampedPage <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            {t("actions.previous", "Previous")}
          </button>
          <span className={styles.paginationIndicator}>
            {t("reviews.pageIndicator", {
              page: clampedPage,
              totalPages,
              defaultValue: `Page ${clampedPage} / ${totalPages}`,
            })}
          </span>
          <button
            type="button"
            data-testid="reviews-pagination-next"
            className="btn-secondary"
            disabled={clampedPage >= totalPages}
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
          >
            {t("actions.next", "Next")}
          </button>
        </div>
      )}
    </div>
  );

  const detailPanel = !selected ? (
    <p data-testid="review-detail-empty" className={styles.mutedText}>
      {t("reviews.selectPrompt", "Select a requirement from the list to view details.")}
    </p>
  ) : (
    <div data-testid="review-detail">
      <div className={styles.detailTabRow}>
        <button
          type="button"
          data-testid="review-detail-tab-details"
          className={tab === "details" ? "btn-primary" : "btn-secondary"}
          onClick={() => setTab("details")}
        >
          {t("reviews.tabDetails", "Details")}
        </button>
        <button
          type="button"
          data-testid="review-detail-tab-history"
          className={tab === "history" ? "btn-primary" : "btn-secondary"}
          onClick={() => setTab("history")}
        >
          {t("reviews.tabHistory", "History")}
        </button>
      </div>

      {tab === "history" ? (
        <ReviewHistoryPanel entries={history} isLoading={historyLoading} error={historyError} />
      ) : (
        <>
          <h2 className={styles.detailTitle}>{selected.title}</h2>
          {proposalOrigin && (
            <p
              className={styles.proposalOrigin}
              data-testid="review-proposal-origin"
            >
              {proposalOrigin}
            </p>
          )}
          <p className={styles.detailDescription}>
            {selected.description}
          </p>

          <button
            type="button"
            data-testid="review-view-diff-btn"
            className={showDiff ? "btn-primary" : "btn-secondary"}
            onClick={() => setShowDiff((v) => !v)}
          >
            {showDiff ? t("editor.hideDiff") : t("editor.viewDiff")}
          </button>

          {showDiff && (
            <ArtifactDiff
              entityId={selected.id}
              entityType={DIFF_KIND[selectedArtifactType]}
              // GH-1200: Goal/MainGoal expose their revisions in the
              // `sequence_number` namespace (1..N); `version` is the
              // never-incremented optimistic-lock counter, so passing it made
              // ArtifactDiff seed to === from and fetch nothing. Prefer the
              // sequence number when the backend supplies it.
              currentVersion={selected.sequence_number ?? selected.version ?? 1}
              diffFetcher={diff}
              versionsFetcher={versions}
              onClose={() => setShowDiff(false)}
            />
          )}

          <div className={styles.changeReasonSlot}>
            <label
              htmlFor="review-change-reason"
              className={styles.changeReasonLabel}
            >
              {t("reviews.changeReasonLabel", "Reason")}
            </label>
            <textarea
              id="review-change-reason"
              data-testid="review-change-reason-input"
              value={changeReason}
              onChange={(e) => setChangeReason(e.target.value)}
              placeholder={t(
                "reviews.changeReasonPlaceholder",
                "Why are you approving/rejecting this requirement?"
              )}
              rows={3}
              className={styles.changeReasonInput}
              disabled={isActing}
            />
          </div>

          {actionError && (
            <p role="alert" data-testid="review-action-error" className={styles.errorText}>
              {actionError}
            </p>
          )}

          {/* GitHub #1192: Rule 5 can refuse an approval while the preset's
              mandatory fields are empty — the transition is still listed as
              allowed, so the button gives no hint until the POST 400s. Explain
              the gate up front; the artifact form marks the concrete fields.
              The hint's `id` lets the Approve button reference it below, so the
              explanation reaches assistive tech too, not only sighted users. */}
          {approveAllowed ? (
            <p
              id="review-gate-hint"
              data-testid="review-gate-hint"
              className={styles.mutedText}
            >
              {t("reviews.gateHint")}
            </p>
          ) : null}

          <div className={styles.detailActions}>
            <button
              type="button"
              data-testid="review-approve-btn"
              className="btn-primary"
              disabled={isActing || transitionsLoading || !approveAllowed}
              aria-describedby={approveAllowed ? "review-gate-hint" : undefined}
              onClick={() => handleAction(APPROVE_TARGET)}
              title={!isActing ? approveDisabledReason : undefined}
              aria-label={
                !isActing && approveDisabledReason
                  ? `${approveLabel}: ${approveDisabledReason}`
                  : undefined
              }
            >
              {isActing ? t("reviews.approving", "Approving...") : approveLabel}
            </button>
            <button
              type="button"
              data-testid="review-reject-btn"
              className="btn-danger"
              disabled={isActing || transitionsLoading || !rejectAllowed}
              onClick={() => handleAction(REJECT_TARGET)}
              title={!isActing ? rejectDisabledReason : undefined}
              aria-label={
                !isActing && rejectDisabledReason
                  ? `${rejectLabel}: ${rejectDisabledReason}`
                  : undefined
              }
            >
              {isActing ? t("reviews.rejecting", "Rejecting...") : rejectLabel}
            </button>
          </div>
        </>
      )}

      {pendingTransition && (
        <SignatureDialog
          isOpen
          targetState={pendingTransition.target_state}
          requiresChangeReason={pendingTransition.requires_change_reason}
          initialChangeReason={changeReason}
          onClose={() => setPendingTransition(null)}
          onSubmit={submitSignatureDialog}
        />
      )}
    </div>
  );

  return (
    <div data-testid="reviews-view">
      <PageHeader
        title={t("nav.reviews", "Reviews")}
        count={{ shown: filtered.length, total: items.length }}
      />
      <SplitView leftPanel={listPanel} rightPanel={detailPanel} moduleType="reviews" />
    </div>
  );
}
