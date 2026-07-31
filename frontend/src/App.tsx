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
    <AuthProvider
      onUnauthorized={() =>
        // GitHub #135: flag the redirect as a session expiry (not a manual
        // logout) so LoginPage can show a clear message instead of silently
        // dropping the user back on the login form.
        navigate("/login", { replace: true, state: { sessionExpired: true } })
      }
    >
      <WorkspaceProvider>
        <NavigationShell />
      </WorkspaceProvider>
    </AuthProvider>
  );
}
// ---------------------------------------------------------------------------

// React Router v7 future flags (Codeberg #98): opt into the upcoming v7
// defaults early so the console stays free of "future flag" warnings and the
// eventual v7 upgrade is a no-op for these two behaviors.
const ROUTER_FUTURE_FLAGS = {
  v7_startTransition: true,
  v7_relativeSplatPath: true,
};

export const App = (): JSX.Element => (
  <ThemeProvider>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter future={ROUTER_FUTURE_FLAGS}>
        <AppInner />
      </BrowserRouter>
    </QueryClientProvider>
  </ThemeProvider>
);
