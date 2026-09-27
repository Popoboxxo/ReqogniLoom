/**
 * useNotificationFeed — the single source of truth for "are there unread
 * notifications?" (ADR-009).
 *
 * The unread signal used to live inside `NotificationBell`, mounted in the
 * sidebar footer. ADR-009 moves the entry point into `InterviewWidget`, so the
 * state had to leave the component with it: the badge on the floating widget
 * and the feed inside its panel must read the *same* fetch, not two
 * independent ones. Two callers of `notificationsApi.list()` would be two
 * sources of truth — exactly the split state the ADR rejects.
 *
 * Two requests, one state
 * -----------------------
 * The feed (`GET /notifications/`) and the account-scoped opt-out
 * (`GET /users/me/notification-preferences/`) are fetched together and applied
 * together, via `Promise.allSettled`. Applying them in one step is what
 * prevents a badge that flashes up and then disappears: there is no
 * intermediate render in which a stale unread count is visible before the
 * preference that suppresses it is known.
 *
 * localStorage vs. the server-side preference (ADR-009 verification note)
 * -----------------------------------------------------------------------
 * They cannot disagree, and the reason is structural rather than defensive:
 * this hook keeps **no** persisted state at all. The only `localStorage` key
 * in this feature area is the widget's panel-open flag
 * (`reqflow-interview-widget-open`), which decides whether a panel is drawn —
 * it never contributes to the unread signal, so an opted-out user cannot end
 * up seeing a badge restored from a cached value. Preferences are re-read
 * from the server on every mount, which is also why the preference and the
 * feed cannot come from two different points in time on the same mount.
 *
 * Fail-open on a broken preferences endpoint
 * ------------------------------------------
 * If `notification-preferences` fails, the hook reports `preferencesFailed`
 * and treats the user as *not* suppressed. Hiding notifications on a
 * transient endpoint failure would be a silent downgrade — a working feed
 * disappearing with no explanation. Instead the feed stays available and
 * discloses the unread items it cannot rule out
 * (`notifications.preferencesUnavailable`).
 *
 * Live-verified staleness, and the signal that closes it
 * ------------------------------------------------------
 * The browser check (2026-09-27) found the case this hook has to answer for:
 * the user switches all four triggers off on `/profile` — a route the widget
 * is mounted alongside, not inside — and the badge keeps sitting on the
 * widget until the next remount. A remount alone would be an acceptable
 * staleness window for most features; for the unread signal it is not, because
 * the switch the user just flipped is the very thing the badge contradicts,
 * and the profile page is where they are looking when they flip it.
 *
 * So `NotificationsSection` announces a successful PATCH on the window and
 * this hook refetches. A DOM event rather than a shared context because the
 * two components live in disjoint subtrees (the profile route is a lazily
 * loaded child of the shell, the widget is a sibling of the shell's content)
 * and a context would mean lifting state above the shell just to publish a
 * boolean. Crucially the hook stays the *only* owner of the unread state: the
 * event carries no count and no feed, it only says "re-read the server", so
 * there is still exactly one source of truth.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import {
  NOTIFICATION_PREFERENCE_KINDS,
  notificationPreferencesApi,
  type NotificationPreferences,
} from "../api/notification-preferences";
import { notificationsApi, type Notification } from "../api/notifications";

/**
 * Window event name a component dispatches after successfully writing the
 * notification preferences, so every mounted consumer of the feed refetches.
 * Carries no data by design — see the header note above.
 */
export const NOTIFICATION_PREFERENCES_CHANGED_EVENT =
  "reqogniloom:notification-preferences-changed";

/** Lifecycle of the feed request itself — the four states every data-bound
 *  surface in this codebase has to distinguish. */
export type NotificationFeedStatus = "loading" | "error" | "success";

export interface NotificationFeedState {
  status: NotificationFeedStatus;
  notifications: Notification[];
  /** Never larger than `notifications.length`; a mark-all clears it. */
  unreadCount: number;
  /**
   * Every trigger is switched off server-side. No enabled trigger can
   * produce a notification, so the badge and the feed tab are withdrawn
   * entirely rather than kept around to show a permanently empty list.
   */
  suppressed: boolean;
  /** A mark-all is in flight — the action is disabled meanwhile. */
  markPending: boolean;
  /** The opt-out could not be read; see the fail-open note in the header. */
  preferencesFailed: boolean;
  /** Refetch feed + preferences (called after every read-state change). */
  reload: () => Promise<void>;
  /** Mark one notification read, then refetch. Never rejects. */
  openNotification: (notification: Notification) => Promise<void>;
  /** Mark the whole feed read, then refetch. Never rejects. */
  markAllRead: () => Promise<void>;
}

/**
 * True when not a single trigger is enabled, i.e. the opt-out is total.
 * Partially opted out is NOT suppressed: an enabled trigger can still
 * produce a notification, so the feed has to stay reachable.
 */
function isFullyOptedOut(preferences: NotificationPreferences): boolean {
  return NOTIFICATION_PREFERENCE_KINDS.every((kind) => preferences[kind] === false);
}

/**
 * The endpoint contract is a complete four-boolean map (a missing row is
 * reported by the server as all-`true`). Anything else is treated as
 * "preferences unknown" rather than guessed at: a partial map would make
 * `isFullyOptedOut` answer `true` for a key that was simply absent, and
 * silently withdraw the notifications of a user who never opted out.
 */
function isPreferenceMap(value: unknown): value is NotificationPreferences {
  if (typeof value !== "object" || value === null) return false;
  const record = value as Record<string, unknown>;
  return NOTIFICATION_PREFERENCE_KINDS.every((kind) => typeof record[kind] === "boolean");
}

const INITIAL: Pick<
  NotificationFeedState,
  "status" | "notifications" | "unreadCount" | "suppressed" | "markPending" | "preferencesFailed"
> = {
  status: "loading",
  notifications: [],
  unreadCount: 0,
  suppressed: false,
  markPending: false,
  preferencesFailed: false,
};

export function useNotificationFeed(): NotificationFeedState {
  const [state, setState] = useState(INITIAL);
  /**
   * Monotonic request generation. A response belonging to an older
   * generation is dropped, so a slow first mount can never overwrite the
   * result of a mark-all that ran after it.
   */
  const generation = useRef(0);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const reload = useCallback(async (): Promise<void> => {
    generation.current += 1;
    const mine = generation.current;

    const [feedResult, preferencesResult] = await Promise.allSettled([
      notificationsApi.list(),
      notificationPreferencesApi.get(),
    ]);

    if (!mounted.current || mine !== generation.current) return;

    const feed = feedResult.status === "fulfilled" ? feedResult.value : null;
    const preferences =
      preferencesResult.status === "fulfilled" && isPreferenceMap(preferencesResult.value)
        ? preferencesResult.value
        : null;
    // A total opt-out withdraws the signal itself, not just the feed tab: a
    // badge the user cannot act on is noise, and the ADR's whole point is
    // that no enabled trigger can produce a notification any more.
    const suppressed = preferences !== null && isFullyOptedOut(preferences);

    setState((previous) => ({
      ...previous,
      // A failed feed is a state the surface has to render, not a value to
      // paper over: the feed tab says so instead of pretending to be empty.
      status: feed === null ? "error" : "success",
      notifications: feed?.notifications ?? [],
      unreadCount: suppressed ? 0 : (feed?.unreadCount ?? 0),
      suppressed,
      preferencesFailed: preferences === null,
    }));
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  // A preference written anywhere in the app (today: the profile page's
  // `NotificationsSection`) invalidates what this hook holds, because the
  // suppression decision is derived from the server map. Refetch instead of
  // patching locally: the server's answer wins, exactly as it does on mount.
  useEffect(() => {
    const handleChanged = (): void => {
      void reload();
    };
    window.addEventListener(NOTIFICATION_PREFERENCES_CHANGED_EVENT, handleChanged);
    return () => {
      window.removeEventListener(NOTIFICATION_PREFERENCES_CHANGED_EVENT, handleChanged);
    };
  }, [reload]);

  const openNotification = useCallback(
    async (notification: Notification): Promise<void> => {
      try {
        await notificationsApi.markRead(notification.id);
      } catch {
        // The read flag is bookkeeping; the caller navigates either way.
      }
      await reload();
    },
    [reload]
  );

  const markAllRead = useCallback(async (): Promise<void> => {
    if (!mounted.current) return;
    setState((previous) => ({ ...previous, markPending: true }));
    try {
      await notificationsApi.markAllRead();
    } catch {
      // Ignore — the refetch below reflects whatever actually happened.
    }
    // `reload` invalidates any request still in flight, so a feed fetched
    // before the mark-all can never land on top of it.
    await reload();
    if (mounted.current) {
      setState((previous) => ({ ...previous, markPending: false }));
    }
  }, [reload]);

  return { ...state, reload, openNotification, markAllRead };
}
