/**
 * The notification feed inside the assistant panel (ADR-009) — regression
 * suite carried over from the deleted `NotificationBell.test.tsx`.
 *
 * Every case in the old suite is reproduced here, at the surface that
 * replaced it, and renders the real `InterviewWidget` rather than the feed in
 * isolation: the point of the carry-over is that the *integration* kept the
 * behaviour, not just the markup.
 *
 *   old case                          → here
 *   fetches the feed once on mount    → "fetches the feed once on mount"
 *   shows the unread count badge       → "shows the unread count on the widget badge"
 *   hides the badge when nothing is    → "hides the badge when nothing is unread"
 *     unread                            (adapted: the live region stays mounted, so
 *                                        the assertion is visibility, not absence —
 *                                        see the case for why)
 *   opens and closes the dropdown      → "opens and closes the panel" + "dismisses the
 *                                        panel on Escape" + "dismisses the panel on a
 *                                        click outside" (#985's half of the contract)
 *   shows an empty state               → "shows the empty state"
 *   marks read and navigates          → "marks read and navigates to the artifact"
 *   no navigate without an artifact    → "does not navigate without an artifact"
 *   marks everything read              → "marks everything read and refetches"
 *   stays silent when the feed fails   → "surfaces a load failure in the feed tab and
 *                                        keeps the widget working"
 *
 * The `role="menu"` / `role="menuitem"` contract the old dropdown carried is
 * pinned explicitly at the end, because it is the one piece of semantics that
 * was deliberately not redesigned.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { MemoryRouter } from "react-router-dom";

import enLocale from "../../i18n/locales/en.json";

const navigate = vi.fn();

vi.mock("react-router-dom", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-router-dom")>()),
  useNavigate: () => navigate,
}));

vi.mock("../../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "ws-1", name: "WS" } }),
}));

/** i18next-shaped `t`: resolves against en.json, pluralises on `count`, and
 *  interpolates `{{count}}` — see src/test/i18n-test-helpers.ts. */
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
            String((options as Record<string, unknown>)[name] ?? "")
          );
    },
  }),
}));

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
import { InterviewWidget } from "./InterviewWidget";

const unread = {
  id: "n1",
  kind: "assigned" as const,
  artifactId: "a1",
  message: "REQ-1 assigned to you",
  read: false,
  createdAt: "2026-09-04T10:00:00Z",
};

const ALL_ON = {
  assigned: true,
  comment_added: true,
  transition_pending: true,
  suspect_flagged: true,
};

/** Open the panel and switch to the notifications tab. */
async function openFeed(user: ReturnType<typeof userEvent.setup>): Promise<void> {
  await user.click(screen.getByTestId("interview-widget-toggle"));
  await user.click(await screen.findByTestId("interview-widget-tab-notifications"));
}

function renderWidget(): ReturnType<typeof render> {
  return render(
    <MemoryRouter>
      <InterviewWidget />
    </MemoryRouter>
  );
}

describe("notification feed in the assistant panel (ADR-009, carried over from NotificationBell)", () => {
  beforeEach(() => {
    navigate.mockReset();
    localStorage.clear();
    vi.mocked(notificationsApi.list)
      .mockReset()
      .mockResolvedValue({ notifications: [unread], unreadCount: 1 });
    vi.mocked(notificationsApi.markRead).mockReset().mockResolvedValue({ ...unread, read: true });
    vi.mocked(notificationsApi.markAllRead).mockReset().mockResolvedValue(1);
    vi.mocked(notificationPreferencesApi.get).mockReset().mockResolvedValue({ ...ALL_ON });
  });

  it("fetches the feed once on mount", async () => {
    renderWidget();
    await waitFor(() => expect(notificationsApi.list).toHaveBeenCalledTimes(1));
  });

  it("shows the unread count on the widget badge", async () => {
    renderWidget();
    const badge = await screen.findByTestId("interview-widget-badge");
    expect(badge).toBeVisible();
    expect(badge).toHaveTextContent("1");
  });

  it("hides the badge when nothing is unread", async () => {
    vi.mocked(notificationsApi.list).mockResolvedValue({ notifications: [], unreadCount: 0 });
    renderWidget();
    await waitFor(() => expect(notificationsApi.list).toHaveBeenCalled());

    // Not `queryByTestId(...)` as in the old suite: the region is permanently
    // mounted so the aria-live announcement is reliable (a region inserted at
    // the same moment its content changes is announced inconsistently across
    // screen readers). "Gone" therefore means not visible and empty.
    const badge = screen.getByTestId("interview-widget-badge");
    expect(badge).not.toBeVisible();
    expect(badge).not.toHaveTextContent("1");
  });

  it("opens and closes the panel", async () => {
    const user = userEvent.setup();
    renderWidget();
    await screen.findByTestId("interview-widget-badge");

    await user.click(screen.getByTestId("interview-widget-toggle"));
    expect(screen.getByTestId("interview-widget-panel")).toBeInTheDocument();

    await user.click(screen.getByTestId("interview-widget-toggle"));
    expect(screen.queryByTestId("interview-widget-panel")).not.toBeInTheDocument();
  });

  // Issue #985, carried over: the popover the feed used to live in was
  // dismissable by keyboard and by a click outside. Removing the sidebar row
  // must not quietly drop either half.
  it("dismisses the panel on Escape and returns focus to the toggle", async () => {
    const user = userEvent.setup();
    renderWidget();
    await screen.findByTestId("interview-widget-badge");

    await user.click(screen.getByTestId("interview-widget-toggle"));
    expect(screen.getByTestId("interview-widget-panel")).toBeInTheDocument();

    await user.keyboard("{Escape}");

    expect(screen.queryByTestId("interview-widget-panel")).not.toBeInTheDocument();
    expect(screen.getByTestId("interview-widget-toggle")).toHaveFocus();
  });

  it("dismisses the panel on a click outside it", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <div data-testid="outside">
          <InterviewWidget />
        </div>
      </MemoryRouter>
    );
    await screen.findByTestId("interview-widget-badge");

    await user.click(screen.getByTestId("interview-widget-toggle"));
    expect(screen.getByTestId("interview-widget-panel")).toBeInTheDocument();

    await user.click(screen.getByTestId("outside"));

    expect(screen.queryByTestId("interview-widget-panel")).not.toBeInTheDocument();
  });

  it("shows the empty state", async () => {
    vi.mocked(notificationsApi.list).mockResolvedValue({ notifications: [], unreadCount: 0 });
    const user = userEvent.setup();
    renderWidget();
    await waitFor(() => expect(notificationsApi.list).toHaveBeenCalled());

    await openFeed(user);
    expect(screen.getByTestId("interview-widget-notifications-empty")).toHaveTextContent("Nothing new.");
  });

  it("marks read and navigates to the artifact on click", async () => {
    const user = userEvent.setup();
    renderWidget();
    await screen.findByTestId("interview-widget-badge");

    await openFeed(user);
    await user.click(screen.getByTestId("interview-widget-notification-item-n1"));

    await waitFor(() => expect(notificationsApi.markRead).toHaveBeenCalledWith("n1"));
    expect(navigate).toHaveBeenCalledWith("/artifacts/a1");
  });

  it("does not navigate without an artifact", async () => {
    vi.mocked(notificationsApi.list).mockResolvedValue({
      notifications: [{ ...unread, artifactId: null }],
      unreadCount: 1,
    });
    const user = userEvent.setup();
    renderWidget();
    await screen.findByTestId("interview-widget-badge");

    await openFeed(user);
    await user.click(screen.getByTestId("interview-widget-notification-item-n1"));

    await waitFor(() => expect(notificationsApi.markRead).toHaveBeenCalled());
    expect(navigate).not.toHaveBeenCalled();
  });

  it("marks everything read and refetches", async () => {
    const user = userEvent.setup();
    renderWidget();
    await screen.findByTestId("interview-widget-badge");

    await openFeed(user);
    await user.click(screen.getByTestId("interview-widget-notifications-mark-all"));

    await waitFor(() => expect(notificationsApi.markAllRead).toHaveBeenCalled());
    await waitFor(() => expect(notificationsApi.list).toHaveBeenCalledTimes(2));
  });

  it("surfaces a load failure in the feed tab and keeps the widget working", async () => {
    vi.mocked(notificationsApi.list).mockRejectedValue(new Error("boom"));
    const user = userEvent.setup();
    renderWidget();
    await waitFor(() => expect(notificationsApi.list).toHaveBeenCalled());

    // The widget itself is untouched — a notification centre must never block
    // the navigation chrome it lives in.
    expect(screen.getByTestId("interview-widget-toggle")).toBeInTheDocument();
    expect(screen.queryByTestId("interview-widget-badge")).not.toBeVisible();

    await openFeed(user);
    expect(screen.getByTestId("interview-widget-notifications-error")).toBeInTheDocument();
  });

  it("keeps the role=menu / role=menuitem contract the old dropdown had", async () => {
    const user = userEvent.setup();
    renderWidget();
    await screen.findByTestId("interview-widget-badge");

    await openFeed(user);

    const menu = screen.getByTestId("interview-widget-notifications-menu");
    expect(menu).toHaveAttribute("role", "menu");
    const item = within(menu).getByTestId("interview-widget-notification-item-n1");
    expect(item).toHaveAttribute("role", "menuitem");
    expect(item).toHaveTextContent(unread.message);
  });
});
