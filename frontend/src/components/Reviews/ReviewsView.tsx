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

  const { approve: APPROVE_TARGET, reject: REJECT_TARGET } =
    REVIEW_ACTION_CONFIG[selectedArtifactType];

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
  } = useReviewsData({
    selectedId,
    includeHistory: tab === "history",
    artifactType: selectedArtifactType,
  });

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
  const approveLabel =
    APPROVE_TARGET === "approved"
      ? t("reviews.approve", "Approve")
      : toTitleCase(APPROVE_TARGET);
  const rejectLabel =
    REJECT_TARGET === "draft"
      ? t("reviews.reject", "Reject")
      : toTitleCase(REJECT_TARGET);

  const listPanel = (
    <div data-testid="reviews-list">
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "var(--space-2)",
          marginBottom: "var(--space-2)",
        }}
      >
        <label
          htmlFor="reviews-type-select"
          style={{ fontWeight: 600, fontSize: "var(--font-size-sm)" }}
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
          style={{
            height: "32px",
            flex: "1 1 0",
            minWidth: 0,
            borderRadius: "var(--radius-sm)",
            border: "1px solid var(--color-border)",
            padding: "0 var(--space-2)",
            fontSize: "var(--font-size-sm)",
            fontFamily: "inherit",
            background: "var(--color-surface)",
            color: "var(--color-text)",
            boxSizing: "border-box",
          }}
        >
          {ARTIFACT_TYPE_OPTIONS.map((type) => (
            <option key={type} value={type}>
              {t(`reviews.type.${type}`, toTitleCase(type))}
            </option>
          ))}
        </select>
      </div>

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
              entityType={DIFF_KIND[selectedArtifactType]}
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
              {isActing ? t("reviews.approving", "Approving...") : approveLabel}
            </button>
            <button
              type="button"
              data-testid="review-reject-btn"
              className="btn-danger"
              disabled={isActing || transitionsLoading || !rejectAllowed}
              onClick={() => handleAction(REJECT_TARGET)}
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
      <h1 style={{ marginTop: 0 }}>{t("nav.reviews", "Reviews")}</h1>
      <SplitView leftPanel={listPanel} rightPanel={detailPanel} moduleType="reviews" />
    </div>
  );
}
