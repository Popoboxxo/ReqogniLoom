/**
 * ARCH-L1-001 ReactFrontend — AuthGate HOC.
 *
 * leaf_id: COMP-RF-001 (NavigationShell)
 * req_id:  REQ-L3-RF001-001 (Authentifizierungs-Gate),
 *          REQ-L2-RF-010 (Bearer-Token auth, 401 → redirect)
 *
 * Wraps protected routes. Redirects to /login when not authenticated.
 */

import { type ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";

interface AuthGateProps {
  children: ReactNode;
}

export function AuthGate({ children }: AuthGateProps): JSX.Element {
  const { isAuthenticated, status } = useAuth();
  const location = useLocation();

  if (status === "restoring") {
    // Session restore (GET /auth/me/) is in flight — render nothing rather than
    // flashing the login page for an already-authenticated user (REQ-052).
    return <div data-testid="auth-restoring" aria-busy="true" />;
  }

  if (!isAuthenticated) {
    // Preserve the intended destination so login can redirect back
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return <>{children}</>;
}
