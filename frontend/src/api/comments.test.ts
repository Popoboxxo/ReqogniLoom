import { describe, expect, it, vi, beforeEach } from "vitest";

vi.mock("./client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}));

import { apiClient } from "./client";
import { commentsApi } from "./comments";
import { notificationsApi } from "./notifications";

const wire = {
  id: "c1",
  artifact_id: "a1",
  text: "hello",
  author_id: "u1",
  author_display: "alice",
  resolved: false,
  resolved_by_id: null,
  resolved_at: null,
  created_at: "2026-09-04T10:00:00Z",
};

describe("commentsApi", () => {
  beforeEach(() => {
    vi.mocked(apiClient.get).mockReset();
    vi.mocked(apiClient.post).mockReset();
    vi.mocked(apiClient.delete).mockReset();
  });

  it("lists an artifact's comments and camel-cases the wire format", async () => {
    vi.mocked(apiClient.get).mockResolvedValue([wire]);

    const rows = await commentsApi.list("a1");

    expect(apiClient.get).toHaveBeenCalledWith("/artifacts/a1/comments/");
    expect(rows[0]).toEqual({
      id: "c1",
      artifactId: "a1",
      text: "hello",
      authorId: "u1",
      authorDisplay: "alice",
      resolved: false,
      resolvedById: null,
      resolvedAt: null,
      createdAt: "2026-09-04T10:00:00Z",
    });
  });

  it("passes include_resolved=false when open comments are requested", async () => {
    vi.mocked(apiClient.get).mockResolvedValue([]);

    await commentsApi.list("a1", { includeResolved: false });

    expect(apiClient.get).toHaveBeenCalledWith(
      "/artifacts/a1/comments/?include_resolved=false"
    );
  });

  it("creates a comment", async () => {
    vi.mocked(apiClient.post).mockResolvedValue(wire);

    const created = await commentsApi.create("a1", "hello");

    expect(apiClient.post).toHaveBeenCalledWith("/artifacts/a1/comments/", {
      text: "hello",
    });
    expect(created.text).toBe("hello");
  });

  it("resolves a comment", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ ...wire, resolved: true });

    const resolved = await commentsApi.resolve("c1");

    expect(apiClient.post).toHaveBeenCalledWith("/comments/c1/resolve/", {});
    expect(resolved.resolved).toBe(true);
  });

  it("deletes a comment", async () => {
    vi.mocked(apiClient.delete).mockResolvedValue(undefined);

    await commentsApi.remove("c1");

    expect(apiClient.delete).toHaveBeenCalledWith("/comments/c1/");
  });
});

describe("notificationsApi", () => {
  beforeEach(() => {
    vi.mocked(apiClient.get).mockReset();
    vi.mocked(apiClient.post).mockReset();
  });

  it("returns the feed and the unread count", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      notifications: [
        {
          id: "n1",
          kind: "assigned",
          artifact_id: "a1",
          message: "m",
          read: false,
          created_at: "2026-09-04T10:00:00Z",
        },
      ],
      unread_count: 1,
    });

    const feed = await notificationsApi.list();

    expect(apiClient.get).toHaveBeenCalledWith("/notifications/?limit=20");
    expect(feed.unreadCount).toBe(1);
    expect(feed.notifications[0].artifactId).toBe("a1");
  });

  it("marks one notification read", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({
      id: "n1",
      kind: "assigned",
      artifact_id: null,
      message: "m",
      read: true,
      created_at: "2026-09-04T10:00:00Z",
    });

    const row = await notificationsApi.markRead("n1");

    expect(apiClient.post).toHaveBeenCalledWith("/notifications/n1/read/", {});
    expect(row.read).toBe(true);
  });

  it("marks everything read", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ marked: 3 });

    expect(await notificationsApi.markAllRead()).toBe(3);
    expect(apiClient.post).toHaveBeenCalledWith("/notifications/mark-all-read/", {});
  });
});
