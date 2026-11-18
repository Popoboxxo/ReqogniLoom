/**
 * Guard: RequirementBundleExportPanel must not carry static inline styles
 * (UI-007 / S3.4 WP-B).
 *
 * Regression this closes
 * -----------------------
 * The panel used a module-level `const styles: Record<string, CSSProperties>`
 * whose values were all static strings / `var()` references, referenced at 25
 * `style={styles.foo}` sites. `local/no-static-inline-style` (gap 4: hoisted
 * identifiers are never inspected) and the now-empty legacy allow-list did not
 * catch it. The declarations were migrated 1:1 onto a co-located CSS Module.
 *
 * Purely static source-level check — no render, no dev server, no CSS-Module
 * processing by Vitest. RED before the migration, GREEN after.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

const PANEL_PATH = resolve(
  __dirname,
  "..",
  "components",
  "RequirementBundleExport",
  "RequirementBundleExportPanel.tsx"
);
const CSS_MODULE_PATH = resolve(
  __dirname,
  "..",
  "components",
  "RequirementBundleExport",
  "RequirementBundleExportPanel.module.css"
);

/** Blank out block and line comments so comment prose cannot trip the scan. */
function withoutComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/[^\n]*/g, "");
}

describe("RequirementBundleExportPanel — inline-style guard", () => {
  const source = readFileSync(PANEL_PATH, "utf-8");
  const code = withoutComments(source);

  it("has zero style={ inline-style sites", () => {
    const sites = code.match(/style=\{/g);
    expect(sites, `found ${sites?.length ?? 0} style={ site(s)} in the panel source`).toBeNull();
  });

  it("has no CSSProperties style record", () => {
    expect(code).not.toMatch(/CSSProperties/);
  });

  it("imports the co-located CSS Module", () => {
    expect(code).toMatch(/import styles from "\.\/RequirementBundleExportPanel\.module\.css";/);
  });

  it("defines every referenced className as a selector in the CSS Module", () => {
    const css = readFileSync(CSS_MODULE_PATH, "utf-8");
    const referenced = new Set(
      Array.from(code.matchAll(/className=\{styles\.([A-Za-z]+)\}/g), (match) => match[1])
    );
    expect(referenced.size).toBeGreaterThan(0);
    for (const name of referenced) {
      expect(css, `.${name} selector missing from CSS Module`).toMatch(
        new RegExp(`\\.${name}\\s*\\{`)
      );
    }
  });
});
