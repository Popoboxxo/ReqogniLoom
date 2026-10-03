/**
 * i18n key-parity guard (Task 7.2, UI-Konzept-Vollrollout).
 *
 * `frontend/src/i18n/locales/de.json` and `en.json` must expose the exact
 * same flattened key set in both directions. A key missing from one file but
 * present in the other means either a broken translation (i18next silently
 * falls back to `fallbackLng` for the missing key, per
 * `frontend/src/i18n/index.ts`) or dead content nobody cleaned up.
 *
 * This exact bug class already happened in this codebase: 3 keys were
 * missing from `de.json` for a long time, causing delete-confirmation
 * dialogs to silently render English text to German users (fixed in an
 * earlier phase of this plan, see Task 0.3). This test exists to catch
 * that automatically going forward.
 *
 * Flattening uses `.` as the separator, matching i18next's own default
 * `keySeparator` (unset, i.e. default, in `frontend/src/i18n/index.ts`'s
 * `i18n.init({...})` call) — the same convention the nested JSON resources
 * are already authored against.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";
import de from "../i18n/locales/de.json";
import en from "../i18n/locales/en.json";

/** A JSON value as loaded from the locale files: string leaves, nested objects, or arrays. */
type LocaleValue = string | number | boolean | null | LocaleValue[] | { [key: string]: LocaleValue };

/**
 * Recursively flatten a nested locale object into dot-separated key paths,
 * mirroring i18next's own default `keySeparator: "."` traversal. Arrays and
 * primitive leaves terminate a path; plain objects recurse.
 */
function flattenKeys(value: LocaleValue, prefix = ""): string[] {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    return [prefix];
  }
  const keys: string[] = [];
  for (const [key, child] of Object.entries(value)) {
    const path = prefix ? `${prefix}.${key}` : key;
    keys.push(...flattenKeys(child, path));
  }
  return keys;
}

describe("i18n key parity (Task 7.2)", () => {
  it("has the same flattened key set in de.json and en.json", () => {
    const deKeys = new Set(flattenKeys(de as LocaleValue));
    const enKeys = new Set(flattenKeys(en as LocaleValue));

    const missingFromEn = [...deKeys].filter((key) => !enKeys.has(key)).sort();
    const missingFromDe = [...enKeys].filter((key) => !deKeys.has(key)).sort();

    // Asserted separately (rather than one combined string) so a failure
    // report clearly labels which file each missing key belongs to.
    expect(missingFromEn, "keys present in de.json but missing from en.json").toEqual([]);
    expect(missingFromDe, "keys present in en.json but missing from de.json").toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// #619 — code-to-locale coverage: keys used in source but absent from BOTH
// locale files. de/en parity alone is blind to this — a key missing from
// both files still "matches" (both sides agree it's absent), while i18next
// falls back to the `t("key", "default")` call's own default string
// regardless of the active language. When that default is German (the
// author's working language), German text leaks into the English UI.
//
// A full backlog (174 keys at discovery time) can't be translated in one
// change, so this follows the same ratchet pattern as `ui-ratchet.test.ts`:
// frozen ceiling, fails only if the count *increases*. Lower
// `MISSING_KEY_BASELINE` in the same change whenever new gaps get fixed;
// never raise it to make this pass.
// ---------------------------------------------------------------------------

const SRC_DIR = resolve(__dirname, "..");

/** Recursively collect `.ts`/`.tsx` source files, excluding tests. */
function collectSourceFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    const stat = statSync(full);
    if (stat.isDirectory()) {
      out.push(...collectSourceFiles(full));
    } else if (/\.tsx?$/.test(entry) && !/\.test\.tsx?$/.test(entry)) {
      out.push(full);
    }
  }
  return out;
}

// Matches `t("literal.key", ...)` / `t('literal.key', ...)` — first-argument
// string literals only. A dynamic first argument (a variable, a template
// literal, a computed expression) cannot be resolved statically and is
// intentionally NOT matched — those keys need a different verification
// approach (e.g. a runtime i18next `missingKeyHandler`), not a source scan.
const T_CALL_PATTERN = /\bt\(\s*["']([a-zA-Z0-9_.]+)["']/g;

/** All statically-resolvable `t("key", ...)` key literals referenced in `dir`. */
function collectReferencedKeys(dir: string): Set<string> {
  const keys = new Set<string>();
  for (const file of collectSourceFiles(dir)) {
    const text = readFileSync(file, "utf-8");
    for (const match of text.matchAll(T_CALL_PATTERN)) {
      keys.add(match[1]!);
    }
  }
  return keys;
}

// Second, separate detector for the *second* `t()` argument — the inline
// default. `T_CALL_PATTERN` above captures only the first-argument key
// literal, so inline defaults were previously invisible to this scan
// (ADR-018 finding 003-04; the "~112" figure quoted in ADR-018 / the
// implementation plan is a stale estimate — a full scan on branch
// feat/w3-p2 finds far more, see INLINE_DEFAULT_BASELINE below).
//
// Coverage gap (documented, deliberately NOT fixable statically): a dynamic
// first key (`t(variable, "default")`) remains invisible because the literal
// key anchor is required for the match. A non-string default (template
// literal, JSX, ternary expression) is likewise not counted. Only the exact
// `t("literal.key", "default")` shape is measured; every excluded site needs
// a runtime i18next `missingKeyHandler` or a generated key union, not a
// source scan. `t("key", {count})` options calls are NOT defaults and are
// intentionally excluded by requiring a *string* second argument.
const INLINE_DEFAULT_PATTERN = /\bt\(\s*["'][a-zA-Z0-9_.]+["']\s*,\s*["']/g;

/**
 * Count `t("literal.key", "default")` call sites in `dir`.
 *
 * Returns a per-call-site count (not a de-duplicated key set): two calls with
 * the same key are two masking sites and must both be visible to the ratchet.
 */
function collectInlineDefaultCount(dir: string): number {
  let count = 0;
  for (const file of collectSourceFiles(dir)) {
    const text = readFileSync(file, "utf-8");
    count += [...text.matchAll(INLINE_DEFAULT_PATTERN)].length;
  }
  return count;
}

// Ratchet baseline — see the file-level comment above. Measured on this
// branch (189) after fixing the 9 keys this same change could concretely
// confirm leak German text into the English UI (settings.traceabilityHint,
// settings.attributeVisibilityHint, settings.visibilityHint,
// settings.visibilityOverridden, settings.visibilityReset,
// needs/adrs/risks/issues.deleteFailed — see #619), bringing it down to 180.
//
// Lowered again to 145 (GESAMTTEST_BERICHT_2026-08-21.md §6 Top-3, "6
// independent spots of hardcoded English in an otherwise fully German UI"):
// fixed the ReqIF Import panel (14 `import.reqif*` keys) and the Backup &
// Restore card (17 `adminOps.*` keys), both previously "komplett"
// untranslated bar one pre-existing key each, plus `baselines.compare` /
// `compareTitle` / `compareRun` (Baselines "Compare" button/panel) and
// `actions.reset` (shared by both CSV and ReqIF import reset buttons) — 35
// keys total, all of which were `t(key, "English default")` calls with no
// matching locale entry in either file, so i18next always rendered the
// English default regardless of the active UI language. (The traceability
// link-type dropdown, ICD placeholders, and TestCase title placeholder —
// the other 3 of the 6 findings — were fixed too, but via 2 new keys
// created and referenced in the same change, a net-zero on this count, or
// via a locale-aware lookup-table call with no locale-key involvement.)
// The remainder is real but unverified backlog (#619's own scan found 174 at
// a different point in time; source has grown since), not immediately
// actionable without confirming each one's actual rendered-language impact.
//
// Lowered to 135 (Systemaudit 2026-08-27, UI-11): `adrs.summary`,
// `risks.summary`, `issues.summary` were referenced via
// `t('<x>.summary', {count})` but only the i18next-pluralized
// `<x>.summary_one`/`<x>.summary_other` forms existed, so this scanner
// (which only sees literal key strings, not i18next's plural-suffix
// resolution) flagged the bare key as unresolved. Runtime rendering was
// unaffected — i18next always resolves `_one`/`_other` for a `count`-bearing
// call regardless of whether a bare key also exists — but the scan itself is
// intentionally naive about that, so a bare `summary` key was added to both
// locale files (mirroring `_other`) purely to keep this ratchet accurate.
// The measured count had already drifted down to 138 since the 145 baseline
// was set (unrelated fixes); this change's 3-key fix brings it to 135.
//
// Lowered to 123 (Task 30, OD-1): the `notificationPreferences.*` namespace —
// referenced by Task 29's NotificationsSection component but absent from both
// locale files — is now defined in de.json and en.json (8 keys: title, hint,
// assigned, comment_added, transition_pending, suspect_flagged, error,
// loading). The measured count was 131 immediately before this change (123
// baseline drift + those 8 keys); with the keys in place it is 123. Task 25
// deliberately left the ceiling at 135 rather than lowering it into a red
// suite, deferring the raise-free reduction to this change (see the Task 25
// commit).
// Lowered to 117 (#925): six `t("key")` calls with no inline default and no
// entry in either locale file rendered their raw key into the UI (no
// `fallbackLng` rescue, since the key is absent from both bundles):
// `traceability.testCasesGroup` (trace-link target dropdown optgroup showed
// the literal key), `export.download` / `export.downloadReqif` /
// `export.downloading` (CSV/ReqIF export buttons and spinner) and
// `workspace.selectFirst` / `workspace.selectPrompt` (empty-state prompts in
// the glossary and test-run list). All six are now translated in de.json and
// en.json (new `export` and `workspace` namespaces), so the measured count is
// 123 - 6 = 117.
//
// PR D of RFC #1002 pre-emptively added the bare `memory.summary` key to both
// locale files instead of leaving the new memory page to breach this ratchet:
// `MemoryPage` calls `t("memory.summary", {count})` while only the pluralized
// `memory.summary_one`/`summary_other` forms existed — the same scanner-blind
// spot as the `adrs/risks/issues.summary` fix above. With the key added the
// measured count is still 117, so the ceiling is unchanged.
//
// Lowered to 116 (cluster 5, #424/#402): the TestCase work added the same bare
// `testcases.summary` key to both locale files for the identical plural-blind
// reason — `TestCaseEditors` calls `t("testcases.summary", {count})` while only
// `summary_one`/`summary_other` existed, so the scanner flagged the bare key
// even though i18next resolves the plural forms at runtime. Every other new
// cluster-5 key (`testcases.*`, `deriveTestcase.aiNotice`, `baseline.*`,
// `traceability.pendingAiReview`/`includeUnreviewedAi`) is present in both
// files, so none of them contributes to this count. Re-measured: 117 - 1 = 116.
const MISSING_KEY_BASELINE = 116;

// ---------------------------------------------------------------------------
// DOC-02 / ADR-018 — deadline budgets (decision 2) and the second, inline-
// default ratchet (decision 1).
//
// Both metrics are enforced by the same two rules:
//   1. Non-increase — the measured value must never exceed its baseline
//      (prevents regression).
//   2. Deadline budget — once the wall-clock date reaches a metric's
//      deadline, its value must be at or below its target or CI goes red.
//      Without this, "monotonically decreasing" is a mere assertion: the
//      frozen ceiling would otherwise institutionalise the gap forever
//      (ADR-018 finding 003-01). Targets are only date-gated, so they cannot
//      make CI red before the deadline.
//
// MISSING_KEY_BASELINE stays 116 — re-measured on branch feat/w3-p2
// (2026-10-03): exactly 116 keys are referenced in `src/` but present in
// neither `de.json` nor `en.json`, so the existing ceiling is still accurate.
// Target 0 is ADR-018's end state ("baseline 0"); deadline 2027-06-30 is a
// dated release-style budget in the future relative to 2026-10-03.
//
// INLINE_DEFAULT_BASELINE is the *real measured* number of inline-default
// call sites on this branch, not the stale ~112 estimate the ADR carries.
// Measured with INLINE_DEFAULT_PATTERN (string second argument only) over
// `frontend/src/**/*.ts{,x}` excluding tests: 1289. With the looser
// `t(<literal>,` shape (including options-object second args) it would be
// higher, but those are not defaults. Target 0 encodes ADR-018 option A as
// the binding end state at the same deadline.
//
// Residual (NOT done in DOC-02, deliberately out of scope): the 536 dead
// locale keys (ADR-018 decision 5 / finding -303) are not removed here, and
// the REQ-L1-094 traceability-matrix entry is not corrected here (finding
// -348). Both remain open; this change only adds the enforceable ratchets.
// ---------------------------------------------------------------------------
/** Undefined referenced keys permitted once MISSING_KEY_DEADLINE is reached. */
const MISSING_KEY_TARGET = 0;
/** UTC date from which MISSING_KEY_TARGET is enforced (non-increase applies now). */
const MISSING_KEY_DEADLINE = "2027-06-30";

/** Inline `t(key, default)` call sites permitted by the non-increase ratchet. */
const INLINE_DEFAULT_BASELINE = 1289;
/** Inline `t(key, default)` call sites permitted once the deadline is reached. */
const INLINE_DEFAULT_TARGET = 0;
/** UTC date from which INLINE_DEFAULT_TARGET is enforced. */
const INLINE_DEFAULT_DEADLINE = "2027-06-30";

/**
 * True once the wall-clock date has reached (or passed) an ISO `YYYY-MM-DD`
 * deadline, interpreted as UTC midnight. Date-gated so a not-yet-due budget
 * never fails CI; only the deadline day itself flips it on.
 */
function deadlineReached(deadline: string): boolean {
  return Date.now() >= Date.parse(`${deadline}T00:00:00Z`);
}

/**
 * Wall-clock budget for the whole-`src/` source scan below, same rationale and
 * same constant as `design-tokens.test.ts` (which documents it at length).
 *
 * This is a static scan over every `.ts`/`.tsx` file, not a unit test: it
 * measures 2.3 s in isolation and 5.0-5.5 s when the suite runs under load,
 * i.e. right on vitest's default 5 s `testTimeout`. Two full-suite runs on
 * 2026-09-27 measured 5.08 s and 5.50 s here and failed on the clock alone,
 * with the de/en key-set parity test above green in the same runs. A source
 * scan should not share a budget with a pure function test. If the scan ever
 * approaches this, the real problem is the scan, not the budget.
 */
const SOURCE_SCAN_TIMEOUT_MS = 60_000;

describe("i18n code-to-locale coverage (#619)", () => {
  it(
    "does not reference more undefined translation keys than the frozen baseline",
    () => {
      const referenced = collectReferencedKeys(SRC_DIR);
      const deKeys = new Set(flattenKeys(de as LocaleValue));
      const enKeys = new Set(flattenKeys(en as LocaleValue));

      const missing = [...referenced]
        .filter((key) => !deKeys.has(key) && !enKeys.has(key))
        .sort();

      expect(
        missing.length,
        missing.length > MISSING_KEY_BASELINE
          ? `New missing i18n key(s) beyond the ${MISSING_KEY_BASELINE}-key baseline: ${missing.join(", ")}`
          : undefined
      ).toBeLessThanOrEqual(MISSING_KEY_BASELINE);

      // Deadline budget (ADR-018 decision 2): non-increase alone freezes the
      // gap; once the deadline is reached, the target binds instead.
      if (deadlineReached(MISSING_KEY_DEADLINE)) {
        expect(
          missing.length,
          `Missing-key deadline ${MISSING_KEY_DEADLINE} reached: ${missing.length} undefined ` +
            `translation key(s) remain (target ${MISSING_KEY_TARGET}). Missing: ${missing.join(", ")}`
        ).toBeLessThanOrEqual(MISSING_KEY_TARGET);
      }
    },
    SOURCE_SCAN_TIMEOUT_MS
  );

  it(
    "does not use more inline `t(key, default)` call sites than the frozen baseline",
    () => {
      const inlineDefaults = collectInlineDefaultCount(SRC_DIR);

      expect(
        inlineDefaults,
        inlineDefaults > INLINE_DEFAULT_BASELINE
          ? `${inlineDefaults} inline \`t(key, default)\` call site(s) exceed the ` +
              `${INLINE_DEFAULT_BASELINE}-site baseline`
          : undefined
      ).toBeLessThanOrEqual(INLINE_DEFAULT_BASELINE);

      // Deadline budget (ADR-018 decision 1/2): once reached, every inline
      // default must be gone (option A becomes binding at baseline 0).
      if (deadlineReached(INLINE_DEFAULT_DEADLINE)) {
        expect(
          inlineDefaults,
          `Inline-default deadline ${INLINE_DEFAULT_DEADLINE} reached: ${inlineDefaults} ` +
            `\`t(key, default)\` call site(s) remain (target ${INLINE_DEFAULT_TARGET}).`
        ).toBeLessThanOrEqual(INLINE_DEFAULT_TARGET);
      }
    },
    SOURCE_SCAN_TIMEOUT_MS
  );
});
