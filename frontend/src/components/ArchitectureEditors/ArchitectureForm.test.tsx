/**
 * Unit tests for ArchitectureForm — button integration for AI Decompose.
 *
 * Verifies:
 *   - "AI Decompose" button is hidden when onDecompose is not provided
 *   - "AI Decompose" button is visible when onDecompose is provided
 *   - Button click triggers the onDecompose callback
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ArchitectureForm } from "./ArchitectureForm";
import { AuthProvider } from "../../context/AuthContext";
import { WorkspaceProvider } from "../../context/WorkspaceContext";
import type { ArchitectureElement } from "../../types";

vi.mock("react-i18next", () => {
  const t = (key: string): string => key;
  return { useTranslation: () => ({ t }) };
});

vi.mock("../../context/EntityTypeContext", () => ({
  useEntityType: () => ({ visibleFields: {} }),
  EntityTypeProvider: ({ children }: { children: React.ReactNode }) => children,
}));

vi.mock("../../api/architecture");
// ArchitectureForm renders MarkdownPreview, which calls useWorkspace() — the
// WorkspaceProvider in turn depends on AuthProvider/apiClient (auth bootstrap)
// and workspacesApi (both routed through apiClient.get). Mock apiClient here,
// matching the pattern in frontend/src/test/ArchitectureEditors.test.tsx.
vi.mock("../../api/client", () => ({
  extractErrorMessage: vi.fn((err: unknown) => String(err)),
  setAuthToken: vi.fn(),
  setUnauthorizedHandler: vi.fn(),
  apiClient: {
    get: vi.fn((path?: string) =>
      Promise.resolve(
        path === "/auth/me/"
          ? {
              user: {
                id: "u-1",
                username: "tester",
                email: "t@x.test",
                first_name: "",
                last_name: "",
                is_active: true,
                tenant_id: "t-1",
                roles: ["admin"],
              },
              tenant_id: "t-1",
              roles: ["admin"],
            }
          : {}
      )
    ),
    post: vi.fn().mockResolvedValue({}),
    put: vi.fn().mockResolvedValue({}),
    patch: vi.fn().mockResolvedValue({}),
    delete: vi.fn().mockResolvedValue({}),
  },
}));

function renderWithProviders(ui: React.ReactElement): ReturnType<typeof render> {
  return render(
    <AuthProvider>
      <WorkspaceProvider>{ui}</WorkspaceProvider>
    </AuthProvider>
  );
}

const MOCK_ELEMENT: ArchitectureElement = {
  id: "arch-123",
  workspace_id: "ws-001",
  title: "Navigation System",
  description: "GPS and positioning",
  element_type: "subsystem",
  parent_id: null,
  level: 1,
  role: "subsystem",
  version: 1,
  lifecycle_status: "active",
  uid: "NAV-SYS-001",
  asil_level: null,
  make_or_buy: null,
  change_reason: undefined,
  custom_fields: {},
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

describe("ArchitectureForm — AI Decompose button", () => {
  it("hides decompose button when onDecompose is not provided", () => {
    renderWithProviders(
      <ArchitectureForm
        element={MOCK_ELEMENT}
        elements={[MOCK_ELEMENT]}
        onSaved={vi.fn()}
        onDelete={vi.fn()}
        isExtendedPreset={false}
      />
    );

    expect(screen.queryByTestId("arch-decompose-btn")).not.toBeInTheDocument();
  });

  it("shows decompose button when onDecompose is provided", () => {
    renderWithProviders(
      <ArchitectureForm
        element={MOCK_ELEMENT}
        elements={[MOCK_ELEMENT]}
        onSaved={vi.fn()}
        onDelete={vi.fn()}
        isExtendedPreset={false}
        onDecompose={vi.fn()}
      />
    );

    expect(screen.getByTestId("arch-decompose-btn")).toBeInTheDocument();
    expect(screen.getByTestId("arch-decompose-btn")).toHaveTextContent(
      "archDecompose.trigger"
    );
  });

  it("calls onDecompose when button is clicked", async () => {
    const handleDecompose = vi.fn();
    const user = userEvent.setup();

    renderWithProviders(
      <ArchitectureForm
        element={MOCK_ELEMENT}
        elements={[MOCK_ELEMENT]}
        onSaved={vi.fn()}
        onDelete={vi.fn()}
        isExtendedPreset={false}
        onDecompose={handleDecompose}
      />
    );

    const button = screen.getByTestId("arch-decompose-btn");
    await user.click(button);

    expect(handleDecompose).toHaveBeenCalledTimes(1);
  });
});
