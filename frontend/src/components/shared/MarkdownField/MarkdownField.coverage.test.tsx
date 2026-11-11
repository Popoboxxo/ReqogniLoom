/**
 * #1287 — the formatting toolbar is preference-aware *everywhere*.
 *
 * `<MarkdownField>` resolves `ui.markdown.toolbar` (auto/on/off) and passes the
 * decision to the one markdown editor this app has
 * (`RequirementEditors/MarkdownPreview`). If another component rendered
 * `<MarkdownToolbar>` directly, it would bypass that resolution and the
 * "Formatierungszeile ein-/ausblendbar" contract would silently break for
 * that field.
 *
 * This guard is intentionally structural: it pins the *rule*, not the current
 * list of call sites. The single allowed renderer is the editor itself.
 */

import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const SRC_DIR = resolve(__dirname, "../../..");
const COMPONENTS_DIR = join(SRC_DIR, "components");

/** The editor implementation owns the toolbar; everyone else uses `<MarkdownField>`. */
const ALLOWED_TOOLBAR_RENDERERS = new Set([
  "components/RequirementEditors/MarkdownPreview.tsx",
]);

function collectTsx(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      out.push(...collectTsx(full));
    } else if (entry.endsWith(".tsx")) {
      out.push(full);
    }
  }
  return out;
}

function toRepoPath(file: string): string {
  return relative(SRC_DIR, file).split(/[\\/]/).join("/");
}

describe("MarkdownField coverage (#1287)", () => {
  it("keeps a single toolbar renderer that MarkdownField can control", () => {
    const renderers = collectTsx(COMPONENTS_DIR)
      .filter((file) => !file.endsWith(".test.tsx"))
      .filter((file) => readFileSync(file, "utf8").includes("<MarkdownToolbar"))
      .map(toRepoPath);

    expect(renderers.sort()).toEqual(
      [...ALLOWED_TOOLBAR_RENDERERS].sort()
    );
  });
});
