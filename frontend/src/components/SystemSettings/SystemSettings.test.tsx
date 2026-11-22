/**
 * Issue #1968 — the tenant-global prompt editors live in System Settings,
 * behind the page's admin gate. Workspace Settings must not offer Global.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import SystemSettings from "./SystemSettings";

const { state } = vi.hoisted(() => ({ state: { roles: ["admin"] as string[] } }));

vi.mock("../../context/AuthContext", () => ({
  useAuth: () => ({ roles: state.roles }),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: string) => fallback ?? key,
  }),
}));

// The tab shell is what is under test — every section it hosts is irrelevant
// here, so stub them all rather than pulling in their API/context graphs.
vi.mock("../WorkflowEditor/WorkflowEditorPage", () => ({
  WorkflowEditorPage: () => null,
}));
vi.mock("../AttributeEditor", () => ({ AttributeEditorPage: () => null }));
vi.mock("./WorkspaceAdminSection", () => ({ WorkspaceAdminSection: () => null }));
vi.mock("./BannerSection", () => ({ BannerSection: () => null }));
vi.mock("./ThemeManagementSection", () => ({ ThemeManagementSection: () => null }));
vi.mock("./PermissionDefaultsTab", () => ({ PermissionDefaultsTab: () => null }));
vi.mock("./MemoryManagementSection", () => ({ MemoryManagementSection: () => null }));
vi.mock("./MemorySystemSettingsSection", () => ({
  MemorySystemSettingsSection: () => null,
}));
vi.mock("./ArtifactVectorSettingsSection", () => ({
  ArtifactVectorSettingsSection: () => null,
}));
vi.mock("./MemoryVisualizationSection", () => ({
  MemoryVisualizationSection: () => null,
}));
vi.mock("./TreeDisplaySection", () => ({ TreeDisplaySection: () => null }));
vi.mock("./CreateFormSection", () => ({ CreateFormSection: () => null }));
vi.mock("../shared/PreferenceLevelSection/PreferenceLevelSection", () => ({
  PreferenceLevelSection: () => null,
}));
vi.mock("../shared/PageHeader", () => ({
  PageHeader: ({ title }: { title: string }) => <div>{title}</div>,
}));
vi.mock("../shared/ConfirmDialog", () => ({ ConfirmDialog: () => null }));
vi.mock("../WorkspaceSettings/AiPromptsSection", () => ({
  AiPromptsSection: ({
    scope,
    canEdit,
  }: {
    scope?: string;
    canEdit?: boolean;
  }) => (
    <div
      data-testid="stub-global-ai-prompts"
      data-scope={scope}
      data-can-edit={String(canEdit)}
    />
  ),
}));
vi.mock("../WorkspaceSettings/PromptVariablesSection", () => ({
  PromptVariablesSection: ({
    scope,
    canEdit,
  }: {
    scope?: string;
    canEdit?: boolean;
  }) => (
    <div
      data-testid="stub-global-prompt-variables"
      data-scope={scope}
      data-can-edit={String(canEdit)}
    />
  ),
}));

function renderSystemSettings(tab?: string): void {
  render(
    <MemoryRouter initialEntries={[`/system${tab ? `?tab=${tab}` : ""}`]}>
      <SystemSettings />
    </MemoryRouter>
  );
}

describe("SystemSettings — global prompts tab (#1968)", () => {
  beforeEach(() => {
    state.roles = ["admin"];
  });

  it("owns the global scope for both prompt editors", () => {
    renderSystemSettings("prompts");

    expect(
      screen.getByTestId("system-settings-tab-prompts")
    ).toBeInTheDocument();
    expect(screen.getByTestId("system-prompts")).toBeInTheDocument();

    const prompts = screen.getByTestId("stub-global-ai-prompts");
    const variables = screen.getByTestId("stub-global-prompt-variables");
    expect(prompts).toHaveAttribute("data-scope", "global");
    expect(variables).toHaveAttribute("data-scope", "global");
    // The page is admin-gated, so the editors are explicitly writable here.
    expect(prompts).toHaveAttribute("data-can-edit", "true");
    expect(variables).toHaveAttribute("data-can-edit", "true");
  });

  it("hides the whole system surface — including the global tab — from non-admins", () => {
    state.roles = ["viewer"];
    renderSystemSettings("prompts");

    expect(screen.getByText("systemSettings.adminOnly")).toBeInTheDocument();
    expect(
      screen.queryByTestId("system-settings-tab-prompts")
    ).not.toBeInTheDocument();
    expect(screen.queryByTestId("system-prompts")).not.toBeInTheDocument();
  });
});
