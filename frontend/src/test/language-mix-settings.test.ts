/**
 * DE/EN language-mix regression guard (#595, #610).
 *
 * `i18n-parity.test.ts` only catches a key present in one locale file but
 * missing from the other. It cannot catch a key missing from *both* files:
 * i18next then falls back to the literal `t(key, defaultValue)` call-site
 * default regardless of the active language, so whatever the developer
 * happened to type there (German in some spots, English in others) leaks
 * straight to the UI. That is exactly what #595/#610 reported on
 * `/settings` (tab labels, "Add" button, attribute-visibility heading) and
 * `/impact` ("Artefakt laden" button) -- five keys that were referenced in
 * component source but never defined in either `en.json` or `de.json`.
 *
 * This test pins that those specific keys resolve in both locales, so a
 * future regression (e.g. a renamed key that forgets to update the JSON)
 * fails here instead of shipping as another silent language mix.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import de from "../i18n/locales/de.json";
import en from "../i18n/locales/en.json";

const KEYS = [
  "settings.tabs.general",
  "settings.tabs.traceability",
  "settings.tabs.visibility",
  "settings.tabs.llm",
  "settings.tabs.governanceReplacement",
  "settings.attributeVisibility",
  "actions.add",
  "impact.load",
] as const;

/** Resolve a dot-separated i18n key against a loaded locale object. */
function lookup(locale: unknown, key: string): string | undefined {
  let current: unknown = locale;
  for (const part of key.split(".")) {
    if (typeof current !== "object" || current === null) return undefined;
    current = (current as Record<string, unknown>)[part];
  }
  return typeof current === "string" ? current : undefined;
}

describe("language-mix regression guard (#595, #610)", () => {
  it("defines every previously-missing key in both locales", () => {
    const missing: string[] = [];
    for (const key of KEYS) {
      if (lookup(en, key) === undefined) missing.push(`en.json: ${key}`);
      if (lookup(de, key) === undefined) missing.push(`de.json: ${key}`);
    }
    expect(missing).toEqual([]);
  });
});

describe("workflow entity state-count label separation (#595)", () => {
  it("stacks .entityItemCount on its own line instead of running into the name", () => {
    // #595: "Requirement6 states" -- .entityItemCount is a <span> (inline by
    // default) sitting right after the name <span> with no separating
    // whitespace in the JSX, so its `margin-top: 2px` (meant to push it onto
    // its own line, below the name) had no effect without `display: block`.
    const css = readFileSync(
      resolve(__dirname, "../components/WorkflowEditor/WorkflowEditor.module.css"),
      "utf-8"
    );
    const match = css.match(/\.entityItemCount\s*\{([^}]*)\}/);
    expect(match, ".entityItemCount rule not found").not.toBeNull();
    expect(match![1]).toMatch(/display:\s*(block|flex|grid)/);
  });
});
