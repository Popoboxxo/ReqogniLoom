/**
 * ARCH-L1-001 ReactFrontend — Root application component.
 *
 * Placeholder scaffold. All feature components are to be implemented
 * by se-developer agents per their COMP-RF-* specifications.
 *
 * TODO(COMP-RF-001): Implement Router setup (react-router-dom).
 * TODO(COMP-RF-002): Implement Dashboard view.
 * TODO(COMP-RF-003): Implement RequirementsEditor view.
 * TODO(COMP-RF-004): Implement ArchitectureEditor view.
 * TODO(COMP-RF-005): Implement ArtifactNavigation sidebar.
 * TODO(COMP-RF-006): Implement TraceabilityView.
 * TODO(COMP-RF-007): Implement WorkspaceSettings view (Preset selector,
 *   Terminology profile — REQ-L1-007, REQ-L1-014).
 * TODO(COMP-RF-008): Implement SeMetricsDashboard (REQ-L1-031).
 *
 * Architecture: L2_ReactFrontendSystem_Architecture.md
 * Communicates exclusively with ARCH-L1-002 RestApiAdapter via REST + Bearer Token.
 */
import { useTranslation } from "react-i18next";

export const App = (): JSX.Element => {
  const { t } = useTranslation();

  return (
    <div>
      <h1>{t("app.title")}</h1>
      <p>{t("app.placeholder")}</p>
    </div>
  );
};
