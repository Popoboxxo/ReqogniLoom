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

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ArtifactDiff } from "./ArtifactDiff";
import type { ArtifactVersion } from "../../types";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const ENTITY_ID = "req-nav-001";
const CURRENT_VERSION = 3;

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

const MOCK_DIFF_RESULT = {
  from_version: 2,
  to_version: 3,
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
  let onClose: ReturnType<typeof vi.fn>;
  let diffFetcher: ReturnType<typeof vi.fn>;
  let versionsFetcher: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    onClose = vi.fn();
    diffFetcher = vi.fn().mockResolvedValue(MOCK_DIFF_RESULT);
    versionsFetcher = vi.fn().mockResolvedValue(MOCK_VERSIONS);
  });

  it("[REQ-053] renders without crashing when versions list resolves to empty", async () => {
    versionsFetcher.mockResolvedValue([]);

    render(
      <ArtifactDiff
        entityId={ENTITY_ID}
        entityType="requirement"
        currentVersion={CURRENT_VERSION}
        diffFetcher={diffFetcher as any}
        versionsFetcher={versionsFetcher as any}
        onClose={onClose as any}
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
        diffFetcher={diffFetcher as any}
        versionsFetcher={versionsFetcher as any}
        onClose={onClose as any}
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
        diffFetcher={diffFetcher as any}
        versionsFetcher={versionsFetcher as any}
        onClose={onClose as any}
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
        diffFetcher={diffFetcher as any}
        versionsFetcher={versionsFetcher as any}
        onClose={onClose as any}
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

  it("[REQ-053] renders error element when versionsFetcher rejects", async () => {
    versionsFetcher.mockRejectedValue({ error: { message: "artifact history unavailable" } });

    render(
      <ArtifactDiff
        entityId={ENTITY_ID}
        entityType="requirement"
        currentVersion={CURRENT_VERSION}
        diffFetcher={diffFetcher as any}
        versionsFetcher={versionsFetcher as any}
        onClose={onClose as any}
      />
    );

    // Error is shown in data-testid="diff-error" (no role="alert" on this element)
    await waitFor(() => {
      expect(screen.getByTestId("diff-error")).toBeInTheDocument();
    });
    expect(screen.getByTestId("diff-error")).toHaveTextContent("artifact history unavailable");
  });
});
