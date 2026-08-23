import { describe, it, expect, vi, beforeEach } from "vitest";
import { bannersApi } from "./banners";
import { apiClient } from "./client";

vi.mock("./client", () => ({
  apiClient: {
    get: vi.fn(),
    put: vi.fn(),
  },
}));

describe("bannersApi", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("getGlobal normalises a null/empty response to null", async () => {
    vi.mocked(apiClient.get).mockResolvedValue(null);
    const result = await bannersApi.getGlobal();
    expect(result).toBeNull();
    expect(apiClient.get).toHaveBeenCalledWith("/admin/banners/global/");
  });

  it("getGlobal returns the banner when configured", async () => {
    const banner = {
      id: "b1",
      scope: "global",
      workspace_id: null,
      level: "info",
      message: "hi",
      enabled: true,
      dismissible: true,
      show_on_login_page: false,
      updated_at: "2026-08-23T00:00:00Z",
    };
    vi.mocked(apiClient.get).mockResolvedValue(banner);
    const result = await bannersApi.getGlobal();
    expect(result).toEqual(banner);
  });

  it("putGlobal sends the full payload including show_on_login_page", async () => {
    vi.mocked(apiClient.put).mockResolvedValue({});
    await bannersApi.putGlobal({
      level: "critical",
      message: "down",
      enabled: true,
      dismissible: false,
      show_on_login_page: true,
    });
    expect(apiClient.put).toHaveBeenCalledWith("/admin/banners/global/", {
      level: "critical",
      message: "down",
      enabled: true,
      dismissible: false,
      show_on_login_page: true,
    });
  });

  it("getWorkspace calls the workspace-scoped endpoint", async () => {
    vi.mocked(apiClient.get).mockResolvedValue(null);
    await bannersApi.getWorkspace("ws-1");
    expect(apiClient.get).toHaveBeenCalledWith("/workspaces/ws-1/banner/");
  });

  it("getLoginBanner calls the public endpoint", async () => {
    vi.mocked(apiClient.get).mockResolvedValue(null);
    await bannersApi.getLoginBanner();
    expect(apiClient.get).toHaveBeenCalledWith("/public/banners/login/");
  });
});
