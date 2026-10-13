/**
 * Failure-artifact record layer for the frontend test run (#1117).
 *
 * Problem this closes: a flaky frontend test failed in a full release run
 * (beta.17), the follow-up run on the same tree was green, and the three
 * failures could never be identified - the log only said "3 failed". Without a
 * name, a class, or a trace, a failure like that is a count, not a finding.
 *
 * This module builds the artifact that makes the next occurrence identifiable
 * instead of countable: one JSON record per failed test with its file, its test
 * name, its error class and a category, plus a run-level summary.
 *
 * Layers, deliberately separated:
 * - this module is pure and is unit-tested directly;
 * - `flaky-artifact-reporter.ts` is the vitest adapter that maps the real
 *   vitest 5 task API onto the input shape defined here.
 *
 * Keeping the adapter out of this file matters: an earlier version folded the
 * vitest task shape into this module and tested that guess, then the reporter
 * silently matched nothing because vitest reports `failed`, not `fail`, and
 * exposes `children` (a `TestCollection`) rather than `tasks`. Pure functions
 * are worth nothing if the pure shape is the wrong one.
 *
 * Category rules:
 * - `timeout`    - vitest's own timeout ("test timed out ...", "Test timed
 *                  out in ...") and hook timeouts. The beta.16 pattern and the
 *                  two known non-determinist cases are timeouts, so this bucket
 *                  is what makes them comparable against each other.
 * - `assertion`  - an `expect` mismatch.
 * - `runtime`    - the test body threw (rendering error, bad mock, unhandled
 *                  rejection).
 * - `other`      - anything else; never silently dropped, so a new failure mode
 *                  shows up as `other` rather than as a missing record.
 */

/** Why a test failed, coarsely. Timeouts are their own bucket by design. */
export type FlakyFailureCategory = "timeout" | "assertion" | "runtime" | "other";

/** One failed test, reduced to what is needed to recognise it next time. */
export interface FlakyFailureRecord {
  /** Test file path as the reporter resolved it. */
  file: string;
  /**
   * Path of suite/test names leading to the failing test ("a > b > c"), as
   * vitest's own full name provides it. Kept as the single string because that
   * is the form the source hands over - re-deriving a nested array here would
   * be a guess about the split character rather than the real thing.
   */
  namePath: string;
  /** The failing test's own name (last segment of `namePath`), when derivable. */
  testName: string | null;
  category: FlakyFailureCategory;
  /** Error message, trimmed to a bounded length. */
  errorMessage: string | null;
  /** First line of the error stack, when present - the code site, not the message. */
  errorLocation: string | null;
  /** Test duration in milliseconds, when the reporter resolved it. */
  durationMs: number | null;
}

/** One file's failures, in the shape the reporter produced them. */
export interface FlakyFailureFile {
  file: string;
  failures: readonly FlakyFailureRecord[];
}

/** The artifact itself. Serialised as JSON by the reporter. */
export interface FlakyFailureArtifact {
  /** ISO timestamp of the run that produced it. */
  finishedAt: string;
  /** Number of failed tests across all files. */
  failed: number;
  /** Number of files containing at least one failure. */
  files: number;
  /** Failure counts per category, always all four keys present. */
  byCategory: Record<FlakyFailureCategory, number>;
  files_failures: readonly FlakyFailureFile[];
}

/** Maximum length of an error message kept in the record. */
export const ERROR_MESSAGE_LIMIT = 2000;

/**
 * One failed test as the reporter extracted it from the vitest task API. This
 * is the adapter's output, in other words - the reporter owns turning vitest's
 * `TestCase` into this, and this module owns the rest.
 */
export interface FlakyTestInput {
  file: string;
  /** Full test name with all parent suites ("a > b > c"), null when unknown. */
  fullName: string | null;
  /** The test's own name, null when unknown. */
  name: string | null;
  error: FlakyErrorLike | null;
  durationMs: number | null;
}

/** Error shape produced by vitest's error normalisation. */
export interface FlakyErrorLike {
  message?: string;
  stack?: string;
  name?: string;
}

/**
 * Classify an error into a coarse category.
 *
 * Deliberately pattern-based rather than instanceof-based: vitest rethrows the
 * original error, so the class name is whatever the test threw, not what
 * failed. Only timeout patterns are semantic (they identify a specific
 * non-determinism class); the rest is a best-effort bucket.
 */
export function classifyFailure(error: FlakyErrorLike | null | undefined): FlakyFailureCategory {
  if (!error) return "other";

  const message = typeof error.message === "string" ? error.message : "";
  const name = typeof error.name === "string" ? error.name : "";

  if (isTimeout({ message, name })) return "timeout";
  if (isAssertion({ message, name })) return "assertion";
  // A failure with neither a name nor a message carries no evidence about what
  // went wrong - bucketing it as `runtime` would assert a cause that is not
  // there. `other` records still land in the artifact, so nothing is dropped.
  if (name.length > 0 || message.length > 0) return "runtime";
  return "other";
}

function isTimeout(candidate: { message: string; name: string }): boolean {
  // vitest 3+: "test timed out in 5000ms." / "Test timed out in 5000ms"
  // hook timeouts: "hook timed out in ..." (case-insensitive)
  if (/timed out in\s/i.test(candidate.message)) return true;
  // A thrown Error whose name marks the timeout, e.g. TimeoutError / DOMException.
  if (/^timeouterror$/i.test(candidate.name)) return true;
  // jsdom/playwright style message without the vitest phrasing.
  if (/^timeout/i.test(candidate.message.trim())) return true;
  return false;
}

function isAssertion(candidate: { message: string; name: string }): boolean {
  if (/^AssertionError$/.test(candidate.name)) return true;
  // Vitest's expect failures carry the expected/received diff block.
  if (/expected .* to (be|equal|match|have|contain)/i.test(candidate.message)) return true;
  if (/^\s*Expected:/.test(candidate.message) && /^\s*Received:/m.test(candidate.message)) return true;
  return false;
}

/** Trim an error message to `ERROR_MESSAGE_LIMIT`, keeping it a single readable blob. */
export function boundedMessage(message: string | undefined | null): string | null {
  if (typeof message !== "string" || message.length === 0) return null;
  const collapsed = message.trim();
  if (collapsed.length <= ERROR_MESSAGE_LIMIT) return collapsed;
  return `${collapsed.slice(0, ERROR_MESSAGE_LIMIT)}…`;
}

/**
 * Extract the first useful code location from a stack: the first frame that is
 * not inside node_modules, or the first frame if none qualifies. Returns `null`
 * when there is no stack at all - an artifact without any location is still a
 * valid record.
 */
export function errorLocation(stack: string | undefined | null): string | null {
  if (typeof stack !== "string" || stack.trim().length === 0) return null;
  const frames = stack
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.startsWith("at "));
  if (frames.length === 0) return null;
  const firstAppFrame = frames.find((line) => !line.includes("node_modules"));
  return firstAppFrame ?? frames[0];
}

/** Derive the failing test's own name from vitest's `a > b > c` full name. */
export function testNameFrom(fullName: string | null, fallback: string | null): string | null {
  if (fallback) return fallback;
  if (!fullName) return null;
  const segments = fullName.split(">").map((segment) => segment.trim());
  return segments[segments.length - 1] || null;
}

const emptyCategories = (): Record<FlakyFailureCategory, number> => ({
  timeout: 0,
  assertion: 0,
  runtime: 0,
  other: 0,
});

/**
 * Build the artifact from already-extracted failed tests.
 *
 * A file with no failures contributes nothing, so a fully green run produces
 * an artifact with `failed: 0` and no file entries rather than no artifact at
 * all - see the reporter's docstring for why a green artifact is the point.
 */
export function buildArtifact(
  tests: readonly FlakyTestInput[] | null | undefined,
  finishedAt: string = new Date().toISOString(),
): FlakyFailureArtifact {
  const byCategory = emptyCategories();
  const byFile = new Map<string, FlakyFailureRecord[]>();

  for (const test of tests ?? []) {
    const record: FlakyFailureRecord = {
      file: test.file,
      namePath: test.fullName ?? test.name ?? "<unknown test>",
      testName: testNameFrom(test.fullName, test.name),
      category: classifyFailure(test.error),
      errorMessage: boundedMessage(test.error?.message),
      errorLocation: errorLocation(test.error?.stack),
      durationMs: typeof test.durationMs === "number" ? test.durationMs : null,
    };
    byCategory[record.category] += 1;
    const bucket = byFile.get(record.file);
    if (bucket) bucket.push(record);
    else byFile.set(record.file, [record]);
  }

  const files: FlakyFailureFile[] = [...byFile.entries()].map(([file, failures]) => ({ file, failures }));
  let failed = 0;
  for (const file of files) failed += file.failures.length;

  return {
    finishedAt,
    failed,
    files: files.length,
    byCategory,
    files_failures: files,
  };
}

/** Serialise the artifact for writing. */
export function serialiseArtifact(artifact: FlakyFailureArtifact): string {
  return `${JSON.stringify(artifact, null, 2)}\n`;
}
