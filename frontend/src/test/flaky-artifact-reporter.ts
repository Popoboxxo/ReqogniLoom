/**
 * Vitest reporter that writes a machine-readable failure artifact (#1117).
 *
 * Why: the beta.17 release cut produced 3 frontend failures that were never
 * identified - the log counted them, then a re-run on the same tree was green.
 * Nobody could name them, so nobody could compare them against the two known
 * non-determinist timeout cases in beta.16. A count is not a finding.
 *
 * What it writes: `test-results/flaky-failures-<timestamp>.json`, one record
 * per failed test (file, full name, category, error message, first
 * application-frame location, duration) plus a run-level category summary.
 * The artifact is written for **every** run, green ones included, so the
 * absence of a record is itself evidence - a green artifact proves the run was
 * instrumented, a missing one proves it was not.
 *
 * The record shape and the classification live in `flaky-artifact.ts` and are
 * unit-tested there; this file is only the adapter onto vitest's task API.
 *
 * API note (vitest 5.0.3, verified against node_modules/dist, not guessed):
 * - the reporter hook is `onTestRunEnd(modules, unhandledErrors, reason)`.
 *   An earlier draft used `onFinished`, which is the *websocket* event name,
 *   not a reporter method - the reporter loaded fine and silently never fired.
 * - a `TestModule` exposes `children`, a `TestCollection`, not `tasks`. It has
 *   no array interface, only `.array()`, `.size`, `.allTests()` and iteration.
 * - state values are the full words: `passed`/`skipped`/`pending`/`failed`.
 *   `failed`, not `fail` - the earlier draft matched `"fail"` and collected
 *   zero records while every test in the run had just failed.
 */

import { mkdir, writeFile } from "node:fs/promises";
import { dirname, isAbsolute, join, resolve } from "node:path";
import type { Reporter, TestCase, TestModule, TestResultFailed } from "vitest/node";
import { buildArtifact, serialiseArtifact, type FlakyTestInput } from "./flaky-artifact";

/**
 * Where artifacts land. `test-results/` is already git-ignored, so a local run
 * never dirties the tree; `FRONTEND_FLAKY_ARTIFACT_DIR` overrides it for CI, so
 * an upload step can point at a per-job path instead of a shared one.
 *
 * Read per call rather than at module scope: the module is evaluated when the
 * reporter is registered, so a module-scope read would freeze whatever the
 * environment happened to be at that point.
 */
function artifactDir(): string {
  return process.env.FRONTEND_FLAKY_ARTIFACT_DIR ?? "test-results";
}

/**
 * Extract one failed test into the record layer's input shape.
 *
 * `allTests("failed")` is the API's own filter, so nested suites and their
 * tests are covered without reimplementing a walk. The state literal is passed
 * as the API's own type so a typo fails at compile time rather than silently
 * yielding an empty artifact.
 */
function toRecord(module: TestModule, testCase: TestCase): FlakyTestInput {
  const result = testCase.result() as TestResultFailed | undefined;
  const diagnostic = testCase.diagnostic();
  const errors = result?.errors;
  return {
    file: module.moduleId,
    fullName: typeof testCase.fullName === "string" ? testCase.fullName : null,
    name: typeof testCase.name === "string" ? testCase.name : null,
    error: errors && errors.length > 0 ? { message: errors[0].message, stack: errors[0].stack, name: undefined } : null,
    durationMs: typeof diagnostic?.duration === "number" ? diagnostic.duration : null,
  };
}

/** Map every module's failed tests into the record layer's input shape. */
function collect(testModules: readonly TestModule[] | undefined): FlakyTestInput[] {
  const records: FlakyTestInput[] = [];
  for (const module of testModules ?? []) {
    const collection: { allTests?: (state?: unknown) => Iterable<TestCase> } = module.children ?? {};
    if (typeof collection.allTests !== "function") continue;
    for (const testCase of collection.allTests("failed")) {
      records.push(toRecord(module, testCase));
    }
  }
  return records;
}

function summarise(artifact: { failed: number; files: number; byCategory: Record<string, number> }): string {
  const cats = Object.entries(artifact.byCategory)
    .filter(([, count]) => count > 0)
    .map(([category, count]) => `${count} ${category}`)
    .join(", ");
  return `${artifact.failed} failure(s) in ${artifact.files} file(s)${cats ? ` (${cats})` : ""}`;
}

function artifactPath(dir: string, timestamp: string): string {
  const base = isAbsolute(dir) ? dir : resolve(process.cwd(), dir);
  return join(base, `flaky-failures-${timestamp}.json`);
}

/**
 * Reporter. `onTestRunEnd` runs after the run settles, so this is the only hook
 * needed. Writing is best-effort by design: a reporter must never be the thing
 * that turns a red suite into a crashing runner, so an I/O failure is reported
 * on stderr and swallowed - the suite's own exit status is the verdict, not
 * this file's existence.
 */
export default class FlakyArtifactReporter implements Reporter {
  onInit(): void {
    process.stderr.write(`[flaky-artifact] reporter loaded, dir=${artifactDir()}\n`);
  }

  async onTestRunEnd(
    testModules?: readonly TestModule[],
    unhandledErrors?: readonly unknown[],
  ): Promise<void> {
    try {
      const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
      const artifact = buildArtifact(collect(testModules), new Date().toISOString());
      const path = artifactPath(artifactDir(), timestamp);
      await mkdir(dirname(path), { recursive: true });
      await writeFile(path, serialiseArtifact(artifact), "utf8");

      const lines = [`[flaky-artifact] ${summarise(artifact)} -> ${path}`];
      // Vitest keeps unhandled errors out of the task tree; a crashed worker
      // would otherwise produce an artifact with `failed: 0` that looks like a
      // green run that was instrumented for nothing.
      const unhandled = Array.isArray(unhandledErrors) ? unhandledErrors.length : 0;
      if (unhandled > 0) {
        lines.push(`[flaky-artifact] ${unhandled} unhandled error(s) outside the task tree`);
      }
      process.stderr.write(`${lines.join("\n")}\n`);
    } catch (error) {
      process.stderr.write(
        `[flaky-artifact] could not write the failure artifact: ${
          error instanceof Error ? error.message : String(error)
        }\n`,
      );
    }
  }
}
