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
 *   - Right panel: title/description, diff-to-previous-version (reusing the
 *     shared ArtifactDiff component), and Approve/Reject actions.
 *
 * Approve/Reject both delegate to the generic WorkflowEngine `transitions`
 * contract (REQ-143): "Approve" targets the `approved` state, "Reject"
 * targets `draft`. Both buttons are disabled while the transitions GET is
 * loading or when the corresponding move is not in `allowed_transitions`
 * (e.g. the caller lacks the approver role, or the workspace preset does
 * not wire an in_review -> draft/approved move).
 *
 * Interfaces consumed:
 *   IF-RF-EXT-OUT-001 → GET  /api/v1/requirements/?workspace_id=&status=in_review
 *   IF-RF-EXT-OUT-001 → GET  /api/v1/requirements/{id}/transitions/
 *   IF-RF-EXT-OUT-001 → POST /api/v1/requirements/{id}/transitions/
 *   IF-RF-EXT-OUT-001 → GET  /api/v1/requirements/{id}/diff/, /versions/
 */

import { useCallback, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { SplitView } from "../SplitView/SplitView";
import { ListToolbar } from "../shared/ListToolbar";
import { ArtifactDiff } from "../ArtifactDiff/ArtifactDiff";
import { requirementsApi, type AllowedTransition } from "../../api/requirements";
import { extractErrorMessage } from "../../api/client";
import { ForbiddenError } from "../../api/errors";
import { useReviewsData } from "./useReviewsData";

// The two moves the review queue cares about — REQ-144 keeps the queue
// scoped to the `in_review` state, so these are the only transitions the
// Approve/Reject buttons ever attempt to resolve.
const APPROVE_TARGET = "approved";
const REJECT_TARGET = "draft";

function findTransition(
  transitions: AllowedTransition[] | undefined,
  targetState: string
): AllowedTransition | undefined {
  return transitions?.find((t) => t.target_state === targetState);
}

export default function ReviewsView(): JSX.Element {
  const { t } = useTranslation();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [showDiff, setShowDiff] = useState(false);
  const [changeReason, setChangeReason] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const [isActing, setIsActing] = useState(false);

  const { requirements, isLoading, error, transitions, transitionsLoading, transition } =
    useReviewsData({ selectedId });

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return requirements;
    return requirements.filter(
      (r) =>
        r.title.toLowerCase().includes(q) ||
        (r.uid ?? "").toLowerCase().includes(q)
    );
  }, [requirements, search]);

  const selected = useMemo(
    () => requirements.find((r) => r.id === selectedId) ?? null,
    [requirements, selectedId]
  );

  const handleSelect = useCallback((id: string): void => {
    setSelectedId(id);
    setShowDiff(false);
    setChangeReason("");
    setActionError(null);
  }, []);

  // REQ-144: Approve/Reject resolve the transition from the GET contract
  // (already loaded via useReviewsData) and POST it directly. change_reason
  // is only enforced client-side when the transition requires it — the
  // server re-validates regardless (REQ-L3-WF-004).
  const handleAction = useCallback(
    async (targetState: string): Promise<void> => {
      const allowed = findTransition(transitions?.allowed_transitions, targetState);
      if (!allowed) {
        setActionError(t("reviews.transitionUnavailable"));
        return;
      }
      if (allowed.requires_change_reason && !changeReason.trim()) {
        setActionError(t("reviews.changeReasonRequired"));
        return;
      }
      setIsActing(true);
      setActionError(null);
      try {
        await transition({ targetState, changeReason });
        setChangeReason("");
      } catch (err: unknown) {
        if (err instanceof ForbiddenError) {
          setActionError(err.message || t("reviews.forbidden"));
        } else {
          setActionError(extractErrorMessage(err));
        }
      } finally {
        setIsActing(false);
      }
    },
    [transitions, changeReason, t, transition]
  );

  const approveAllowed = findTransition(transitions?.allowed_transitions, APPROVE_TARGET);
  const rejectAllowed = findTransition(transitions?.allowed_transitions, REJECT_TARGET);

  const listPanel = (
    <div data-testid="reviews-list">
      <ListToolbar
        searchValue={search}
        onSearchChange={setSearch}
        searchPlaceholder={t("reviews.searchPlaceholder", "Search reviews...")}
        countLabel={`${filtered.length} / ${requirements.length}`}
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
          entityType="requirement"
          currentVersion={selected.version}
          diffFetcher={requirementsApi.diff}
          versionsFetcher={requirementsApi.versions}
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
          onClick={() => void handleAction(APPROVE_TARGET)}
        >
          {isActing ? t("reviews.approving", "Approving...") : t("reviews.approve", "Approve")}
        </button>
        <button
          type="button"
          data-testid="review-reject-btn"
          className="btn-danger"
          disabled={isActing || transitionsLoading || !rejectAllowed}
          onClick={() => void handleAction(REJECT_TARGET)}
        >
          {isActing ? t("reviews.rejecting", "Rejecting...") : t("reviews.reject", "Reject")}
        </button>
      </div>
    </div>
  );

  return (
    <div data-testid="reviews-view">
      <h1 style={{ marginTop: 0 }}>{t("nav.reviews", "Reviews")}</h1>
      <SplitView leftPanel={listPanel} rightPanel={detailPanel} moduleType="reviews" />
    </div>
  );
}
