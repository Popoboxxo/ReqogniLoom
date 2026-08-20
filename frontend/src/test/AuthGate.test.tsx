/**
 * ARCH-L1-001 ReactFrontend — AuthGate tests.
 *
 * leaf_id: COMP-RF-001 (NavigationShell)
 * req_id:  REQ-L3-RF001-001 (Authentifizierungs-Gate),
 *          REQ-L2-RF-010 (Bearer-Token, 401 → redirect to /login)
 *
 * Tests:
 * 1. Unauthenticated access → redirects to /login.
 * 2. Authenticated access → renders children.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { AuthGate } from "../components/NavigationShell/AuthGate";
import { AuthProvider } from "../context/AuthContext";
import { WorkspaceProvider } from "../context/WorkspaceContext";
import { ThemeProvider } from "../context/ThemeContext";

// jsdom in this test runtime does not provide window.localStorage (Node's
// --localstorage-file experimental flag is not set), which ThemeProvider
// (now a WorkspaceProvider dependency, #568 phase 1) reads synchronously on
// mount. Polyfill a minimal in-memory implementation so it does not throw.
function installLocalStorageStub(): void {
  const store = new Map<string, string>();
  Object.defineProperty(window, "localStorage", {
    configurable: true,
    value: {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => void store.set(key, value),
      removeItem: (key: string) => void store.delete(key),
      clear: () => store.clear(),
    },
  });
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const MOCK_USER = {
  id: "u-1",
  username: "tester",
  email: "t@x.test",
  first_name: "",
  last_name: "",
  is_active: true,
  tenant_id: "t-1",
  roles: ["viewer"],
};

/**
 * The session is now restored via GET /auth/me/ (httpOnly cookie, REQ-052)
 * instead of a sessionStorage token. ``authenticated`` decides whether that
 * bootstrap resolves to a user (200) or to the anonymous state (401).
 */
function renderWithAuth(
  initialPath: string,
  authenticated: boolean
): ReturnType<typeof render> {
  vi.spyOn(globalThis, "fetch").mockImplementation((async (url: string) => {
    if (url.endsWith("/auth/me/")) {
      return authenticated
        ? { ok: true, status: 200, json: async () => ({ user: MOCK_USER, tenant_id: "t-1", roles: ["viewer"] }) }
        : { ok: false, status: 401, json: async () => ({}) };
    }
    return { ok: true, status: 200, json: async () => ({ count: 0, results: [] }) };
  }) as typeof fetch);

  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <AuthProvider>
        <ThemeProvider>
          <WorkspaceProvider>
            <Routes>
              <Route path="/login" element={<div>Login Page</div>} />
              <Route
                path="/protected"
                element={
                  <AuthGate>
                    <div>Protected Content</div>
                  </AuthGate>
                }
              />
            </Routes>
          </WorkspaceProvider>
        </ThemeProvider>
      </AuthProvider>
    </MemoryRouter>
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("AuthGate (COMP-RF-001 / REQ-L3-RF001-001)", () => {
  beforeEach(() => {
    sessionStorage.clear();
    installLocalStorageStub();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("redirects unauthenticated users to /login", async () => {
    renderWithAuth("/protected", false);
    expect(await screen.findByText("Login Page")).toBeInTheDocument();
    expect(screen.queryByText("Protected Content")).not.toBeInTheDocument();
  });

  it("renders children for authenticated users", async () => {
    renderWithAuth("/protected", true);
    expect(await screen.findByText("Protected Content")).toBeInTheDocument();
    expect(screen.queryByText("Login Page")).not.toBeInTheDocument();
  });
});
