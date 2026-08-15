/**
 * Primary-create-action label convention (GH-343).
 *
 * `docs/UI_KONZEPT.md` ch. 12.1 and ch. 14.2 require the single filled
 * primary action of an artifact route to name its **result** ("Neues
 * Requirement"), never the gesture ("+ New"). GH-343 recorded eight
 * different shapes for the very same "create one of these" action:
 *
 *   "+ New" · "New need" · "New ADR" · "New architecture element"
 *   "Create Run" · "New Link" · "Add term" · "New goal"
 *
 * The i18n key-parity guard (`i18n-parity.test.ts`) cannot catch this: all
 * of those keys existed in both locales, they were merely worded
 * inconsistently. This test pins the *shape* of the label values instead,
 * in both languages, plus the source-level rule that no route may rebuild
 * the "+"-prefixed gesture label by string concatenation.
 *
 * Deliberately a shape rule, not a golden-value snapshot: translators must
 * stay free to reword an entity noun, but not to reintroduce a verb phrase
 * ("Testlauf erstellen") or a bare gesture ("+ New").
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import { describe, expect, it } from "vitest";

import de from "../i18n/locales/de.json";
import en from "../i18n/locales/en.json";

const SRC_DIR = resolve(__dirname, "..");

/**
 * Every i18n key that labels a page-level "create a new <entity>" action.
 *
 * Keyed by the route the action belongs to, so a failure names the screen a
 * user would see rather than just a JSON path. Kept explicit (rather than
 * derived from the sources) because that is precisely the list GH-343
 * enumerated — a new artifact route must be added here consciously.
 */
const CREATE_ACTION_KEYS: Readonly<Record<string, string>> = {
  "System Requirements": "requirements.newRequirement",
  "Stakeholder Needs": "needs.newNeed",
  ADRs: "adrs.newAdr",
  Risks: "risks.newRisk",
  Issues: "issues.newIssue",
  "Test Cases": "testcases.newTestCase",
  Architecture: "arch.newElement",
  "Test Runs": "testRuns.create",
  Traceability: "traceability.create",
  Glossary: "glossary.addTerm",
  Goals: "goals.newGoal",
  ICDs: "icds.create",
  Diagrams: "diagrams.create",
};

/**
 * English: `New <Entity>`, entity in Title Case so that acronyms ("ADR",
 * "ICD") and multi-word nouns ("Test Case") read alike.
 */
const EN_PATTERN = /^New [A-Z][A-Za-z]*( [A-Z][A-Za-z]*)*$/;

/**
 * German: `Neue|Neuer|Neues <Substantiv>` — a nominative noun phrase.
 * Excludes both the verb-final phrasing ("Testlauf erstellen", "Begriff
 * hinzufügen") and the accusative leftovers of a verb phrase ("Neuen Link
 * erstellen"), which is exactly the drift GH-343 reported.
 */
const DE_PATTERN = /^Neue[rs]? [A-ZÄÖÜ][\wÄÖÜäöüß-]*( [A-ZÄÖÜ][\wÄÖÜäöüß-]*)*$/u;

/** Resolve a dot-separated i18n key against a loaded locale object. */
function lookup(locale: unknown, key: string): string | undefined {
  let current: unknown = locale;
  for (const part of key.split(".")) {
    if (typeof current !== "object" || current === null) return undefined;
    current = (current as Record<string, unknown>)[part];
  }
  return typeof current === "string" ? current : undefined;
}

/** Recursively collect `.tsx` sources under `dir`, excluding test files. */
function collectComponentSources(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      out.push(...collectComponentSources(full));
    } else if (entry.endsWith(".tsx") && !entry.endsWith(".test.tsx")) {
      out.push(full);
    }
  }
  return out;
}

describe("primary create-action labels (GH-343)", () => {
  it("defines every create-action key in both locales", () => {
    const missing: string[] = [];
    for (const [route, key] of Object.entries(CREATE_ACTION_KEYS)) {
      if (lookup(en, key) === undefined) missing.push(`${route}: en.json ${key}`);
      if (lookup(de, key) === undefined) missing.push(`${route}: de.json ${key}`);
    }
    expect(missing).toEqual([]);
  });

  it("labels the result in English, never the gesture or a verb phrase", () => {
    const offenders: string[] = [];
    for (const [route, key] of Object.entries(CREATE_ACTION_KEYS)) {
      const value = lookup(en, key);
      if (value !== undefined && !EN_PATTERN.test(value)) {
        offenders.push(`${route} (${key}): ${JSON.stringify(value)}`);
      }
    }
    expect(offenders, 'expected "New <Entity>"').toEqual([]);
  });

  it("labels the result in German, never a verb phrase", () => {
    const offenders: string[] = [];
    for (const [route, key] of Object.entries(CREATE_ACTION_KEYS)) {
      const value = lookup(de, key);
      if (value !== undefined && !DE_PATTERN.test(value)) {
        offenders.push(`${route} (${key}): ${JSON.stringify(value)}`);
      }
    }
    expect(offenders, 'expected "Neue/Neuer/Neues <Substantiv>"').toEqual([]);
  });

  it("builds no action label from a '+' gesture prefix", () => {
    // Catches `label: `+ ${t("actions.new")}`` — the RequirementEditors
    // regression GH-343 opened with, and the one shape a locale-value rule
    // cannot see because the "+" lives in the component, not the JSON.
    const gesturePrefix = /label:\s*[`'"]\+\s/;
    const offenders: string[] = [];
    for (const file of collectComponentSources(SRC_DIR)) {
      const source = readFileSync(file, "utf-8");
      for (const [index, line] of source.split("\n").entries()) {
        if (gesturePrefix.test(line)) {
          offenders.push(`${relative(SRC_DIR, file)}:${index + 1}: ${line.trim()}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });
});
