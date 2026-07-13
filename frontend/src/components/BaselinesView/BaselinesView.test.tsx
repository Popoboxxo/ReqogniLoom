/**
 * BaselinesView.test.tsx
 *
 * Unit tests for the DiffItemRow sub-component (REQ-006).
 *
 * Covers:
 *   - Renders backend-supplied artifact_name instead of the raw UUID
 *   - Falls back to truncated item_id when artifact_name is null/absent
 *   - data-testid="diff-item-name" is present in both cases (E2E contract)
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { DiffItemRow } from "./BaselinesView";
import type { DiffItem } from "../../api/baselines";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string, fallback?: string) => fallback ?? key }),
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const ITEM_ID = "aaaaaaaa-0000-0000-0000-000000000001";

function makeDiffItem(overrides: Partial<DiffItem> = {}): DiffItem {
  return {
    item_id: ITEM_ID,
    entity_type: "item",
    status: "changed",
    field_changes: null,
    artifact_name: "Login must succeed",
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("DiffItemRow (REQ-006)", () => {
  it("displays backend-supplied artifact_name instead of the UUID", () => {
    const item = makeDiffItem();
    render(
      <ul>
        <DiffItemRow item={item} />
      </ul>
    );

    expect(screen.getByTestId("diff-item-name")).toHaveTextContent(
      "Login must succeed"
    );
  });

  it("falls back to truncated item_id when artifact_name is null", () => {
    const item = makeDiffItem({ artifact_name: null });
    render(
      <ul>
        <DiffItemRow item={item} />
      </ul>
    );

    expect(screen.getByTestId("diff-item-name")).toHaveTextContent(
      `${ITEM_ID.slice(0, 8)}…`
    );
  });

  it("falls back to truncated item_id when artifact_name is absent", () => {
    const { artifact_name, ...rest } = makeDiffItem();
    const item = rest as DiffItem;
    render(
      <ul>
        <DiffItemRow item={item} />
      </ul>
    );

    expect(screen.getByTestId("diff-item-name")).toHaveTextContent(
      `${ITEM_ID.slice(0, 8)}…`
    );
  });
});
