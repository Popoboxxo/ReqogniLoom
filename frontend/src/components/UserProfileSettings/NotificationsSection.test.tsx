/**
 * ARCH-L1-001 ReactFrontend — NotificationsSection tests (Task 29, OD-1).
 *
 * leaf_id: COMP-RF-006 (UserProfileSettings)
 *
 * Covers the seven cases the plan specifies for Task 29:
 *  (a) four checkboxes, all checked for an all-enabled response,
 *  (b) an all-disabled response renders four unchecked boxes,
 *  (c) clicking a checkbox calls update() once with only that kind,
 *  (d) the server's returned map wins over the local guess,
 *  (e) a rejected update shows a role="alert" and keeps the previous state,
 *  (f) a rejected get shows the same alert and no checkboxes,
 *  (g) the section renders inside UserProfileSettings after MemorySection.
 *
 * Mirrors MemorySection.test.tsx: the API wrapper module is mocked rather than
 * the HTTP client, and react-i18next is stubbed to its fallback strings.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { NotificationsSection } from "./NotificationsSection";
import { UserProfileSettings } from "./index";
import {
  NOTIFICATION_PREFERENCE_KINDS,
  notificationPreferencesApi,
} from "../../api/notification-preferences";
import { apiKeysApi } from "../../api/api-keys";
import { memoryApi } from "../../api/memory";

vi.mock("../../api/notification-preferences", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("../../api/notification-preferences")>();
  return {
    ...actual,
    notificationPreferencesApi: { get: vi.fn(), update: vi.fn() },
  };
});

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string, fallback?: string) => fallback ?? key }),
}));

// --- (g) providers/APIs UserProfileSettings transitively needs ---------------
// Deliberately mocked at the module boundary instead of mounting the real app
// shell (no router/WorkspaceProvider/AuthProvider): activeWorkspace is null so
// the workspace-scoped visibility block does not render and the user-global
// section order is observable. The three child sections' APIs are stubbed so
// they mount quietly and cannot fail this test for unrelated reasons.
vi.mock("../../context/WorkspaceContext", () => ({
  useWorkspace: () => ({
    activeWorkspace: null,
    isFeatureVisible: () => false,
    setFeatureVisible: vi.fn(),
    resetFeatureOverride: vi.fn(),
    isFeatureOverridden: () => false,
  }),
}));

vi.mock("../../context/AuthContext", () => ({
  useAuth: () => ({ user: null, updateProfile: vi.fn() }),
}));

vi.mock("../../api/api-keys", () => ({
  apiKeysApi: { list: vi.fn(), create: vi.fn(), revoke: vi.fn() },
}));

vi.mock("../../api/memory", () => ({
  memoryApi: {
    getSelfOverview: vi.fn(),
    deleteSelfMemory: vi.fn(),
    forgetEntry: vi.fn(),
  },
}));

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

describe("NotificationsSection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(notificationPreferencesApi.get).mockResolvedValue({ ...ALL_ON });
    vi.mocked(notificationPreferencesApi.update).mockImplementation(async (changes) => ({
      ...ALL_ON,
      ...changes,
    }));
    vi.mocked(apiKeysApi.list).mockResolvedValue([]);
    vi.mocked(memoryApi.getSelfOverview).mockResolvedValue({
      entry_count: 0,
      last_updated_at: null,
      entries: [],
      total: 0,
      page: 1,
      page_size: 100,
      backend: "pgvector",
      degraded: false,
    });
  });

  it("(a) renders four checkboxes, all checked for an all-enabled response", async () => {
    render(<NotificationsSection />);

    await waitFor(() => {
      expect(screen.getAllByRole("checkbox")).toHaveLength(4);
    });

    for (const kind of NOTIFICATION_PREFERENCE_KINDS) {
      expect(screen.getByTestId(`notification-pref-checkbox-${kind}`)).toBeChecked();
      expect(screen.getByTestId(`notification-pref-row-${kind}`)).toBeInTheDocument();
    }
  });

  it("(b) renders four unchecked boxes for an all-disabled response", async () => {
    vi.mocked(notificationPreferencesApi.get).mockResolvedValue({ ...ALL_OFF });

    render(<NotificationsSection />);

    await waitFor(() => {
      expect(screen.getAllByRole("checkbox")).toHaveLength(4);
    });

    for (const kind of NOTIFICATION_PREFERENCE_KINDS) {
      expect(screen.getByTestId(`notification-pref-checkbox-${kind}`)).not.toBeChecked();
    }
  });

  it("(c) clicking comment_added calls update({comment_added:false}) exactly once", async () => {
    const user = userEvent.setup();
    vi.mocked(notificationPreferencesApi.update).mockResolvedValue({
      ...ALL_ON,
      comment_added: false,
    });

    render(<NotificationsSection />);

    await user.click(await screen.findByTestId("notification-pref-checkbox-comment_added"));

    await waitFor(() => {
      expect(notificationPreferencesApi.update).toHaveBeenCalledTimes(1);
    });
    expect(notificationPreferencesApi.update).toHaveBeenCalledWith({ comment_added: false });
  });

  it("(d) the server's returned map wins over the local guess", async () => {
    const user = userEvent.setup();
    // Start all-off, so the click implies "on" — but the server answers with the
    // unchanged all-off map. A component that trusted its own guess would render
    // a checked box here.
    vi.mocked(notificationPreferencesApi.get).mockResolvedValue({ ...ALL_OFF });
    vi.mocked(notificationPreferencesApi.update).mockResolvedValue({ ...ALL_OFF });

    render(<NotificationsSection />);

    const box = await screen.findByTestId("notification-pref-checkbox-comment_added");
    expect(box).not.toBeChecked();

    await user.click(box);

    await waitFor(() => {
      expect(notificationPreferencesApi.update).toHaveBeenCalledWith({ comment_added: true });
    });
    expect(screen.getByTestId("notification-pref-checkbox-comment_added")).not.toBeChecked();
  });

  it("(e) a rejected update renders an alert and leaves the checkbox unchanged", async () => {
    const user = userEvent.setup();
    vi.mocked(notificationPreferencesApi.update).mockRejectedValue({
      error: { message: "nope" },
    });

    render(<NotificationsSection />);

    const box = await screen.findByTestId("notification-pref-checkbox-comment_added");
    expect(box).toBeChecked();

    await user.click(box);

    expect(await screen.findByTestId("notification-preferences-error")).toHaveTextContent("nope");
    expect(screen.getByTestId("notification-pref-checkbox-comment_added")).toBeChecked();
  });

  it("(f) a rejected get renders the same alert and no checkboxes", async () => {
    vi.mocked(notificationPreferencesApi.get).mockRejectedValue({
      error: { message: "boom" },
    });

    render(<NotificationsSection />);

    expect(await screen.findByTestId("notification-preferences-error")).toHaveTextContent("boom");
    expect(screen.queryByTestId("notification-preferences-loading")).not.toBeInTheDocument();
    expect(screen.queryAllByRole("checkbox")).toHaveLength(0);
  });

  it("(g) renders inside UserProfileSettings after MemorySection", async () => {
    render(<UserProfileSettings />);

    const memory = await screen.findByTestId("memory-self-service-section");
    const notifications = await screen.findByTestId("notification-preferences-section");

    expect(screen.getByTestId("user-profile-settings")).toContainElement(notifications);
    // Notification section must follow the memory section (user-global sections
    // stay contiguous and precede the workspace-scoped visibility block).
    expect(
      memory.compareDocumentPosition(notifications) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();
  });
});
