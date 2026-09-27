/**
 * Interview-management web widget — the assistant entry point, and since
 * ADR-009 also the home of the system notification feed.
 *
 * A `position: fixed` overlay, always mounted (via NavigationShell) on every
 * authenticated route. Its interview job is picking what to interview about
 * and handing off to `/interviews?start=<Type>`, which starts the session and
 * routes to `/interviews/{id}`.
 *
 * It deliberately hosts no chat: interviews are multi-turn conversations that
 * need more room than an overlay comfortably gives, and an overlay that stays
 * open across navigation while covering forms is a UX problem for long
 * sessions (audit finding S19). `/interviews` is the single full interview
 * surface — `InterviewChatPane`/`InterviewArtifactPane` (still in this folder)
 * are rendered there, by `InterviewEditors/InterviewDetail`.
 *
 * A notification *feed* is not a chat, which is why the feed could move in
 * without reopening S19: the panel is already 360px wide, exactly the width
 * the old 20rem sidebar dropdown used, so the feed fits without a new
 * surface and without a second entry point. What did move with it:
 *
 * - the unread signal, which used to sit on the sidebar's `NotificationBell`.
 *   It is now a badge on the widget toggle. That badge is the *only* access
 *   to the signal now that the sidebar row is gone (ADR-009 §Entscheidung 1
 *   and 3), so it is permanently mounted, carries `aria-live`, and fails
 *   visibly rather than silently;
 * - the panel's dismissal contract. `NotificationBell`'s popover was closed by
 *   Escape and by a click outside it, both pinned in `NotificationBell.test.tsx`
 *   (#985). The panel now honours the same two, and returns focus to the
 *   trigger — so removing the sidebar row did not quietly drop a keyboard
 *   affordance on the way;
 * - the unread count's single source of truth, `useNotificationFeed`. The
 *   sidebar row and the badge are not two counters; see that hook's header for
 *   why the widget persists only its open state in `localStorage` and can
 *   therefore never restore a cached badge for a user who switched the
 *   triggers off.
 *
 * WRITE-gate note: WorkspaceContext exposes no currentUserRole-like field, so
 * all nine buttons stay visible for every authenticated user — pre-existing
 * behaviour, deliberately unchanged here.
 */
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { useWorkspace } from "../../context/WorkspaceContext";
import { useNotificationFeed } from "../../hooks/useNotificationFeed";
import { INTERVIEW_ARTIFACT_TYPES, MULTI_START_PARAM } from "../../constants/interviewArtifactTypes";
import { NotificationFeed } from "./NotificationFeed";
import styles from "./InterviewWidget.module.css";

const STORAGE_KEY = "reqflow-interview-widget-open";

/** The two tabs of the panel. The interview start actions stay the default. */
type WidgetTab = "start" | "notifications";

const TAB_ORDER: readonly WidgetTab[] = ["start", "notifications"];

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
  const [tab, setTab] = useState<WidgetTab>("start");

  const toggleRef = useRef<HTMLButtonElement | null>(null);
  const dockRef = useRef<HTMLDivElement | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);
  const tabRefs = useRef<Partial<Record<WidgetTab, HTMLButtonElement | null>>>({});

  const feed = useNotificationFeed();

  // A total opt-out withdraws the notifications tab. If the user was reading
  // it when the preferences arrived, the selection falls back to the interview
  // tab — otherwise the panel would render a tabpanel no tab owns.
  useEffect(() => {
    if (feed.suppressed) setTab("start");
  }, [feed.suppressed]);

  useEffect(() => {
    setOpen(safeLocalStorage.getItem(STORAGE_KEY) === "true");
  }, []);

  const setOpenPersisted = useCallback((next: boolean): void => {
    setOpen(next);
    safeLocalStorage.setItem(STORAGE_KEY, String(next));
  }, []);

  // Issue #985, carried over from NotificationBell: the panel has to be
  // dismissable from the keyboard, and a click outside has to close it. Both
  // halves of the standard popover contract live here now that the feed's old
  // container is gone.
  //
  // Escape follows the same precedence as `useFocusTrap` (the shared Dialog
  // primitive): the *innermost* overlay handles the key and stops it, so an
  // outer overlay listening on the document does not also close. Focus returns
  // to the trigger, which is where the user came from.
  useEffect(() => {
    if (!open) return;

    const handleKeyDown = (event: KeyboardEvent): void => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      event.stopPropagation();
      setOpenPersisted(false);
      toggleRef.current?.focus();
    };

    // `pointerdown`, not `click`: the click that *opens* the panel would
    // otherwise be caught by the same listener on the way up the document.
    const handlePointerDown = (event: PointerEvent): void => {
      const target = event.target;
      if (!(target instanceof Node)) return;
      if (dockRef.current?.contains(target)) return;
      if (panelRef.current?.contains(target)) return;
      setOpenPersisted(false);
    };

    document.addEventListener("keydown", handleKeyDown, true);
    document.addEventListener("pointerdown", handlePointerDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown, true);
      document.removeEventListener("pointerdown", handlePointerDown);
    };
  }, [open, setOpenPersisted]);

  /**
   * Hand off to the interviews route, which owns session creation. Closing
   * the panel first is what satisfies the S19 "must not stay open across
   * navigation, covering the page underneath" finding.
   */
  const goToInterview = (startParam: string): void => {
    setOpenPersisted(false);
    navigate(`/interviews?start=${startParam}`);
  };

  /**
   * A feed row: mark it read, then follow it. The panel closes for the same
   * S19 reason `goToInterview` closes it — a navigation happened underneath.
   */
  const followArtifact = useCallback(
    (artifactId: string | null): void => {
      setOpenPersisted(false);
      if (artifactId !== null) navigate(`/artifacts/${artifactId}`);
    },
    [navigate, setOpenPersisted]
  );

  /**
   * ARIA tabs keyboard support: Left/Right move between the two tabs, Home/End
   * jump to the ends, and the move activates the tab (the automatic-activation
   * pattern, correct for a two-tab panel this short). Tab order itself stays
   * out of the tablist — the roving `tabIndex` below means one Tab press
   * enters the tablist and the next leaves it.
   */
  const handleTabListKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>): void => {
    const index = TAB_ORDER.indexOf(tab);
    let next: number;
    switch (event.key) {
      case "ArrowRight":
        next = (index + 1) % TAB_ORDER.length;
        break;
      case "ArrowLeft":
        next = (index - 1 + TAB_ORDER.length) % TAB_ORDER.length;
        break;
      case "Home":
        next = 0;
        break;
      case "End":
        next = TAB_ORDER.length - 1;
        break;
      default:
        return;
    }
    event.preventDefault();
    const target = TAB_ORDER[next];
    setTab(target);
    tabRefs.current[target]?.focus();
  };

  const startBody = (
    <>
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
    </>
  );

  const feedBody = (
    <NotificationFeed
      status={feed.status}
      notifications={feed.notifications}
      markPending={feed.markPending}
      preferencesFailed={feed.preferencesFailed}
      onOpen={(notification) => {
        void feed.openNotification(notification).then(() =>
          followArtifact(notification.artifactId)
        );
      }}
      onMarkAllRead={() => void feed.markAllRead()}
    />
  );

  if (!activeWorkspace) return <></>;

  const unread = feed.unreadCount;

  return (
    <>
      <div className={styles.dock} ref={dockRef}>
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
          ref={toggleRef}
        >
          <span aria-hidden="true">{"\u{1F4AC}"}</span>
        </button>
        {/*
          The unread signal, and since ADR-009 the only one on the page.
          Permanently mounted — a live region inserted at the moment the count
          becomes non-zero is announced inconsistently across screen readers, so
          the region exists first and its *content* changes. `hidden` rather
          than a conditional render is what makes it "disappear" visually while
          keeping the region registered. The visible number is `aria-hidden`;
          the sentence beside it is what a screen reader announces, so a count
          is never read out as a bare number.
        */}
        <span
          className={styles.badge}
          data-testid="interview-widget-badge"
          role="status"
          aria-live="polite"
          aria-atomic="true"
          hidden={unread === 0}
        >
          <span className={styles.badgeCount} aria-hidden="true">
            {unread}
          </span>
          <span className={styles.badgeLabel}>{t("notifications.unread", { count: unread })}</span>
        </span>
      </div>
      {open && (
        <div
          id="interview-widget-panel"
          data-testid="interview-widget-panel"
          className={styles.panel}
          role="group"
          aria-label={t("interview.widget.title", "Interview-Assistent")}
          ref={panelRef}
        >
          {/*
            A tablist only exists when there is something to switch between.
            A total opt-out withdraws the feed, and a single tab would leave a
            half-rounded `btn-tab` (global.css styles :first-child and
            :last-child separately), so the suppressed panel renders the
            interview actions as plain panel content. `feed.suppressed` is only
            ever true once the preferences have actually arrived, so this never
            flickers.
          */}
          {feed.suppressed ? (
            <div className={styles.tabPanel}>{startBody}</div>
          ) : (
            <>
              <div
                className={styles.tabList}
                role="tablist"
                aria-label={t("interview.widget.tabsLabel", "Interview-Assistent-Bereiche")}
                onKeyDown={handleTabListKeyDown}
              >
                <button
                  type="button"
                  role="tab"
                  className={`${styles.tab} btn-tab`}
                  id="interview-widget-tab-start"
                  aria-selected={tab === "start"}
                  aria-controls="interview-widget-tabpanel-start"
                  tabIndex={tab === "start" ? 0 : -1}
                  onClick={() => setTab("start")}
                  data-testid="interview-widget-tab-start"
                  ref={(node) => {
                    tabRefs.current.start = node;
                  }}
                >
                  {t("interview.widget.tabStart", "Interview starten")}
                </button>
                <button
                  type="button"
                  role="tab"
                  className={`${styles.tab} btn-tab`}
                  id="interview-widget-tab-notifications"
                  aria-selected={tab === "notifications"}
                  aria-controls="interview-widget-tabpanel-notifications"
                  tabIndex={tab === "notifications" ? 0 : -1}
                  onClick={() => setTab("notifications")}
                  data-testid="interview-widget-tab-notifications"
                  ref={(node) => {
                    tabRefs.current.notifications = node;
                  }}
                >
                  {t("notifications.label", "Benachrichtigungen")}
                </button>
              </div>
              <div
                role="tabpanel"
                id="interview-widget-tabpanel-start"
                aria-labelledby="interview-widget-tab-start"
                className={styles.tabPanel}
                hidden={tab !== "start"}
                data-testid="interview-widget-tabpanel-start"
              >
                {startBody}
              </div>
              <div
                role="tabpanel"
                id="interview-widget-tabpanel-notifications"
                aria-labelledby="interview-widget-tab-notifications"
                className={styles.tabPanel}
                hidden={tab !== "notifications"}
                data-testid="interview-widget-tabpanel-notifications"
              >
                {feedBody}
              </div>
            </>
          )}
        </div>
      )}
    </>
  );
}
