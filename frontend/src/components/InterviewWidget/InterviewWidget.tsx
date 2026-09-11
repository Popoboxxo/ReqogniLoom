/**
 * Interview-management web widget — quick entry point (spec L2.5).
 *
 * A `position: fixed` overlay, always mounted (via NavigationShell) on every
 * authenticated route. Its ONLY job is picking what to interview about and
 * handing off to `/interviews?start=<Type>`, which starts the session and
 * routes to `/interviews/{id}`.
 *
 * It deliberately hosts no chat: interviews are multi-turn conversations that
 * need more room than an overlay comfortably gives, and an overlay that stays
 * open across navigation while covering forms is a UX problem for long
 * sessions (audit finding S19). `/interviews` is the single full interview
 * surface — `InterviewChatPane`/`InterviewArtifactPane` (still in this folder)
 * are rendered there, by `InterviewEditors/InterviewDetail`.
 *
 * WRITE-gate note: WorkspaceContext exposes no currentUserRole-like field, so
 * all nine buttons stay visible for every authenticated user — pre-existing
 * behaviour, deliberately unchanged here.
 */
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { useWorkspace } from "../../context/WorkspaceContext";
import { INTERVIEW_ARTIFACT_TYPES } from "../../constants/interviewArtifactTypes";
import { MULTI_START_PARAM } from "../InterviewEditors/InterviewEditors";
import styles from "./InterviewWidget.module.css";

const STORAGE_KEY = "reqflow-interview-widget-open";

/**
 * Defensive localStorage wrapper (issue #679) — direct `window.localStorage`
 * access throws in third-party-cookie-restricted browsers, private-browsing
 * storage lockouts, and JSDOM test environments where the property is
 * unavailable/mocked out (`TypeError: Cannot read properties of undefined`,
 * or a `SecurityError`). The toggle-open state persisted here is a
 * nice-to-have, never worth freezing the widget over.
 */
export const safeLocalStorage = {
  getItem: (key: string): string | null => {
    try {
      return window.localStorage.getItem(key);
    } catch {
      return null;
    }
  },
  setItem: (key: string, value: string): void => {
    try {
      window.localStorage.setItem(key, value);
    } catch {
      // Storage unavailable (private browsing, disabled cookies, etc.) — silently no-op.
    }
  },
};

export function InterviewWidget(): JSX.Element {
  const { activeWorkspace } = useWorkspace();
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    setOpen(safeLocalStorage.getItem(STORAGE_KEY) === "true");
  }, []);

  const setOpenPersisted = (next: boolean): void => {
    setOpen(next);
    safeLocalStorage.setItem(STORAGE_KEY, String(next));
  };

  /**
   * Hand off to the interviews route, which owns session creation. Closing
   * the panel first is what satisfies the S19 "must not stay open across
   * navigation, covering the page underneath" finding.
   */
  const goToInterview = (startParam: string): void => {
    setOpenPersisted(false);
    navigate(`/interviews?start=${startParam}`);
  };

  if (!activeWorkspace) return <></>;

  return (
    <>
      <button
        type="button"
        data-testid="interview-widget-toggle"
        className={styles.toggle}
        onClick={() => setOpenPersisted(!open)}
        // #741: the FAB renders nothing but the 💬 glyph, so the label IS the
        // whole accessible name. It used to be a hardcoded English string —
        // now translated and state-aware (open vs. close), matching the
        // sidebar burger toggle (nav.openMenu / nav.closeMenu).
        aria-label={
          open
            ? t("interview.widget.close", "Interview-Assistent schließen")
            : t("interview.widget.open", "Interview-Assistent öffnen")
        }
        title={t("interview.widget.title", "Interview-Assistent")}
        aria-expanded={open}
        aria-controls="interview-widget-panel"
      >
        <span aria-hidden="true">{"\u{1F4AC}"}</span>
      </button>
      {open && (
        <div
          id="interview-widget-panel"
          data-testid="interview-widget-panel"
          className={styles.panel}
          role="group"
          aria-label={t("interview.widget.title", "Interview-Assistent")}
        >
          <p className={styles.hint}>{t("interview.widget.hint")}</p>
          <div className={styles.startRow}>
            {INTERVIEW_ARTIFACT_TYPES.map((type) => (
              <button
                key={type}
                type="button"
                data-testid={`interview-widget-start-${type}`}
                className={styles.startButton}
                onClick={() => goToInterview(type)}
              >
                {t(`interview.start.${type}`)}
              </button>
            ))}
            {/* Discovery entry point for users who don't know yet which
                artifact type they need (WRITE-gate: see module docstring —
                visible for all users by deliberate default). */}
            <button
              type="button"
              data-testid={`interview-widget-start-${MULTI_START_PARAM}`}
              className={styles.startButton}
              onClick={() => goToInterview(MULTI_START_PARAM)}
            >
              {t("interview.multiEntry")}
            </button>
          </div>
        </div>
      )}
    </>
  );
}
