/**
 * Regression test for a real, but COSMETIC, staleness gap in
 * `ArtifactDiff.fetchDiff()` — found during the BUG-04 investigation
 * (SYSTEMAUDIT_2026-08-18 §4, e2e/tests/artifact-diff.spec.ts:114), but NOT
 * a reproduction of BUG-04 itself.
 *
 * IMPORTANT: `ArtifactDiff.tsx` renders `diff-fields` from `diffResult`,
 * which is only ever set on a SUCCESSFUL fetch — a failed fetch sets `error`
 * but never clears `diffResult` (see the `{diffResult && !loading && ...}`
 * block). So a late, superseded rejection can only ADD a spurious
 * `diff-error` banner above an already-correct diff; it can never hide
 * `diff-fields` or leave the panel stuck loading. That means this gap
 * cannot explain the originally reported ">30s timeout" (BUG-04) — live
 * re-execution of the e2e spec traced that symptom to `saveWithChangeReason`
 * timing out on a cold-started dev backend/Vite server, unrelated to version
 * selection, and it did not reproduce on 5 further warm runs. See the
 * PR description / fetchDiff's own comment for the full write-up.
 *
 * The gap itself is still real: `ArtifactDiff.fetchDiff()` had no
 * request-generation/cancellation guard (unlike the sibling
 * `versionsFetcher` effect a few lines above it, which already tracks a
 * `cancelled` flag). Every time `currentVersion` changes — e.g. right after
 * the artifact's first save, because `currentVersion` seeds `toVersion` —
 * a NEW diff fetch fires while a PREVIOUS one may still be in flight. If
 * that older request later rejects (e.g. it targeted a version that a
 * single-row entity no longer keeps a retrievable snapshot for — issue
 * #213), its stale rejection could overwrite a fresher, successful result
 * with an incorrect error banner.
 *
 * This test fails on the pre-guard code (the stale rejection appends a
 * spurious `diff-error` banner) and passes once fetchDiff ignores
 * out-of-order/stale responses.
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { ArtifactDiff } from "./ArtifactDiff";
import type { ArtifactVersion } from "../../types";

const ENTITY_ID = "req-bug04-race-001";

const VERSIONS_AT_V1: ArtifactVersion[] = [
  { version: 0, label: "Creation baseline", modified_at: null },
  { version: 1, label: "Current", modified_at: "2026-08-18T09:00:00Z" },
];

const VERSIONS_AT_V2: ArtifactVersion[] = [
  { version: 0, label: "Creation baseline", modified_at: null },
  { version: 2, label: "Current", modified_at: "2026-08-18T10:00:00Z" },
];

const GOOD_DIFF_0_2 = {
  from_version: 0,
  to_version: 2,
  fields: [
    { name: "title", status: "added" as const, from: null, to: "Baseline Diff Test" },
  ],
};

describe("ArtifactDiff — stale diff response race (spurious error banner, not BUG-04 itself)", () => {
  it("does not let a late-resolving, superseded diff(0,1) request clobber the fresh diff(0,2) result", async () => {
    // Deferred promise so we control resolution order explicitly, and so we
    // can `await` its actual settlement afterwards instead of an arbitrary
    // fixed delay.
    let failSlowFirstCall: (() => void) | null = null;
    let slowFirstCallPromise: Promise<unknown> | null = null;
    let callCount = 0;

    const diffFetcher = vi.fn().mockImplementation((_id: string, from: number, to: number) => {
      callCount += 1;
      if (callCount === 1) {
        // First call — diff(0,1), triggered right after mount (currentVersion=1).
        // Simulate it straggling behind the save: it resolves LATE, and by
        // the time it "reaches the server" version 1 no longer exists as a
        // retrievable snapshot (real backend behaviour, issue #213).
        slowFirstCallPromise = new Promise((_resolve, reject) => {
          failSlowFirstCall = () =>
            reject({ error: { message: `Version ${from} not available` } });
        });
        return slowFirstCallPromise;
      }
      // Second call — diff(0,2), triggered once currentVersion updates to 2.
      // Resolves immediately (fast), BEFORE the slow first call above.
      return Promise.resolve({ ...GOOD_DIFF_0_2, from_version: from, to_version: to });
    });

    const versionsFetcher = vi
      .fn()
      .mockResolvedValueOnce(VERSIONS_AT_V1)
      .mockResolvedValueOnce(VERSIONS_AT_V2);

    const { rerender } = render(
      <ArtifactDiff
        entityId={ENTITY_ID}
        entityType="requirement"
        currentVersion={1}
        diffFetcher={diffFetcher as any}
        versionsFetcher={versionsFetcher as any}
        onClose={vi.fn()}
      />
    );

    // First (slow) call has been kicked off — wait until it's registered.
    await waitFor(() => expect(diffFetcher).toHaveBeenCalledTimes(1));

    // The artifact is saved again — currentVersion prop flips to 2, exactly
    // as RequirementEditors re-renders RightSidebar/DiffPanel after the
    // detail refetch that follows a PATCH.
    rerender(
      <ArtifactDiff
        entityId={ENTITY_ID}
        entityType="requirement"
        currentVersion={2}
        diffFetcher={diffFetcher as any}
        versionsFetcher={versionsFetcher as any}
        onClose={vi.fn()}
      />
    );

    // Second (fast) call resolves first — diff(0,2) succeeds.
    await waitFor(() => {
      expect(screen.getByTestId("diff-fields")).toBeInTheDocument();
    });

    // NOW the first, superseded call finally rejects — after the good
    // result is already on screen. Await the actual promise settlement
    // (not an arbitrary fixed delay) so fetchDiff's catch handler — and any
    // resulting state update — has definitely run before we assert.
    expect(failSlowFirstCall).not.toBeNull();
    expect(slowFirstCallPromise).not.toBeNull();
    failSlowFirstCall!();
    await slowFirstCallPromise!.catch(() => {
      /* expected — this is the stale request's own rejection */
    });

    // The stale error must NOT have overwritten the good, current result.
    // waitFor gives React's act()-wrapped state flush (if any) a chance to
    // run before the final assertion, without hardcoding a delay.
    await waitFor(() => {
      expect(screen.getByTestId("diff-fields")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("diff-error")).not.toBeInTheDocument();
  });
});
