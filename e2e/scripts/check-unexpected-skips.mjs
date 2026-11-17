#!/usr/bin/env node
/**
 * OPS-002 guard against false assurance.
 *
 * A `test.skip(true, ...)` in an E2E spec converts a failing assertion into a
 * green run. A release gate that stays green on such skips is worthless, so
 * this checker scans e2e/tests/ recursively (*.spec.ts) for unconditional
 * skips and fails
 * unless the skip is explicitly allowed:
 *
 *   1. an inline `// SKIP-ALLOWED:<ticket-or-reason>` comment on/adjacent to the
 *      skip (or inside its reason expression), or
 *   2. an entry in the committed ALLOWLIST below.
 *
 * Dependency-free (Node built-ins only) and deterministic: it reads only the
 * checked-out working tree, so the same ref always produces the same verdict.
 * Conditional skips (`test.skip(condition, ...)`) are intentionally out of
 * scope — they are ordinary feature gating, not hidden failures.
 */

import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
const SPEC_ROOT = join(REPO_ROOT, 'e2e', 'tests');
const MARKER_RE = /SKIP-ALLOWED:\s*(\S+)/;
// `\s*` also catches the multi-line form `test.skip(\n  true, ...)`.
const UNCONDITIONAL_SKIP_RE = /test\.skip\(\s*true\b/g;

/**
 * Committed allowlist of unconditional skips that have a concrete, documented
 * reason. Entries match a file plus a stable substring of the skip's reason
 * text — never a line number, so unrelated edits do not drift the gate.
 *
 * Do NOT add failure-path skips here ("IDs fehlen — Phase x fehlgeschlagen",
 * "not found — check implementation", dynamic API error messages). Those are
 * precisely the false assurance this gate exists to surface; fix the spec
 * instead. Each entry must name the ticket/reason that justifies it.
 */
const ALLOWLIST = [
  {
    file: 'e2e/tests/toothbrush-syseng.spec.ts',
    reasonContains: 'seed_toothbrush',
    why: 'GH-691: Playwright cannot seed the toothbrush workspace in CI; the skip carries the exact management command and points to README.md.',
  },
];

/** Recursively collect *.spec.ts files, sorted for a stable report. */
function collectSpecs(dir) {
  const out = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) out.push(...collectSpecs(full));
    else if (entry.isFile() && entry.name.endsWith('.spec.ts')) out.push(full);
  }
  return out.sort();
}

/**
 * Text window for one skip: up to two preceding lines (inline marker
 * comments), the skip line, and the following lines until the closing `);`
 * (the reason expression, capped). Used for both marker and allowlist checks.
 */
function skipWindow(lines, lineNo) {
  const start = Math.max(0, lineNo - 2);
  let end = lineNo;
  const limit = Math.min(lines.length - 1, lineNo + 12);
  while (end < limit && !lines[end].includes(');')) end += 1;
  return lines.slice(start, end + 1).join('\n');
}

/** True when the `test.skip(true` occurrence sits in a comment, not in code. */
function isCommentOccurrence(lines, lineNo, column) {
  const line = lines[lineNo];
  if (line.slice(0, column).includes('//')) return true;
  const trimmed = line.trimStart();
  return trimmed.startsWith('//') || trimmed.startsWith('*') || trimmed.startsWith('/*');
}

function main() {
  let specs;
  try {
    specs = collectSpecs(SPEC_ROOT);
  } catch (err) {
    console.error(`check-unexpected-skips: cannot scan ${SPEC_ROOT}: ${err.message}`);
    process.exit(2);
  }

  const violations = [];
  const allowed = [];
  let scanned = 0;

  for (const spec of specs) {
    const rel = relative(REPO_ROOT, spec).split('\\').join('/');
    const text = readFileSync(spec, 'utf8');
    const lines = text.split(/\r?\n/);
    // Character offsets of each line start, for O(log n) line lookup.
    const offsets = [];
    let pos = 0;
    for (const line of lines) {
      offsets.push(pos);
      pos += line.length + 1; // +1 for the consumed newline
    }
    const lineOf = (index) => {
      let lo = 0;
      let hi = offsets.length - 1;
      while (lo < hi) {
        const mid = (lo + hi + 1) >> 1;
        if (offsets[mid] <= index) lo = mid;
        else hi = mid - 1;
      }
      return lo;
    };

    UNCONDITIONAL_SKIP_RE.lastIndex = 0;
    let match;
    while ((match = UNCONDITIONAL_SKIP_RE.exec(text)) !== null) {
      const lineNo = lineOf(match.index);
      const column = match.index - offsets[lineNo];
      if (isCommentOccurrence(lines, lineNo, column)) continue;

      scanned += 1;
      const window = skipWindow(lines, lineNo);
      const inline = window.match(MARKER_RE);
      const listed = ALLOWLIST.find(
        (a) => rel.endsWith(a.file) && window.includes(a.reasonContains)
      );

      const record = {
        file: rel,
        line: lineNo + 1,
        text: (lines[lineNo] || '').trim(),
      };
      if (inline) allowed.push({ ...record, by: `inline marker ${inline[0]}` });
      else if (listed) allowed.push({ ...record, by: `allowlist: ${listed.why}` });
      else violations.push(record);
    }
  }

  if (violations.length > 0) {
    console.error(
      `check-unexpected-skips: FAIL — ${violations.length} unconditional skip(s) ` +
        'without a documented allowlist marker:'
    );
    for (const v of violations) console.error(`  ${v.file}:${v.line}: ${v.text}`);
    console.error(
      'A skip hides a failure from the E2E gate. Either fix the failing path or ' +
        'add a SKIP-ALLOWED:<ticket-or-reason> comment with a real justification.'
    );
    process.exit(1);
  }

  console.log(
    `check-unexpected-skips: OK — ${scanned} unconditional skip(s) scanned, ` +
      `${allowed.length} explicitly allowed.`
  );
  for (const a of allowed) console.log(`  allowed ${a.file}:${a.line} (${a.by})`);
}

main();
