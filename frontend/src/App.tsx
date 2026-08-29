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
 *           └── AuthProvider (session cookie restore + 401 handler)
 *                 └── ThemeProvider (palette/mode — depends on auth status)
 *                       └── WorkspaceProvider (preset + terminology)
 *                             └── NavigationShell (routes + auth gate)
 *
 * Fix (systemaudit 2026-08-29, Bug 3): ThemeProvider used to sit OUTSIDE
 * AuthProvider and fetch GET /users/me/theme-preference/,
 * GET /admin/theme-palettes/ and GET /system/theme-default/ unconditionally
 * on mount — all three require an authenticated session. On every fresh page
 * load (before the httpOnly session cookie exists, i.e. on the login page
 * itself) that guaranteed 3 doomed 401s plus a doomed single-flight
 * POST /auth/refresh/, whose retry/refresh promises could still be settling
 * around the moment the user actually completed login, making the console
 * noise look login-triggered. ThemeProvider now lives inside AuthProvider
 * and gates its fetch on `status === "authenticated"` (see ThemeContext.tsx)
 * instead of firing blind on mount.
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
      <ThemeProvider>
        <WorkspaceProvider>
          <NavigationShell />
        </WorkspaceProvider>
      </ThemeProvider>
    </AuthProvider>
  );
}
// ---------------------------------------------------------------------------

// #261: react-router-dom 7.18.2 (up from 6.30.4, CVE fix) IS the v7 default
// behavior these flags used to opt into early — `BrowserRouterProps` no
// longer accepts a `future` prop at all, so it's simply removed rather than
// replaced.

export const App = (): JSX.Element => (
  <QueryClientProvider client={queryClient}>
    <BrowserRouter>
      <AppInner />
    </BrowserRouter>
  </QueryClientProvider>
);
