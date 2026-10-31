import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { LoginPage } from "./LoginPage";
import { bannersApi, type LoginBanner } from "../../api/banners";
import { versionApi } from "../../api/version";
import { useAuth, type LoginOutcome } from "../../context/AuthContext";
import { MfaLoginError } from "../../api/mfa";

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
  useTranslation: () => ({
    t: (key: string, options?: string | Record<string, unknown>) =>
      typeof options === "string"
        ? options
        : `${key}${options ? `:${JSON.stringify(options)}` : ""}`,
  }),
}));

const DISMISSIBLE_BANNER: LoginBanner = {
  id: "banner-1",
  level: "warning",
  message: "Maintenance tonight",
  dismissible: true,
  updated_at: "2026-08-23T10:00:00Z",
};

/** The key LoginPage writes on dismiss — spec: `scope=global-login`. */
const DISMISS_KEY = `banner-dismissed-global-login-${DISMISSIBLE_BANNER.id}-${DISMISSIBLE_BANNER.updated_at}`;

function renderLoginPage(): void {
  render(
    <MemoryRouter>
      <LoginPage />
    </MemoryRouter>
  );
}

describe("LoginPage banner", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.sessionStorage.clear();
    vi.mocked(versionApi.getVersion).mockResolvedValue({
      app_version: "1.0.0",
      commit_short: "abc1234",
    });
    vi.mocked(useAuth).mockReturnValue({
      login: vi.fn(),
      completeMfaLogin: vi.fn(),
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
    vi.mocked(bannersApi.getLoginBanner).mockResolvedValue(DISMISSIBLE_BANNER);
    renderLoginPage();
    expect(await screen.findByTestId("login-page-banner")).toHaveTextContent(
      "Maintenance tonight"
    );
  });

  it("shows a dismiss button when the banner is dismissible", async () => {
    vi.mocked(bannersApi.getLoginBanner).mockResolvedValue(DISMISSIBLE_BANNER);
    renderLoginPage();
    expect(await screen.findByTestId("login-page-banner-dismiss")).toHaveAttribute(
      "aria-label",
      "Dismiss"
    );
  });

  it("hides the dismiss button when the banner is not dismissible", async () => {
    vi.mocked(bannersApi.getLoginBanner).mockResolvedValue({
      ...DISMISSIBLE_BANNER,
      dismissible: false,
    });
    renderLoginPage();
    await screen.findByTestId("login-page-banner");
    expect(screen.queryByTestId("login-page-banner-dismiss")).toBeNull();
  });

  it("hides the banner and records the dismissal on click", async () => {
    vi.mocked(bannersApi.getLoginBanner).mockResolvedValue(DISMISSIBLE_BANNER);
    renderLoginPage();

    fireEvent.click(await screen.findByTestId("login-page-banner-dismiss"));

    expect(screen.queryByTestId("login-page-banner")).toBeNull();
    expect(window.sessionStorage.getItem(DISMISS_KEY)).toBe("1");
  });

  it("stays hidden on a fresh render when the dismissal is already stored", async () => {
    window.sessionStorage.setItem(DISMISS_KEY, "1");
    vi.mocked(bannersApi.getLoginBanner).mockResolvedValue(DISMISSIBLE_BANNER);
    renderLoginPage();

    await waitFor(() => expect(bannersApi.getLoginBanner).toHaveBeenCalled());
    await waitFor(() =>
      expect(screen.queryByTestId("login-page-banner")).toBeNull()
    );
  });

  it("reappears when the admin edits the banner (updated_at changes)", async () => {
    // The dismiss key embeds updated_at, so a stale dismissal must not
    // suppress a newly edited announcement.
    window.sessionStorage.setItem(DISMISS_KEY, "1");
    vi.mocked(bannersApi.getLoginBanner).mockResolvedValue({
      ...DISMISSIBLE_BANNER,
      message: "Maintenance moved to Friday",
      updated_at: "2026-08-24T09:00:00Z",
    });
    renderLoginPage();

    expect(await screen.findByTestId("login-page-banner")).toHaveTextContent(
      "Maintenance moved to Friday"
    );
  });

  it("renders the message as plain text, never as markup", async () => {
    // Deliberate security divergence from BannerStack: this endpoint is
    // unauthenticated, so its content must never render links or HTML.
    vi.mocked(bannersApi.getLoginBanner).mockResolvedValue({
      ...DISMISSIBLE_BANNER,
      message: "[click](https://evil.example) <b>bold</b>",
    });
    renderLoginPage();

    const banner = await screen.findByTestId("login-page-banner");
    expect(banner).toHaveTextContent("[click](https://evil.example) <b>bold</b>");
    expect(banner.querySelector("a")).toBeNull();
    expect(banner.querySelector("b")).toBeNull();
  });
});

describe("LoginPage MFA second step", () => {
  const challenge = "signed-challenge";

  function setupAuth(outcome: LoginOutcome, complete = vi.fn()): void {
    vi.mocked(useAuth).mockReturnValue({
      login: vi.fn().mockResolvedValue(outcome),
      completeMfaLogin: complete,
    } as unknown as ReturnType<typeof useAuth>);
  }

  async function submitCredentials(): Promise<HTMLElement> {
    fireEvent.change(screen.getByTestId("login-username-input"), {
      target: { value: "e2e-mfa" },
    });
    fireEvent.change(screen.getByTestId("login-password-input"), {
      target: { value: "secret-password" },
    });
    fireEvent.click(screen.getByTestId("login-submit-button"));
    return screen.findByTestId("login-mfa-step");
  }

  beforeEach(() => {
    vi.clearAllMocks();
    window.sessionStorage.clear();
    vi.mocked(versionApi.getVersion).mockResolvedValue({
      app_version: "1.0.0",
      commit_short: "abc1234",
    });
    vi.mocked(bannersApi.getLoginBanner).mockResolvedValue(null);
  });

  it("renders the code step when the password needs a second factor", async () => {
    setupAuth({ kind: "mfa", challenge, methods: ["totp", "recovery_code"] });
    renderLoginPage();

    await submitCredentials();

    expect(screen.getByTestId("login-mfa-code-input")).toBeInTheDocument();
    expect(screen.queryByTestId("login-password-input")).toBeNull();
  });

  it("submits a TOTP code against the challenge", async () => {
    const complete = vi.fn().mockResolvedValue(undefined);
    setupAuth({ kind: "mfa", challenge, methods: ["totp"] }, complete);
    renderLoginPage();

    await submitCredentials();
    fireEvent.change(screen.getByTestId("login-mfa-code-input"), {
      target: { value: "123456" },
    });
    fireEvent.click(screen.getByTestId("login-mfa-submit"));

    await waitFor(() =>
      expect(complete).toHaveBeenCalledWith(challenge, { code: "123456" })
    );
  });

  it("switches to a recovery code and submits it", async () => {
    const complete = vi.fn().mockResolvedValue(undefined);
    setupAuth({ kind: "mfa", challenge, methods: ["totp", "recovery_code"] }, complete);
    renderLoginPage();

    await submitCredentials();
    fireEvent.click(screen.getByTestId("login-mfa-recovery-toggle"));
    fireEvent.change(screen.getByTestId("login-mfa-recovery-input"), {
      target: { value: "AAAA-BBBB-CCCC-DDDD" },
    });
    fireEvent.click(screen.getByTestId("login-mfa-submit"));

    await waitFor(() =>
      expect(complete).toHaveBeenCalledWith(challenge, {
        recoveryCode: "AAAA-BBBB-CCCC-DDDD",
      })
    );
  });

  it("shows an invalid-code error without losing the step", async () => {
    const complete = vi
      .fn()
      .mockRejectedValue(new MfaLoginError("MFA_INVALID_CODE", 401));
    setupAuth({ kind: "mfa", challenge, methods: ["totp"] }, complete);
    renderLoginPage();

    await submitCredentials();
    fireEvent.change(screen.getByTestId("login-mfa-code-input"), {
      target: { value: "000000" },
    });
    fireEvent.click(screen.getByTestId("login-mfa-submit"));

    expect(await screen.findByTestId("login-mfa-error")).toHaveTextContent(
      "login.mfa.invalidCode"
    );
    expect(screen.getByTestId("login-mfa-step")).toBeInTheDocument();
  });

  it("shows the lockout minutes from Retry-After", async () => {
    const complete = vi
      .fn()
      .mockRejectedValue(new MfaLoginError("MFA_LOCKED", 429, 120));
    setupAuth({ kind: "mfa", challenge, methods: ["totp"] }, complete);
    renderLoginPage();

    await submitCredentials();
    fireEvent.change(screen.getByTestId("login-mfa-code-input"), {
      target: { value: "000000" },
    });
    fireEvent.click(screen.getByTestId("login-mfa-submit"));

    expect(await screen.findByTestId("login-mfa-error")).toHaveTextContent(
      'login.mfa.locked:{"minutes":2}'
    );
  });

  it("returns to step one when the challenge expired", async () => {
    const complete = vi
      .fn()
      .mockRejectedValue(new MfaLoginError("MFA_CHALLENGE_INVALID", 401));
    setupAuth({ kind: "mfa", challenge, methods: ["totp"] }, complete);
    renderLoginPage();

    await submitCredentials();
    fireEvent.change(screen.getByTestId("login-mfa-code-input"), {
      target: { value: "000000" },
    });
    fireEvent.click(screen.getByTestId("login-mfa-submit"));

    await waitFor(() =>
      expect(screen.queryByTestId("login-mfa-step")).toBeNull()
    );
    expect(screen.getByTestId("login-password-input")).toBeInTheDocument();
  });

  it("shows the enrollment-required notice", async () => {
    setupAuth({ kind: "enroll", challenge });
    renderLoginPage();

    await submitCredentials();

    expect(screen.getByTestId("login-mfa-step")).toHaveTextContent(
      "login.mfa.enrollRequired"
    );
  });
});
