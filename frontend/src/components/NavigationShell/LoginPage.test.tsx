import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { LoginPage } from "./LoginPage";
import { bannersApi } from "../../api/banners";
import { versionApi } from "../../api/version";
import { useAuth } from "../../context/AuthContext";

vi.mock("../../api/banners", () => ({
  bannersApi: { getLoginBanner: vi.fn() },
}));

vi.mock("../../api/version", () => ({
  versionApi: { getVersion: vi.fn() },
}));

vi.mock("../../context/AuthContext", () => ({
  useAuth: vi.fn(),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (_key: string, fallback?: string) => fallback ?? _key }),
}));

describe("LoginPage banner", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(versionApi.getVersion).mockResolvedValue({
      app_version: "1.0.0",
      commit_short: "abc1234",
    });
    vi.mocked(useAuth).mockReturnValue({
      login: vi.fn(),
    } as unknown as ReturnType<typeof useAuth>);
  });

  it("renders nothing when no login banner is configured", async () => {
    vi.mocked(bannersApi.getLoginBanner).mockResolvedValue(null);
    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>
    );
    await waitFor(() => expect(bannersApi.getLoginBanner).toHaveBeenCalled());
    expect(screen.queryByTestId("login-page-banner")).toBeNull();
  });

  it("renders the banner message when configured", async () => {
    vi.mocked(bannersApi.getLoginBanner).mockResolvedValue({
      level: "warning",
      message: "Maintenance tonight",
      dismissible: true,
    });
    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>
    );
    expect(await screen.findByTestId("login-page-banner")).toHaveTextContent(
      "Maintenance tonight"
    );
  });
});
