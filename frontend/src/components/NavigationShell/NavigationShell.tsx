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

import { Suspense, lazy } from "react";
import { Routes, Route, Navigate, useParams } from "react-router-dom";
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
const NeedsEditors = lazy(
  () => import("../NeedsEditors/NeedsEditors")
);
const ArchitectureEditors = lazy(
  () => import("../ArchitectureEditors/ArchitectureEditors")
);
const WorkspaceSettings = lazy(
  () => import("../WorkspaceSettings/WorkspaceSettings")
);
const SystemSettings = lazy(
  () => import("../SystemSettings/SystemSettings")
);
const TraceabilityView = lazy(
  () => import("../TraceabilityView/TraceabilityView")
);
const ImpactView = lazy(() =>
  import("../ImpactView/ImpactView").then((m) => ({ default: m.ImpactView }))
);
const BaselinesView = lazy(
  () => import("../BaselinesView/BaselinesView")
);
const ReviewsView = lazy(
  () => import("../Reviews/ReviewsView")
);
const AdrEditors = lazy(() => import("../AdrEditors/AdrEditors"));
const RiskEditors = lazy(() => import("../RiskEditors/RiskEditors"));
const IssueEditors = lazy(() => import("../IssueEditors/IssueEditors"));
const TestCaseEditors = lazy(() => import("../TestCaseEditors/TestCaseEditors"));
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
const AuditDashboard = lazy(() =>
  import("../Audit/audit-dashboard").then((m) => ({ default: m.AuditDashboard }))
);
const UserProfileSettings = lazy(
  () => import("../UserProfileSettings/UserProfileSettings")
);
const GlossaryView = lazy(() => import("../GlossaryView"));
const WorkflowEditorPage = lazy(
  () => import("../WorkflowEditor/WorkflowEditorPage")
);

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
          <Suspense fallback={<div role="status">{t("loading")}</div>}>
            <Routes>
              <Route path="/" element={<DashboardViews />} />
              <Route path="/needs" element={<NeedsEditors />} />
              <Route path="/needs/:id" element={<NeedsEditors />} />
              <Route path="/requirements" element={<RequirementEditors />} />
              <Route path="/requirements/:id" element={<RequirementEditors />} />
              <Route path="/architecture" element={<ArchitectureEditors />} />
              <Route path="/architecture/:id" element={<ArchitectureEditors />} />
              <Route path="/traceability" element={<TraceabilityView />} />
              <Route path="/impact" element={<ImpactView />} />
              <Route path="/baselines" element={<BaselinesView />} />
              <Route path="/reviews" element={<ReviewsView />} />
              <Route path="/adrs" element={<AdrEditors />} />
              <Route path="/adrs/:id" element={<AdrEditors />} />
              <Route path="/risks" element={<RiskEditors />} />
              <Route path="/risks/:id" element={<RiskEditors />} />
              <Route path="/issues" element={<IssueEditors />} />
              <Route path="/issues/:id" element={<IssueEditors />} />
              <Route path="/testcases" element={<TestCaseEditors />} />
              <Route path="/testcases/:id" element={<TestCaseEditors />} />
              <Route path="/test-runs" element={<TestRunsList />} />
              <Route path="/import" element={<CsvImport />} />
              <Route path="/icds" element={<IcdView />} />
              <Route path="/icds/:id" element={<IcdView />} />
              <Route path="/diagrams" element={<DiagramView />} />
              <Route path="/diagrams/:id" element={<DiagramView />} />
              <Route path="/diagrams/:id/canvas" element={<CanvasEditorWrapper />} />
              <Route path="/diagrams/:id/mermaid" element={<MermaidEditorWrapper />} />
              <Route path="/metrics" element={<MetricsDashboard />} />
              <Route path="/audit" element={<AuditDashboard />} />
              <Route path="/settings" element={<WorkspaceSettings />} />
              <Route path="/system-settings" element={<SystemSettings />} />
              <Route
                path="/workspace-settings"
                element={<Navigate to="/settings" replace />}
              />
              <Route path="/glossary" element={<GlossaryView />} />
              <Route path="/workflows" element={<WorkflowEditorPage />} />
              <Route
                path="/workflows/:entityType"
                element={<WorkflowEditorPage />}
              />
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
