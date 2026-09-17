import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { BannerSection } from "./BannerSection";
import { bannersApi } from "../../api/banners";

vi.mock("../../api/banners", () => ({
  bannersApi: { getGlobal: vi.fn(), putGlobal: vi.fn() },
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (_key: string, fallback?: string) => fallback ?? _key }),
}));

describe("BannerSection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("loads and pre-fills the existing global banner", async () => {
    vi.mocked(bannersApi.getGlobal).mockResolvedValue({
      id: "g1",
      scope: "global",
      workspace_id: null,
      level: "warning",
      message: "existing text",
      enabled: true,
      dismissible: false,
      show_on_login_page: true,
      updated_at: "2026-08-23T00:00:00Z",
    });
    render(<BannerSection />);
    expect(await screen.findByDisplayValue("existing text")).toBeInTheDocument();
    expect(screen.getByTestId("banner-level-warning")).toBeChecked();
    expect(screen.getByTestId("banner-enabled-toggle")).toBeChecked();
    expect(screen.getByTestId("banner-dismissible-toggle")).not.toBeChecked();
    expect(screen.getByTestId("banner-show-on-login-toggle")).toBeChecked();
  });

  it("pre-fills dismissible=false only for a brand-new banner when critical is picked", async () => {
    vi.mocked(bannersApi.getGlobal).mockResolvedValue(null);
    render(<BannerSection />);
    await waitFor(() => expect(bannersApi.getGlobal).toHaveBeenCalled());
    expect(screen.getByTestId("banner-dismissible-toggle")).toBeChecked();
    fireEvent.click(screen.getByTestId("banner-level-critical"));
    expect(screen.getByTestId("banner-dismissible-toggle")).not.toBeChecked();
  });

  it("save calls putGlobal with the current form state", async () => {
    vi.mocked(bannersApi.getGlobal).mockResolvedValue(null);
    vi.mocked(bannersApi.putGlobal).mockResolvedValue({
      id: "g1",
      scope: "global",
      workspace_id: null,
      level: "info",
      message: "hello",
      enabled: true,
      dismissible: true,
      show_on_login_page: false,
      updated_at: "2026-08-23T00:00:00Z",
    });
    render(<BannerSection />);
    await waitFor(() => expect(bannersApi.getGlobal).toHaveBeenCalled());

    fireEvent.change(screen.getByTestId("banner-message-input"), {
      target: { value: "hello" },
    });
    fireEvent.click(screen.getByTestId("banner-enabled-toggle"));
    fireEvent.click(screen.getByTestId("banner-save-button"));

    await waitFor(() =>
      expect(bannersApi.putGlobal).toHaveBeenCalledWith({
        level: "neutral",
        message: "hello",
        enabled: true,
        dismissible: true,
        show_on_login_page: false,
      })
    );
    expect(await screen.findByText("Saved.")).toBeInTheDocument();
  });

  it("shows an error message when save fails (e.g. 403 for a non-System-Admin)", async () => {
    vi.mocked(bannersApi.getGlobal).mockResolvedValue(null);
    vi.mocked(bannersApi.putGlobal).mockRejectedValue({
      error: { message: "tenant-admin (System-Admin) role required." },
    });
    render(<BannerSection />);
    await waitFor(() => expect(bannersApi.getGlobal).toHaveBeenCalled());
    fireEvent.click(screen.getByTestId("banner-save-button"));
    expect(await screen.findByText("tenant-admin (System-Admin) role required.")).toBeInTheDocument();
  });
});
