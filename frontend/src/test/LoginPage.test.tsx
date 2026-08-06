/**
 * ARCH-L1-001 ReactFrontend — LoginPage tests.
 *
 * leaf_id: COMP-RF-001 (NavigationShell)
 * req_id:  REQ-L2-RF-010 (Authentication, 401/403 → redirect to login)
 *
 * Tests:
 * 1. Successful login → token stored, user navigated away.
 * 2. 401 response → error message displayed (invalidCredentials).
 * 3. Empty username → validation error shown.
 * 4. Empty password → validation error shown.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { LoginPage } from "../components/NavigationShell/LoginPage";
import { AuthProvider } from "../context/AuthContext";
import { I18nextProvider } from "react-i18next";
import i18next from "i18next";
import { initReactI18next } from "react-i18next";

// ---------------------------------------------------------------------------
// Minimal i18n setup for tests
// ---------------------------------------------------------------------------

const i18n = i18next.createInstance();
i18n.use(initReactI18next).init({
  lng: "en",
  resources: {
    en: {
      translation: {
        "login.title": "Sign In",
        "login.usernameLabel": "Username",
        "login.usernamePlaceholder": "Enter username...",
        "login.usernameRequired": "Please enter a username.",
        "login.passwordLabel": "Password",
        "login.passwordPlaceholder": "Enter password...",
        "login.passwordRequired": "Please enter a password.",
        "login.submit": "Sign In",
        "login.invalidCredentials": "Invalid credentials. Please try again.",
        loading: "Loading...",
      },
    },
  },
});

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderLoginPage(
  initialPath = "/login"
): ReturnType<typeof render> & { navigatedTo: string[] } {
  sessionStorage.clear();
  const navigatedTo: string[] = [];

  const result = render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter initialEntries={[initialPath]}>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route
              path="/"
              element={<div data-testid="home-page">Home</div>}
            />
            <Route
              path="/dashboard"
              element={<div data-testid="dashboard-page">Dashboard</div>}
            />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    </I18nextProvider>
  );

  return { ...result, navigatedTo };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

/**
 * Route fetch by URL: the AuthProvider mount fires GET /auth/me/ (session
 * restore, REQ-052) before any login attempt. Default it to 401 (anonymous)
 * and let ``loginResponse`` drive POST /auth/login/.
 */
function installFetch(loginResponse?: Partial<Response> & { json?: () => Promise<unknown> }): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn(async (url: string) => {
    if (url.endsWith("/auth/me/")) {
      return { ok: false, status: 401, json: async () => ({}) } as Response;
    }
    return (loginResponse ?? { ok: false, status: 401, json: async () => ({}) }) as Response;
  });
  vi.spyOn(globalThis, "fetch").mockImplementation(fetchMock as typeof fetch);
  return fetchMock;
}

describe("LoginPage (COMP-RF-001 / REQ-L2-RF-010)", () => {
  beforeEach(() => {
    installFetch();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    sessionStorage.clear();
  });

  it("renders username and password fields", () => {
    renderLoginPage();
    expect(screen.getByLabelText("Username")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Sign In" })
    ).toBeInTheDocument();
  });

  it("shows validation error when username is empty", async () => {
    const user = userEvent.setup();
    renderLoginPage();

    await user.click(screen.getByRole("button", { name: "Sign In" }));

    expect(
      screen.getByRole("alert")
    ).toHaveTextContent("Please enter a username.");
  });

  it("shows validation error when password is empty", async () => {
    const user = userEvent.setup();
    renderLoginPage();

    await user.type(screen.getByLabelText("Username"), "testuser");
    await user.click(screen.getByRole("button", { name: "Sign In" }));

    expect(
      screen.getByRole("alert")
    ).toHaveTextContent("Please enter a password.");
  });

  it("authenticates and navigates on successful login", async () => {
    // The token is delivered as an httpOnly cookie (REQ-052); the SPA no longer
    // persists it to sessionStorage. Success is observed via navigation.
    const mockLoginResponse = {
      token: "test-jwt-token-123",
      user: {
        id: "user-1",
        username: "testuser",
        email: "test@example.com",
        is_active: true,
        tenant_id: "tenant-1",
        roles: ["viewer"],
      },
      tenant_id: "tenant-1",
      roles: ["viewer"],
    };

    installFetch({
      ok: true,
      status: 200,
      json: async () => mockLoginResponse,
    });

    const user = userEvent.setup();
    renderLoginPage();

    await user.type(screen.getByLabelText("Username"), "testuser");
    await user.type(screen.getByLabelText("Password"), "secret123");
    await user.click(screen.getByRole("button", { name: "Sign In" }));

    // The access token must never be written to sessionStorage (XSS-fix).
    expect(sessionStorage.getItem("reqflow_token")).toBeNull();

    // Navigated away from login
    await waitFor(() => {
      expect(screen.queryByRole("button", { name: "Sign In" })).not.toBeInTheDocument();
    });
  });

  it("shows invalidCredentials error on 401 response", async () => {
    installFetch({
      ok: false,
      status: 401,
      json: async () => ({
        // #271: the login endpoint reports "invalid_credentials";
        // "invalid_token" is reserved for JWT parse/expiry failures.
        error: "invalid_credentials",
        message: "Invalid username or password",
      }),
    });

    const user = userEvent.setup();
    renderLoginPage();

    await user.type(screen.getByLabelText("Username"), "wronguser");
    await user.type(screen.getByLabelText("Password"), "wrongpass");
    await user.click(screen.getByRole("button", { name: "Sign In" }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(
        "Invalid credentials. Please try again."
      );
    });

    // Token must NOT be stored
    expect(sessionStorage.getItem("reqflow_token")).toBeNull();
  });

  it("sends POST to /api/v1/auth/login/ with credentials and correct payload", async () => {
    const fetchSpy = installFetch({
      ok: true,
      status: 200,
      json: async () => ({
        token: "tok",
        user: {
          id: "1",
          username: "admin",
          email: "admin@test.com",
          is_active: true,
          tenant_id: "t1",
          roles: [],
        },
        tenant_id: "t1",
        roles: [],
      }),
    });

    const user = userEvent.setup();
    renderLoginPage();

    await user.type(screen.getByLabelText("Username"), "admin");
    await user.type(screen.getByLabelText("Password"), "pass");
    await user.click(screen.getByRole("button", { name: "Sign In" }));

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith(
        "/api/v1/auth/login/",
        expect.objectContaining({
          method: "POST",
          credentials: "same-origin",
          body: JSON.stringify({ username: "admin", password: "pass" }),
        })
      );
    });
  });
});
