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
import { ThemeProvider } from "../../context/ThemeContext";
import type { ArchitectureElement } from "../../types";

// jsdom in this test runtime does not provide window.localStorage (Node's
// --localstorage-file experimental flag is not set), which ThemeProvider
// (now a WorkspaceProvider dependency, #568 phase 1) reads synchronously on
// mount. Polyfill a minimal in-memory implementation so it does not throw.
function installLocalStorageStub(): void {
  const store = new Map<string, string>();
  Object.defineProperty(window, "localStorage", {
    configurable: true,
    value: {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => void store.set(key, value),
      removeItem: (key: string) => void store.delete(key),
      clear: () => store.clear(),
    },
  });
}
installLocalStorageStub();

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
      <ThemeProvider>
        <WorkspaceProvider>{ui}</WorkspaceProvider>
      </ThemeProvider>
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

describe("ArchitectureForm — change control consistency (#417/#418/#422)", () => {
  it("shows a required marker on the change_reason label for the extended preset, like Requirement/StakeholderNeed", () => {
    renderWithProviders(
      <ArchitectureForm
        element={MOCK_ELEMENT}
        elements={[MOCK_ELEMENT]}
        onSaved={vi.fn()}
        onDelete={vi.fn()}
        isExtendedPreset={true}
      />
    );

    const input = screen.getByTestId("arch-change-reason-input");
    expect(input).toBeInTheDocument();
    // The label + required marker share the same <label>; querying by id
    // via getAttribute keeps this independent of the DOM structure.
    const label = document.querySelector('label[for="arch-change-reason"]');
    expect(label?.textContent).toContain("*");
  });

  it("uses the architecture-specific change_reason placeholder, not the requirement one (#418)", () => {
    renderWithProviders(
      <ArchitectureForm
        element={MOCK_ELEMENT}
        elements={[MOCK_ELEMENT]}
        onSaved={vi.fn()}
        onDelete={vi.fn()}
        isExtendedPreset={true}
      />
    );

    const input = screen.getByTestId("arch-change-reason-input");
    expect(input).toHaveAttribute("placeholder", "req.changeReasonPlaceholderArchitecture");
  });

  it("hides the change_reason field for non-extended presets", () => {
    renderWithProviders(
      <ArchitectureForm
        element={MOCK_ELEMENT}
        elements={[MOCK_ELEMENT]}
        onSaved={vi.fn()}
        onDelete={vi.fn()}
        isExtendedPreset={false}
      />
    );

    expect(screen.queryByTestId("arch-change-reason-input")).not.toBeInTheDocument();
  });

  it("renders a hint clarifying element_type is independent of the derived role (#422)", () => {
    renderWithProviders(
      <ArchitectureForm
        element={MOCK_ELEMENT}
        elements={[MOCK_ELEMENT]}
        onSaved={vi.fn()}
        onDelete={vi.fn()}
        isExtendedPreset={false}
      />
    );

    expect(screen.getByTestId("arch-element-type-hint")).toBeInTheDocument();
  });
});
