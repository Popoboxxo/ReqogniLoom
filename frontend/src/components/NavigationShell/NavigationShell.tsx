/**
 * ARCH-L1-001 ReactFrontend — NavigationShell (COMP-RF-001).
 *
 * leaf_id: COMP-RF-001
 * req_id:  REQ-L2-RF-005 (Artefakt-Navigation),
 *          REQ-L2-RF-007 (Preset-basierte Sichtbarkeit),
 *          REQ-L2-RF-009 (UI-Performance),
 *          REQ-L2-RF-010 (REST-API Bearer-Token auth),
 *          REQ-L2-RF-011 (Fehleranzeige),
 *          REQ-L2-RF-012 (Workspace-Konfigurations-UI),
 *          REQ-L3-RF001-001 (AuthGate),
 *          REQ-L3-RF001-002 (Preset-gesteuertes Routing),
 *          REQ-L3-RF001-003 (Error Boundary),
 *          REQ-L3-RF001-004 (Artefakt-Selektion)
 *
 * Interfaces implemented:
 *   IF-RF-EXT-IN-001  ← Browser-Nutzer
 *   IF-RF-EXT-OUT-001 → REST API (via AuthContext + API client)
 *   IF-RF-EXT-OUT-002 → Rendered Shell UI
 *   IF-RF-INT-001     → Child view activation via React Router
 *   IF-RF-INT-003     → Artifact selection passed to editors via Router state
 */

import React, { Suspense, lazy, useCallback } from "react";
import { Routes, Route, Navigate, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ErrorBoundary } from "./ErrorBoundary";
import { AuthGate } from "./AuthGate";
import { SidebarNavigation } from "./SidebarNavigation";
import { LoginPage } from "./LoginPage";

// Lazy-loaded route components for performance (REQ-L2-RF-009)
const DashboardViews = lazy(
  () => import("../DashboardViews/DashboardViews")
);
const RequirementEditors = lazy(
  () => import("../RequirementEditors/RequirementEditors")
);
const ArchitectureEditors = lazy(
  () => import("../ArchitectureEditors/ArchitectureEditors")
);
const WorkspaceSettings = lazy(
  () => import("../WorkspaceSettings/WorkspaceSettings")
);
const TraceabilityView = lazy(
  () => import("../TraceabilityView/TraceabilityView")
);
const BaselinesView = lazy(
  () => import("../BaselinesView/BaselinesView")
);
const AdrList = lazy(() => import("../AdrList/AdrList"));
const RiskList = lazy(() => import("../RiskList/RiskList"));
const IssueList = lazy(() => import("../IssueList/IssueList"));
const TestcaseList = lazy(() =>
  import("../TestCases/TestcaseList").then((m) => ({ default: m.TestcaseList }))
);
const TestRunsList = lazy(() =>
  import("../TestRuns/TestRunsList").then((m) => ({ default: m.TestRunsList }))
);
const CsvImport = lazy(() => import("../CsvImport/CsvImport"));
const IcdView = lazy(() => import("../IcdView/IcdView"));
const DiagramView = lazy(() => import("../DiagramView/DiagramView"));
const CanvasEditor = lazy(() =>
  import("../canvas/CanvasEditor").then((m) => ({ default: m.CanvasEditor }))
);
const MermaidEditor = lazy(() => import("../mermaid/MermaidEditor"));
const MetricsDashboard = lazy(
  () => import("../MetricsDashboard/MetricsDashboard")
);
const UserProfileSettings = lazy(
  () => import("../UserProfileSettings/UserProfileSettings")
);
const GlossaryView = lazy(() => import("../GlossaryView"));

// ---------------------------------------------------------------------------
// Shell layout — authenticated shell with sidebar
// ---------------------------------------------------------------------------

function AppShell(): JSX.Element {
  const { t } = useTranslation();

  return (
    <div
      style={{
        display: "flex",
        minHeight: "100vh",
        fontFamily: "sans-serif",
      }}
    >
      <SidebarNavigation />
      <main
        style={{ flex: 1, height: "100%", padding: "1.5rem", overflow: "auto" }}
        role="main"
      >
        <ErrorBoundary
          errorTitle={t("errors.generic")}
          reloadLabel={t("actions.reload")}
          backLabel={t("actions.back")}
        >
          <Suspense fallback={<div>{t("loading")}</div>}>
            <Routes>
              <Route path="/" element={<DashboardViews />} />
              <Route path="/requirements" element={<RequirementEditors />} />
              <Route path="/requirements/:id" element={<RequirementEditors />} />
              <Route path="/architecture" element={<ArchitectureEditors />} />
              <Route path="/architecture/:id" element={<ArchitectureEditors />} />
              <Route path="/traceability" element={<TraceabilityView />} />
              <Route path="/baselines" element={<BaselinesView />} />
              <Route path="/adrs" element={<AdrList />} />
              <Route path="/adrs/:id" element={<AdrList />} />
              <Route path="/risks" element={<RiskList />} />
              <Route path="/risks/:id" element={<RiskList />} />
              <Route path="/issues" element={<IssueList />} />
              <Route path="/issues/:id" element={<IssueList />} />
              <Route path="/testcases" element={<TestcaseList />} />
              <Route path="/test-runs" element={<TestRunsList />} />
              <Route path="/import" element={<CsvImport />} />
              <Route path="/icds" element={<IcdView />} />
              <Route path="/icds/:id" element={<IcdView />} />
              <Route path="/diagrams" element={<DiagramView />} />
              <Route path="/diagrams/:id" element={<DiagramView />} />
              <Route path="/diagrams/:id/canvas" element={<CanvasEditorWrapper />} />
              <Route path="/diagrams/:id/mermaid" element={<MermaidEditorWrapper />} />
              <Route path="/metrics" element={<MetricsDashboard />} />
              <Route path="/settings" element={<WorkspaceSettings />} />
              <Route path="/workspace-settings" element={<WorkspaceSettings />} />
              <Route path="/glossary" element={<GlossaryView />} />
              <Route path="/profile" element={<UserProfileSettings />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </Suspense>
        </ErrorBoundary>
      </main>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Route wrappers — extract :id param and pass to editor components
// ---------------------------------------------------------------------------

function CanvasEditorWrapper(): JSX.Element {
  const { id } = useParams<{ id: string }>();
  if (!id) return <Navigate to="/diagrams" replace />;
  return <CanvasEditor diagramId={id} />;
}

function MermaidEditorWrapper(): JSX.Element {
  const { id } = useParams<{ id: string }>();
  if (!id) return <Navigate to="/diagrams" replace />;
  return <MermaidEditor diagramId={id} />;
}

// ---------------------------------------------------------------------------
// NavigationShell — top-level router with auth gate
// ---------------------------------------------------------------------------

export function NavigationShell(): JSX.Element {
  return (
    <Routes>
      {/* Public route — no auth required */}
      <Route path="/login" element={<LoginPage />} />

      {/* All other routes require authentication (REQ-L3-RF001-001) */}
      <Route
        path="/*"
        element={
          <AuthGate>
            <AppShell />
          </AuthGate>
        }
      />
    </Routes>
  );
}
