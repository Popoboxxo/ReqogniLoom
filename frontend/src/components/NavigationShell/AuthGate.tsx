/**
 * ARCH-L1-001 ReactFrontend — AuthGate HOC.
 *
 * leaf_id: COMP-RF-001 (NavigationShell)
 * req_id:  REQ-L3-RF001-001 (Authentifizierungs-Gate),
 *          REQ-L2-RF-010 (Bearer-Token auth, 401 → redirect)
 *
 * Wraps protected routes. Redirects to /login when not authenticated.
 */

import React, { type ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";

interface AuthGateProps {
  children: ReactNode;
}

export function AuthGate({ children }: AuthGateProps): JSX.Element {
  const { isAuthenticated } = useAuth();
  const location = useLocation();

  if (!isAuthenticated) {
    // Preserve the intended destination so login can redirect back
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return <>{children}</>;
}
