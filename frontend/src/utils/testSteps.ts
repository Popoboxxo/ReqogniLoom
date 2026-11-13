/**
 * Issue #1564: adapters between the typed step shape and the legacy pair.
 *
 * The backend stores and returns `{id, step_type, text}` and normalises any
 * legacy `{step, expected_result}` value it receives. The UI still has two
 * places that think in "action / expected result" pairs (the AI derivation
 * panel and pre-#1564 fixtures), so the conversion lives here once instead of
 * in every widget.
 */

import type {
  LegacyTestCaseStep,
  StepType,
  TestCaseStep,
} from "../api/testcases";

export const STEP_TYPES: readonly StepType[] = [
  "given",
  "when",
  "then",
  "and",
  "but",
] as const;

/** Turn any stored/legacy entry into a typed step. Never throws. */
export function normalizeStep(entry: unknown): TestCaseStep {
  if (entry && typeof entry === "object" && !Array.isArray(entry)) {
    const record = entry as Record<string, unknown>;
    if (typeof record.step_type === "string" && STEP_TYPES.includes(record.step_type as StepType)) {
      return {
        id: typeof record.id === "string" ? record.id : undefined,
        step_type: record.step_type as StepType,
        text: typeof record.text === "string" ? record.text : "",
      };
    }
    if ("step" in record || "expected_result" in record) {
      // A legacy pair is a `when` here; the `then` half is produced by
      // `pairsToSteps`, because one pair maps to up to two typed steps.
      return {
        step_type: "when",
        text: typeof record.step === "string" ? record.step : "",
      };
    }
    return { step_type: "when", text: "" };
  }
  return { step_type: "when", text: String(entry ?? "") };
}

export function newStep(step_type: StepType = "when"): TestCaseStep {
  return { step_type, text: "" };
}

/** Any stored/legacy list -> typed steps (legacy pairs become when + then). */
export function normalizeSteps(steps: unknown): TestCaseStep[] {
  if (!Array.isArray(steps)) return [];
  const hasTyped = steps.some(
    (entry) =>
      entry &&
      typeof entry === "object" &&
      typeof (entry as Record<string, unknown>).step_type === "string"
  );
  if (hasTyped) return steps.map(normalizeStep);
  if (
    steps.some(
      (entry) =>
        entry &&
        typeof entry === "object" &&
        ("step" in (entry as Record<string, unknown>) ||
          "expected_result" in (entry as Record<string, unknown>))
    )
  ) {
    return pairsToSteps(stepsToPairs(steps));
  }
  return steps.map(normalizeStep);
}

/** Typed steps -> action/expected pairs (derive panel layout, tests). */
export function stepsToPairs(steps: unknown): LegacyTestCaseStep[] {
  if (!Array.isArray(steps)) return [];
  const pairs: LegacyTestCaseStep[] = [];
  for (const raw of steps) {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
      pairs.push({ step: String(raw ?? ""), expected_result: "" });
      continue;
    }
    const record = raw as Record<string, unknown>;
    if (typeof record.step_type === "string" && "text" in record) {
      const text = typeof record.text === "string" ? record.text : "";
      if (record.step_type === "then") {
        if (pairs.length === 0) pairs.push({ step: "", expected_result: text });
        else pairs[pairs.length - 1].expected_result = text;
      } else if (record.step_type === "when") {
        pairs.push({ step: text, expected_result: "" });
      } else {
        // given/and/but: keep the text visible without inventing a second
        // column; it belongs to the action side.
        const last = pairs[pairs.length - 1];
        if (last && !last.step) last.step = text;
        else pairs.push({ step: text, expected_result: "" });
      }
      continue;
    }
    if ("step" in record || "expected_result" in record) {
      pairs.push({
        step: typeof record.step === "string" ? record.step : "",
        expected_result:
          typeof record.expected_result === "string" ? record.expected_result : "",
      });
      continue;
    }
    pairs.push({ step: String(raw ?? ""), expected_result: "" });
  }
  return pairs;
}

/** Action/expected pairs -> typed steps (`when`, then `then` when non-empty). */
export function pairsToSteps(pairs: LegacyTestCaseStep[]): TestCaseStep[] {
  const steps: TestCaseStep[] = [];
  for (const pair of pairs) {
    const action = pair.step.trim();
    const expected = pair.expected_result.trim();
    if (action) steps.push({ step_type: "when", text: pair.step });
    if (expected) steps.push({ step_type: "then", text: pair.expected_result });
  }
  return steps;
}
