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

import { useCallback, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { SplitView } from "../SplitView/SplitView";
import { ListToolbar } from "../shared/ListToolbar";
import { ArtifactDiff, type DiffEntityType } from "../ArtifactDiff/ArtifactDiff";
import { type AllowedTransition } from "../../api/requirements";
import type { WorkflowArtifactType } from "../../api/workflow-transitions";
import { extractErrorMessage } from "../../api/client";
import { ForbiddenError } from "../../api/errors";
import { useReviewsData } from "./useReviewsData";
import { SignatureDialog } from "./SignatureDialog";
import { ReviewHistoryPanel } from "./ReviewHistoryPanel";

type ReviewTab = "details" | "history";

// The two moves the review queue cares about — REQ-144 keeps the queue
// scoped to the `in_review` state, so these are the only transitions the
// Approve/Reject buttons ever attempt to resolve.
const APPROVE_TARGET = "approved";
const REJECT_TARGET = "draft";

// REQ-167: map the workflow artifact type to the ArtifactDiff entity kind so
// the shared diff renderer labels/routes correctly for every entity type.
const DIFF_KIND: Record<WorkflowArtifactType, DiffEntityType> = {
  requirement: "requirement",
  need: "stakeholderNeed",
  adr: "adr",
  "test-case": "testCase",
  risk: "risk",
  issue: "issue",
};

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
  artifactType = "requirement",
}: ReviewsViewProps = {}): JSX.Element {
  const { t } = useTranslation();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [tab, setTab] = useState<ReviewTab>("details");
  const [showDiff, setShowDiff] = useState(false);
  const [changeReason, setChangeReason] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const [isActing, setIsActing] = useState(false);
  const [pendingTransition, setPendingTransition] = useState<AllowedTransition | null>(null);

  const {
    items,
    isLoading,
    error,
    transitions,
    transitionsLoading,
    history,
    historyLoading,
    historyError,
    transition,
    diff,
    versions,
  } = useReviewsData({ selectedId, includeHistory: tab === "history", artifactType });

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return items;
    return items.filter(
      (r) =>
        r.title.toLowerCase().includes(q) ||
        (r.uid ?? "").toLowerCase().includes(q)
    );
  }, [items, search]);

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

  const listPanel = (
    <div data-testid="reviews-list">
      <ListToolbar
        searchValue={search}
        onSearchChange={setSearch}
        searchPlaceholder={t("reviews.searchPlaceholder", "Search reviews...")}
        countLabel={`${filtered.length} / ${items.length}`}
        testIdPrefix="reviews"
      />

      {isLoading && (
        <p role="status" style={{ color: "var(--color-text-muted)" }}>
          {t("loading")}
        </p>
      )}

      {error && (
        <p role="alert" data-testid="reviews-list-error" style={{ color: "var(--color-danger)" }}>
          {error}
        </p>
      )}

      {!isLoading && !error && filtered.length === 0 && (
        <p data-testid="reviews-empty" style={{ color: "var(--color-text-muted)" }}>
          {t("reviews.empty", "No requirements pending review.")}
        </p>
      )}

      <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
        {filtered.map((r) => (
          <li key={r.id}>
            <button
              type="button"
              data-testid={`review-list-item-${r.id}`}
              onClick={() => handleSelect(r.id)}
              style={{
                width: "100%",
                textAlign: "left",
                padding: "var(--space-2) var(--space-3)",
                marginBottom: "var(--space-1)",
                borderRadius: "var(--radius-md)",
                border: "1px solid var(--color-border)",
                background:
                  r.id === selectedId
                    ? "var(--color-surface-hover, #eef2ff)"
                    : "var(--color-surface)",
                cursor: "pointer",
              }}
            >
              <div style={{ fontWeight: 600 }}>{r.title}</div>
              {r.uid && (
                <div style={{ fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)" }}>
                  {r.uid}
                </div>
              )}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );

  const detailPanel = !selected ? (
    <p data-testid="review-detail-empty" style={{ color: "var(--color-text-muted)" }}>
      {t("reviews.selectPrompt", "Select a requirement from the list.")}
    </p>
  ) : (
    <div data-testid="review-detail">
      <div style={{ display: "flex", gap: "var(--space-2)", marginBottom: "var(--space-3)" }}>
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
          <h2 style={{ margin: 0 }}>{selected.title}</h2>
          <p style={{ whiteSpace: "pre-wrap", color: "var(--color-text)" }}>
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
              entityType={DIFF_KIND[artifactType]}
              currentVersion={selected.version ?? 1}
              diffFetcher={diff}
              versionsFetcher={versions}
              onClose={() => setShowDiff(false)}
            />
          )}

          <div style={{ marginTop: "var(--space-4)" }}>
            <label
              htmlFor="review-change-reason"
              style={{ display: "block", fontWeight: 600, marginBottom: "var(--space-1)" }}
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
              style={{ width: "100%", boxSizing: "border-box" }}
              disabled={isActing}
            />
          </div>

          {actionError && (
            <p role="alert" data-testid="review-action-error" style={{ color: "var(--color-danger)" }}>
              {actionError}
            </p>
          )}

          <div style={{ display: "flex", gap: "var(--space-2)", marginTop: "var(--space-3)" }}>
            <button
              type="button"
              data-testid="review-approve-btn"
              className="btn-primary"
              disabled={isActing || transitionsLoading || !approveAllowed}
              onClick={() => handleAction(APPROVE_TARGET)}
            >
              {isActing ? t("reviews.approving", "Approving...") : t("reviews.approve", "Approve")}
            </button>
            <button
              type="button"
              data-testid="review-reject-btn"
              className="btn-danger"
              disabled={isActing || transitionsLoading || !rejectAllowed}
              onClick={() => handleAction(REJECT_TARGET)}
            >
              {isActing ? t("reviews.rejecting", "Rejecting...") : t("reviews.reject", "Reject")}
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
      <h1 style={{ marginTop: 0 }}>{t("nav.reviews", "Reviews")}</h1>
      <SplitView leftPanel={listPanel} rightPanel={detailPanel} moduleType="reviews" />
    </div>
  );
}
