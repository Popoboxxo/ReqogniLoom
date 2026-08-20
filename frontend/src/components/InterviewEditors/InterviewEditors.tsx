/**
 * ARCH-L1-001 ReactFrontend — InterviewEditors (plan Task 6/7).
 *
 * Main view for interview sessions -- SplitView(InterviewList | InterviewDetail),
 * same page shape every other artifact type gets (AdrEditors/RiskEditors/...).
 * Closes the "Interview artifact doesn't show up in the UI / workflow engine"
 * gap: sessions are now workflow-tracked entities with their own list/detail
 * route instead of only existing behind the floating chat widget.
 *
 * Interfaces implemented:
 * IF-RF-INT-001 <- NavigationShell activates
 * IF-RF-INT-003 <- session id URL params
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { SplitView } from "../SplitView/SplitView";
import { PageHeader } from "../shared/PageHeader";
import { Dialog } from "../shared/Dialog";
import { Spinner } from "../shared/Spinner/Spinner";
import { InterviewList } from "./InterviewList";
import { InterviewDetail } from "./InterviewDetail";
import { useInterviewData } from "./useInterviewData";
import { useWorkspace } from "../../context/WorkspaceContext";
import { interviewsApi } from "../../api/interviews";
import { extractErrorMessage } from "../../api/client";
import { INTERVIEW_ARTIFACT_TYPES } from "../../constants/interviewArtifactTypes";
import styles from "./InterviewEditors.module.css";

export default function InterviewEditors(): JSX.Element {
  const { t } = useTranslation();
  const { id: selectedId } = useParams<{ id?: string }>();
  const navigate = useNavigate();
  const { activeWorkspace } = useWorkspace();
  const { items, item, isLoading, error, refresh } = useInterviewData(selectedId);

  const [showStartDialog, setShowStartDialog] = useState(false);
  const [startingType, setStartingType] = useState<string | null>(null);
  const [startError, setStartError] = useState<string | null>(null);
  const firstTypeButtonRef = useRef<HTMLButtonElement>(null);

  const openStartDialog = useCallback((): void => {
    setStartError(null);
    setShowStartDialog(true);
  }, []);

  const closeStartDialog = useCallback((): void => {
    setShowStartDialog(false);
    setStartError(null);
  }, []);

  const handleStart = async (artifactType: string): Promise<void> => {
    if (!activeWorkspace) return;
    setStartingType(artifactType);
    setStartError(null);
    try {
      const state = await interviewsApi.start(activeWorkspace.id, artifactType);
      setShowStartDialog(false);
      refresh();
      navigate(`/interviews/${state.id}`);
    } catch (err) {
      setStartError(extractErrorMessage(err));
    } finally {
      setStartingType(null);
    }
  };

  // CTA entry point from other artifact list pages ("Prefer to create it in
  // a dialog?" -- RequirementEditors & co. link here as `/interviews?start=<Type>`).
  // Skips the picker dialog since the type is already known; the param is
  // stripped right away so back/refresh never re-triggers a second session.
  const [searchParams, setSearchParams] = useSearchParams();
  const autoStartRequested = useRef(false);
  useEffect(() => {
    const requestedType = searchParams.get("start");
    if (!requestedType || autoStartRequested.current || !activeWorkspace) return;
    if (!INTERVIEW_ARTIFACT_TYPES.includes(requestedType as (typeof INTERVIEW_ARTIFACT_TYPES)[number])) return;
    autoStartRequested.current = true;
    setSearchParams({}, { replace: true });
    void handleStart(requestedType);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams, activeWorkspace]);

  const selectedSummary = items.find((s) => s.id === selectedId);

  if (isLoading && items.length === 0) {
    return <p className={styles.statusMessage}>{t("loading", "Laden...")}</p>;
  }

  if (error && items.length === 0) {
    return (
      <div role="alert" className={styles.errorMessage}>
        <p className={styles.errorText}>{error.message}</p>
        <button className="btn-secondary" onClick={refresh} data-testid="interview-reload-btn">
          {t("actions.retry", "Retry")}
        </button>
      </div>
    );
  }

  return (
    <div data-testid="interviews-page" className={styles.page}>
      <PageHeader
        title={t("nav.interviews", "Interviews")}
        summary={t("interviews.summary", { count: items.length })}
        primaryAction={{
          label: t("interviews.newInterview", "New Interview"),
          onClick: openStartDialog,
          testId: "create-interview-btn",
        }}
      />

      <div className={styles.splitWrapper}>
        <SplitView
          leftPanel={<InterviewList items={items} selectedId={selectedId} onSelect={(id) => navigate(`/interviews/${id}`)} />}
          rightPanel={<InterviewDetail interview={item} artifactType={selectedSummary?.artifact_type} onChanged={refresh} />}
          initialLeftWidth={350}
          moduleType="interviews"
        />
      </div>

      {showStartDialog && (
        <Dialog
          title={t("interviews.newInterview", "New Interview")}
          description={t(
            "interviews.newInterviewDescription",
            "Pick what you want to brainstorm -- the assistant will interview you for it.",
          )}
          onClose={closeStartDialog}
          testId="interview-start-dialog"
          initialFocusRef={firstTypeButtonRef}
        >
          <div className={styles.typeGrid}>
            {INTERVIEW_ARTIFACT_TYPES.map((type, i) => (
              <button
                key={type}
                type="button"
                ref={i === 0 ? firstTypeButtonRef : undefined}
                className={styles.typeButton}
                data-testid={`interview-start-${type}`}
                disabled={startingType !== null}
                onClick={() => void handleStart(type)}
              >
                {startingType === type ? <Spinner label={t("actions.creating", "Starting...")} /> : type}
              </button>
            ))}
          </div>
          {startError && (
            <p role="alert" data-testid="interview-start-error" className={styles.createError}>
              {startError}
            </p>
          )}
        </Dialog>
      )}
    </div>
  );
}
