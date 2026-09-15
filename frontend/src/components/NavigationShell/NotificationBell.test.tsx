import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";

const navigate = vi.fn();

vi.mock("react-router-dom", () => ({ useNavigate: () => navigate }));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, fallbackOrOpts?: unknown) =>
      typeof fallbackOrOpts === "string" ? fallbackOrOpts : key,
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

import { notificationsApi } from "../../api/notifications";
import { NotificationBell } from "./NotificationBell";

const unread = {
  id: "n1",
  kind: "assigned" as const,
  artifactId: "a1",
  message: "REQ-1 assigned to you",
  read: false,
  createdAt: "2026-09-04T10:00:00Z",
};

describe("NotificationBell", () => {
  beforeEach(() => {
    navigate.mockReset();
    vi.mocked(notificationsApi.list)
      .mockReset()
      .mockResolvedValue({ notifications: [unread], unreadCount: 1 });
    vi.mocked(notificationsApi.markRead).mockReset().mockResolvedValue({ ...unread, read: true });
    vi.mocked(notificationsApi.markAllRead).mockReset().mockResolvedValue(1);
  });

  it("fetches the feed once on mount", async () => {
    render(<NotificationBell />);
    await waitFor(() => expect(notificationsApi.list).toHaveBeenCalledTimes(1));
  });

  it("shows the unread count badge", async () => {
    render(<NotificationBell />);
    expect(await screen.findByTestId("notification-bell-badge")).toHaveTextContent("1");
  });

  it("hides the badge when nothing is unread", async () => {
    vi.mocked(notificationsApi.list).mockResolvedValue({ notifications: [], unreadCount: 0 });

    render(<NotificationBell />);
    await waitFor(() => expect(notificationsApi.list).toHaveBeenCalled());

    expect(screen.queryByTestId("notification-bell-badge")).not.toBeInTheDocument();
  });

  it("opens and closes the dropdown", async () => {
    const user = userEvent.setup();
    render(<NotificationBell />);
    await screen.findByTestId("notification-bell-badge");

    await user.click(screen.getByTestId("notification-bell-toggle"));
    expect(screen.getByTestId("notification-bell-dropdown")).toBeInTheDocument();

    await user.click(screen.getByTestId("notification-bell-toggle"));
    expect(screen.queryByTestId("notification-bell-dropdown")).not.toBeInTheDocument();
  });

  it("shows an empty state with no notifications", async () => {
    vi.mocked(notificationsApi.list).mockResolvedValue({ notifications: [], unreadCount: 0 });
    const user = userEvent.setup();
    render(<NotificationBell />);
    await waitFor(() => expect(notificationsApi.list).toHaveBeenCalled());

    await user.click(screen.getByTestId("notification-bell-toggle"));
    expect(screen.getByTestId("notification-bell-empty")).toBeInTheDocument();
  });

  it("marks read and navigates to the artifact on click", async () => {
    const user = userEvent.setup();
    render(<NotificationBell />);
    await screen.findByTestId("notification-bell-badge");

    await user.click(screen.getByTestId("notification-bell-toggle"));
    await user.click(screen.getByTestId("notification-bell-item-n1"));

    await waitFor(() => expect(notificationsApi.markRead).toHaveBeenCalledWith("n1"));
    expect(navigate).toHaveBeenCalledWith("/artifacts/a1");
  });

  it("does not navigate for a notification without an artifact", async () => {
    vi.mocked(notificationsApi.list).mockResolvedValue({
      notifications: [{ ...unread, artifactId: null }],
      unreadCount: 1,
    });
    const user = userEvent.setup();
    render(<NotificationBell />);
    await screen.findByTestId("notification-bell-badge");

    await user.click(screen.getByTestId("notification-bell-toggle"));
    await user.click(screen.getByTestId("notification-bell-item-n1"));

    await waitFor(() => expect(notificationsApi.markRead).toHaveBeenCalled());
    expect(navigate).not.toHaveBeenCalled();
  });

  it("marks everything read and refetches", async () => {
    const user = userEvent.setup();
    render(<NotificationBell />);
    await screen.findByTestId("notification-bell-badge");

    await user.click(screen.getByTestId("notification-bell-toggle"));
    await user.click(screen.getByTestId("notification-bell-mark-all"));

    await waitFor(() => expect(notificationsApi.markAllRead).toHaveBeenCalled());
    await waitFor(() => expect(notificationsApi.list).toHaveBeenCalledTimes(2));
  });

  it("stays silent when the feed cannot be loaded", async () => {
    vi.mocked(notificationsApi.list).mockRejectedValue(new Error("boom"));

    render(<NotificationBell />);
    await waitFor(() => expect(notificationsApi.list).toHaveBeenCalled());

    expect(screen.queryByTestId("notification-bell-badge")).not.toBeInTheDocument();
    expect(screen.getByTestId("notification-bell-toggle")).toBeInTheDocument();
  });
});
