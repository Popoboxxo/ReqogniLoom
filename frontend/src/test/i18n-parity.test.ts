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
