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

import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { AuthGate } from "../components/NavigationShell/AuthGate";
import { AuthProvider } from "../context/AuthContext";
import { WorkspaceProvider } from "../context/WorkspaceContext";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderWithAuth(
  initialPath: string,
  token: string | null
): ReturnType<typeof render> {
  // Pre-load token into sessionStorage so AuthProvider picks it up
  if (token) {
    sessionStorage.setItem("reqflow_token", token);
  } else {
    sessionStorage.removeItem("reqflow_token");
  }

  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <AuthProvider>
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
  });

  it("redirects unauthenticated users to /login", () => {
    renderWithAuth("/protected", null);
    expect(screen.getByText("Login Page")).toBeInTheDocument();
    expect(screen.queryByText("Protected Content")).not.toBeInTheDocument();
  });

  it("renders children for authenticated users", () => {
    renderWithAuth("/protected", "test-bearer-token");
    expect(screen.getByText("Protected Content")).toBeInTheDocument();
    expect(screen.queryByText("Login Page")).not.toBeInTheDocument();
  });
});
