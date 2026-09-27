/**
 * Interview-management web widget — quick entry point (plan Task 5 / 16).
 *
 * Since Task 16 the widget navigates instead of hosting a session, so every
 * render needs a router around it (`useNavigate`).
 */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { act, render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import userEvent from "@testing-library/user-event";
import { InterviewWidget } from "./InterviewWidget";
import enLocale from "../../i18n/locales/en.json";

vi.mock("../../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "ws-1", name: "WS" } }),
}));

// Plan Task 13 pins English copy ("Architecture Element"), so resolve keys
// against en.json instead of the de.json-based shared helper
// (src/test/i18n-test-helpers.ts) used by specs that assert German copy.
//
// ADR-009 widened the job: the widget now renders the notification feed, whose
// announced count is a `count`-bearing call that i18next pluralises
// (`notifications.unread_one` / `_other`). A stub that ignores the options
// object would hand every count the same string, so the plural and the
// `{{count}}` interpolation are reproduced here.
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) => {
      const lookup = (candidate: string): unknown =>
        candidate
          .split(".")
          .reduce<unknown>(
            (node, segment) =>
              node && typeof node === "object"
                ? (node as Record<string, unknown>)[segment]
                : undefined,
            enLocale
          );
      const count = typeof options?.count === "number" ? options.count : null;
      const raw =
        count === null
          ? lookup(key)
          : (lookup(`${key}_${count === 1 ? "one" : "other"}`) ?? lookup(key));
      if (typeof raw !== "string") return key;
      return count === null
        ? raw
        : raw.replace(/\{\{(\w+)\}\}/g, (_m, name: string) =>
            String(options[name] ?? "")
          );
    },
  }),
}));

// Factory vi.mock, same convention as InterviewChatPane.test.tsx (plan Task 8).
// Since Task 16 the widget must not call any of these at all -- they are
// mocked so "was never called" is an assertion, not an accident.
vi.mock("../../api/interviews", () => ({
  interviewsApi: {
    start: vi.fn(),
    getState: vi.fn(),
    propose: vi.fn(),
    formalize: vi.fn(),
  },
}));
import { interviewsApi } from "../../api/interviews";

// ADR-009: the widget is now also the home of the notification feed, so it
// fetches on mount. Both API modules are mocked so "the interview start path
// is unaffected" stays an assertion rather than an accident — and so the
// pre-existing cases below do not depend on a network stack they never had.
vi.mock("../../api/notifications", () => ({
  NOTIFICATION_FEED_LIMIT: 20,
  notificationsApi: {
    list: vi.fn(),
    markRead: vi.fn(),
    markAllRead: vi.fn(),
  },
}));

vi.mock("../../api/notification-preferences", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/notification-preferences")>()),
  notificationPreferencesApi: { get: vi.fn(), update: vi.fn() },
}));

import { notificationsApi } from "../../api/notifications";
import { notificationPreferencesApi } from "../../api/notification-preferences";

/** The widget uses `useNavigate`, so it only mounts inside a router. */
function renderWidget(): ReturnType<typeof render> {
  return render(
    <MemoryRouter>
      <InterviewWidget />
    </MemoryRouter>
  );
}

describe("InterviewWidget", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("renders collapsed by default", () => {
    renderWidget();
    expect(screen.getByTestId("interview-widget-toggle")).toBeInTheDocument();
    expect(screen.queryByTestId("interview-widget-panel")).not.toBeInTheDocument();
  });

  it("expands on toggle click and persists the open state", () => {
    renderWidget();
    fireEvent.click(screen.getByTestId("interview-widget-toggle"));

    expect(screen.getByTestId("interview-widget-panel")).toBeInTheDocument();
    expect(localStorage.getItem("reqflow-interview-widget-open")).toBe("true");
  });

  it("renders expanded on mount when localStorage says open", () => {
    localStorage.setItem("reqflow-interview-widget-open", "true");
    renderWidget();
    expect(screen.getByTestId("interview-widget-panel")).toBeInTheDocument();
  });

  it("collapses on a second toggle click", () => {
    renderWidget();
    const toggle = screen.getByTestId("interview-widget-toggle");
    fireEvent.click(toggle);
    fireEvent.click(toggle);
    expect(screen.queryByTestId("interview-widget-panel")).not.toBeInTheDocument();
  });

  // Issue #955: the FAB renders nothing but the 💬 glyph, so its accessible
  // name has to come from an explicit label — the emoji alone is announced as
  // a generic speech balloon.
  it("gives the icon-only toggle a translated accessible name", () => {
    renderWidget();
    const toggle = screen.getByTestId("interview-widget-toggle");
    expect(toggle).toHaveAccessibleName(
      /open interview assistant|interview-assistent öffnen/i
    );
    expect(toggle.querySelector('[aria-hidden="true"]')).not.toBeNull();
  });

  // Issue #679: direct `window.localStorage` access threw an unhandled
  // TypeError/SecurityError in storage-restricted environments (private
  // browsing, third-party-cookie lockouts, some JSDOM setups) and froze the
  // widget. `safeLocalStorage` must absorb that instead of crashing.
  describe("when localStorage access throws (issue #679)", () => {
    let originalLocalStorage: Storage;

    beforeEach(() => {
      originalLocalStorage = window.localStorage;
      Object.defineProperty(window, "localStorage", {
        configurable: true,
        value: {
          getItem: vi.fn(() => {
            throw new Error("SecurityError: localStorage access is blocked");
          }),
          setItem: vi.fn(() => {
            throw new Error("SecurityError: localStorage access is blocked");
          }),
        },
      });
    });

    afterEach(() => {
      Object.defineProperty(window, "localStorage", {
        configurable: true,
        value: originalLocalStorage,
      });
    });

    it("mounts and renders the collapsed toggle without crashing", () => {
      expect(() => renderWidget()).not.toThrow();
      expect(screen.getByTestId("interview-widget-toggle")).toBeInTheDocument();
      expect(screen.queryByTestId("interview-widget-panel")).not.toBeInTheDocument();
    });

    it("still expands on toggle click even though persisting the state fails", () => {
      renderWidget();
      const toggle = screen.getByTestId("interview-widget-toggle");
      expect(() => fireEvent.click(toggle)).not.toThrow();
      expect(screen.getByTestId("interview-widget-panel")).toBeInTheDocument();
    });
  });
});

describe("InterviewWidget multi entry", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  it("renders a 9th button for multi-mode discovery", () => {
    localStorage.setItem("reqflow-interview-widget-open", "true");
    renderWidget();
    expect(screen.getByTestId("interview-widget-start-multi")).toBeInTheDocument();
  });

  it("existing type buttons show translated labels, not raw type strings", () => {
    localStorage.setItem("reqflow-interview-widget-open", "true");
    renderWidget();
    expect(screen.getByText("Requirement")).toBeInTheDocument(); // en.json value happens to match the raw string for this one type
    expect(screen.queryByText("ArchitectureElement")).not.toBeInTheDocument(); // raw string must NOT appear
    expect(screen.getByText("Architecture Element")).toBeInTheDocument(); // translated value
  });
});

// Task 16 (spec L2.5): the widget is a quick entry point, not a session host.
describe("InterviewWidget hand-off to /interviews", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  function renderRouted(): ReturnType<typeof render> {
    return render(
      <MemoryRouter initialEntries={["/requirements"]}>
        <Routes>
          <Route path="/requirements" element={<InterviewWidget />} />
          <Route path="/interviews" element={<div data-testid="interviews-route" />} />
        </Routes>
      </MemoryRouter>
    );
  }

  it("navigates to the interviews route instead of hosting a session", async () => {
    renderRouted();

    fireEvent.click(screen.getByTestId("interview-widget-toggle"));
    fireEvent.click(screen.getByTestId("interview-widget-start-Risk"));

    expect(await screen.findByTestId("interviews-route")).toBeInTheDocument();
    // The widget must not start the session itself -- /interviews owns that,
    // so there is exactly one start path and one chat surface.
    expect(interviewsApi.start).not.toHaveBeenCalled();
  });

  it("routes the discovery entry point to ?start=multi", async () => {
    renderRouted();

    fireEvent.click(screen.getByTestId("interview-widget-toggle"));
    fireEvent.click(screen.getByTestId("interview-widget-start-multi"));

    expect(await screen.findByTestId("interviews-route")).toBeInTheDocument();
    expect(interviewsApi.start).not.toHaveBeenCalled();
  });

  it("closes the panel after navigating away", async () => {
    render(
      <MemoryRouter initialEntries={["/requirements"]}>
        <Routes>
          <Route path="/requirements" element={<InterviewWidget />} />
          <Route path="/interviews" element={<InterviewWidget />} />
        </Routes>
      </MemoryRouter>
    );

    fireEvent.click(screen.getByTestId("interview-widget-toggle"));
    fireEvent.click(screen.getByTestId("interview-widget-start-Adr"));

    await waitFor(() => {
      expect(screen.queryByTestId("interview-widget-panel")).not.toBeInTheDocument();
    });
    expect(localStorage.getItem("reqflow-interview-widget-open")).toBe("false");
  });

  it("renders no chat pane at all", () => {
    renderWidget();

    fireEvent.click(screen.getByTestId("interview-widget-toggle"));

    expect(screen.queryByTestId("interview-chat-input")).not.toBeInTheDocument();
    expect(screen.queryByTestId("interview-artifact-formalize")).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// ADR-009 — system notifications move into the assistant entry point as a
// badge plus a feed tab. The badge is now the ONLY unread signal on the page,
// which is why the accessibility expectations on it are stricter than the
// sidebar bell's ever were.
// ---------------------------------------------------------------------------

const ALL_ON = {
  assigned: true,
  comment_added: true,
  transition_pending: true,
  suspect_flagged: true,
};

const ALL_OFF = {
  assigned: false,
  comment_added: false,
  transition_pending: false,
  suspect_flagged: false,
};

const twoUnread = [
  {
    id: "n1",
    kind: "assigned" as const,
    artifactId: "a1",
    message: "REQ-1 assigned to you",
    read: false,
    createdAt: "2026-09-04T10:00:00Z",
  },
  {
    id: "n2",
    kind: "comment_added" as const,
    artifactId: null,
    message: "Someone commented on REQ-2",
    read: false,
    createdAt: "2026-09-04T11:00:00Z",
  },
];

function seedFeed(
  notifications: typeof twoUnread | [] = twoUnread,
  unreadCount = notifications.length
): void {
  vi.mocked(notificationsApi.list).mockResolvedValue({ notifications, unreadCount });
}

describe("InterviewWidget unread badge (ADR-009)", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.mocked(notificationsApi.list).mockReset();
    vi.mocked(notificationsApi.markRead).mockReset().mockResolvedValue(twoUnread[0]);
    vi.mocked(notificationsApi.markAllRead).mockReset().mockResolvedValue(2);
    vi.mocked(notificationPreferencesApi.get).mockReset().mockResolvedValue({ ...ALL_ON });
    seedFeed();
  });

  it("mounts the badge even before there is anything to announce", async () => {
    renderWidget();
    // Permanently mounted, not conditionally rendered: a live region inserted
    // at the same moment its content changes is announced inconsistently
    // across screen readers, so the region has to exist first.
    expect(screen.getByTestId("interview-widget-badge")).toBeInTheDocument();
    // Flush the mount fetch so React's pending state update is not reported as
    // an unwrapped act() after the assertions above have already run.
    await act(async () => {
      await Promise.resolve();
    });
  });

  it("shows the unread count while notifications are unread", async () => {
    renderWidget();
    const badge = await screen.findByTestId("interview-widget-badge");
    await waitFor(() => expect(badge).toBeVisible());
    expect(badge).toHaveTextContent("2");
  });

  it("hides the badge when nothing is unread", async () => {
    seedFeed([], 0);
    renderWidget();
    await waitFor(() => expect(notificationsApi.list).toHaveBeenCalled());
    expect(screen.getByTestId("interview-widget-badge")).not.toBeVisible();
  });

  // The badge is the only access to the signal now that the sidebar row is
  // gone, so it must be announced, and announced as a sentence rather than as
  // a bare number.
  it("announces the count through an aria-live status region", async () => {
    renderWidget();
    const badge = await screen.findByTestId("interview-widget-badge");
    await waitFor(() => expect(badge).toBeVisible());

    expect(badge).toHaveAttribute("aria-live", "polite");
    expect(badge).toHaveAttribute("role", "status");
    expect(badge).toHaveAttribute("aria-atomic", "true");
    // The visible number is hidden from assistive tech, and a real sentence
    // sits beside it — "2" on its own says nothing.
    expect(badge.querySelector('[aria-hidden="true"]')).not.toBeNull();
    expect(badge).toHaveTextContent("2 unread notifications");
  });

  it("pluralises the announced count for exactly one", async () => {
    seedFeed([twoUnread[0]], 1);
    renderWidget();
    const badge = await screen.findByTestId("interview-widget-badge");
    await waitFor(() => expect(badge).toHaveTextContent("1 unread notification"));
    expect(badge).not.toHaveTextContent("1 unread notifications");
  });

  it("disappears after 'mark all as read'", async () => {
    const user = userEvent.setup();
    renderWidget();
    await waitFor(() => expect(screen.getByTestId("interview-widget-badge")).toBeVisible());

    // Server side of the mark-all: the feed is empty and the count is 0, so
    // the refetch the hook performs is what clears the badge.
    vi.mocked(notificationsApi.list).mockResolvedValue({ notifications: [], unreadCount: 0 });

    await user.click(screen.getByTestId("interview-widget-toggle"));
    await user.click(await screen.findByTestId("interview-widget-tab-notifications"));
    await user.click(screen.getByTestId("interview-widget-notifications-mark-all"));

    await waitFor(() => expect(notificationsApi.markAllRead).toHaveBeenCalled());
    await waitFor(() =>
      expect(screen.getByTestId("interview-widget-badge")).not.toBeVisible()
    );
  });
});

describe("InterviewWidget notification feed tab (ADR-009)", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.mocked(notificationsApi.list).mockReset();
    vi.mocked(notificationsApi.markRead).mockReset().mockResolvedValue(twoUnread[0]);
    vi.mocked(notificationsApi.markAllRead).mockReset().mockResolvedValue(2);
    vi.mocked(notificationPreferencesApi.get).mockReset().mockResolvedValue({ ...ALL_ON });
    seedFeed();
  });

  it("reaches the feed inside the existing panel, with no second toggle", async () => {
    const user = userEvent.setup();
    renderWidget();
    await waitFor(() => expect(notificationsApi.list).toHaveBeenCalled());

    // One trigger for the whole feature: the widget toggle that already
    // existed. A second floating control would be a second entry point, which
    // is the state ADR-009 rejects.
    expect(screen.getAllByTestId("interview-widget-toggle")).toHaveLength(1);

    await user.click(screen.getByTestId("interview-widget-toggle"));
    const feedTab = await screen.findByTestId("interview-widget-tab-notifications");
    expect(feedTab).toHaveAttribute("role", "tab");
    expect(screen.getAllByRole("tab")).toHaveLength(2);

    await user.click(feedTab);
    expect(screen.getByTestId("interview-widget-tabpanel-notifications")).toBeVisible();
    expect(screen.getByTestId("interview-widget-notifications-menu")).toBeInTheDocument();
  });

  it("keeps the interview start actions as the default tab", async () => {
    const user = userEvent.setup();
    renderWidget();
    await user.click(screen.getByTestId("interview-widget-toggle"));

    expect(screen.getByTestId("interview-widget-tab-start")).toHaveAttribute(
      "aria-selected",
      "true"
    );
    expect(screen.getByTestId("interview-widget-tabpanel-start")).toBeVisible();
    expect(screen.getByTestId("interview-widget-start-multi")).toBeVisible();
  });

  it("moves arrow keys between the tabs", async () => {
    const user = userEvent.setup();
    renderWidget();
    await user.click(screen.getByTestId("interview-widget-toggle"));

    const startTab = await screen.findByTestId("interview-widget-tab-start");
    startTab.focus();
    await user.keyboard("{ArrowRight}");
    expect(screen.getByTestId("interview-widget-tab-notifications")).toHaveFocus();
    expect(screen.getByTestId("interview-widget-tab-notifications")).toHaveAttribute(
      "aria-selected",
      "true"
    );

    await user.keyboard("{ArrowLeft}");
    expect(screen.getByTestId("interview-widget-tab-start")).toHaveFocus();
  });

  it("renders the empty state", async () => {
    seedFeed([], 0);
    const user = userEvent.setup();
    renderWidget();
    await waitFor(() => expect(notificationsApi.list).toHaveBeenCalled());

    await user.click(screen.getByTestId("interview-widget-toggle"));
    await user.click(await screen.findByTestId("interview-widget-tab-notifications"));
    expect(screen.getByTestId("interview-widget-notifications-empty")).toHaveTextContent(
      "Nothing new."
    );
  });

  it("renders the list state with one row per notification", async () => {
    const user = userEvent.setup();
    renderWidget();
    await waitFor(() => expect(notificationsApi.list).toHaveBeenCalled());

    await user.click(screen.getByTestId("interview-widget-toggle"));
    await user.click(await screen.findByTestId("interview-widget-tab-notifications"));

    expect(
      screen.getByTestId("interview-widget-notification-item-n1")
    ).toHaveTextContent("REQ-1 assigned to you");
    expect(
      screen.getByTestId("interview-widget-notification-item-n2")
    ).toHaveTextContent("Someone commented on REQ-2");
  });

  it("offers the per-item action and the mark-all action moved over with the feed", async () => {
    const user = userEvent.setup();
    renderWidget();
    await waitFor(() => expect(notificationsApi.list).toHaveBeenCalled());

    await user.click(screen.getByTestId("interview-widget-toggle"));
    await user.click(await screen.findByTestId("interview-widget-tab-notifications"));

    expect(screen.getByTestId("interview-widget-notifications-mark-all")).toBeInTheDocument();
    await user.click(screen.getByTestId("interview-widget-notification-item-n1"));
    await waitFor(() => expect(notificationsApi.markRead).toHaveBeenCalledWith("n1"));
  });

  it("shows a loading state before the feed arrives", async () => {
    const user = userEvent.setup();
    // Never resolves, so the loading state is observable rather than a race
    // against a microtask that has already flushed by the time the click ends.
    vi.mocked(notificationsApi.list).mockReturnValue(new Promise(() => {}) as never);
    renderWidget();
    await user.click(screen.getByTestId("interview-widget-toggle"));
    expect(screen.getByTestId("interview-widget-notifications-loading")).toBeInTheDocument();
  });
});

describe("InterviewWidget and the account-scoped opt-out (ADR-009)", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.mocked(notificationsApi.list).mockReset();
    vi.mocked(notificationsApi.markRead).mockReset().mockResolvedValue(twoUnread[0]);
    vi.mocked(notificationsApi.markAllRead).mockReset().mockResolvedValue(2);
    vi.mocked(notificationPreferencesApi.get).mockReset();
    seedFeed();
  });

  it("keeps the badge and the feed while at least one trigger is enabled", async () => {
    vi.mocked(notificationPreferencesApi.get).mockResolvedValue({
      ...ALL_ON,
      comment_added: false,
    });
    renderWidget();

    await waitFor(() =>
      expect(screen.getByTestId("interview-widget-badge")).toBeVisible()
    );
    const user = userEvent.setup();
    await user.click(screen.getByTestId("interview-widget-toggle"));
    expect(screen.getByTestId("interview-widget-tab-notifications")).toBeInTheDocument();
  });

  // The four switches in UserProfileSettings/NotificationsSection have no
  // effect on the surface at all unless the widget honours them.
  it("suppresses the badge and the feed when every trigger is switched off", async () => {
    vi.mocked(notificationPreferencesApi.get).mockResolvedValue({ ...ALL_OFF });
    renderWidget();

    await waitFor(() => expect(notificationsApi.list).toHaveBeenCalled());
    await waitFor(() =>
      expect(screen.queryByTestId("interview-widget-tab-notifications")).not.toBeInTheDocument()
    );
    expect(screen.getByTestId("interview-widget-badge")).not.toBeVisible();

    // The panel itself keeps working — the interview start actions are the
    // widget's own job and have nothing to do with notifications.
    const user = userEvent.setup();
    await user.click(screen.getByTestId("interview-widget-toggle"));
    expect(screen.getByTestId("interview-widget-start-multi")).toBeInTheDocument();
  });

  it("falls back to the interview tab if the opt-out arrives while the feed is open", async () => {
    const user = userEvent.setup();
    // Preferences still in flight when the panel is opened: the tab is there,
    // because "we do not know yet" is not "opted out".
    let resolvePrefs: (value: typeof ALL_OFF) => void = () => undefined;
    vi.mocked(notificationPreferencesApi.get).mockReturnValue(
      new Promise<typeof ALL_OFF>((resolve) => {
        resolvePrefs = resolve;
      })
    );
    renderWidget();
    await waitFor(() => expect(notificationsApi.list).toHaveBeenCalled());

    await user.click(screen.getByTestId("interview-widget-toggle"));
    await user.click(await screen.findByTestId("interview-widget-tab-notifications"));
    expect(screen.getByTestId("interview-widget-tabpanel-notifications")).toBeVisible();

    // The opt-out lands while the user is reading the feed.
    await act(async () => {
      resolvePrefs({ ...ALL_OFF });
    });

    expect(screen.queryByTestId("interview-widget-tab-notifications")).not.toBeInTheDocument();
    expect(screen.getByTestId("interview-widget-start-multi")).toBeVisible();
  });

  // "Never leave a silent downgrade": a broken preferences endpoint must not
  // quietly hide unread notifications, but it must not pretend it is sure
  // either.
  it("discloses an unread preferences endpoint instead of hiding the feed", async () => {
    vi.mocked(notificationPreferencesApi.get).mockRejectedValue(new Error("boom"));
    renderWidget();

    await waitFor(() =>
      expect(screen.getByTestId("interview-widget-badge")).toBeVisible()
    );
    const user = userEvent.setup();
    await user.click(screen.getByTestId("interview-widget-toggle"));
    await user.click(await screen.findByTestId("interview-widget-tab-notifications"));

    expect(
      screen.getByTestId("interview-widget-notifications-preferences-unavailable")
    ).toBeInTheDocument();
  });
});

