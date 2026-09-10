/**
 * Frontend counterpart of `backend/traceability/tests/test_link_type_consumers.py`.
 *
 * No retired link-type literal may survive anywhere under `frontend/src`.
 *
 * Why this exists: the backend ratchet caught every retired literal on its
 * own side, and the frontend had none — because nobody had looked. The final
 * whole-branch review then found `ArtifactInspector/types.ts` still exporting
 * an eight-value `ALL_LINK_TYPES` list of *retired* types, which `TracePanel`
 * used as a filter: any link whose type was not in that stale list was
 * dropped from the rendered list with no error and no visible sign. Five of
 * the eight real catalog types were invisible in production for the whole
 * branch. This test is what would have caught it on day one.
 *
 * Same shape as the backend one deliberately: a raw-text grep for the
 * quoted literal (comments included, so prose has to use backticks) with an
 * explicit, justified exceptions list. A file that legitimately still names a
 * retired type goes in `ALLOWED` with a reason — not silently.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { describe, expect, it } from "vitest";

const SRC_DIR = join(__dirname, "..");

/** Same list as the backend ratchet's `RETIRED`. */
const RETIRED = [
  "parent-child",
  "satisfies",
  "implements",
  "refines",
  "realizes",
  "documents",
  "traces",
  "uses-term",
  "copy-of",
];

/**
 * Files that legitimately still name a retired type. Each entry needs a
 * reason; "it was already there" is not one.
 */
const ALLOWED = new Set<string>([
  // This file — it is the list.
  "test/link-type-consumers.test.ts",
  // Pins that a stored workspace value absent from the catalog (a retired
  // pre-catalog default) still renders as a disabled option instead of being
  // silently downgraded on save. The retired value IS the fixture.
  "components/WorkspaceSettings/WorkspaceSettings.test.tsx",
]);

function collectSourceFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      out.push(...collectSourceFiles(full));
    } else if (/\.tsx?$/.test(entry)) {
      out.push(full);
    }
  }
  return out;
}

const FILES = collectSourceFiles(SRC_DIR)
  .map((full) => [relative(SRC_DIR, full).split(sep).join("/"), full] as const)
  .filter(([rel]) => !ALLOWED.has(rel));

describe("retired link-type literals", () => {
  it.each(RETIRED)("'%s' is not hardcoded anywhere in frontend/src", (retired) => {
    const pattern = new RegExp(`['"]${retired}['"]`);
    const offenders = FILES.filter(([, full]) =>
      pattern.test(readFileSync(full, "utf-8")),
    ).map(([rel]) => rel);

    expect(offenders).toEqual([]);
  });

  it("scans a non-trivial number of files (guards against a broken walker)", () => {
    // A silently empty file list would make every assertion above pass.
    expect(FILES.length).toBeGreaterThan(100);
  });
});
