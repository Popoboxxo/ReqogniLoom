/**
 * Characterization test for ArtifactDiff's sparse [0, N] version shape
 * (SYSTEMAUDIT_2026-08-18 §4, BUG-04 investigation, e2e/tests/artifact-diff.spec.ts:114).
 *
 * NOTE: this does NOT reproduce or prove a fix for BUG-04. Live re-execution
 * of the e2e spec (see the note on ArtifactDiff.tsx's fetchDiff) showed the
 * reported ">30s timeout" is not deterministic and does not correlate with
 * version-0 selection — the root cause could not be confirmed as
 * application code. Both cases below already pass against ArtifactDiff.tsx
 * as it existed before the BUG-04 investigation (confirmed by running them
 * against that revision); they document/lock in the seeding behaviour for a
 * version-list shape the pre-existing smoke test never exercised, not a
 * red-before/green-after regression.
 *
 * The real backend (ArtifactDiffService.list_versions, single-row entities
 * such as Requirement) never returns a contiguous version list. It always
 * returns exactly TWO entries: the synthetic "Creation baseline" (version 0)
 * and the CURRENT optimistic-lock version, which after even a single save is
 * already >= 2 (POST sets version=1, the first PATCH bumps it to 2 — version
 * 1 itself is never independently retrievable, see issue #213 / the
 * ArtifactDiffService docstring). The pre-existing smoke test
 * (ArtifactDiff.smoke.test.tsx) mocks an unrealistic contiguous [1,2,3] list
 * that never exercises this shape.
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { ArtifactDiff } from "./ArtifactDiff";
import type { ArtifactVersion } from "../../types";

const ENTITY_ID = "req-bug04-001";

// Mirrors ArtifactDiffService.list_versions() for a single-row entity that
// has been created (version 1) and saved once (version 2): only 0 and 2
// are retrievable, 1 never exists.
const REAL_SHAPE_VERSIONS: ArtifactVersion[] = [
  { version: 0, label: "Creation baseline", modified_at: null },
  { version: 2, label: "Current", modified_at: "2026-08-18T10:00:00Z" },
];

const MOCK_DIFF_RESULT = {
  from_version: 0,
  to_version: 2,
  fields: [
    { name: "title", status: "added" as const, from: null, to: "Baseline Diff Test" },
  ],
};

describe("ArtifactDiff — version-0 comparison against a sparse [0, N] list (characterization)", () => {
  it("seeds from=0 automatically and fetches the diff without requiring a non-existent version 1", async () => {
    const diffFetcher = vi.fn().mockResolvedValue(MOCK_DIFF_RESULT);
    const versionsFetcher = vi.fn().mockResolvedValue(REAL_SHAPE_VERSIONS);

    render(
      <ArtifactDiff
        entityId={ENTITY_ID}
        entityType="requirement"
        currentVersion={2}
        diffFetcher={diffFetcher as any}
        versionsFetcher={versionsFetcher as any}
        onClose={vi.fn()}
      />
    );

    // The "from" select must offer version 0 as an option — this is what
    // e2e/tests/artifact-diff.spec.ts:145 selects via selectOption({value:'0'}).
    await waitFor(() => {
      const fromSelect = screen.getByTestId("diff-from-version") as HTMLSelectElement;
      const optionValues = Array.from(fromSelect.options).map((o) => o.value);
      expect(optionValues).toContain("0");
    });

    // The component must auto-fetch diff(0, 2) — never diff(0, 1), which
    // 404s on the real backend because version 1 was never a retrievable
    // snapshot (only 0 and the current lock version are).
    await waitFor(() => {
      expect(diffFetcher).toHaveBeenCalledWith(ENTITY_ID, 0, 2);
    });
    expect(diffFetcher).not.toHaveBeenCalledWith(ENTITY_ID, 0, 1);

    await waitFor(() => {
      expect(screen.getByTestId("diff-fields")).toBeInTheDocument();
    });
  });

  it("stays on the real current version even when the currentVersion prop is stale (e.g. version 1)", async () => {
    // Regression guard: if a caller passes a stale `currentVersion` (e.g. the
    // ArtifactInspector's cached version before a refetch lands), the
    // component must fall back to the *actual* latest entry from the
    // versions list instead of seeding a "to" version that was never real.
    const diffFetcher = vi.fn().mockResolvedValue(MOCK_DIFF_RESULT);
    const versionsFetcher = vi.fn().mockResolvedValue(REAL_SHAPE_VERSIONS);

    render(
      <ArtifactDiff
        entityId={ENTITY_ID}
        entityType="requirement"
        currentVersion={1}
        diffFetcher={diffFetcher as any}
        versionsFetcher={versionsFetcher as any}
        onClose={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(diffFetcher).toHaveBeenCalledWith(ENTITY_ID, 0, 2);
    });
    expect(diffFetcher).not.toHaveBeenCalledWith(ENTITY_ID, 0, 1);
  });
});
