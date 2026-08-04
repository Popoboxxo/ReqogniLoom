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

/** CSS and module.css files. */
function collectCssFiles(dir: string): string[] {
  return collectFiles(dir, /\.module\.css$|\.css$/);
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
//
// Task 1.6 (status-badge consolidation) removed the inline `style={{...}}`
// blocks from the deleted `TestRuns/StatusBadge.tsx`, the local `StatusBadge`
// in `TestRuns.tsx`, and the three hand-rolled pill returns in
// `WorkspaceSettings/DefaultStatusBadge.tsx` — all now render through the
// single `shared/StatusBadge`, which owns its own inline style. Re-measured
// after that change: 1463.
//
// Task 1.3 (dialog migration) replaced the hand-built overlay/panel/header
// `style={{...}}` chrome of eleven modals (SystemHealthDialog,
// TriLabelOverviewDialog, CreateWorkspaceModal, SignatureDialog,
// CreateTraceLinkDialog, WorkspaceAdminSection's delete confirmation,
// WorkflowModal and its ArchitectureEditors/ArchitectureForm/
// RequirementEditors call sites) with `<Dialog>`, which owns that chrome via
// CSS Modules instead of inline styles. Re-measured after that change: 1437.
// Baseline lowered in the same PR per the ratchet rule above.
//
// Task 2.1 (ADR concept remodel) replaced AdrList's inline-styled `<h3>`
// heading, "+ New" button and inline create `<form>` with `<PageHeader>` +
// `<Dialog>` + `<ArtifactRow>`/`<EmptyState>` (all of which own their own
// chrome via CSS Modules or a handful of already-counted inline styles), and
// moved the row list's own layout into `AdrList.module.css`. Re-measured
// after that change: 1433. Baseline lowered in the same PR per the ratchet
// rule above.
//
// Task 2.2 (Risk concept remodel) applied the same replacement to
// RiskList/RiskEditors, plus removed the floating inline-styled "Neue
// Verknüpfung" button and its bespoke CreateTraceLinkDialog wiring in favor
// of the already-existing `<TraceLinkPanel>` (which owns its own new-link
// action). Re-measured after that change: 1428. Baseline lowered in the same
// PR per the ratchet rule above.
//
// Task 2.3 (Issue concept remodel) applied the same replacement to
// IssueList/IssueEditors — including dropping IssueList's inline-styled
// `<h3>` heading, "+ New" button and inline create `<form>` (formerly
// rendered via WorkspaceTree instead of ArtifactRow) — plus removed the
// floating inline-styled "Neue Verknüpfung" button and its bespoke
// CreateTraceLinkDialog wiring in favor of `<TraceLinkPanel>`. Re-measured
// after that change: 1423. Baseline lowered in the same PR per the ratchet
// rule above.
//
// Task 5.1 (ICDs/Diagrams frame) replaced IcdView's and DiagramView's
// inline-styled `<h3>{count}</h3>` + ad-hoc `<ul>/<li>` list markup with
// `<PageHeader>` + the new `IcdList`/`DiagramList` (`ListToolbar` +
// `ArtifactRow` + `EmptyState`). Re-measured after that change: 1404.
// Baseline lowered in the same PR per the ratchet rule above.
//
// Task 5.3 (Reviews, Traceability, Impact) replaced ReviewsView's and
// ImpactView's inline-styled `<h1>`/`<h2>` headings with `<PageHeader>`, and
// restructured TraceabilityView's bare `<h2>` + ad-hoc header row into
// `<PageHeader>` + `<SplitView>` (list: cycle warning + grouped trace-link
// list; detail: the Impact-Analysis panel), dropping several inline-styled
// wrapper elements in the process. Re-measured after that change: 1388.
// Baseline lowered in the same PR per the ratchet rule above.
//
// Task 4.2: `DecompositionTree.tsx` (fully inline-styled, no CSS module) was
// removed as confirmed dead code — see the tree-implementation-count note
// below for why. Re-measured after the deletion: 1376. Baseline lowered in
// the same PR per the ratchet rule above.
//
// Issue #119: `PromptTemplateSection.tsx` (dead duplicate) was deleted and
// the heavily inline-styled `AiPromptsSection.tsx` was rebuilt on hoisted
// style constants instead of per-element object literals. Re-measured after
// that change: 1316. Baseline lowered in the same PR per the ratchet rule
// above.
//
// Header unification (audit-2026-07 follow-up, no issue number): replaced
// the bespoke inline-styled `<h1>` (plus, for MetricsDashboard and the
// Audit dashboard, the wrapping flex row that combined the heading with the
// filter/action controls) on WorkspaceSettings, SystemSettings,
// UserProfileSettings, MetricsDashboard, CsvImport, DashboardViews and the
// Audit dashboard with `<PageHeader>`, matching the ~21 already-migrated
// artifact routes. Re-measured after that change: 1307.
//
// Issue #161 (inline-style ratchet reach) follow-up: moved the two worst
// offenders, `CsvImport.tsx` (59 inline `style={{...}}` blocks) and
// `NavigationShell/SidebarNavigation.tsx` (43 blocks), onto co-located CSS
// Modules (`CsvImport.module.css`, extended `SidebarNavigation.module.css`),
// eliminating both files' inline styles entirely (0 remaining in either).
// Genuinely stateful visuals (drag-over highlight, radio/nav-link/workspace
// selection, hover feedback, the optional-artifacts toggle knob) were
// expressed as a second, mutually-exclusive CSS class or a `:hover`/
// `:disabled` pseudo-class instead of JS-computed inline styles, so the
// associated `hoveredPath`/`hoveredButton`/`hoveredOptionId`/`hoveredHitId`
// state in SidebarNavigation was removed as dead code in the same change.
// Re-measured (whole `components/` tree, includes unrelated concurrent
// changes to other files present in the working tree at measurement time):
// 1091. Baseline lowered in the same PR per the ratchet rule above.
// Phase 6 / decision E2-D4 (Diagrams preview): `DiagramDetailView` no longer
// mounts an editable `<CanvasEditor>` in the overview's detail pane (its
// inline-styled sizing wrapper went with it) and its Mermaid preview box now
// shares the hoisted `previewBoxStyle` constant from `diagram-view-shared.ts`
// with the new canvas SVG preview instead of an inline object literal. One
// inline style was added back for the "canvas is still empty" hint.
// Re-measured after that change: 1090. Baseline lowered in the same PR per
// the ratchet rule above.
const STYLE_BRACE_PATTERN = /style=\{\{/g;
const STYLE_BRACE_BASELINE = 1090;

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
//
// Task 1.6 removed the hardcoded hex palette from `TestRuns.tsx`'s local
// `StatusBadge` (`#3b82f6`, `#22c55e`, `#ef4444`, `#eab308`, `#64748b`) and
// the `rgba(...)`/`var(--color-warning, #f59e0b)` fallbacks in
// `WorkspaceSettings/DefaultStatusBadge.tsx`. Re-measured: 128 occurrences
// in 35 files. Baseline lowered in the same PR per the ratchet rule above.
const HEX_LITERAL_PATTERN = /#[0-9a-fA-F]{3,8}/g;
const HEX_LITERAL_OCCURRENCE_BASELINE = 128;
const HEX_LITERAL_FILE_BASELINE = 35;

// --- (b.1) Hex color literals in .css / .module.css files (project-wide) ---
//
// Tracked separately from (b) since CSS files were not scanned initially and
// the baseline was only established for .tsx files. CSS files (both .css and
// .module.css) are now included in the hex-literal ratchet to prevent new
// hardcoded colors being introduced via stylesheets.
//
// Initial measurement (2026-08-04, extending the scanner from .tsx to CSS):
// 66 occurrences in 6 files (EmptyState.module.css, WorkflowEditor.module.css,
// CanvasEditor.module.css, MermaidEditor.module.css, global.css, tokens.css).
// This baseline is applied with the same monotonic non-increasing ratchet
// principle as the .tsx baseline above.
const HEX_LITERAL_CSS_OCCURRENCE_BASELINE = 66;
const HEX_LITERAL_CSS_FILE_BASELINE = 6;

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
//
// Task 4.2: `DecompositionTree.tsx` was removed as confirmed dead code — it
// had zero consumers (the live Architecture tree in `ArchitectureEditors.tsx`
// renders `WorkspaceTree` directly and explicitly opted out of drag-and-drop
// reparenting on 2026-07-13; `architectureApi.reparent()`, the API it was
// built to drive, was never called from anywhere in the frontend). Measured
// again after the deletion: 3. Baseline lowered in the same PR per the
// ratchet rule above.
//
// Task 4.3: investigated `RequirementTreeNode.tsx` as the next migration
// target (plan's stated goal: 1 tree implementation after Phase 4). Unlike
// `DecompositionTree`, it is NOT dead code — it is live in
// `ReqTraceLinkPanel.tsx`. It was also found NOT to be an accidental
// duplicate of the artifact-tree pattern this gate exists to catch: it is a
// lazy, per-node-fetching explorer over the `derives-from`/`derived-by`
// trace-link graph (async fetch on expand, `MAX_DEPTH` cycle guard, two
// independently-labeled Parent/Child groups per node), not a rendering of a
// known-upfront artifact list — it cannot be expressed through
// `WorkspaceTree`'s synchronous flat-`nodes[]`/single-`parentId` contract
// without either an eager-fetch behavior change or a new lazy-loading /
// multi-group `WorkspaceTree` API (see `docs/UI_KONZEPT.md` §16.3,
// "Dokumentierte Ausnahmen vom Standard" — `RequirementTreeNode.tsx` entry,
// Task 4.3). It was therefore removed from this gate's tracked list: this
// gate exists to catch accidental duplication of the artifact-tree pattern,
// not to flag a deliberately different, permanently-exempt UI pattern.
// Baseline lowered 3 -> 2 in the same PR per the ratchet rule above.
//
// Do NOT "fix" this by re-adding `RequirementTreeNode.tsx` here or by
// force-migrating it onto `WorkspaceTree` — read the §16.3 exception entry
// first; the mismatch is structural (lazy graph explorer vs. eager flat
// tree), not a naming coincidence.
//
// Follow-up investigation (post-Phase-4, on user request): re-checked
// `GoalsTree.tsx` against this gate's own purpose ("catch accidental
// duplication of the artifact-tree rendering pattern"). It is not a
// duplicate — it is a thin, page-local adapter that filters/sorts `Goal[]`
// into `WorkspaceTreeNode[]` and renders exactly one `<WorkspaceTree>`
// (`Goals/GoalsTree.tsx:146-155`), structurally identical to
// `NeedList.tsx`/`RequirementList.tsx`, neither of which is (correctly)
// tracked here. It contains zero tree-rendering logic of its own (no
// indent/expand-collapse/selection code — all of that lives in
// `WorkspaceTree`). Removed from the tracked list as a false positive left
// over from before Goals was rebuilt onto `WorkspaceTree`; baseline lowered
// 2 -> 1, leaving only the primitive itself. `WorkspaceTree` is the target,
// not a duplicate of itself — this gate's "0 remaining" state is now `1`,
// i.e. exactly the primitive, correctly never removable.
const KNOWN_TREE_IMPLEMENTATIONS = [
  join(COMPONENTS_DIR, "shared", "WorkspaceTree", "workspace-tree.tsx"),
];
const TREE_IMPLEMENTATION_BASELINE = 1;

// --- (d) Duplicate status-badge implementations ----------------------------
//
// Plan baseline: 3, target 1 after Task 1.6. Task 1.6 folded
// `TestRuns/StatusBadge.tsx` into `shared/StatusBadge` as a label/variant
// call (test-run execution states are a different semantic domain from
// artifact workflow status but render through the same tokens, so the
// honest outcome is a variant of the one component, not a second one — see
// the task-1.6-brief risk note). `WorkspaceSettings/DefaultStatusBadge.tsx`
// now also delegates its actual badge markup to `shared/StatusBadge`
// (status/label/badgeVariant translation only); it stays as its own file
// because it keeps a distinct public API (isCustomized/hasSource) plus the
// co-located `ResetToDefaultButton`, but it renders no badge markup itself
// anymore. Baseline lowered to 1 in the same PR per the ratchet rule above.
const KNOWN_STATUS_BADGE_IMPLEMENTATIONS = [join(COMPONENTS_DIR, "shared", "StatusBadge.tsx")];
const STATUS_BADGE_IMPLEMENTATION_BASELINE = 1;

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

  it("does not add new hardcoded hex color literals in CSS files beyond the frozen baseline", () => {
    const stylesDir = join(SRC_DIR, "styles");
    const cssFilesInStyles = collectCssFiles(stylesDir);
    const cssFilesInComponents = collectCssFiles(COMPONENTS_DIR);
    const allCssFiles = [...cssFilesInStyles, ...cssFilesInComponents];

    let totalOccurrences = 0;
    let filesWithHex = 0;
    for (const file of allCssFiles) {
      const content = readFileSync(file, "utf-8");
      // For CSS files, strip /* */ and // comments before counting hex literals
      // (CSS comments are either /* */ block comments or modern // line comments).
      const cleanContent = content
        .replace(/\/\*[\s\S]*?\*\//g, "") // Remove /* */ block comments
        .replace(/\/\/.*$/gm, ""); // Remove // line comments
      const count = countOccurrences(cleanContent, HEX_LITERAL_PATTERN);
      if (count > 0) {
        totalOccurrences += count;
        filesWithHex += 1;
      }
    }
    expect(totalOccurrences).toBeLessThanOrEqual(HEX_LITERAL_CSS_OCCURRENCE_BASELINE);
    expect(filesWithHex).toBeLessThanOrEqual(HEX_LITERAL_CSS_FILE_BASELINE);
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
