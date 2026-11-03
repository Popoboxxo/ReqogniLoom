/**
 * #1596 — `/attributes` direct URL for non-admins.
 *
 * The sidebar entry is already `requires: "admin"`, but the ROUTE was not
 * guarded: a viewer who typed /attributes (or followed a bookmark) got the full
 * attribute editor, with export/import merely disabled. This spec pins the
 * routed admin gate and — as the contrast case — that an admin still sees the
 * editor unchanged.
 */
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

// Real i18next instance (DE/EN resources + interpolation), same precedent as
// AttributeEditor.test.tsx.
import { i18n } from "../i18n/index";

const getWorkspaceMock = vi.fn();
vi.mock("../api/attribute-definitions", () => ({
  attributeDefinitionsApi: {
    getWorkspace: (...args: unknown[]) => getWorkspaceMock(...args),
    getGlobal: vi.fn().mockResolvedValue(null),
    putWorkspace: vi.fn(),
    putGlobal: vi.fn(),
    resetWorkspace: vi.fn(),
    reorderWorkspace: vi.fn(),
    reorderGlobal: vi.fn(),
  },
}));

vi.mock("../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "ws-1", preset: "standard" } }),
  useOptionalWorkspace: () => ({
    activeWorkspace: { id: "ws-1", preset: "standard" },
  }),
}));

// Roles are swapped per test through this hoisted holder; the module mock
// factory runs before the imports above are evaluated.
const authState = vi.hoisted(() => ({ roles: ["viewer"] as string[] }));
vi.mock("../context/AuthContext", () => ({
  useAuth: () => authState,
}));

import { AttributeEditorPage } from "../components/AttributeEditor";

function renderRoutedPage() {
  return render(
    <MemoryRouter initialEntries={["/attributes/Requirement"]}>
      <AttributeEditorPage />
    </MemoryRouter>
  );
}

describe("AttributeEditorPage — routed admin gate (#1596)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authState.roles = ["viewer"];
    getWorkspaceMock.mockResolvedValue({
      item_type: "Requirement",
      preset: "standard",
      is_customized: false,
      version: 1,
      attributes: [],
      origins: {},
      sections: [],
    });
  });

  it("shows the admin notice instead of the editor for a viewer's direct URL", () => {
    renderRoutedPage();

    expect(screen.getByTestId("attribute-editor-admin-gate")).toBeInTheDocument();
    expect(screen.getByTestId("attribute-editor-admin-only")).toHaveTextContent(
      i18n.t("attributes.adminOnly")
    );
    // Nothing actionable from the editor is reachable.
    expect(screen.queryByTestId("attribute-editor")).not.toBeInTheDocument();
    expect(screen.queryByTestId("attribute-editor-export")).not.toBeInTheDocument();
    expect(screen.queryByTestId("attribute-editor-import")).not.toBeInTheDocument();
    expect(screen.queryByTestId("attribute-editor-entity-type")).not.toBeInTheDocument();
  });

  it("renders the editor unchanged for an admin", async () => {
    authState.roles = ["admin"];
    renderRoutedPage();

    expect(screen.queryByTestId("attribute-editor-admin-gate")).not.toBeInTheDocument();
    expect(await screen.findByTestId("attribute-editor")).toBeInTheDocument();
    expect(screen.getByTestId("attribute-editor-export")).toBeInTheDocument();
  });
});
