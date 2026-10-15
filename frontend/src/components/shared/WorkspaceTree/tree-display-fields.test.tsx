/**
 * Issue #1257 â€” the navigation tree renders the *configured* field selection.
 *
 * Two halves are pinned here:
 *   1. `WorkspaceTree`'s own default row honours the selection (identifier,
 *      level badge, status badge, `updated_at`);
 *   2. a `<ArtifactRow>` rendered through the tree's `renderRow` slot honours
 *      the same selection, because the tree publishes it through
 *      `TreeDisplayFieldsProvider` â€” otherwise hiding a field in the tree would
 *      leave it visible in every artifact list row.
 *
 * The pre-#1257 combination (`uid`, `level`, `status`, `updated_at`,
 * `version`) is the default, so the first test also pins "an unconfigured tree
 * is unchanged".
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import type { ComponentProps } from "react";

import { ArtifactRow } from "../ArtifactRow/ArtifactRow";
import {
  resetTreeDisplayFields,
  setTreeDisplayFields,
} from "../../../hooks/useTreeDisplayFields";
import { WorkspaceTree } from "./workspace-tree";
import type { WorkspaceTreeNode } from "./workspace-tree";

// The tree resolves its own labels through i18n; echoing the key back keeps the
// assertions independent of the locale files (repo-wide test convention).
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

// The loader must never touch the network in a unit test. It resolves never
// (rather than to a value) on purpose: the selection under test is seeded
// directly into the store, and a resolved request would update the tree
// asynchronously and warn about an unwrapped `act`. Behaviour of the store and
// loader themselves is covered by `hooks/useTreeDisplayFields.test.ts`.
vi.mock("../../../api/tree-display-config", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("../../../api/tree-display-config")>();
  return {
    ...actual,
    treeDisplayConfigApi: {
      getEffective: vi.fn(() => new Promise(() => {})),
      getScope: vi.fn(),
      set: vi.fn(),
    },
  };
});

// Issue #1094's readable-id preference is a module store too; keep it at its
// default (visible) so this file only exercises the #1257 selection.
vi.mock("../../../hooks/useReadableIdsVisible", () => ({
  useReadableIdsVisible: () => [true, vi.fn()],
}));

const NODES: WorkspaceTreeNode[] = [
  {
    id: "n1",
    name: "Alpha",
    parentId: null,
    identifier: "REQ-001",
    level: "L1",
    updatedAt: "2026-10-01",
    badge: { text: "SR", bg: "var(--color-surface-raised)", color: "var(--color-text)" },
  },
];

function renderTree(props: Partial<ComponentProps<typeof WorkspaceTree>> = {}) {
  return render(
    <WorkspaceTree
      nodes={NODES}
      onSelect={vi.fn()}
      showLevelBadge
      data-testid="tree"
      {...props}
    />
  );
}

describe("WorkspaceTree â€” configured display fields (#1257)", () => {
  beforeEach(() => resetTreeDisplayFields());
  afterEach(() => resetTreeDisplayFields());

  it("renders the pre-#1257 combination when nothing is configured", () => {
    renderTree();

    expect(screen.getByTestId("tree-identifier-n1")).toHaveTextContent("REQ-001");
    expect(screen.getByTestId("tree-level-n1")).toBeInTheDocument();
    expect(screen.getByTestId("tree-badge-n1")).toBeInTheDocument();
    expect(screen.getByTestId("tree-updated-n1")).toHaveTextContent("2026-10-01");
  });

  it("renders only the configured fields", () => {
    setTreeDisplayFields("Requirement", ["updated_at", "uid"]);

    renderTree({ itemType: "Requirement" });

    expect(screen.getByTestId("tree-identifier-n1")).toBeInTheDocument();
    expect(screen.getByTestId("tree-updated-n1")).toBeInTheDocument();
    // `level` and `status` are not part of the selection.
    expect(screen.queryByTestId("tree-level-n1")).not.toBeInTheDocument();
    expect(screen.queryByTestId("tree-badge-n1")).not.toBeInTheDocument();
  });

  it("renders no fields at all for an explicitly empty selection", () => {
    setTreeDisplayFields("Requirement", []);

    renderTree({ itemType: "Requirement" });

    expect(screen.queryByTestId("tree-identifier-n1")).not.toBeInTheDocument();
    expect(screen.queryByTestId("tree-level-n1")).not.toBeInTheDocument();
    expect(screen.queryByTestId("tree-badge-n1")).not.toBeInTheDocument();
    expect(screen.queryByTestId("tree-updated-n1")).not.toBeInTheDocument();
    // The row itself (name) always stays â€” this is a tree, not a blank list.
    expect(screen.getByText("Alpha")).toBeInTheDocument();
  });

  it("ignores another item type's selection", () => {
    setTreeDisplayFields("Adr", []);

    renderTree({ itemType: "Requirement" });

    expect(screen.getByTestId("tree-identifier-n1")).toBeInTheDocument();
  });

  it("publishes the selection to an ArtifactRow rendered as a row", () => {
    setTreeDisplayFields("Requirement", ["uid"]);

    renderTree({
      itemType: "Requirement",
      renderRow: () => (
        <ArtifactRow
          title="Alpha"
          id="REQ-001"
          systemId="11111111-1111-1111-1111-111111111111"
          levelLabel="L1"
          status="approved"
          version={3}
          testId="row"
        />
      ),
    });

    // `uid` is configured â†’ the identity chip stays.
    expect(screen.getByTestId("row-id")).toBeInTheDocument();
    // Everything else is not.
    expect(screen.queryByTestId("row-level")).not.toBeInTheDocument();
    expect(screen.queryByTestId("row-status")).not.toBeInTheDocument();
    expect(screen.queryByText("v3")).not.toBeInTheDocument();
  });

  it("leaves an ArtifactRow outside a tree fully visible", () => {
    setTreeDisplayFields("Requirement", []);

    render(
      <ArtifactRow
        title="Alpha"
        id="REQ-001"
        systemId="11111111-1111-1111-1111-111111111111"
        levelLabel="L1"
        status="approved"
        testId="lone-row"
      />
    );

    expect(screen.getByTestId("lone-row-id")).toBeInTheDocument();
    expect(screen.getByTestId("lone-row-level")).toBeInTheDocument();
    expect(screen.getByTestId("lone-row-status")).toBeInTheDocument();
  });

  it("keeps the version badge visible under the default selection", () => {
    // Regression guard: `version` is part of the pre-#1257 combination, so an
    // unconfigured list must not lose the v2+ badge it rendered before #1257.
    renderTree({
      itemType: "Requirement",
      renderRow: () => (
        <ArtifactRow
          title="Alpha"
          id="REQ-001"
          systemId="11111111-1111-1111-1111-111111111111"
          status="approved"
          version={3}
          testId="row"
        />
      ),
    });

    expect(screen.getByText("v3")).toBeInTheDocument();
  });
});
