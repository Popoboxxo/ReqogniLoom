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

/**
 * GH-797 — exactly one visible create action per entity list route.
 *
 * The QA sweep behind GH-797 counted the create buttons per route and found
 * three shapes at once: seven routes rendered TWO visible create buttons (the
 * primary `+ {Entity}` plus the guided-interview start as a `secondaryActions`
 * button beside it), five rendered one, and Diagrams rendered the same action
 * as `+ Neues Diagramm` in the header but `Neues Diagramm` in the empty state.
 *
 * The convention that replaced it, pinned here:
 *
 *  1. Each entity list route has exactly one *visible* create action — the
 *     <PageHeader> primary action. The guided-interview start is a second
 *     *create path*, not a variant of the primary one, so it belongs in the
 *     overflow menu (UI concept ch. 12.1: "Genau eine Primäraktion …
 *     Sekundäraktionen ins Überlaufmenü").
 *  2. That action is labelled `+ {Entity}` — `prefixWithPlus` on the same
 *     result-named key the locale rule above already pins.
 *  3. The <EmptyState> next-step action (ch. 13.3) reuses the identical label
 *     shape, so the two never read differently while both are on screen.
 *
 * Baselines is the one conscious exception: creating a baseline is a rare,
 * consequential snapshot rather than routine artifact creation, so its create
 * action stays in the overflow menu (task 5.2 brief; five E2E specs open it
 * through the "⋯" menu). It is named explicitly below rather than left
 * unmentioned, so dropping or moving it stays a deliberate act.
 */

/**
 * Route → component source that owns the route's <PageHeader> primary create
 * action. Explicit for the same reason `CREATE_ACTION_KEYS` is: a new artifact
 * route has to be added here consciously. Settings-style pages
 * (LinkTypeEditor, UserManagement) are not entity list routes and are absent.
 */
const PRIMARY_CREATE_SOURCES: Readonly<Record<string, string>> = {
  "System Requirements": "components/RequirementEditors/RequirementEditors.tsx",
  "Stakeholder Needs": "components/NeedsEditors/NeedsEditors.tsx",
  ADRs: "components/AdrEditors/AdrEditors.tsx",
  Risks: "components/RiskEditors/RiskEditors.tsx",
  Issues: "components/IssueEditors/IssueEditors.tsx",
  "Test Cases": "components/TestCaseEditors/TestCaseEditors.tsx",
  Architecture: "components/ArchitectureEditors/ArchitectureEditors.tsx",
  Glossary: "components/GlossaryView/GlossaryView.tsx",
  Goals: "components/Goals/GoalsPage.tsx",
  ICDs: "components/IcdView/IcdView.tsx",
  Interviews: "components/InterviewEditors/InterviewEditors.tsx",
  "Test Runs": "components/TestRuns/TestRunsList.tsx",
  Traceability: "components/TraceabilityView/TraceabilityView.tsx",
  Diagrams: "components/DiagramView/DiagramView.tsx",
};

/**
 * Routes that start a guided interview instead of (or beside) the dialog
 * form. Each must wire `useInterviewStartCta`'s result through
 * `overflowActions` — never through `secondaryActions`, which renders it as a
 * second visible create button.
 */
const INTERVIEW_CTA_SOURCES: readonly string[] = [
  "components/RequirementEditors/RequirementEditors.tsx",
  "components/NeedsEditors/NeedsEditors.tsx",
  "components/AdrEditors/AdrEditors.tsx",
  "components/RiskEditors/RiskEditors.tsx",
  "components/IssueEditors/IssueEditors.tsx",
  "components/TestCaseEditors/TestCaseEditors.tsx",
  "components/ArchitectureEditors/ArchitectureEditors.tsx",
  "components/Goals/GoalsPage.tsx",
];

/** The route that deliberately keeps creation in the overflow menu. */
const OVERFLOW_ONLY_CREATE = "components/BaselinesView/BaselinesView.tsx";

/** Return the object/JSX-expression literal passed to `propName`, if any. */
function propBlock(source: string, propName: string): string | null {
  const at = source.indexOf(propName);
  if (at < 0) return null;
  const open = source.indexOf("{", at);
  if (open < 0) return null;
  let depth = 0;
  for (let i = open; i < source.length; i++) {
    if (source[i] === "{") depth++;
    else if (source[i] === "}") {
      depth--;
      if (depth === 0) return source.slice(open, i + 1);
    }
  }
  return null;
}

/**
 * Innermost `{ … }` literal enclosing `index`.
 *
 * Walks backwards through the candidate openers and returns the first one
 * whose matching brace closes at or after `index`. Balances plain braces only,
 * which is sufficient here: the action objects below contain no lone `}` in a
 * string.
 */
function enclosingBlock(source: string, index: number): string | null {
  for (let open = index; open >= 0; open--) {
    if (source[open] !== "{") continue;
    let depth = 0;
    for (let i = open; i < source.length; i++) {
      if (source[i] === "{") depth++;
      else if (source[i] === "}") {
        depth--;
        if (depth === 0) {
          if (i >= index) return source.slice(open, i + 1);
          break;
        }
      }
    }
  }
  return null;
}

describe("one visible create action per entity list route (GH-797)", () => {
  it("labels every primary create action with the '+' gesture", () => {
    const offenders: string[] = [];
    for (const [route, relPath] of Object.entries(PRIMARY_CREATE_SOURCES)) {
      const block = propBlock(readFileSync(join(SRC_DIR, relPath), "utf-8"), "primaryAction");
      if (block === null) {
        offenders.push(`${route} (${relPath}): no primaryAction`);
        continue;
      }
      if (!block.includes("prefixWithPlus")) {
        offenders.push(`${route} (${relPath}): primaryAction without prefixWithPlus`);
      }
    }
    expect(offenders, 'expected a "+ {Entity}" primary create action').toEqual([]);
  });

  it("labels every empty-state create action with the same '+' gesture", () => {
    // Diagrams rendered "+ Neues Diagramm" in the header and "Neues Diagramm"
    // in the empty state — the same action under two labels on one screen.
    // Both are now "+ {Entity}"; the header CTA is always on screen next to
    // the empty state (ch. 13.3), so the two must read alike.
    const offenders: string[] = [];
    for (const file of collectComponentSources(SRC_DIR)) {
      const source = readFileSync(file, "utf-8");
      for (const match of source.matchAll(/[-a-z]*-empty-create/g)) {
        const block = enclosingBlock(source, match.index ?? 0);
        if (block === null || !block.includes("prefixWithPlus")) {
          const line = source.slice(0, match.index ?? 0).split("\n").length;
          offenders.push(`${relative(SRC_DIR, file)}:${line}: ${match[0]}`);
        }
      }
    }
    expect(offenders, 'expected every "*empty-create" action to set prefixWithPlus').toEqual([]);
  });

  it("never renders the interview start as a visible secondary header action", () => {
    const offenders: string[] = [];
    for (const file of collectComponentSources(SRC_DIR)) {
      const source = readFileSync(file, "utf-8");
      for (const match of source.matchAll(/secondaryActions=\{\[[\s\S]{0,240}?\]\}/g)) {
        if (match[0].includes("interviewCta")) {
          const line = source.slice(0, match.index ?? 0).split("\n").length;
          offenders.push(`${relative(SRC_DIR, file)}:${line}`);
        }
      }
    }
    expect(offenders, "interview CTA belongs in overflowActions (ch. 12.1)").toEqual([]);
  });

  it("keeps the interview start reachable through the overflow menu", () => {
    const offenders: string[] = [];
    for (const relPath of INTERVIEW_CTA_SOURCES) {
      const source = readFileSync(join(SRC_DIR, relPath), "utf-8");
      if (!source.includes("interviewCta")) {
        offenders.push(`${relPath}: interviewCta missing entirely`);
        continue;
      }
      if (!/overflowActions=\{\[[\s\S]{0,400}?interviewCta/.test(source)) {
        offenders.push(`${relPath}: interviewCta not wired into overflowActions`);
      }
    }
    expect(offenders).toEqual([]);
  });

  it("documents Baselines as a deliberate overflow-only create action", () => {
    // Not an immutable resource — a baseline is created through the "⋯" menu.
    // The assertion makes that a documented choice instead of an oversight:
    // the route must expose the create trigger and must not grow a competing
    // primary header button without this test being updated on purpose.
    const source = readFileSync(join(SRC_DIR, OVERFLOW_ONLY_CREATE), "utf-8");
    expect(source).toContain('testId: "create-baseline-btn"');
    expect(propBlock(source, "primaryAction")).toBeNull();
  });
});
