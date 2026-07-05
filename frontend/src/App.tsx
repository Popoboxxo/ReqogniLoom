/**
 * ARCH-L1-001 ReactFrontend — Root application component.
 *
 * leaf_id: COMP-RF-001 (NavigationShell)
 * req_id:  REQ-L2-RF-010 (Bearer-Token auth + 401 redirect),
 *          REQ-L2-RF-001 (i18n DE/EN),
 *          REQ-L2-RF-007 (Preset-basierte Sichtbarkeit),
 *          REQ-L2-RF-008 (Terminologie-Profil)
 *
 * Provider hierarchy:
 *   QueryClientProvider (TanStack Query cache)
 *     └── BrowserRouter
 *           └── AuthProvider (token management + 401 handler)
 *                 └── WorkspaceProvider (preset + terminology)
 *                       └── NavigationShell (routes + auth gate)
 */

import React from "react";
import { BrowserRouter, useNavigate } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { queryClient } from "./queries/queryClient";
import { AuthProvider } from "./context/AuthContext";
import { WorkspaceProvider } from "./context/WorkspaceContext";
import { ThemeProvider } from "./context/ThemeContext";
import { NavigationShell } from "./components/NavigationShell/NavigationShell";

// ---------------------------------------------------------------------------
// Inner wrapper — needs Router context to call useNavigate
// ---------------------------------------------------------------------------

function AppInner(): JSX.Element {
  const navigate = useNavigate();

  return (
    <AuthProvider onUnauthorized={() => navigate("/login", { replace: true })}>
      <WorkspaceProvider>
        <NavigationShell />
      </WorkspaceProvider>
    </AuthProvider>
  );
}
// ---------------------------------------------------------------------------

export const App = (): JSX.Element => (
  <ThemeProvider>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AppInner />
      </BrowserRouter>
    </QueryClientProvider>
  </ThemeProvider>
);
