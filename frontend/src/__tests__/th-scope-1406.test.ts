/**
 * #1406 — every table header cell declares its `scope`.
 *
 * WCAG 1.3.1 (Info and Relationships): a `<th>` conveys the header relation to
 * screen readers only if it says whether it heads a column or a row. Before
 * this test, 11 of 77 `<th>` elements in the app had no `scope` — five in the
 * user-management table, six in the tri-label overview.
 *
 * The scan is **multi-line safe** on purpose: several tables already put
 * `scope="col"` on the line *after* `<th`, so a line-oriented grep (`<th` on a
 * line without `scope`) reports four false positives (AttributeTable,
 * WorkflowPermissionsSection, CsvImport, MatrixRenderer). Those files are
 * correct and must not be "fixed" a second time. The regex therefore matches
 * the whole tag, attributes across newlines included.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, resolve } from "node:path";

import { describe, expect, it } from "vitest";

const COMPONENTS_ROOT = resolve(process.cwd(), "src/components");

function tsxFiles(directory: string): string[] {
  const found: string[] = [];
  for (const entry of readdirSync(directory)) {
    const path = join(directory, entry);
    if (statSync(path).isDirectory()) {
      found.push(...tsxFiles(path));
      continue;
    }
    if (entry.endsWith(".tsx") && !entry.includes(".test.")) {
      found.push(path);
    }
  }
  return found;
}

/** Every `<th …>` opening tag, attributes may span lines. */
function thTags(source: string): string[] {
  return source.match(/<th\b[^>]*>/g) ?? [];
}

describe("table header scope (#1406)", () => {
  it("finds the header cells at all (guards against a vacuous scan)", () => {
    const total = tsxFiles(COMPONENTS_ROOT).reduce(
      (sum, file) => sum + thTags(readFileSync(file, "utf8")).length,
      0,
    );

    // The repo carried 77 when this test was written. A lower bound keeps the
    // guard meaningful without turning every added table into a test edit.
    expect(total).toBeGreaterThan(60);
  });

  it("declares scope on every <th>, including multi-line tags", () => {
    const offenders: string[] = [];

    for (const file of tsxFiles(COMPONENTS_ROOT)) {
      const source = readFileSync(file, "utf8");
      for (const tag of thTags(source)) {
        if (!/\bscope\s*=/.test(tag)) {
          offenders.push(
            `${file.slice(COMPONENTS_ROOT.length + 1)}: ${tag
              .replace(/\s+/g, " ")
              .slice(0, 120)}`,
          );
        }
      }
    }

    expect(offenders).toEqual([]);
  });
});
