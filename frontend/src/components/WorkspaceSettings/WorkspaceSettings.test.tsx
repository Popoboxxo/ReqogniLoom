/**
 * Tests for WorkspaceSettings tab structure (REQ-015).
 *
 * Verifies the settings surface is organised into tabs and that switching a tab
 * swaps the visible panel while preserving the existing controls' data-testids.
 * Child sections and contexts are stubbed so the test isolates the tab shell.
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import WorkspaceSettings from "./WorkspaceSettings";
import { workspacesApi } from "../../api/workspaces";

vi.mock("react-i18next", () => {
  const t = (_key: string, fallback?: unknown): string =>
    typeof fallback === "string" ? fallback : _key;
  return { useTranslation: () => ({ t }) };
});

const { mockSearchParams } = vi.hoisted(() => ({
  mockSearchParams: { current: new URLSearchParams() },
}));

vi.mock("react-router-dom", () => ({
  useNavigate: () => vi.fn(),
  useSearchParams: () => [mockSearchParams.current],
}));

const activeWorkspace = {
  id: "ws-1",
  name: "Demo Workspace",
  preset: "standard",
  terminology_profile: "dev_mode",
  language: "de",
  theme: "dark",
  decomposition_link_type: "parent-child",
  is_active: true,
};

vi.mock("../../context/WorkspaceContext", () => ({
  useWorkspace: () => ({
    activeWorkspace,
    reloadWorkspaces: vi.fn(),
    isFeatureVisible: () => true,
  }),
}));

vi.mock("../../context/AuthContext", () => ({
  useAuth: () => ({ roles: ["admin"] }),
}));

vi.mock("../../context/ThemeContext", () => ({
  useTheme: () => ({ setTheme: vi.fn() }),
  THEMES: [
    { id: "dark", labelKey: "nav.darkMode" },
    { id: "light", labelKey: "nav.lightMode" },
  ],
}));

vi.mock("../../api/workspaces", () => ({
  workspacesApi: {
    update: vi.fn().mockResolvedValue({}),
    setPreset: vi.fn().mockResolvedValue({}),
    clone: vi.fn().mockResolvedValue({ id: "ws-2" }),
    closeWorkspace: vi.fn().mockResolvedValue({}),
    reactivateWorkspace: vi.fn().mockResolvedValue({}),
    deleteWorkspace: vi.fn().mockResolvedValue({}),
  },
}));

vi.mock("../../i18n/index", () => ({ i18n: { changeLanguage: vi.fn() } }));

// Stub child sections so their own effects/api calls do not run here.
vi.mock("./WorkflowPermissionsSection", () => ({
  WorkflowPermissionsSection: () => <div data-testid="stub-workflow-permissions" />,
}));
vi.mock("./PermissionsSection", () => ({
  PermissionsSection: () => <div data-testid="stub-permissions" />,
}));
vi.mock("./LlmSettingsSection", () => ({
  LlmSettingsSection: () => <div data-testid="stub-llm" />,
}));
vi.mock("./AiPromptsSection", () => ({
  AiPromptsSection: () => <div data-testid="stub-prompts" />,
}));
vi.mock("../AdminDialog/AttributeVisibilityAdmin", () => ({
  AttributeVisibilityAdmin: () => <div data-testid="stub-visibility" />,
}));

// Stub CustomFieldsSection (REQ-016) to prevent api calls in unit tests.
vi.mock("./CustomFieldsSection", () => ({
  CustomFieldsSection: () => <div data-testid="stub-custom-fields" />,
}));

// Stub McpConnectionSection — it renders a router <Link>, which the stubbed
// react-router-dom above does not provide. Covered by its own test file.
vi.mock("./McpConnectionSection", () => ({
  McpConnectionSection: () => <div data-testid="stub-mcp-connection" />,
}));

describe("WorkspaceSettings tabs (REQ-015)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockSearchParams.current = new URLSearchParams();
  });

  it("renders the workspace-scoped tabs and shows the General tab by default", () => {
    render(<WorkspaceSettings />);
    for (const id of ["general", "traceability", "visibility", "llm", "workflows-permissions"]) {
      expect(screen.getByTestId(`settings-tab-${id}`)).toBeInTheDocument();
    }
    // The Administration tab relocated to System Settings (REQ-184) — gone here.
    expect(screen.queryByTestId("settings-tab-admin")).not.toBeInTheDocument();
    // General panel is active initially.
    expect(screen.getByTestId("settings-tab-general")).toHaveAttribute("aria-selected", "true");
    expect(screen.getByTestId("workspace-name-input")).toBeInTheDocument();
    // A control from another tab is not mounted.
    expect(screen.queryByTestId("decomposition-link-type-select")).not.toBeInTheDocument();
  });

  // Regression test for the WCAG 4.1.2/3.3.2 fix: the name field must be
  // queryable via its accessible name (aria-labelledby -> the "Workspace
  // Name" heading), not just visually adjacent to it.
  it("a11y: the workspace-name field is queryable by its accessible name", () => {
    render(<WorkspaceSettings />);
    expect(screen.getByLabelText("Workspace Name")).toBe(screen.getByTestId("workspace-name-input"));
  });

  it("#609: opens directly on the LLM tab when deep-linked via ?tab=llm", () => {
    mockSearchParams.current = new URLSearchParams("tab=llm");
    render(<WorkspaceSettings />);

    expect(screen.getByTestId("settings-tab-llm")).toHaveAttribute("aria-selected", "true");
    expect(screen.queryByTestId("workspace-name-input")).not.toBeInTheDocument();
  });

  it("#609: falls back to the General tab for an unknown ?tab= value", () => {
    mockSearchParams.current = new URLSearchParams("tab=not-a-real-tab");
    render(<WorkspaceSettings />);

    expect(screen.getByTestId("settings-tab-general")).toHaveAttribute("aria-selected", "true");
  });

  it("lets an admin change the workspace-default theme (#568)", async () => {
    render(<WorkspaceSettings />);
    await userEvent.click(screen.getByTestId("theme-option-light"));
    expect(workspacesApi.update).toHaveBeenCalledWith("ws-1", { theme: "light" });
  });

  it("shows the rebuilt Workflows & Permissions tab (SCR-202)", async () => {
    render(<WorkspaceSettings />);
    await userEvent.click(screen.getByTestId("settings-tab-workflows-permissions"));

    expect(screen.getByTestId("settings-tab-workflows-permissions")).toHaveAttribute("aria-selected", "true");
    expect(screen.getByTestId("stub-workflow-permissions")).toBeInTheDocument();
    expect(screen.getByTestId("stub-permissions")).toBeInTheDocument();
  });

  it("switches to the Traceability tab and swaps the visible controls", async () => {
    render(<WorkspaceSettings />);
    await userEvent.click(screen.getByTestId("settings-tab-traceability"));

    expect(screen.getByTestId("settings-tab-traceability")).toHaveAttribute("aria-selected", "true");
    expect(screen.getByTestId("decomposition-link-type-select")).toBeInTheDocument();
    expect(screen.getByTestId("default-link-type-select")).toBeInTheDocument();
    expect(screen.queryByTestId("workspace-name-input")).not.toBeInTheDocument();
  });

  it("renders the LLM and prompt sections together on the LLM tab", async () => {
    render(<WorkspaceSettings />);
    await userEvent.click(screen.getByTestId("settings-tab-llm"));

    expect(screen.getByTestId("stub-llm")).toBeInTheDocument();
    expect(screen.getByTestId("stub-prompts")).toBeInTheDocument();
  });

  it("disables the save button when the name is emptied", () => {
    render(<WorkspaceSettings />);
    const input = screen.getByTestId("workspace-name-input");
    fireEvent.change(input, { target: { value: "" } });
    expect(screen.getByTestId("workspace-name-save")).toBeDisabled();
  });

  it("disables the save button when the name is only whitespace", () => {
    render(<WorkspaceSettings />);
    const input = screen.getByTestId("workspace-name-input");
    fireEvent.change(input, { target: { value: "   " } });
    expect(screen.getByTestId("workspace-name-save")).toBeDisabled();
  });
});
