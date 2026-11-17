/**
 * S4.3 / R2T-003 — one-way ratchet for explicit-any casts in frontend tests.
 *
 * ESLint enforces `@typescript-eslint/no-explicit-any` at 'error' level in
 * every test file that was clean when this gate landed; this test covers the
 * 31 legacy carriers that still hold the frozen baseline. It fails as soon as
 * a new type assertion to `any` appears anywhere in the test tree, and the
 * recorded ceiling can never be raised (only lowered after casts are removed).
 */
import { readdirSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";

import baseline from "./explicit-any.baseline.json";

/** The value at gate time. Hard-coded so re-baselining cannot hide a regression. */
const INITIAL_CEILING = 262;

// Vitest runs with the frontend project root as cwd (see vite.config.ts).
// `import.meta.url` is a virtual http URL under Vitest, so it cannot be used
// with fileURLToPath here.
const srcDir = resolve(process.cwd(), "src");

function collectTestFiles(dir: string): string[] {
  const files: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...collectTestFiles(path));
    } else if (
      /\.test\.(ts|tsx)$/.test(entry.name) &&
      // The measuring instrument must not count its own prose/constant.
      entry.name !== "explicit-any-ratchet.test.ts"
    ) {
      files.push(path);
    }
  }
  return files;
}

/** `\b` before `as` keeps prose such as "has any" out of the count. */
const AS_ANY = /\bas\s+any\b/g;

function countAsAnyCasts(): number {
  return collectTestFiles(srcDir).reduce((sum, file) => {
    const matches = readFileSync(file, "utf8").match(AS_ANY);
    return sum + (matches?.length ?? 0);
  }, 0);
}

describe("explicit-any one-way ratchet (S4.3 / R2T-003)", () => {
  it("has not grown past the frozen explicit-any ceiling", () => {
    const measured = countAsAnyCasts();
    if (measured > baseline.asAnyCasts) {
      throw new Error(
        `R2T-003: ${measured} explicit-any casts in test files exceed the ` +
          `one-way baseline of ${baseline.asAnyCasts}. Remove the new cast(s); ` +
          "never raise the ceiling to make this test pass."
      );
    }
    expect(measured).toBeLessThanOrEqual(baseline.asAnyCasts);
  });

  it("never raises the recorded ceiling above the gate-time value", () => {
    expect(baseline.asAnyCasts).toBeLessThanOrEqual(INITIAL_CEILING);
  });
});
