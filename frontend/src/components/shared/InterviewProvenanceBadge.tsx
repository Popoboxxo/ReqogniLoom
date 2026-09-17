/**
 * InterviewProvenanceBadge — "this artifact came out of an interview".
 *
 * Renders nothing until the backend confirms an interview provenance row for
 * `artifactId` (`GET /interviews/by-artifact/{artifact_id}/` answers
 * `{ session_id: null }` for plain artifacts), then links to that session.
 *
 * `artifactId` may be either the Artifact PK or the artifact's own subtype id
 * — the backend resolves both (InterviewService.provenance_session_id) — so
 * callers can pass whichever id they already hold.
 *
 * Mounted once, in the shared ArtifactInspector RightSidebar, rather than in
 * each artifact editor: RightSidebar is the single detail-panel shell every
 * artifact route already renders, so one mount covers all of them and no new
 * artifact type can forget it.
 */
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { interviewsApi } from "../../api/interviews";
import styles from "./InterviewProvenanceBadge.module.css";

interface InterviewProvenanceBadgeProps {
  artifactId: string;
}

export function InterviewProvenanceBadge({
  artifactId,
}: InterviewProvenanceBadgeProps): JSX.Element | null {
  const { t } = useTranslation();
  const [sessionId, setSessionId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setSessionId(null);
    interviewsApi
      .getProvenance(artifactId)
      .then((r) => {
        if (!cancelled) setSessionId(r.session_id);
      })
      .catch(() => {
        // Lookup failure degrades to "no provenance" -- the badge is purely
        // informational and must never surface as an unhandled rejection.
        if (!cancelled) setSessionId(null);
      });
    return () => {
      cancelled = true;
    };
  }, [artifactId]);

  if (!sessionId) return null;

  return (
    <Link
      to={`/interviews/${sessionId}`}
      className={styles.badge}
      data-testid="interview-provenance-badge"
      title={t("interviews.provenanceHint", "Open the interview that created this")}
    >
      {t("interview.multi.createdBadge")}
    </Link>
  );
}
