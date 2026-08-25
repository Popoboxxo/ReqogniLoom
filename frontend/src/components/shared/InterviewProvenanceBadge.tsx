/**
 * InterviewProvenanceBadge — multi-artifact-interview plan, Task 14
 * (frontend half).
 *
 * Renders nothing until the backend confirms an interview provenance row
 * for `artifactId` (`GET /interviews/by-artifact/{artifact_id}/` returns
 * `{ session_id: null }` for plain artifacts), then renders a link to the
 * interview area labeled via the shared `interview.multi.createdBadge`
 * i18n key. Kept in `components/shared/` per plan — wiring it into each of
 * the 9 artifact detail views is explicitly scoped-out follow-up work.
 */
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { interviewsApi } from "../../api/interviews";

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
    <Link to="/interviews" data-testid="interview-provenance-badge">
      {t("interview.multi.createdBadge")}
    </Link>
  );
}
