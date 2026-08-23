import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { WorkspaceBannerSection } from "./WorkspaceBannerSection";
import { bannersApi } from "../../api/banners";

vi.mock("../../api/banners", () => ({
  bannersApi: { getWorkspace: vi.fn(), putWorkspace: vi.fn() },
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (_key: string, fallback?: string) => fallback ?? _key }),
}));

describe("WorkspaceBannerSection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("loads and pre-fills the existing workspace banner", async () => {
    vi.mocked(bannersApi.getWorkspace).mockResolvedValue({
      id: "w1",
      scope: "workspace",
      workspace_id: "ws-1",
      level: "warning",
      message: "existing text",
      enabled: true,
      dismissible: false,
      show_on_login_page: false,
      updated_at: "2026-08-23T00:00:00Z",
    });
    render(<WorkspaceBannerSection workspaceId="ws-1" />);
    expect(await screen.findByDisplayValue("existing text")).toBeInTheDocument();
    expect(screen.getByTestId("workspace-banner-level-warning")).toBeChecked();
    expect(screen.getByTestId("workspace-banner-enabled-toggle")).toBeChecked();
    expect(screen.getByTestId("workspace-banner-dismissible-toggle")).not.toBeChecked();
    expect(bannersApi.getWorkspace).toHaveBeenCalledWith("ws-1");
  });

  it("pre-fills dismissible=false only for a brand-new banner when critical is picked", async () => {
    vi.mocked(bannersApi.getWorkspace).mockResolvedValue(null);
    render(<WorkspaceBannerSection workspaceId="ws-1" />);
    await waitFor(() => expect(bannersApi.getWorkspace).toHaveBeenCalled());
    expect(screen.getByTestId("workspace-banner-dismissible-toggle")).toBeChecked();
    fireEvent.click(screen.getByTestId("workspace-banner-level-critical"));
    expect(screen.getByTestId("workspace-banner-dismissible-toggle")).not.toBeChecked();
  });

  it("save calls putWorkspace with the workspace id and current form state", async () => {
    vi.mocked(bannersApi.getWorkspace).mockResolvedValue(null);
    vi.mocked(bannersApi.putWorkspace).mockResolvedValue({
      id: "w1",
      scope: "workspace",
      workspace_id: "ws-1",
      level: "info",
      message: "hello",
      enabled: true,
      dismissible: true,
      show_on_login_page: false,
      updated_at: "2026-08-23T00:00:00Z",
    });
    render(<WorkspaceBannerSection workspaceId="ws-1" />);
    await waitFor(() => expect(bannersApi.getWorkspace).toHaveBeenCalled());

    fireEvent.change(screen.getByTestId("workspace-banner-message-input"), {
      target: { value: "hello" },
    });
    fireEvent.click(screen.getByTestId("workspace-banner-enabled-toggle"));
    fireEvent.click(screen.getByTestId("workspace-banner-save-button"));

    await waitFor(() =>
      expect(bannersApi.putWorkspace).toHaveBeenCalledWith("ws-1", {
        level: "neutral",
        message: "hello",
        enabled: true,
        dismissible: true,
      })
    );
    expect(await screen.findByText("Saved.")).toBeInTheDocument();
  });

  it("shows an error message when save fails (e.g. 403 for a non-admin)", async () => {
    vi.mocked(bannersApi.getWorkspace).mockResolvedValue(null);
    vi.mocked(bannersApi.putWorkspace).mockRejectedValue({
      error: { message: "workspace-admin or System-Admin role required." },
    });
    render(<WorkspaceBannerSection workspaceId="ws-1" />);
    await waitFor(() => expect(bannersApi.getWorkspace).toHaveBeenCalled());
    fireEvent.click(screen.getByTestId("workspace-banner-save-button"));
    expect(
      await screen.findByText("workspace-admin or System-Admin role required.")
    ).toBeInTheDocument();
  });
});
