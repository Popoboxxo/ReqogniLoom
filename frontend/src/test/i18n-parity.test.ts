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
const MISSING_KEY_BASELINE = 145;

describe("i18n code-to-locale coverage (#619)", () => {
  it("does not reference more undefined translation keys than the frozen baseline", () => {
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
  });
});
