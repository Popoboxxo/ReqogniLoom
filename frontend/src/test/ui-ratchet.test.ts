/**
 * UI concept ratchet guards (Task 7.4, UI-Konzept-Vollrollout).
 *
 * These tests implement the "Sperrklinke" (ratchet) principle from the UI
 * concept plan (16.2), mirroring the backend pattern in
 * `backend/rest_api/tests/test_architecture.py`: legacy violations that
 * cannot be fixed in a single change get a frozen numeric ceiling instead.
 * A test fails the moment the measured value *increases* past its baseline;
 * it stays green as long as the value holds steady or drops.
 *
 * Why introduce this now (Phase 7, ahead of Phases 2-5): the whole point of
 * a ratchet is that it works *during* the migration, not after it — it must
 * be in place before the bulk of the structural refactoring starts so that
 * every subsequent PR is checked against it automatically.
 *
 * Updating a baseline: when a PR genuinely lowers one of these counts (e.g.
 * migrating an inline `style={{...}}` block onto a CSS custom property, or
 * collapsing a duplicate tree/status-badge implementation into the shared
 * one), lower the matching `*_BASELINE` constant below to the new measured
 * value in the SAME PR. Never raise a baseline to make a test pass — that
 * defeats the ratchet's purpose. No external baseline file is used
 * deliberately; the constants below ARE the baseline.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const SRC_DIR = resolve(__dirname, "..");
const COMPONENTS_DIR = join(SRC_DIR, "components");

/** Recursively collect files under `dir` whose basename matches `extPattern`. */
function collectFiles(dir: string, extPattern: RegExp): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    const stat = statSync(full);
    if (stat.isDirectory()) {
      out.push(...collectFiles(full, extPattern));
    } else if (extPattern.test(entry)) {
      out.push(full);
    }
  }
  return out;
}

/** `.tsx` source files, excluding `*.test.tsx`. */
function collectNonTestTsxFiles(dir: string): string[] {
  return collectFiles(dir, /\.tsx$/).filter((f) => !f.endsWith(".test.tsx"));
}

function countOccurrences(text: string, pattern: RegExp): number {
  const matches = text.match(pattern);
  return matches ? matches.length : 0;
}

/**
 * Count `pattern` matches in `text`, skipping comment lines — mirroring
 * `_count_orm_lines` in `backend/rest_api/tests/test_architecture.py`,
 * which skips lines whose trimmed content starts with `#`. Here that means
 * skipping `//` line comments and `*`/`/*` JSDoc/block-comment lines.
 *
 * Without this, a naive full-text scan for hex literals also matches
 * decimal GitHub issue references in comments (e.g. `// #135`,
 * `* ...(issue #173):`), since digits 0-9 are valid hex characters too.
 * That produced a materially inflated, wrong baseline in an earlier
 * revision of this file (see the comment on HEX_LITERAL_OCCURRENCE_BASELINE
 * below) — a real bug, not a scope/methodology quirk.
 */
function countNonCommentOccurrences(text: string, pattern: RegExp): number {
  let count = 0;
  for (const line of text.split("\n")) {
    const trimmed = line.trim();
    if (trimmed.startsWith("//") || trimmed.startsWith("*") || trimmed.startsWith("/*")) {
      continue;
    }
    count += countOccurrences(line, pattern);
  }
  return count;
}

// --- (a) Inline `style={{` usage in components/ ---------------------------
//
// Plan baseline (2026-08-01, .superpowers/sdd/2026-08-01-ui-konzept-vollrollout/task-7.4-brief.md): 1462.
// Actually measured on this branch (feat/ui-konzept-vollrollout-phase0,
// after Tasks 0.1-0.3): 1468. The +6 delta is plausible drift from Phase 0
// work landing between the plan's measurement date and this task; the
// measured value is used as the enforced baseline per the task instructions
// (measure the real current value, don't blindly trust the plan number).
const STYLE_BRACE_PATTERN = /style=\{\{/g;
const STYLE_BRACE_BASELINE = 1468;

// --- (b) Hex color literals in .tsx files (project-wide, no test files) ---
//
// Plan baseline: 145 occurrences in 29 files.
//
// CORRECTION (post-review, see task-7.4-report.md "Fix" section): an
// earlier revision of this file counted 152 occurrences in 48 files using
// a naive full-text `text.match(pattern)` scan. That count was WRONG, not
// just a methodology drift from the plan: `/#[0-9a-fA-F]{3,8}/` also
// matches decimal GitHub issue references in comments (e.g. `// #135`,
// `* ...(issue #173):`), because digits 0-9 are valid hex characters. 15 of
// those 48 files (e.g. App.tsx, LoginPage.tsx, StatusBadge.tsx) contained
// ONLY such comment references and zero real hex colors.
//
// Fixed by skipping comment lines (see countNonCommentOccurrences above),
// mirroring how the backend counterpart skips `#`-prefixed comment lines.
// Actually measured with the fix, whole frontend/src, `.tsx`, excluding
// `*.test.tsx`: 135 occurrences in 36 files. This is close to the plan's
// 145/29 — the small remaining gap is plausible normal drift between the
// plan's 2026-08-01 measurement and now, not a counting bug (spot-checked:
// every remaining match is a real hex color in a style/color context).
const HEX_LITERAL_PATTERN = /#[0-9a-fA-F]{3,8}/g;
const HEX_LITERAL_OCCURRENCE_BASELINE = 135;
const HEX_LITERAL_FILE_BASELINE = 36;

// --- (c) Duplicate tree implementations ------------------------------------
//
// Plan baseline: 3 (WorkspaceTree, DecompositionTree, RequirementTreeNode),
// with a target of 1 after Phase 4. Actually measured: 4 — `GoalsTree.tsx`
// was added under `components/Goals/` after the plan's 2026-08-01
// measurement (Goal/MainGoal traceability work, see commit 3c71b8a6) and
// was not yet accounted for. This fixed list is a deliberate implementation
// choice (not mandated by the task brief) rather than a naming heuristic,
// since generic name matching (e.g. "*tree*") also matches unrelated files
// (TraceSpine, ListToolbar, ArtifactId, etc.) whose basenames merely
// contain the substring "tree" without being tree implementations.
const KNOWN_TREE_IMPLEMENTATIONS = [
  join(COMPONENTS_DIR, "shared", "WorkspaceTree", "workspace-tree.tsx"),
  join(COMPONENTS_DIR, "ArchitectureEditors", "DecompositionTree.tsx"),
  join(COMPONENTS_DIR, "RequirementEditors", "RequirementTreeNode.tsx"),
  join(COMPONENTS_DIR, "Goals", "GoalsTree.tsx"),
];
const TREE_IMPLEMENTATION_BASELINE = 4;

// --- (d) Duplicate status-badge implementations ----------------------------
//
// Plan baseline: 3, target 1 after Task 1.6. Actually measured: 3, matching
// the plan exactly — no deviation to document here.
const KNOWN_STATUS_BADGE_IMPLEMENTATIONS = [
  join(COMPONENTS_DIR, "shared", "StatusBadge.tsx"),
  join(COMPONENTS_DIR, "TestRuns", "StatusBadge.tsx"),
  join(COMPONENTS_DIR, "WorkspaceSettings", "DefaultStatusBadge.tsx"),
];
const STATUS_BADGE_IMPLEMENTATION_BASELINE = 3;

describe("UI concept ratchet (Task 7.4)", () => {
  it("does not add new inline style={{ usages beyond the frozen baseline", () => {
    const files = collectNonTestTsxFiles(COMPONENTS_DIR);
    let total = 0;
    for (const file of files) {
      total += countOccurrences(readFileSync(file, "utf-8"), STYLE_BRACE_PATTERN);
    }
    expect(total).toBeLessThanOrEqual(STYLE_BRACE_BASELINE);
  });

  it("does not exceed the frozen baseline of style={{ occurrences (monotonic)", () => {
    // Guards against a stale ceiling, mirroring
    // `test_ratchet_is_monotonic` in the backend counterpart: if the real
    // count has already dropped below the baseline, lower the constant.
    const files = collectNonTestTsxFiles(COMPONENTS_DIR);
    let total = 0;
    for (const file of files) {
      total += countOccurrences(readFileSync(file, "utf-8"), STYLE_BRACE_PATTERN);
    }
    expect(total).toBe(STYLE_BRACE_BASELINE);
  });

  it("does not add new hardcoded hex color literals beyond the frozen baseline", () => {
    const files = collectNonTestTsxFiles(SRC_DIR);
    let totalOccurrences = 0;
    let filesWithHex = 0;
    for (const file of files) {
      // Comment lines are excluded — see countNonCommentOccurrences: a
      // naive full-text scan also matches decimal issue references like
      // `// #135`, which are not hex color literals.
      const count = countNonCommentOccurrences(readFileSync(file, "utf-8"), HEX_LITERAL_PATTERN);
      if (count > 0) {
        totalOccurrences += count;
        filesWithHex += 1;
      }
    }
    expect(totalOccurrences).toBeLessThanOrEqual(HEX_LITERAL_OCCURRENCE_BASELINE);
    expect(filesWithHex).toBeLessThanOrEqual(HEX_LITERAL_FILE_BASELINE);
  });

  it("does not exceed the frozen tree-implementation baseline", () => {
    const existing = KNOWN_TREE_IMPLEMENTATIONS.filter((f) => {
      try {
        return statSync(f).isFile();
      } catch {
        return false;
      }
    });
    expect(existing.length).toBeLessThanOrEqual(TREE_IMPLEMENTATION_BASELINE);
  });

  it("does not exceed the frozen status-badge-implementation baseline", () => {
    const existing = KNOWN_STATUS_BADGE_IMPLEMENTATIONS.filter((f) => {
      try {
        return statSync(f).isFile();
      } catch {
        return false;
      }
    });
    expect(existing.length).toBeLessThanOrEqual(STATUS_BADGE_IMPLEMENTATION_BASELINE);
  });
});
