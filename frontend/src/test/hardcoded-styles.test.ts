/**
 * Static guard against hardcoded colour literals (proposal V2, plan leftovers).
 *
 * The project's design system puts every colour in `src/styles/tokens.css`
 * (primitive layer: raw values allowed, semantic layer: `var(--palette-*)`
 * references only). Components must consume the semantic tokens — either via
 * `var(--color-*)` in CSS or via a CSS class/module — so a theme switch
 * (design-system themes, dark mode, workspace themes) recolours them for free.
 *
 * A literal such as `#4f6ef7` or `rgba(99, 102, 241, 0.25)` in a component
 * silently opts out of that: it stays the same in every theme, and it is
 * invisible to `theme-contrast.test.ts`. `ui-ratchet.test.ts` already ratchets
 * hex literals under `src/components/`, but not the rest of `src/`, and not
 * `rgb()/rgba()/hsl()/hsla()` at all.
 *
 * What this file scans: every `*.ts`, `*.tsx` and `*.css` file under
 * `frontend/src/`, minus
 *
 *   - `src/styles/tokens.css` — the one place raw values are *supposed* to
 *     live (UI concept ch. 8.6). Not a migration target.
 *   - `src/test/**`, `**\/*.test.ts(x)`, `**\/*.spec.ts(x)`,
 *     `**\/__tests__/**`, `**\/__mocks__/**` — tests and fixtures may use
 *     literals freely (assertions, expected values, fake canvas stubs).
 *   - `src/i18n/locales/**` — translation data, no styles.
 *
 * Rules:
 *   - `*.ts` / `*.tsx`: no hex colour, no `rgb()/rgba()/hsl()/hsla()` literal.
 *   - `*.css`: same, but `var(--...)` is always fine (that is the token
 *     reference form); only the literal fallback/arg form is flagged.
 *   - `rgb(var(--color-x-rgb), 0.5)` is *allowed*: its arguments are a token
 *     reference, not a literal. Only a first argument that is not `var(...)`
 *     counts as hardcoded.
 *   - A 3-character hex match made of digits only (`#317`) is treated as a
 *     GitHub issue reference, not a colour — this codebase writes issue
 *     numbers inline everywhere. A real colour of that form should be written
 *     in six digits anyway; 6- and 8-digit all-digit values (`#000000`) are
 *     still flagged.
 *
 * Known, documented exceptions live in `BASELINE` below ("Bestand, bei
 * Gelegenheit abbauen"): each entry pins the *current* number of violations
 * for that file, so the test starts green but fails the moment a file grows a
 * new literal. Lowering an entry after a cleanup is expected; raising one
 * needs the same justification as the entry's `reason` and should be rare.
 *
 * Failures name the file and line, so a new violation is trivially located.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const SRC_DIR = resolve(__dirname, '..');

/** The only file allowed to contain raw colour values (token primitives). */
const TOKENS_FILE = 'styles/tokens.css';

/** Directory names never scanned (tests, fixtures, generated mocks). */
const EXCLUDED_DIR_NAMES = new Set(['test', '__tests__', '__mocks__']);

/** Path prefixes (relative to `src/`) never scanned. */
const EXCLUDED_PREFIXES = ['i18n/locales/'];

/** `*.test.ts`, `*.spec.tsx`, … are test code, not production styles. */
const TEST_FILE_PATTERN = /\.(test|spec)\.tsx?$/;

/**
 * A hex colour: `#rgb`, `#rrggbb` or `#rrggbbaa`. The trailing lookahead keeps
 * a longer run of hex characters (`#abcdef0` in an id-ish string) from being
 * matched half-way.
 */
const HEX_COLOR_PATTERN = /#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3})(?![0-9a-fA-F])/g;

/** Colour-function literals: `rgb(`, `rgba(`, `hsl(`, `hsla(` (case-insensitive). */
const COLOR_FUNCTION_PATTERN = /\b(?:rgba?|hsla?)\(/gi;

/**
 * Digits-only 3-character hex matches are issue references (`#317`), not
 * colours — see the file docstring.
 */
const ISSUE_REFERENCE_PATTERN = /^#[0-9]{3}$/;

/** A violation as reported to the test failure message. */
export type ColorViolation = {
  /** Path relative to `src/`, POSIX separators. */
  readonly file: string;
  /** 1-based line number in the original file. */
  readonly line: number;
  /** The offending literal, trimmed. */
  readonly literal: string;
};

type BaselineEntry = {
  /** Highest number of violations tolerated in this file. */
  readonly count: number;
  /** Why these literals exist and have not been migrated yet. */
  readonly reason: string;
};

/**
 * Known violations at the time this guard was introduced (2026-11-13).
 *
 * Every entry is *existing debt*, not an endorsement: the count is a ceiling,
 * not a target. New files must not appear here — fix the literal instead
 * (use a token, a CSS class, or `rgb(var(--color-…-rgb), α)`).
 */
const BASELINE: Readonly<Record<string, BaselineEntry>> = {
  // Fabric.js draws into a <canvas> and only accepts real colour strings, so
  // these cannot be CSS custom properties. Kept as-is until the canvas layer
  // gets a token->literal resolver (same exception class as
  // `ui-ratchet.test.ts`'s CanvasEditor entry).
  'components/canvas/CanvasEditor.tsx': {
    count: 15,
    reason: 'Fabric.js canvas engine requires literal colour strings; no token resolver yet.',
  },
  'components/canvas/canvas-geometry.ts': {
    count: 1,
    reason: 'Fallback stroke colour for a Fabric.js object without a stroke.',
  },
  'components/canvas/use-canvas-tool-settings.ts': {
    count: 2,
    reason: 'Initial tool colours for the Fabric.js canvas (state defaults).',
  },
  'styles/components/CanvasEditor.module.css': {
    count: 2,
    reason: 'Canvas chrome shadows; no shadow token with this alpha exists.',
  },
  // ASIL safety-integrity badges: the palette encodes a certification scale
  // (gray/amber/orange/red/dark red) and is deliberately theme-independent.
  'utils/asilUtils.ts': {
    count: 18,
    reason:
      'ASIL badge colours encode a fixed safety-integrity scale; theme-independent by design.',
  },
  // `var(--token, #fallback)` pairs: the token wins everywhere it is defined;
  // the fallback only matters for a consumer without tokens.css (print/export).
  'components/AllocationGraph/buildGraph.ts': {
    count: 2,
    reason: '`var(--token, #fallback)` strokes for the allocation graph.',
  },
  'components/DiagramView/diagram-view-shared.ts': {
    count: 2,
    reason: '`var(--color-danger, #ef4444)` fallbacks for the diagram preview.',
  },
  'components/DiagramGraphEditor/GraphEdge.tsx': {
    count: 1,
    reason: 'Containment edge colour has no adequately close token (see tokens.css).',
  },
  // Focus-ring / hover-glow shadows: alpha variants of a palette colour that
  // the token layer does not expose as a ready-made shadow.
  'components/DiagramGraphEditor/DiagramGraphEditor.module.css': {
    count: 12,
    reason: 'Focus-ring and node-glow shadows with per-state alpha.',
  },
  'components/WorkflowEditor/WorkflowEditor.module.css': {
    count: 15,
    reason: 'Focus-ring, node-glow and canvas-overlay shadows with per-state alpha.',
  },
  'components/NavigationShell/SidebarNavigation.module.css': {
    count: 1,
    reason: 'Selected-nav focus ring using a primary-alpha shadow.',
  },
  'components/Audit/audit-dashboard.module.css': {
    count: 1,
    reason: '`var(--shadow-md, ...)` fallback for the audit dashboard.',
  },
  'components/shared/Dialog/Dialog.module.css': {
    count: 1,
    reason: 'Modal overlay dim layer; no overlay token exists yet.',
  },
  'styles/global.css': {
    count: 1,
    reason: '`var(--shadow-sm, ...)` fallback for the base button shadow.',
  },
};

/** Recursively collect production source files under `dir`. */
function collectSourceFiles(dir: string, files: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      if (!EXCLUDED_DIR_NAMES.has(entry)) {
        collectSourceFiles(full, files);
      }
      continue;
    }
    if (!/\.(ts|tsx|css)$/.test(entry) || TEST_FILE_PATTERN.test(entry)) {
      continue;
    }
    const relativePath = full
      .slice(SRC_DIR.length + 1)
      .split('\\')
      .join('/');
    if (relativePath === TOKENS_FILE) {
      continue;
    }
    if (EXCLUDED_PREFIXES.some((prefix) => relativePath.startsWith(prefix))) {
      continue;
    }
    files.push(full);
  }
  return files;
}

/**
 * Blank out `/* … *\/` block comments while preserving line numbers.
 *
 * A multi-line comment must not shift the reported line of a later hit, so
 * every non-newline character is replaced by a space instead of deleting the
 * comment outright.
 */
function blankBlockComments(text: string): string {
  return text.replace(/\/\*[\s\S]*?\*\//g, (comment) => comment.replace(/[^\n]/g, ' '));
}

/**
 * Blank out a `//` line comment, preserving the line length.
 *
 * Deliberately naive (first `//` wins): a `//` inside a string literal (a URL
 * in a test id, say) would blank the rest of its line. That can only ever
 * *hide* a violation on that same line, never invent one — the acceptable
 * trade-off for not shipping a JS tokenizer in a lint test.
 */
function blankLineComment(line: string): string {
  const marker = line.indexOf('//');
  return marker === -1 ? line : line.slice(0, marker) + ' '.repeat(line.length - marker);
}

/** Return the argument text of the call whose `(` is at `openIndex`, plus its end. */
function readCall(text: string, openIndex: number): { argument: string; endIndex: number } {
  let depth = 0;
  for (let index = openIndex; index < text.length; index += 1) {
    const character = text[index];
    if (character === '(') {
      depth += 1;
    } else if (character === ')') {
      depth -= 1;
      if (depth === 0) {
        return { argument: text.slice(openIndex + 1, index), endIndex: index };
      }
    }
  }
  return { argument: text.slice(openIndex + 1), endIndex: text.length - 1 };
}

/** Collapse whitespace and cap the length, for a one-line failure message. */
function abbreviate(text: string, maxLength = 60): string {
  const collapsed = text.replace(/\s+/g, ' ').trim();
  return collapsed.length > maxLength ? `${collapsed.slice(0, maxLength)}…` : collapsed;
}

/**
 * Find hardcoded colour literals in one source text.
 *
 * Exported for the scanner's own unit tests below — a lint that silently
 * stops matching is worse than no lint.
 */
export function findColorViolations(text: string, file: string, suffix: string): ColorViolation[] {
  const isCss = suffix === '.css';
  // Comments are blanked (not deleted) so indices and line numbers stay those
  // of the original file. Line comments only exist in JS/TS, not in CSS.
  const lines = blankBlockComments(text)
    .split('\n')
    .map((line) => (isCss ? line : blankLineComment(line)));
  const scanText = lines.join('\n');
  const violations: ColorViolation[] = [];

  lines.forEach((line, index) => {
    for (const match of line.matchAll(HEX_COLOR_PATTERN)) {
      const literal = match[0];
      if (ISSUE_REFERENCE_PATTERN.test(literal)) {
        continue;
      }
      violations.push({ file, line: index + 1, literal });
    }
  });

  // Functions are matched over the whole text so `rgba(\n  var(--x)\n)` is
  // still recognised as a token reference; the line is derived from the index.
  for (const match of scanText.matchAll(COLOR_FUNCTION_PATTERN)) {
    const openIndex = match.index + match[0].length - 1;
    const { argument, endIndex } = readCall(scanText, openIndex);
    // `rgb(var(--color-x-rgb), 0.5)` is a token reference, not a literal.
    if (argument.trim().toLowerCase().startsWith('var(')) {
      continue;
    }
    const line = scanText.slice(0, openIndex).split('\n').length;
    violations.push({
      file,
      line,
      literal: abbreviate(scanText.slice(match.index, endIndex + 1)),
    });
  }

  return violations.sort((a, b) => a.line - b.line);
}

/** Scan the whole production tree and group the hits per file. */
function scanTree(): Map<string, ColorViolation[]> {
  const grouped = new Map<string, ColorViolation[]>();
  for (const fullPath of collectSourceFiles(SRC_DIR)) {
    const file = fullPath
      .slice(SRC_DIR.length + 1)
      .split('\\')
      .join('/');
    const suffix = fullPath.endsWith('.css') ? '.css' : '.ts';
    const violations = findColorViolations(readFileSync(fullPath, 'utf8'), file, suffix);
    if (violations.length > 0) {
      grouped.set(file, violations);
    }
  }
  return grouped;
}

/** Render violations as `file:line literal` lines for a readable failure. */
function formatViolations(violations: readonly ColorViolation[]): string[] {
  return violations.map(
    (violation) => `  ${violation.file}:${violation.line}  ${violation.literal}`
  );
}

describe('hardcoded colour literals', () => {
  it('does not introduce literals beyond the documented baseline', () => {
    const grouped = scanTree();
    const problems: string[] = [];

    for (const [file, violations] of [...grouped].sort(([a], [b]) => a.localeCompare(b))) {
      const allowance = BASELINE[file];
      if (allowance === undefined) {
        problems.push(
          `${file}: ${violations.length} hardcoded colour literal(s) — use a ` +
            'token (`var(--color-…)`), a CSS class, or `rgb(var(--color-…-rgb), α)`',
          ...formatViolations(violations)
        );
        continue;
      }
      if (violations.length > allowance.count) {
        problems.push(
          `${file}: ${violations.length} literal(s), baseline allows ` +
            `${allowance.count} (${allowance.reason})`,
          ...formatViolations(violations)
        );
      }
    }

    expect(
      problems,
      problems.length === 0 ? '' : `Hardcoded colours found:\n${problems.join('\n')}`
    ).toEqual([]);
  });

  it('keeps every baseline entry attached to a real file', () => {
    const productionFiles = new Set(
      collectSourceFiles(SRC_DIR).map((fullPath) =>
        fullPath
          .slice(SRC_DIR.length + 1)
          .split('\\')
          .join('/')
      )
    );

    const dead = Object.keys(BASELINE)
      .filter((file) => !productionFiles.has(file))
      .sort();

    expect(
      dead,
      dead.length === 0
        ? ''
        : `BASELINE names files that no longer exist (remove the entries): ${dead.join(', ')}`
    ).toEqual([]);
  });
});

describe('findColorViolations scanner', () => {
  const scan = (text: string, suffix = '.tsx'): ColorViolation[] =>
    findColorViolations(text, 'sample.tsx', suffix);

  it('flags 3-, 6- and 8-digit hex colours', () => {
    expect(scan('a = "#fff"')).toHaveLength(1);
    expect(scan('a = "#1f2937"')).toHaveLength(1);
    expect(scan('a = "#1f2937ff"')).toHaveLength(1);
    expect(scan('a = "var(--color-text)"')).toHaveLength(0);
  });

  it('flags rgb/rgba/hsl/hsla literals', () => {
    expect(scan('style={{ color: "rgb(1, 2, 3)" }}')).toHaveLength(1);
    expect(scan('style={{ color: "rgba(1, 2, 3, 0.5)" }}')).toHaveLength(1);
    expect(scan('style={{ color: "hsl(1, 2%, 3%)" }}')).toHaveLength(1);
    expect(scan('style={{ color: "hsla(1, 2%, 3%, 0.5)" }}')).toHaveLength(1);
  });

  it('allows rgb() wrapped around a token reference', () => {
    expect(scan('color: rgba(var(--color-primary-rgb), 0.5);')).toHaveLength(0);
    expect(scan('color: rgb(var(--color-fg-rgb));')).toHaveLength(0);
  });

  it('recognises a token reference that spans several lines', () => {
    const text = ['color: rgba(', '  var(--color-primary-rgb),', '  0.5', ');'].join('\n');

    expect(scan(text, '.css')).toHaveLength(0);
  });

  it('reports the offending call itself, not just the function name', () => {
    const [violation] = scan('color: rgba(1, 2, 3, 0.5);', '.css');

    expect(violation.literal).toBe('rgba(1, 2, 3, 0.5)');
  });

  it('allows var() references and plain token usage', () => {
    expect(scan('color: var(--color-text);')).toHaveLength(0);
    expect(scan('.x { background: var(--palette-blue-500); }', '.css')).toHaveLength(0);
  });

  it('ignores issue references written as 3-digit hashes', () => {
    expect(scan('const note = "see #317";')).toHaveLength(0);
  });

  it('ignores line and block comments but keeps line numbers intact', () => {
    const text = ['// color: #fff', '/* #000', 'rgb(1,2,3) */', 'a = "#fff";'].join('\n');
    const violations = scan(text);

    expect(violations).toHaveLength(1);
    expect(violations[0].line).toBe(4);
  });

  it('reports the file and 1-based line of each hit', () => {
    const [violation] = findColorViolations("\n\nx = '#abcdef';", 'src/x.ts', '.ts');

    expect(violation).toEqual({
      file: 'src/x.ts',
      line: 3,
      literal: '#abcdef',
    });
  });
});
