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

/**
 * Structural (non-themeable) custom properties consumed via `var(--name)`
 * in stylesheets but *set* dynamically per element through React inline
 * styles (`style={{ ['--name']: value }}`), not via a declaration in
 * tokens.css.
 *
 * These are not design tokens: they carry per-instance layout state
 * (e.g. tree depth for connector-line geometry), vary per row/node rather
 * than globally, and are meaningless as a themable global default. Adding
 * them to tokens.css would create a fake token entry just to silence this
 * test — hence this explicit, documented allow-list instead.
 *
 * When adding a name here:
 *  1. Confirm the property is set inline per element (search for the name
 *     inside a `style={{ ... }}` block) and is purely structural.
 *  2. Reference the defining component below so the exemption is auditable.
 */
const STRUCTURAL_INLINE_STYLE_TOKENS: ReadonlyMap<string, string> = new Map([
  [
    "--tree-depth",
    "WorkspaceTree/workspace-tree.tsx sets it per row <li> from the node depth; workspace-tree.module.css uses it to offset connector lines (var(--tree-depth, 0)).",
  ],
]);

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

    // Structural inline-style tokens are exempt only when they are NOT also
    // accidentally defined in tokens.css — if someone adds a definition there,
    // the global one wins and the exemption must be re-evaluated.
    const exempt = [...STRUCTURAL_INLINE_STYLE_TOKENS.keys()].filter(
      (name) => !definedTokens.has(name),
    );
    const filteredReferences = undefinedReferences.filter(
      (ref) => !exempt.includes(ref.name),
    );

    if (filteredReferences.length > 0) {
      const details = filteredReferences
        .map((ref) => `  ${relative(SRC_DIR, ref.file)}:${ref.line} -> ${ref.name}`)
        .join("\n");
      throw new Error(
        `Found ${filteredReferences.length} reference(s) to token(s) not defined in styles/tokens.css:\n${details}`,
      );
    }

    expect(filteredReferences).toEqual([]);
  });

  it("every structural inline-style exemption still points at an actually-referenced token", () => {
    // Guards against stale exemptions: if the consuming stylesheet is ever
    // refactored away, the allow-list entry should be removed too, not left
    // behind as dead documentation.
    const files = collectScannableFiles(SRC_DIR);
    const referencedNames = new Set<string>();
    for (const file of files) {
      const text = readFileSync(file, "utf-8");
      for (const ref of collectTokenReferences(text, file)) {
        referencedNames.add(ref.name);
      }
    }

    for (const [name] of STRUCTURAL_INLINE_STYLE_TOKENS) {
      expect(
        referencedNames.has(name),
        `stale exemption: '${name}' is listed in STRUCTURAL_INLINE_STYLE_TOKENS but no longer referenced anywhere in src/`,
      ).toBe(true);
    }
  });
});

/**
 * Per-theme key-set parity (multi-palette theming Phase 3, Task 2, issue
 * #568). The single generic scanner above only confirms every `var(--x)`
 * *reference* resolves to *some* declaration somewhere in the file — it does
 * not confirm that each named theme block (`:root[data-theme="..."]`)
 * defines the SAME set of `--color-*` semantic tokens as the others. A theme
 * block that is missing a token would not be caught by the scanner above
 * (the token is still "defined" elsewhere, e.g. in the `dark` block), but
 * would silently fall back to an unstyled/inherited value for that token
 * whenever the theme is active — exactly the bug class Task 7.1 was
 * written to catch, just one layer down (per-theme instead of global).
 */

interface CssBlock {
  /** `null` for a bare `:root {}` block, else the `data-theme` value. */
  theme: string | null;
  body: string;
}

/**
 * Split `tokensCss` into its top-level `:root {...}` /
 * `:root[data-theme="id"] {...}` blocks. Declaration values never contain a
 * literal `{`/`}`, but doc comments occasionally do (e.g. a `{id}` path
 * placeholder in a code example inside a comment) — a naive non-greedy match
 * up to the first `}` would stop early on those. Comments are stripped first
 * so only real block-boundary braces remain, then a simple depth counter
 * finds each top-level block's true extent.
 */
function collectCssBlocks(tokensCss: string): CssBlock[] {
  const withoutComments = tokensCss.replace(/\/\*[\s\S]*?\*\//g, (comment) =>
    // Preserve line count (for debuggability) and non-brace length roughly,
    // while removing any brace characters the comment body might contain.
    comment.replace(/[{}]/g, " "),
  );

  const blocks: CssBlock[] = [];
  const selectorPattern = /:root(?:\[data-theme="([a-zA-Z0-9_-]+)"\])?\s*\{/g;
  let match: RegExpExecArray | null;
  while ((match = selectorPattern.exec(withoutComments)) !== null) {
    const bodyStart = selectorPattern.lastIndex;
    let depth = 1;
    let i = bodyStart;
    while (i < withoutComments.length && depth > 0) {
      if (withoutComments[i] === "{") depth++;
      else if (withoutComments[i] === "}") depth--;
      i++;
    }
    const bodyEnd = i - 1; // position of the matching closing brace
    blocks.push({ theme: match[1] ?? null, body: withoutComments.slice(bodyStart, bodyEnd) });
    selectorPattern.lastIndex = i;
  }
  return blocks;
}

/** `--color-*` token names (not `--palette-*`, `--space-*`, etc.) defined directly in `body`. */
function collectColorTokenNames(body: string): Set<string> {
  const names = new Set<string>();
  const pattern = /^\s*(--color-[a-zA-Z0-9-]+)\s*:/gm;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(body)) !== null) {
    names.add(match[1]);
  }
  return names;
}

describe("per-theme --color-* key-set parity (theming phase 3, Task 2, #568)", () => {
  const tokensCss = readFileSync(TOKENS_FILE, "utf-8");
  const blocks = collectCssBlocks(tokensCss);

  // The `dark` theme has no `data-theme` attribute (it lives on bare
  // `:root {}` so it also applies before ThemeContext writes data-theme onto
  // <html>) — tokens.css has multiple bare `:root {}` blocks (primitives,
  // dark semantics, theme-independent spacing/typography), so the reference
  // key set is the union of `--color-*` names across all of them; only the
  // dark-semantics block actually contains any.
  const darkColorTokens = new Set<string>();
  for (const block of blocks) {
    if (block.theme === null) {
      for (const name of collectColorTokenNames(block.body)) {
        darkColorTokens.add(name);
      }
    }
  }

  it("the dark (bare :root) block defines a non-trivial set of --color-* tokens", () => {
    expect(darkColorTokens.size).toBeGreaterThan(0);
  });

  it.each(["bauhaus", "nordic", "sepia"])(
    "theme '%s' defines the same --color-* key set as the dark theme",
    (themeId) => {
      const themeBlock = blocks.find((b) => b.theme === themeId);
      expect(themeBlock, `expected a :root[data-theme="${themeId}"] block in tokens.css`).toBeDefined();

      const themeColorTokens = collectColorTokenNames(themeBlock!.body);
      const darkList = Array.from(darkColorTokens).sort();
      const themeList = Array.from(themeColorTokens).sort();

      const missing = darkList.filter((name) => !themeColorTokens.has(name));
      const extra = themeList.filter((name) => !darkColorTokens.has(name));

      expect(
        missing,
        `theme '${themeId}' is missing --color-* tokens present in dark: ${missing.join(", ")}`,
      ).toEqual([]);
      expect(
        extra,
        `theme '${themeId}' defines --color-* tokens not present in dark: ${extra.join(", ")}`,
      ).toEqual([]);
      expect(themeList).toEqual(darkList);
    },
  );
});
