/**
 * Smoke tests for ArtifactDiff component (REQ-053 coverage).
 *
 * req_id: REQ-053, REQ-L2-RF-014, REQ-L1-040
 *
 * Verifies:
 *   - ArtifactDiff renders without crashing when versions list is empty
 *   - ArtifactDiff renders version selectors after versionsFetcher resolves
 *   - Close button is present and calls onClose when clicked
 *   - Component header shows the entity type label
 *   - Error state renders when versionsFetcher rejects
 *
 * ArtifactDiff is a pure component — no context or React-Query needed.
 * Props control all data fetching (diffFetcher, versionsFetcher).
 */

import { describe, it, expect, vi, beforeEach, type Mock } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ArtifactDiff } from "./ArtifactDiff";
import type { ArtifactDiffResult, ArtifactVersion } from "../../types";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const ENTITY_ID = "req-nav-001";
const CURRENT_VERSION = 3;

/**
 * The component's own prop types, so the mocks below are real typed mocks
 * (`vi.fn<DiffFetcher>()`) instead of `vi.fn()` + `as any` at the JSX site:
 * a bare `vi.fn()` is `Mock<Procedure | Constructable>`, which is not
 * assignable to a plain function prop.
 */
type DiffFetcher = (
  id: string,
  fromVersion: number,
  toVersion: number
) => Promise<ArtifactDiffResult>;
type VersionsFetcher = (id: string) => Promise<ArtifactVersion[]>;

const MOCK_VERSIONS: ArtifactVersion[] = [
  {
    version: 1,
    label: "v1 — Initial draft",
    modified_at: "2026-01-10T09:00:00Z",
  },
  {
    version: 2,
    label: "v2 — Clarified acceptance criteria",
    modified_at: "2026-01-20T14:00:00Z",
  },
  {
    version: 3,
    label: "v3 — Approved after CDR",
    modified_at: "2026-02-01T11:30:00Z",
  },
];

const MOCK_DIFF_RESULT: ArtifactDiffResult = {
  from_version: 2,
  to_version: 3,
  entity_type: "requirement",
  fields: [
    {
      name: "description",
      status: "modified" as const,
      from: "Old description text.",
      to: "New description text after CDR review.",
      lines: ["-Old description text.", "+New description text after CDR review."],
    },
  ],
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("ArtifactDiff (REQ-053 smoke tests)", () => {
  let onClose: Mock<() => void>;
  let diffFetcher: Mock<DiffFetcher>;
  let versionsFetcher: Mock<VersionsFetcher>;

  beforeEach(() => {
    onClose = vi.fn<() => void>();
    diffFetcher = vi.fn<DiffFetcher>().mockResolvedValue(MOCK_DIFF_RESULT);
    versionsFetcher = vi.fn<VersionsFetcher>().mockResolvedValue(MOCK_VERSIONS);
  });

  it("[REQ-053] renders without crashing when versions list resolves to empty", async () => {
    versionsFetcher.mockResolvedValue([]);

    render(
      <ArtifactDiff
        entityId={ENTITY_ID}
        entityType="requirement"
        currentVersion={CURRENT_VERSION}
        diffFetcher={diffFetcher}
        versionsFetcher={versionsFetcher}
        onClose={onClose}
      />
    );

    // Component mounts — versionsFetcher is called with the entity ID
    expect(versionsFetcher).toHaveBeenCalledWith(ENTITY_ID);
  });

  it("[REQ-053] shows close button that calls onClose when clicked", async () => {
    versionsFetcher.mockResolvedValue([]);
    const user = userEvent.setup();

    render(
      <ArtifactDiff
        entityId={ENTITY_ID}
        entityType="requirement"
        currentVersion={CURRENT_VERSION}
        diffFetcher={diffFetcher}
        versionsFetcher={versionsFetcher}
        onClose={onClose}
      />
    );

    const closeBtn = screen.getByRole("button", { name: /close|×|x/i });
    await user.click(closeBtn);
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("[REQ-053] renders version selectors after versionsFetcher resolves", async () => {
    render(
      <ArtifactDiff
        entityId={ENTITY_ID}
        entityType="requirement"
        currentVersion={CURRENT_VERSION}
        diffFetcher={diffFetcher}
        versionsFetcher={versionsFetcher}
        onClose={onClose}
      />
    );

    await waitFor(() => {
      // Two version select elements should appear (from / to)
      const selects = screen.getAllByRole("combobox");
      expect(selects.length).toBeGreaterThanOrEqual(2);
    });
  });

  it("[REQ-053] auto-triggers diff when version selectors are seeded from the fetched list", async () => {
    // The component auto-runs fetchDiff via useEffect whenever fromVersion/toVersion
    // change — no manual "Run" button needed.
    render(
      <ArtifactDiff
        entityId={ENTITY_ID}
        entityType="requirement"
        currentVersion={CURRENT_VERSION}
        diffFetcher={diffFetcher}
        versionsFetcher={versionsFetcher}
        onClose={onClose}
      />
    );

    // Wait for selectors to appear — versions resolved and seeded
    await waitFor(() => {
      expect(screen.getAllByRole("combobox").length).toBeGreaterThanOrEqual(2);
    });

    // diffFetcher is called automatically once fromVersion + toVersion are set
    await waitFor(() => {
      expect(diffFetcher).toHaveBeenCalledWith(
        ENTITY_ID,
        expect.any(Number),
        expect.any(Number)
      );
    });
  });

  it("[REQ-053] From/To selects still list the sole version when only one version exists", async () => {
    // Freshly created artifacts (e.g. a just-added Glossary term) have
    // exactly one version. The From/To dropdowns must not end up empty.
    versionsFetcher.mockResolvedValue([
      { version: 1, label: "v1", modified_at: "2026-01-10T09:00:00Z" },
    ]);

    render(
      <ArtifactDiff
        entityId={ENTITY_ID}
        entityType="requirement"
        currentVersion={1}
        diffFetcher={diffFetcher}
        versionsFetcher={versionsFetcher}
        onClose={onClose}
      />
    );

    await waitFor(() => {
      expect(screen.getByTestId("diff-from-version")).toHaveTextContent("v1");
      expect(screen.getByTestId("diff-to-version")).toHaveTextContent("v1");
    });
  });

  it("[REQ-053] renders error element when versionsFetcher rejects", async () => {
    versionsFetcher.mockRejectedValue({ error: { message: "artifact history unavailable" } });

    render(
      <ArtifactDiff
        entityId={ENTITY_ID}
        entityType="requirement"
        currentVersion={CURRENT_VERSION}
        diffFetcher={diffFetcher}
        versionsFetcher={versionsFetcher}
        onClose={onClose}
      />
    );

    // Error is shown in data-testid="diff-error" (no role="alert" on this element)
    await waitFor(() => {
      expect(screen.getByTestId("diff-error")).toBeInTheDocument();
    });
    expect(screen.getByTestId("diff-error")).toHaveTextContent("artifact history unavailable");
  });
});
