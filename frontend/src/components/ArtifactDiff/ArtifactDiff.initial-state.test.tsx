/**
 * M-04 — a version with no stored predecessor must be presented as the
 * artifact's initial state, not as a comparison against itself.
 *
 * Two defects were reported together and are covered separately below:
 *
 *  1. The ArtifactInspector announced "Comparing v1 → v1" — a comparison of a
 *     version against itself — because it described the comparison from its
 *     own `diffLeft`/`diffRight` state, which it seeds to the *same* number.
 *     Meanwhile the panel underneath was showing 0 → 1. The resolved range is
 *     owned by `ArtifactDiff` (it holds the version list), so it now reports
 *     that range upward and the host labels the panel with it.
 *
 *  2. Every field rendered an "Added" badge, because version 0 is the
 *     synthetic empty creation baseline. The badges are correct as far as the
 *     backend is concerned and `e2e/tests/artifact-diff.spec.ts` asserts them,
 *     so they stay — what was missing is the framing that says why they all
 *     say "Added". Hence a notice above the list rather than a hidden list.
 *
 * The version-list shapes below mirror the real backend: single-row entities
 * (Requirement, ADR, …) expose only `[0, <current lock version>]`, while
 * entities with a real version table (Glossary, Diagram, …) expose every
 * stored snapshot. See `ArtifactDiff.version-zero.test.tsx` and issue #213.
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { ArtifactDiff, type ArtifactDiffRange } from "./ArtifactDiff";
import type { ArtifactDiffResult, ArtifactVersion } from "../../types";

vi.mock("react-i18next", () => {
  const t = (_key: string, fallback?: string | Record<string, unknown>): string =>
    typeof fallback === "string" ? fallback : _key;
  return { useTranslation: () => ({ t }) };
});

const ENTITY_ID = "req-m04-001";

/** Single-row entity: only the empty creation baseline and the current state. */
const NO_PREDECESSOR_VERSIONS: ArtifactVersion[] = [
  { version: 0, label: "Creation baseline", modified_at: null },
  { version: 1, label: "Current", modified_at: "2026-08-30T10:00:00Z" },
];

/** Versioned entity: real snapshots sit between the baseline and the head. */
const WITH_PREDECESSOR_VERSIONS: ArtifactVersion[] = [
  { version: 0, label: "Creation baseline", modified_at: null },
  { version: 1, label: "v1", modified_at: "2026-08-28T10:00:00Z" },
  { version: 2, label: "v2", modified_at: "2026-08-29T10:00:00Z" },
  { version: 3, label: "v3", modified_at: "2026-08-30T10:00:00Z" },
];

const ALL_ADDED_DIFF: ArtifactDiffResult = {
  from_version: 0,
  to_version: 1,
  fields: [
    { name: "title", status: "added", from: null, to: "A brand new requirement" },
    { name: "description", status: "added", from: null, to: "" },
  ],
};

const REAL_DIFF: ArtifactDiffResult = {
  from_version: 2,
  to_version: 3,
  fields: [{ name: "title", status: "modified", from: "Old", to: "New" }],
};

/**
 * `waitFor`'s own default is 1000 ms regardless of vitest's `testTimeout`, and
 * under full-suite load these renders routinely need longer (the first run of
 * this file failed on exactly that, with `diff-loading` still in the DOM).
 */
const SETTLE_TIMEOUT_MS = 15000;

/**
 * Resolve once the component has finished loading and committed a diff.
 * `diff-fields` and `diff-initial-state` render under the same `!loading`
 * gate, so this is the deterministic anchor for asserting on either — there
 * is no in-between state where one is present and the other is not.
 */
async function settle(): Promise<void> {
  await waitFor(
    () => {
      expect(screen.getByTestId("diff-fields")).toBeInTheDocument();
    },
    { timeout: SETTLE_TIMEOUT_MS },
  );
}

function renderDiff(
  versions: ArtifactVersion[],
  result: ArtifactDiffResult,
  extra: Partial<{
    currentVersion: number;
    initialFromVersion: number;
    onRangeChange: (r: ArtifactDiffRange | null) => void;
  }> = {},
): { diffFetcher: ReturnType<typeof vi.fn> } {
  const diffFetcher = vi.fn().mockResolvedValue(result);
  const versionsFetcher = vi.fn().mockResolvedValue(versions);
  render(
    <ArtifactDiff
      entityId={ENTITY_ID}
      entityType="requirement"
      currentVersion={extra.currentVersion ?? versions[versions.length - 1]!.version}
      initialFromVersion={extra.initialFromVersion}
      onRangeChange={extra.onRangeChange}
      diffFetcher={diffFetcher as never}
      versionsFetcher={versionsFetcher as never}
      onClose={vi.fn()}
    />,
  );
  return { diffFetcher };
}

describe("ArtifactDiff — initial state vs. real comparison (M-04)", () => {
  it("labels a version with no stored predecessor as the initial state", async () => {
    renderDiff(NO_PREDECESSOR_VERSIONS, ALL_ADDED_DIFF);

    await settle();
    expect(screen.getByTestId("diff-initial-state")).toBeInTheDocument();
    expect(screen.getByTestId("diff-initial-state")).toHaveTextContent("Ausgangszustand");
  });

  it("still renders the field list under the notice, all-added badges included", async () => {
    // e2e/tests/artifact-diff.spec.ts asserts both of these for a version-0
    // comparison; the notice explains the badges, it does not replace them.
    renderDiff(NO_PREDECESSOR_VERSIONS, ALL_ADDED_DIFF);

    await settle();
    expect(screen.getByTestId("diff-field-title")).toHaveTextContent("Added");
  });

  it("does NOT claim an initial state when real snapshots sit below the head", async () => {
    renderDiff(WITH_PREDECESSOR_VERSIONS, REAL_DIFF);

    await settle();
    expect(screen.queryByTestId("diff-initial-state")).not.toBeInTheDocument();
  });

  it("keeps the notice off a deliberate widening of the range back to creation", async () => {
    // Choosing "from = creation baseline" on an artifact that HAS history is
    // a real question ("what has this accumulated since it was created?"),
    // and the all-added answer is the correct one — not an initial state.
    renderDiff(WITH_PREDECESSOR_VERSIONS, ALL_ADDED_DIFF, { initialFromVersion: 0 });

    await settle();
    expect(screen.queryByTestId("diff-initial-state")).not.toBeInTheDocument();
  });
});

describe("ArtifactDiff — resolved range reporting (M-04)", () => {
  it("reports the range it actually fetched, not the one the host asked for", async () => {
    const onRangeChange = vi.fn();
    // The ArtifactInspector seeds left === right; the panel must not echo it.
    const { diffFetcher } = renderDiff(NO_PREDECESSOR_VERSIONS, ALL_ADDED_DIFF, {
      currentVersion: 1,
      initialFromVersion: 1,
      onRangeChange,
    });

    await waitFor(
      () => {
        expect(diffFetcher).toHaveBeenCalledWith(ENTITY_ID, 0, 1);
      },
      { timeout: SETTLE_TIMEOUT_MS },
    );
    await waitFor(
      () => {
        expect(onRangeChange).toHaveBeenLastCalledWith({
          from: 0,
          to: 1,
          isInitialState: true,
        });
      },
      { timeout: SETTLE_TIMEOUT_MS },
    );
    // The degenerate request itself must never be reported back.
    expect(onRangeChange).not.toHaveBeenCalledWith(
      expect.objectContaining({ from: 1, to: 1 }),
    );
  });

  it("honours a host-selected left version that is a real predecessor", async () => {
    // Regression: "Compare to current" on a version row set the inspector's
    // `diffLeft`, but nothing forwarded it — the diff always fell back to
    // "the version immediately below the head".
    const onRangeChange = vi.fn();
    const { diffFetcher } = renderDiff(WITH_PREDECESSOR_VERSIONS, REAL_DIFF, {
      currentVersion: 3,
      initialFromVersion: 1,
      onRangeChange,
    });

    await waitFor(
      () => {
        expect(diffFetcher).toHaveBeenCalledWith(ENTITY_ID, 1, 3);
      },
      { timeout: SETTLE_TIMEOUT_MS },
    );
    expect(diffFetcher).not.toHaveBeenCalledWith(ENTITY_ID, 2, 3);
    await waitFor(
      () => {
        expect(onRangeChange).toHaveBeenLastCalledWith({
          from: 1,
          to: 3,
          isInitialState: false,
        });
      },
      { timeout: SETTLE_TIMEOUT_MS },
    );
  });

  it("ignores a host-selected left version that does not exist", async () => {
    const { diffFetcher } = renderDiff(WITH_PREDECESSOR_VERSIONS, REAL_DIFF, {
      currentVersion: 3,
      initialFromVersion: 99,
    });

    await waitFor(
      () => {
        // Falls back to the automatic seeding (highest version below the head).
        expect(diffFetcher).toHaveBeenCalledWith(ENTITY_ID, 2, 3);
      },
      { timeout: SETTLE_TIMEOUT_MS },
    );
  });
});
