/**
 * Token-existence test (Task 7.1, UI-Konzept-Vollrollout).
 *
 * Every `var(--token-name)` reference anywhere in `src/` must correspond to
 * a custom property actually defined in `styles/tokens.css`. This exact bug
 * class bit the codebase twice before: `--font-size-md` and
 * `--color-background` were referenced for a long time without ever being
 * defined, silently falling back to an inherited (or no) value instead of
 * failing loudly. This test catches that class of bug at CI time.
 *
 * Approach mirrors `src/test/ui-ratchet.test.ts`: a small recursive file
 * walker plus regex scanning, no external dependencies.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const SRC_DIR = resolve(__dirname, "..");
const TOKENS_FILE = join(SRC_DIR, "styles", "tokens.css");

/** Recursively collect files under `dir` whose basename matches `extPattern`. */
function collectFiles(dir: string, extPattern: RegExp): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    const stat = statSync(full);
    if (stat.isDirectory()) {
      out.push(...collectFiles(full, extPattern));
    } else if (extPattern.test(entry)) {
      out.push(full);
    }
  }
  return out;
}

/**
 * `.tsx`, `.ts`, `.css`, `.module.css` and `.scss` source files under `src/`,
 * excluding this test file itself — its own docstring/examples contain the
 * literal string `var(--token-name)`, which is documentation, not a real
 * token reference, and would otherwise show up as a false positive.
 */
function collectScannableFiles(dir: string): string[] {
  return collectFiles(dir, /\.tsx$|\.ts$|\.css$|\.scss$/).filter(
    (f) => resolve(f) !== resolve(__filename),
  );
}

/**
 * Parse `tokens.css` and return the set of every `--token-name` custom
 * property defined across ALL blocks (`:root`, `:root[data-theme="light"]`,
 * and any future theme/scope blocks) — the file uses a two-layer
 * `--palette-*` (primitives) / `--color-*` (semantics, per theme) system,
 * plus theme-independent blocks for spacing/typography/etc. A definition is
 * any line of the form `--name: value;` regardless of which block it lives
 * in, so no block-boundary parsing is needed.
 */
function collectDefinedTokens(tokensCss: string): Set<string> {
  const defined = new Set<string>();
  const definitionPattern = /^\s*(--[a-zA-Z0-9-]+)\s*:/gm;
  let match: RegExpExecArray | null;
  while ((match = definitionPattern.exec(tokensCss)) !== null) {
    defined.add(match[1]);
  }
  return defined;
}

/**
 * Collect `--name: value;` declarations found anywhere in `text` (i.e. not
 * restricted to `tokens.css`). CSS allows component-scoped custom
 * properties declared and consumed entirely within one stylesheet (e.g.
 * `.stateNode { --wf-accent: var(--color-primary); ... border-left: 4px
 * solid var(--wf-accent); }` in `WorkflowEditor.module.css`) — a distinct,
 * valid mechanism from the global design-token vocabulary in
 * `styles/tokens.css` and not the bug class this test targets. Declarations
 * are scoped per-file (see `collectDefinedTokens` usage below) so a local
 * variable in one file cannot mask a genuinely undefined global token
 * reference in another.
 */
function collectLocalDeclarations(text: string): Set<string> {
  return collectDefinedTokens(text);
}

interface TokenReference {
  name: string;
  file: string;
  line: number;
}

/**
 * Scan `text` for `var(--token-name)` and `var(--token-name, fallback)`
 * references, returning the token name (never the fallback) plus its
 * 1-based line number.
 */
function collectTokenReferences(text: string, file: string): TokenReference[] {
  const references: TokenReference[] = [];
  const referencePattern = /var\(\s*(--[a-zA-Z0-9-]+)\s*(?:,[^)]*)?\)/g;
  const lines = text.split("\n");
  lines.forEach((line, index) => {
    let match: RegExpExecArray | null;
    referencePattern.lastIndex = 0;
    while ((match = referencePattern.exec(line)) !== null) {
      references.push({ name: match[1], file, line: index + 1 });
    }
  });
  return references;
}

describe("design token existence (Task 7.1)", () => {
  it("every var(--token) reference in src/ resolves to a token defined in styles/tokens.css", () => {
    const tokensCss = readFileSync(TOKENS_FILE, "utf-8");
    const definedTokens = collectDefinedTokens(tokensCss);
    expect(definedTokens.size).toBeGreaterThan(0);

    const files = collectScannableFiles(SRC_DIR);
    const undefinedReferences: TokenReference[] = [];

    for (const file of files) {
      const text = readFileSync(file, "utf-8");
      const localDeclarations = collectLocalDeclarations(text);
      const references = collectTokenReferences(text, file);
      for (const ref of references) {
        if (!definedTokens.has(ref.name) && !localDeclarations.has(ref.name)) {
          undefinedReferences.push(ref);
        }
      }
    }

    if (undefinedReferences.length > 0) {
      const details = undefinedReferences
        .map((ref) => `  ${relative(SRC_DIR, ref.file)}:${ref.line} -> ${ref.name}`)
        .join("\n");
      throw new Error(
        `Found ${undefinedReferences.length} reference(s) to token(s) not defined in styles/tokens.css:\n${details}`,
      );
    }

    expect(undefinedReferences).toEqual([]);
  });
});
