/**
 * ARCH-L1-001 ReactFrontend — AuthContext httpOnly-cookie session tests (REQ-052).
 *
 * leaf_id: COMP-RF-001 (AuthGate / session restore)
 * req_id:  REQ-052 (Auth-Token XSS-fix — httpOnly cookie + /auth/me/ bootstrap)
 *
 * Verifies the XSS-hardened auth lifecycle:
 * - mount restores the session via GET /auth/me/ (200 → authenticated,
 *   401 → anonymous) and exposes a "restoring" loading state in between,
 * - the access token is NEVER written to sessionStorage,
 * - the API client sends credentials + X-CSRFToken on unsafe methods.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { AuthProvider, useAuth } from "../context/AuthContext";
import { apiClient } from "../api/client";

const MOCK_USER = {
  id: "u-1",
  username: "tester",
  email: "t@x.test",
  first_name: "Ada",
  last_name: "Lovelace",
  is_active: true,
  tenant_id: "t-1",
  roles: ["admin"],
};

function StatusProbe(): JSX.Element {
  const { status, isAuthenticated, user } = useAuth();
  return (
    <div>
      <span data-testid="status">{status}</span>
      <span data-testid="is-auth">{String(isAuthenticated)}</span>
      <span data-testid="username">{user?.username ?? ""}</span>
    </div>
  );
}

function renderProbe(): void {
  render(
    <AuthProvider>
      <StatusProbe />
    </AuthProvider>
  );
}

describe("AuthContext session restore (REQ-052)", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("renders a restoring state, then authenticated on /auth/me/ 200", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        status: 200,
        json: async () => ({ user: MOCK_USER, tenant_id: "t-1", roles: ["admin"] }),
      }) as unknown as Response)
    );

    renderProbe();

    // Loading state is shown before /auth/me/ resolves.
    expect(screen.getByTestId("status").textContent).toBe("restoring");

    expect(await screen.findByText("tester")).toBeInTheDocument();
    expect(screen.getByTestId("status").textContent).toBe("authenticated");
    expect(screen.getByTestId("is-auth").textContent).toBe("true");
  });

  it("resolves to anonymous on /auth/me/ 401", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: false, status: 401, json: async () => ({}) }) as unknown as Response)
    );

    renderProbe();

    await vi.waitFor(() =>
      expect(screen.getByTestId("status").textContent).toBe("anonymous")
    );
    expect(screen.getByTestId("is-auth").textContent).toBe("false");
  });

  it("never writes the access token to sessionStorage on login", async () => {
    const setItemSpy = vi.spyOn(Storage.prototype, "setItem");
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url.endsWith("/auth/me/")) {
          return { ok: false, status: 401, json: async () => ({}) } as Response;
        }
        // /auth/login/
        return {
          ok: true,
          status: 200,
          json: async () => ({ token: "secret-jwt", user: MOCK_USER, tenant_id: "t-1", roles: ["admin"] }),
        } as Response;
      }) as typeof fetch
    );

    let loginFn: ((c: { username: string; password: string }) => Promise<void>) | null = null;
    function LoginCapture(): JSX.Element {
      loginFn = useAuth().login;
      return <StatusProbe />;
    }
    render(
      <AuthProvider>
        <LoginCapture />
      </AuthProvider>
    );

    await vi.waitFor(() => expect(loginFn).not.toBeNull());
    await loginFn!({ username: "tester", password: "pw" });

    // No sessionStorage write may contain the token key or its value.
    const tokenWrites = setItemSpy.mock.calls.filter(
      ([key, value]) => key === "reqflow_token" || String(value).includes("secret-jwt")
    );
    expect(tokenWrites).toEqual([]);
  });
});

describe("apiClient CSRF + credentials (REQ-052)", () => {
  beforeEach(() => {
    document.cookie = "csrftoken=csrf-abc";
  });

  afterEach(() => {
    vi.restoreAllMocks();
    document.cookie = "csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
  });

  it("sends credentials and X-CSRFToken on POST", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue({ ok: true, status: 200, json: async () => ({}) } as Response);

    await apiClient.post("/things/", { a: 1 });

    const [, options] = fetchSpy.mock.calls[0] as [string, RequestInit];
    expect(options.credentials).toBe("same-origin");
    expect((options.headers as Record<string, string>)["X-CSRFToken"]).toBe("csrf-abc");
  });

  it("does not send X-CSRFToken on GET", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue({ ok: true, status: 200, json: async () => ({}) } as Response);

    await apiClient.get("/things/");

    const [, options] = fetchSpy.mock.calls[0] as [string, RequestInit];
    expect(options.credentials).toBe("same-origin");
    expect((options.headers as Record<string, string>)["X-CSRFToken"]).toBeUndefined();
  });
});
