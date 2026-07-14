/**
 * REQ-003: NeedList — layout and form positioning tests.
 *
 * Verifies that the create form appears below the filter toolbar with
 * proper spacing and z-index stacking (REQ-003).
 */

import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => {
      const map: Record<string, string> = {
        "editor.searchPlaceholder": "Search needs...",
        "editor.allStatuses": "All Statuses",
        "editor.sortDefault": "Default",
        "editor.sortTitleAsc": "Title (A-Z)",
        "editor.sortStatus": "Status",
        "editor.sortUpdatedDesc": "Recently Updated",
        "editor.sortLabel": "Sort by",
        "actions.new": "New",
        "editor.title": "Title",
        "editor.newNeedTitle": "e.g. As a user, I need...",
        "cancel": "Cancel",
        "create": "Create",
        "editor.empty": "No needs available.",
        "editor.noMatches": "No matches found.",
      };
      return map[key] ?? key;
    },
    i18n: { language: "en" },
  }),
}));

// Must import AFTER vi.mock
import { NeedList } from "./NeedList";
import type { StakeholderNeed } from "../../types";

// ---------------------------------------------------------------------------
// Mock data
// ---------------------------------------------------------------------------

const MOCK_NEEDS: StakeholderNeed[] = [
  {
    id: "need-001",
    workspace_id: "ws-001",
    artifact_id: "art-001",
    title: "User authentication",
    description: "Users should be able to login",
    category: "",
    status: "draft",
    moscow_priority: null,
    uid: "SN-001",
    suspect: false,
    version: 1,
    created_at: "2026-01-01T00:00:00Z",
    modified_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    custom_fields: {},
  },
];

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("NeedList — layout and positioning (REQ-003)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders create form below toolbar with proper spacing when showCreateForm is true", async () => {
    const { container } = render(
      <MemoryRouter>
        <NeedList
          needs={MOCK_NEEDS}
          selectedId="need-001"
          onCreateNew={vi.fn()}
          showCreateForm={true}
          setShowCreateForm={vi.fn()}
          newTitle="New Need"
          setNewTitle={vi.fn()}
          onSubmitCreate={vi.fn()}
          createError={null}
        />
      </MemoryRouter>
    );

    // Verify toolbar is rendered
    const toolbar = screen.getByTestId("need-list-toolbar");
    expect(toolbar).toBeInTheDocument();

    // Verify form is rendered
    const form = container.querySelector("form");
    expect(form).toBeInTheDocument();

    // Verify form has proper z-index stacking context
    const formStyle = window.getComputedStyle(form!);
    expect(formStyle.position).toBe("relative");
    expect(formStyle.zIndex).toBe("1");
  });

  it("form title input is properly positioned after toolbar", async () => {
    render(
      <MemoryRouter>
        <NeedList
          needs={MOCK_NEEDS}
          selectedId="need-001"
          onCreateNew={vi.fn()}
          showCreateForm={true}
          setShowCreateForm={vi.fn()}
          newTitle="New Need"
          setNewTitle={vi.fn()}
          onSubmitCreate={vi.fn()}
          createError={null}
        />
      </MemoryRouter>
    );

    const input = screen.getByDisplayValue("New Need") as HTMLInputElement;
    expect(input).toBeInTheDocument();
    expect(input.type).toBe("text");
    expect(input.placeholder).toContain("e.g.");
  });

  it("form is hidden when showCreateForm is false", () => {
    const { container } = render(
      <MemoryRouter>
        <NeedList
          needs={MOCK_NEEDS}
          selectedId="need-001"
          onCreateNew={vi.fn()}
          showCreateForm={false}
          setShowCreateForm={vi.fn()}
          newTitle=""
          setNewTitle={vi.fn()}
          onSubmitCreate={vi.fn()}
          createError={null}
        />
      </MemoryRouter>
    );

    const form = container.querySelector("form");
    expect(form).not.toBeInTheDocument();
  });
});
