/**
 * Design-system ratchet: interactive elements must use the `btn-*` system
 * (#954, #797, #1091, #1092, #1093).
 *
 * The gap this suite closes
 * -------------------------
 * `src/test/ui-ratchet.test.ts` already freezes the *presence* of hand-rolled
 * chrome — inline `style={{...}}`, hex literals, page-local toasts, duplicated
 * `background: var(--color-primary)` fills. Every one of those checks answers
 * "is something re-declared that the design system already owns?".
 *
 * None of them answers the question that produced four separate issues for the
 * same defect on four different pages: "does this interactive element USE the
 * design system at all?" A `<button>` with no `className` whatsoever renders a
 * default UA button. There is no inline style to flag, no hex literal, no
 * duplicated fill — a clean bill of health from every existing check, and a
 * visibly wrong button. That is the class of defect a ratchet has to catch:
 * #954 closed it on the admin create dialogs, #797 on the entity create
 * buttons, #927 on the derive buttons, and #1091/#1093 found it again on
 * `/system-settings` and the requirement editors. Per-page review found the
 * first three and let the fourth through.
 *
 * The user's own conclusion, which this file implements: *"ein solcher Test
 * hätte #954, #797 und diesen Befund gleichzeitig gefunden und verhindert die
 * Wiederholung."*
 *
 * How it works
 * ------------
 * Purely static, at the source level: a small hand-rolled JSX open-tag scanner
 * over every non-test `.tsx` under `src/components`. No browser, no dev
 * server, no database, no
 * rendering — so it is a real CI gate rather than something that only the
 * developer with a dev stack can run. It mirrors the file-walker + regex
 * approach of `ui-ratchet.test.ts` and `design-tokens.test.ts`.
 *
 * The classes it enforces are the ones `styles/global.css` actually defines.
 * Read them from there rather than from an issue's "Soll" text. Issue #1099
 * closed the gap #1093 opened: #1093's "Soll" asked for `btn-icon`, which did
 * not exist, and this gate would have waved it through while the component
 * rendered an unstyled button — confirming a false statement. `btn-icon` is
 * now a real variant in `global.css`, added to `CHROME_CLASSES`, and the test
 * "enforces only ... classes that styles/global.css actually defines" pins
 * every enforced class to a real CSS rule, so no future phantom class can
 * slip past. `CHROME_CLASSES` stays an explicit *positive* list; the scanner
 * never matches the `btn-*` prefix.
 *
 * Ratchet semantics
 * -----------------
 * `design-system-ratchet.baseline.json` holds a per-check `maxViolations`
 * ceiling plus an allow-list of documented exemptions. The suite is green
 * while the *unexempted* violation count per check is at or below its ceiling,
 * so:
 *
 * - a NEW violation raises the count and fails, even if some other violation
 *   was fixed in the same change (a ceiling alone would let that trade pass);
 * - an exemption is only honoured for a violation that actually exists, and
 *   every exemption must carry a substantive one-line reason — a bare
 *   allow-list is the failure mode this file is written against, so an
 *   exemption that goes stale, or that is justified with a single word, fails
 *   instead of quietly widening the hole;
 * - a *stale* baseline (a count that no longer matches reality because someone
 *   fixed violations without re-baselining) fails too, with the re-baseline
 *   command in the message. Same two-test shape as `ui-ratchet.test.ts`
 *   (`toBeLessThanOrEqual` ratchet + `toBe` staleness detector).
 *
 * The ceiling is *monotonically non-increasing* (issue #1099). The re-baseline
 * command refuses to raise `maxViolations`: a fresh violation must be fixed,
 * or explicitly exempted with a substantive reason — it can never be silently
 * absorbed into the ceiling. That is what turns the baseline from a frozen
 * backlog into a ratchet that only moves down. The only allowed increase is
 * the bootstrap run that creates a missing baseline file.
 *
 * Re-baselining (single command, no extra tooling):
 *
 *   DESIGN_SYSTEM_RATCHET_DUMP=1 npx vitest run src/test/design-system-ratchet.test.ts
 *
 * In the project's Docker test stack that is:
 *
 *   docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml \
 *     --project-directory . run --rm frontend-test \
 *     sh -c "npx vitest run src/test/design-system-ratchet.test.ts"   # with the env var set
 *
 * The dump rewrites `maxViolations` down to the measured count and drops
 * exemptions that no longer match a real violation. It never invents an
 * exemption and never raises the ceiling: a fresh violation is either fixed or
 * explicitly exempted, so the deliberate "look at this and decide" step stays
 * in the diff. A dump that would raise a ceiling aborts before writing.
 */
import {
  existsSync,
  readdirSync,
  readFileSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { join, relative, resolve } from "node:path";
import { describe, expect, it } from "vitest";
import de from "../i18n/locales/de.json";

const SRC_DIR = resolve(__dirname, "..");
const COMPONENTS_DIR = join(SRC_DIR, "components");
const BASELINE_PATH = join(__dirname, "design-system-ratchet.baseline.json");
const DUMP_ENV_VAR = "DESIGN_SYSTEM_RATCHET_DUMP";
const REPORT_ENV_VAR = "DESIGN_SYSTEM_RATCHET_REPORT";

/**
 * The `btn-*` classes that carry *chrome* (fill, border, colour, geometry
 * base), i.e. the ones that make an element look like a design-system button.
 * Read from `styles/global.css`. This is an explicit POSITIVE list (issue
 * #1099) — the scanner never matches the `btn-*` prefix, so an invented class
 * cannot pass the gate, and the test "enforces only ... classes that
 * styles/global.css actually defines" pins each entry to a real CSS rule.
 *
 * `btn-sm` / `btn-lg` are deliberately excluded: they only override height,
 * padding and font size, so `className="btn-sm"` on a bare `<button>` is
 * still a default UA button. `btn-icon` *is* included — since #1099 it carries
 * its own colour/geometry/hover chrome (see its rule in `global.css`).
 */
const CHROME_CLASSES = [
  "btn-primary",
  "btn-secondary",
  "btn-danger",
  "btn-ghost",
  "btn-tab",
  "btn-icon",
] as const;

/** `<button>`, plus anything that behaves like one. */
const CLICK_HANDLER_PATTERN =
  /\bon(?:Click|DoubleClick|PointerDown|MouseDown|TouchStart)\s*=/;
const BUTTON_ROLE_PATTERN = /\brole\s*=\s*["'{]?\s*["']?button\b/;
const DATA_TESTID_PATTERN = /\bdata-testid\s*=\s*(?:"([^"]*)"|'([^']*)'|\{\s*`([^`]*)`)/;

/**
 * Extract the `className` value from a tag's raw attribute text.
 *
 * Brace-balanced rather than regex-matched, because the interesting cases are
 * the nested ones — `className={cond ? styles.a : `${styles.b} ${styles.c}`}` —
 * and a `\{([^}]*)\}` regex stops at the first inner `}`, producing a truncated
 * value that runs across several source lines. Collapsed to a single line so a
 * violation message stays one line per violation.
 */
function extractClassName(attrs: string): string | null {
  const match = /\bclassName\s*=\s*/.exec(attrs);
  if (match === null) return null;
  let i = match.index + match[0].length;
  if (i >= attrs.length) return null;

  const quote = attrs[i];
  if (quote === '"' || quote === "'") {
    const end = attrs.indexOf(quote, i + 1);
    return end === -1 ? null : attrs.slice(i + 1, end);
  }
  if (quote === "{") {
    let depth = 0;
    let inner: string | null = null;
    for (; i < attrs.length; i += 1) {
      const ch = attrs[i];
      if (ch === "{") {
        depth += 1;
        if (depth === 1) {
          inner = "";
          continue;
        }
      } else if (ch === "}") {
        depth -= 1;
        if (depth === 0) break;
      }
      if (inner !== null) inner += ch;
    }
    return inner === null ? null : inner;
  }
  // Unquoted JSX attribute value.
  const end = attrs.search(/[\s/>]/);
  return end === -1 ? attrs : attrs.slice(0, end);
}

/** One-line, whitespace-collapsed form of an attribute value, for messages. */
function condense(value: string): string {
  const flat = value.replace(/\s+/g, " ").trim();
  return flat.length > 80 ? `${flat.slice(0, 77)}...` : flat;
}

/**
 * Check 4 (issue #1099) — an icon-only `.btn-icon` button must carry an
 * accessible name.
 *
 * `global.css` documents the contract above the `.btn-icon` rule ("ACCESSIBLE
 * NAME IS PART OF THE CONTRACT"), but a CSS comment cannot enforce it. A
 * `.btn-icon` button has no text content by construction, so without
 * `aria-label` / `aria-labelledby` / a visually-hidden label it is announced as
 * an unlabelled "button" — WCAG 4.1.2 (Name, Role, Value), and the whole point
 * of an icon-only control is lost on a screen reader. `title` is deliberately
 * NOT accepted: it is not exposed as the accessible name by every assistive
 * technology and never as the primary name, so it cannot stand in for one.
 *
 * Accessible-name attributes. `aria-label` and `aria-labelledby` are checked
 * as attributes (not by resolving their value): a non-empty literal counts, an
 * expression such as `{t("…")}` counts (the developer declared a name), and an
 * explicit empty literal (`aria-label=""`) does not.
 */
const ARIA_LABEL_ATTR = "aria-label";
const ARIA_LABELLEDBY_ATTR = "aria-labelledby";

/** True when `attrs` carries `name` with a non-empty literal or any expression. */
function hasNonEmptyAriaAttr(attrs: string, name: string): boolean {
  const literal = new RegExp(
    `\\b${name}\\s*=\\s*(?:"([^"]*)"|'([^']*)')`,
  ).exec(attrs);
  if (literal !== null) {
    const value = (literal[1] ?? literal[2] ?? "").trim();
    return value !== "";
  }
  return new RegExp(`\\b${name}\\s*=\\s*\\{`).test(attrs);
}

/**
 * Non-whitespace content of a `<button>`'s children after its child tags are
 * removed — i.e. the element's text alternative, including a visually-hidden
 * `<span>`. JSX expressions (`{t("close")}`) are left in place and count as
 * content, so a translated label is never a false positive; an icon-only button
 * (`<Icon />` child, no text) reduces to the empty string.
 */
function buttonTextContent(inner: string): string {
  return inner
    .replace(/<[^>]*>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * Whether a `.btn-icon` `<button>` has an accessible name. `inner` is the raw
 * JSX between the open and close tags, or `null` for a self-closing button.
 */
function hasAccessibleName(attrs: string, inner: string | null): boolean {
  if (hasNonEmptyAriaAttr(attrs, ARIA_LABEL_ATTR)) return true;
  if (hasNonEmptyAriaAttr(attrs, ARIA_LABELLEDBY_ATTR)) return true;
  return inner !== null && buttonTextContent(inner) !== "";
}

/**
 * Emoji / pictograph code-point ranges, for check 2.
 *
 * Excluded on purpose: U+2190-U+21FF (arrows — `->` and friends appear in
 * ordinary German prose and in code comments), U+203C-U+2049 (‼ ‾, which are
 * punctuation), U+2600-U+27BF's ASCII-adjacent dingbats are kept because
 * ✅/❌/⚠/✨ in a button ARE the defect, and U+FE0F/U+FE0E (emoji presentation
 * selectors) because they are modifiers, never glyphs on their own.
 *
 * The two variation selectors are top-level alternates rather than members of
 * the character class: they are combining marks, and a class that mixes marks
 * with non-marks is exactly what eslint's `no-misleading-character-class`
 * rejects. The matched set is identical either way.
 */
const EMOJI_PATTERN =
  /[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}\u{1F1E6}-\u{1F1FF}]|️|︎/u;

/**
 * Bare action verbs that name no object. A button labelled with one of these
 * is only unambiguous because of where it happens to sit; the moment the same
 * verb appears twice in the component tree (check 3) it is genuinely
 * unreadable. Kept to verbs whose object is a *thing* rather than the
 * interaction itself, so dialog chrome ("Abbrechen", "Schließen") is not
 * swept in.
 */
const GENERIC_LABEL_PATTERN =
  /^(?:Exportieren|Export|Importieren|Import|Herunterladen|Download|Hochladen|Teilen|Share|Synchronisieren|Generieren|Erzeugen|Ausführen)$/u;

/** Recursively collect files under `dir` whose basename matches `extPattern`. */
function collectFiles(dir: string, extPattern: RegExp): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      out.push(...collectFiles(full, extPattern));
    } else if (extPattern.test(entry)) {
      out.push(full);
    }
  }
  return out;
}

/**
 * Component `.tsx` sources, excluding the colocated tests. Test files contain
 * deliberately malformed markup and their own fixture strings, so counting them
 * would be noise.
 */
function collectComponentTsx(): string[] {
  return collectFiles(COMPONENTS_DIR, /\.tsx$/).filter(
    (file) => !/\.(test|stories)\.tsx$/.test(file),
  );
}

/**
 * Comment-stripped source per file, read once.
 *
 * The three checks each walk all ~200 component files. Without this the suite
 * would do ~600 reads and three redundant parses of the same tree, and it would
 * be the slowest source-scanning test in the suite — which matters, because
 * `design-tokens.test.ts` and `i18n-parity.test.ts` already sit close to
 * vitest's 5s default timeout when the whole frontend suite runs in parallel.
 */
const sourceCache = new Map<string, string>();

function readScanned(file: string): string {
  const cached = sourceCache.get(file);
  if (cached !== undefined) return cached;
  const scanned = blankOutComments(readFileSync(file, "utf-8"));
  sourceCache.set(file, scanned);
  return scanned;
}

/**
 * Blank out `/* ... *\/` and `// ...` comments, preserving every offset and
 * line break.
 *
 * Preserving offsets matters twice over: violation messages must cite the real
 * line number in the real file, and the JSX scanner works on absolute indices.
 * Replacing with spaces (rather than deleting, as `ui-ratchet.test.ts` does)
 * keeps both. JSX comments `{/* ... *\/}` are covered by the block-comment
 * pass, since the leading `{` is just expression syntax around a comment.
 */
function blankOutComments(source: string): string {
  let out = "";
  let i = 0;
  const n = source.length;
  while (i < n) {
    const two = source.slice(i, i + 2);
    if (two === "/*") {
      const end = source.indexOf("*/", i + 2);
      const stop = end === -1 ? n : end + 2;
      out += source.slice(i, stop).replace(/[^\n]/g, " ");
      i = stop;
      continue;
    }
    if (two === "//") {
      let end = source.indexOf("\n", i);
      if (end === -1) end = n;
      out += " ".repeat(end - i);
      i = end;
      continue;
    }
    out += source[i];
    i += 1;
  }
  return out;
}

interface OpenTag {
  /** Lowercased intrinsic element name, or the component name as written. */
  tag: string;
  /** Raw attribute text between the tag name and its closing `>`. */
  attrs: string;
  /** Offset of the `<` in the blanked source. */
  start: number;
}

/**
 * Scan for JSX open tags.
 *
 * A regex like `/<button[^>]*>/` is not good enough: attribute values
 * routinely contain `>` (every `onClick={() => ...}` does). This walks the
 * attribute region instead, tracking quote state and brace depth, so the tag
 * ends at the first `>` that is not inside a string or an expression.
 *
 * Closing tags (`</button>`) cannot match: the character after `<` is `/`, not
 * a name character.
 */
function scanOpenTags(source: string): OpenTag[] {
  const tags: OpenTag[] = [];
  const opener = /<([A-Za-z][A-Za-z0-9._-]*)/g;
  let match: RegExpExecArray | null;
  while ((match = opener.exec(source)) !== null) {
    let i = match.index + match[0].length;
    let depth = 0;
    let quote: string | null = null;
    while (i < source.length) {
      const ch = source[i];
      if (quote !== null) {
        if (ch === quote) quote = null;
        i += 1;
        continue;
      }
      if (ch === '"' || ch === "'") {
        quote = ch;
        i += 1;
        continue;
      }
      if (ch === "{") {
        depth += 1;
        i += 1;
        continue;
      }
      if (ch === "}") {
        depth -= 1;
        i += 1;
        continue;
      }
      if (ch === ">" && depth === 0) break;
      i += 1;
    }
    tags.push({
      tag: match[1],
      attrs: source.slice(match.index + match[0].length, i),
      start: match.index,
    });
    opener.lastIndex = i + 1;
  }
  return tags;
}

/** 1-based line number of `offset` within `source`. */
function lineOf(source: string, offset: number): number {
  let line = 1;
  for (let i = 0; i < offset && i < source.length; i += 1) {
    if (source[i] === "\n") line += 1;
  }
  return line;
}

/** First capture group that actually matched, for the attribute regexes above. */
function firstGroup(match: RegExpMatchArray | null): string | undefined {
  if (match === null) return undefined;
  for (let g = 1; g < match.length; g += 1) {
    if (match[g] !== undefined) return match[g];
  }
  return undefined;
}

/**
 * True for lowercase HTML/SVG tag names (`button`, `div`, `li`, `th`, ...),
 * false for React component names (`Dialog`, `SplitView`, `ArtifactRow`, ...).
 *
 * Issue #1099: a React component's `onClick` is a *prop*, not a DOM button.
 * Whether the component forwards it to a DOM element is the component's own
 * business, and a `btn-*` class cannot be applied to the component tag, so the
 * gate must not demand one. JSX capitalises component names and lowercases
 * intrinsic tags, which is a reliable discriminator in this codebase (no
 * lowercase custom elements are used).
 */
function isIntrinsicElement(tag: string): boolean {
  return /^[a-z]/.test(tag);
}

/** Locale JSON as loaded from `de.json`. */
type LocaleValue = string | LocaleValue[] | { [key: string]: LocaleValue };

/**
 * Flatten the nested German resource into dot-separated key paths, mirroring
 * i18next's default `keySeparator: "."` — the same traversal and the same
 * helper shape as `i18n-parity.test.ts`.
 */
function flattenLocale(value: LocaleValue, prefix = ""): Map<string, string> {
  const out = new Map<string, string>();
  if (typeof value === "string") {
    if (prefix !== "") out.set(prefix, value);
    return out;
  }
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    return out;
  }
  for (const [key, child] of Object.entries(value)) {
    const path = prefix ? `${prefix}.${key}` : key;
    for (const [k, v] of flattenLocale(child, path)) out.set(k, v);
  }
  return out;
}

const DE_LABELS = flattenLocale(de as LocaleValue);

/**
 * The visible label of a `<button>`, resolved far enough to judge it.
 *
 * Button labels in this codebase are almost never literals — they are
 * `t("systemSettings.themes.export")` — so comparing against the source text
 * would miss every real case. `t("...")` / `i18n.t("...")` are resolved
 * through `de.json`, the locale the ambiguity complaint was filed in. A key
 * that cannot be resolved falls back to the raw key, which is never generic
 * and therefore never a false positive.
 */
function resolveButtonLabel(inner: string): string | null {
  const parts: string[] = [];
  const call = /\bt\(\s*["']([^"']+)["']/g;
  let match: RegExpExecArray | null;
  let sawTranslation = false;
  while ((match = call.exec(inner)) !== null) {
    sawTranslation = true;
    parts.push(DE_LABELS.get(match[1]) ?? match[1]);
  }
  if (sawTranslation) return parts.join(" ").replace(/\s+/g, " ").trim();

  // No translation call: fall back to the literal JSX text, with nested tags
  // and expression containers removed.
  const text = inner
    .replace(/<[^>]*>/g, " ")
    .replace(/\{[^{}]*\}/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  return text === "" ? null : text;
}

interface Violation {
  /** Stable, line-number-free identity — the key an exemption must match. */
  key: string;
  check: CheckId;
  file: string;
  line: number;
  element: string;
  reason: string;
}

type CheckId =
  | "button-missing-design-system-class"
  | "emoji-as-ui-glyph"
  | "ambiguous-button-label";

/**
 * Identity of an element for the exemption allow-list.
 *
 * Deliberately NOT line-number based: a single added line at the top of a file
 * would orphan every exemption in it, and a ratchet whose exemptions rot
 * through ordinary edits gets disabled rather than maintained. `data-testid` is
 * the stable anchor and is a repo-wide convention on interactive elements
 * (AGENTS.md), so it is preferred; the resolved label is the fallback.
 */
function fingerprint(tag: OpenTag, label: string | null): string {
  const testId = firstGroup(DATA_TESTID_PATTERN.exec(tag.attrs));
  if (testId !== undefined) return `${tag.tag}[data-testid=${testId}]`;
  if (label !== null && label !== "") return `${tag.tag}[label=${label}]`;
  return tag.tag;
}

function toRelative(file: string): string {
  return relative(SRC_DIR, file).replace(/\\/g, "/");
}

/** Check 1 — every interactive element carries a chrome `btn-*` class. */
function scanMissingDesignSystemClass(): Violation[] {
  const out: Violation[] = [];
  for (const file of collectComponentTsx()) {
    const source = readScanned(file);
    const rel = toRelative(file);
    for (const tag of scanOpenTags(source)) {
      const isButton = tag.tag === "button";
      // Issue #1099: only intrinsic elements are judged. `<Dialog onClick=…>`,
      // `<SplitView …>` and `<ArtifactRow …>` receive `onClick` as a React
      // prop, not as a DOM handler; they used to be reported as "buttons
      // without btn-* chrome", which is neither fixable nor true.
      if (!isButton && !isIntrinsicElement(tag.tag)) continue;
      const isClickable =
        CLICK_HANDLER_PATTERN.test(tag.attrs) || BUTTON_ROLE_PATTERN.test(tag.attrs);
      if (!isButton && !isClickable) continue;

      const hasChrome = CHROME_CLASSES.some((cls) =>
        new RegExp(`\\b${cls}\\b`).test(tag.attrs),
      );
      if (hasChrome) continue;

      const className = extractClassName(tag.attrs);
      let reason: string;
      if (className === null) {
        reason =
          "no className attribute at all — this renders a default user-agent button, " +
          "not a design-system button";
      } else if (/^\s*styles\./.test(className)) {
        reason =
          `className={${condense(className)}} is a CSS-module class, not a btn-* ` +
          "design-system class — the button keeps default UA chrome plus an " +
          "ad-hoc fill";
      } else {
        reason =
          `className=${JSON.stringify(condense(className))} carries no btn-* ` +
          `design-system class (expected one of ${CHROME_CLASSES.join(", ")})`;
      }

      out.push({
        key: `button-missing-design-system-class::${rel}::${fingerprint(tag, null)}`,
        check: "button-missing-design-system-class",
        file: rel,
        line: lineOf(source, tag.start),
        element: tag.tag,
        reason,
      });
    }
  }
  return out;
}

interface IconButtonViolation {
  file: string;
  line: number;
}

/**
 * Check 4 (issue #1099) — every `.btn-icon` button has an accessible name.
 *
 * Scanned over the component sources, mirroring check 1's open-tag scan. The
 * `>` offset is computed from the tag's own attribute length rather than a
 * naive `indexOf(">")`, so a `>` inside an attribute expression cannot
 * truncate the child content and hide the missing name.
 */
function scanIconButtonsMissingAccessibleName(): IconButtonViolation[] {
  const out: IconButtonViolation[] = [];
  for (const file of collectComponentTsx()) {
    const source = readScanned(file);
    const rel = toRelative(file);
    for (const tag of scanOpenTags(source)) {
      if (tag.tag !== "button") continue;
      if (!/\bbtn-icon\b/.test(tag.attrs)) continue;
      const openEnd = tag.start + 1 + tag.tag.length + tag.attrs.length;
      if (source[openEnd] !== ">") continue;
      const selfClosing = source[openEnd - 1] === "/";
      let inner: string | null = null;
      if (!selfClosing) {
        const close = source.indexOf("</button>", openEnd);
        if (close === -1) continue;
        inner = source.slice(openEnd + 1, close);
      }
      if (hasAccessibleName(tag.attrs, inner)) continue;
      out.push({ file: rel, line: lineOf(source, tag.start) });
    }
  }
  return out;
}

/** Check 2 — no emoji used as a UI glyph. */
function scanEmojiGlyphs(): Violation[] {
  const out: Violation[] = [];
  for (const file of collectComponentTsx()) {
    const source = readScanned(file);
    const rel = toRelative(file);
    const lines = source.split("\n");
    for (let i = 0; i < lines.length; i += 1) {
      const line = lines[i];
      const hit = EMOJI_PATTERN.exec(line);
      if (hit === null) continue;
      out.push({
        key: `emoji-as-ui-glyph::${rel}::${hit[0]}`,
        check: "emoji-as-ui-glyph",
        file: rel,
        line: i + 1,
        element: hit[0],
        reason:
          `${JSON.stringify(hit[0])} is used as a UI glyph but is not a ` +
          "design-system icon. Whatever font the platform substitutes, it has " +
          "no size, weight or colour contract with the icons around it — and " +
          "with an emoji-presentation selector it switches to the platform " +
          "colour-emoji font mid-string. Use a monochrome icon from the " +
          "existing icon set in currentColor, 16-20px.",
      });
    }
  }
  return out;
}

/** Check 3 — a button label must not be a bare verb that names no object. */
function scanAmbiguousButtonLabels(): Violation[] {
  const candidates: Array<{ violation: Violation; label: string }> = [];
  for (const file of collectComponentTsx()) {
    const source = readScanned(file);
    const rel = toRelative(file);
    const tags = scanOpenTags(source);
    for (const tag of tags) {
      if (tag.tag !== "button") continue;
      const openEnd = source.indexOf(">", tag.start);
      if (openEnd === -1) continue;
      // Self-closing: no label to judge.
      if (source[openEnd - 1] === "/") continue;
      const close = source.indexOf("</button>", openEnd);
      if (close === -1) continue;
      const inner = source.slice(openEnd + 1, close);
      const label = resolveButtonLabel(inner);
      if (label === null || !GENERIC_LABEL_PATTERN.test(label)) continue;
      candidates.push({
        label,
        violation: {
          key: `ambiguous-button-label::${rel}::${fingerprint(tag, label)}`,
          check: "ambiguous-button-label",
          file: rel,
          line: lineOf(source, tag.start),
          element: tag.tag,
          reason: "",
        },
      });
    }
  }

  // The defect is that the label names no object, NOT that the verb happens to
  // repeat. #1093's seven "Exportieren" buttons are ONE JSX site rendered
  // inside a `.map()` over the seven palettes, so a repetition count over source
  // occurrences cannot see it — the reader still cannot tell which palette is
  // meant. The occurrence count is therefore reported as context, not used as
  // the trigger.
  const byLabel = new Map<string, typeof candidates>();
  for (const candidate of candidates) {
    const bucket = byLabel.get(candidate.label);
    if (bucket) bucket.push(candidate);
    else byLabel.set(candidate.label, [candidate]);
  }

  const out: Violation[] = [];
  for (const [label, group] of byLabel) {
    const files = new Set(group.map((c) => c.violation.file)).size;
    const spread =
      group.length > 1
        ? ` The same label is used by ${group.length} button(s) across ${files} ` +
          "source file(s), so it is not merely terse but actively unreadable."
        : "";
    for (const candidate of group) {
      out.push({
        ...candidate.violation,
        reason:
          `label ${JSON.stringify(label)} is a bare action verb and is the ` +
          "button's entire text, so it never states what is acted on — the " +
          "reader has to supply the object from context. Name the object " +
          `(e.g. "JSON exportieren", "Bauhaus exportieren").${spread}`,
      });
    }
  }
  return out;
}

const SCANNERS: Record<CheckId, () => Violation[]> = {
  "button-missing-design-system-class": scanMissingDesignSystemClass,
  "emoji-as-ui-glyph": scanEmojiGlyphs,
  "ambiguous-button-label": scanAmbiguousButtonLabels,
};

interface CheckBaseline {
  /** Ceiling on unexempted violations. The headline ratchet number. */
  maxViolations: number;
  /**
   * Identity of every violation known at record time, sorted.
   *
   * The count alone cannot answer "which violation is new?": slicing the
   * violation list at `maxViolations` names an arbitrary tail element, so a
   * developer reading the failure would be sent to the wrong file. Recording
   * the keys makes the diff exact in both directions — a key that appears is
   * the new violation, a key that disappears is one somebody fixed.
   */
  known: string[];
  issue: string;
  note: string;
}

interface BaselineFile {
  version: number;
  recordedAt: string;
  recordedBy: string;
  checks: Record<CheckId, CheckBaseline>;
  /** `<check>::<file>::<element fingerprint>` -> one-line justification. */
  exemptions: Record<string, { reason: string }>;
}

const CHECK_ISSUES: Record<CheckId, string> = {
  "button-missing-design-system-class": "#954, #797, #1091, #1093",
  "emoji-as-ui-glyph": "#1092",
  "ambiguous-button-label": "#1093",
};

const CHECK_NOTES: Record<CheckId, string> = {
  "button-missing-design-system-class":
    "Interactive elements with no btn-* chrome class. Fix by adding the " +
    "correct variant (btn-primary / btn-secondary / btn-danger / btn-ghost / " +
    "btn-tab) and deleting the ad-hoc fill; do not raise this ceiling to " +
    "silence a new button.",
  "emoji-as-ui-glyph":
    "Emoji standing in for a design-system icon. Fix by swapping in a " +
    "monochrome currentColor icon from the existing icon set.",
  "ambiguous-button-label":
    "Buttons whose whole label is a bare action verb that is used more than " +
    "once in the component tree, so the object is unstated. Fix by naming the " +
    "object in the label (i18n key + both locales).",
};

/**
 * Seed used when the baseline file does not exist yet, so the very first
 * `DESIGN_SYSTEM_RATCHET_DUMP=1` run can create it. `maxViolations: -1` would
 * fail any non-dump run, so a missing baseline is reported as "no exemptions,
 * zero allowed" — the ratchet tests then fail loudly and point at the
 * re-baseline command, which is the correct state for a missing gate.
 */
const BASELINE_SEED: BaselineFile = {
  version: 1,
  recordedAt: "",
  recordedBy: "",
  checks: {
    "button-missing-design-system-class": {
      maxViolations: 0,
      known: [],
      issue: CHECK_ISSUES["button-missing-design-system-class"],
      note: CHECK_NOTES["button-missing-design-system-class"],
    },
    "emoji-as-ui-glyph": {
      maxViolations: 0,
      known: [],
      issue: CHECK_ISSUES["emoji-as-ui-glyph"],
      note: CHECK_NOTES["emoji-as-ui-glyph"],
    },
    "ambiguous-button-label": {
      maxViolations: 0,
      known: [],
      issue: CHECK_ISSUES["ambiguous-button-label"],
      note: CHECK_NOTES["ambiguous-button-label"],
    },
  },
  exemptions: {},
};

function loadBaseline(): BaselineFile {
  if (!existsSync(BASELINE_PATH)) return BASELINE_SEED;
  return JSON.parse(readFileSync(BASELINE_PATH, "utf-8")) as BaselineFile;
}

interface Measured {
  unexempted: Violation[];
  /** Violations present now but absent from the recorded `known` set. */
  fresh: Violation[];
  /** Recorded `known` keys that no longer reproduce. */
  fixed: string[];
  /** Exemption keys that no longer describe a real violation. */
  staleExemptions: string[];
}

/** All violations for a check, classified against the recorded baseline. */
function measure(check: CheckId, baseline: BaselineFile): Measured {
  const all = SCANNERS[check]();
  const exempted = new Set(Object.keys(baseline.exemptions));
  const unexempted = all.filter((v) => !exempted.has(v.key));
  const known = new Set(baseline.checks[check]?.known ?? []);
  const live = new Set(all.map((v) => v.key));

  return {
    unexempted,
    fresh: unexempted.filter((v) => !known.has(v.key)),
    fixed: [...known].filter((key) => !live.has(key)).sort(),
    // An exemption that no longer matches a real violation is rot: it silently
    // widens the gate for the day someone re-introduces the same element.
    staleExemptions: [...exempted]
      .filter((key) => key.startsWith(`${check}::`) && !live.has(key))
      .sort(),
  };
}

function formatViolations(violations: Violation[]): string {
  return violations
    .map((v) => `  ${v.file}:${v.line}  <${v.element}>  ${v.reason}`)
    .join("\n");
}

const REBASELINE_HINT = `Re-baseline deliberately with:\n    ${DUMP_ENV_VAR}=1 npx vitest run src/test/design-system-ratchet.test.ts`;

/**
 * Monotonicity guard for re-baselining (issue #1099).
 *
 * The ratchet exists to drive the backlog down, so `maxViolations` is a
 * one-way number: a re-baseline may keep it or lower it, never raise it. The
 * old dump silently absorbed a fresh violation into the ceiling, which made
 * the "re-baseline" command the very escape hatch the gate is meant to close.
 * A genuinely new violation must now be fixed, or — if it is a legitimate
 * exception — explicitly exempted with a substantive reason; both are visible
 * decisions in the diff. The only allowed increase is the bootstrap run that
 * creates a missing baseline file, otherwise the gate could never be installed.
 *
 * Extracted as a pure function so the policy is unit-testable in-process
 * without spawning a re-baseline that would rewrite the real baseline.
 */
function assertBaselineNotRaised(
  check: CheckId,
  previousMax: number,
  measuredUnexempted: number,
  baselineExists: boolean,
): void {
  if (!baselineExists) return;
  if (measuredUnexempted > previousMax) {
    throw new Error(
      `refusing to raise the "${check}" baseline from ${previousMax} to ` +
        `${measuredUnexempted}: the design-system ratchet is monotonically ` +
        "non-increasing (#1099).\n" +
        "Fix the new violation(s), or — if they are legitimate exceptions — " +
        "add one entry per violation to the `exemptions` map in " +
        "design-system-ratchet.baseline.json with a substantive one-line " +
        "reason. Never raise `maxViolations`.",
    );
  }
}

// One measurement per check, shared by the ratchet and drift tests.
const measured = new Map<CheckId, Measured>();

// In dump mode the baseline is rewritten from the measurement and the
// assertions that would object to the drift are skipped, so the command both
// re-baselines and confirms the file it just wrote is green.
if (process.env[DUMP_ENV_VAR] === "1") {
  const current = loadBaseline();
  const checks = {} as BaselineFile["checks"];
  const exemptions: BaselineFile["exemptions"] = {};
  for (const check of Object.keys(SCANNERS) as CheckId[]) {
    const result = measure(check, current);
    measured.set(check, result);
    assertBaselineNotRaised(
      check,
      current.checks[check]?.maxViolations ?? 0,
      result.unexempted.length,
      existsSync(BASELINE_PATH),
    );
    checks[check] = {
      maxViolations: result.unexempted.length,
      known: result.unexempted.map((v) => v.key).sort(),
      issue: current.checks[check]?.issue ?? CHECK_ISSUES[check],
      note: current.checks[check]?.note ?? CHECK_NOTES[check],
    };
    // Keep an exemption only while it still describes a real violation.
    const live = new Set(SCANNERS[check]().map((v) => v.key));
    for (const key of Object.keys(current.exemptions)) {
      if (key.startsWith(`${check}::`) && live.has(key)) {
        exemptions[key] = current.exemptions[key];
      }
    }
  }
  const dumped: BaselineFile = {
    version: 1,
    recordedAt: new Date().toISOString().slice(0, 10),
    recordedBy: `${DUMP_ENV_VAR}=1 npx vitest run src/test/design-system-ratchet.test.ts`,
    checks,
    exemptions,
  };
  writeFileSync(BASELINE_PATH, `${JSON.stringify(dumped, null, 2)}\n`, "utf-8");

  // The measurements above were taken against the *previous* baseline, so they
  // are stale by construction. Dropping them makes the assertions re-measure
  // against the file just written — which is what makes this command
  // self-verifying: a dump that produced a baseline its own suite rejects
  // fails here instead of passing silently.
  measured.clear();
}

const baseline = loadBaseline();
const DUMPING = process.env[DUMP_ENV_VAR] === "1";

/**
 * Report mode: print every violation of every check, grouped, without failing.
 * This is the "what would the gate say if I asked nicely" mode, and the one to
 * use when working out which of the current violations to fix first.
 */
if (process.env[REPORT_ENV_VAR] === "1") {
  for (const check of Object.keys(SCANNERS) as CheckId[]) {
    const { unexempted } = measure(check, baseline);
    console.log(
      `\n=== ${check} (${unexempted.length} unexempted, baseline ` +
        `${baseline.checks[check]?.maxViolations ?? "?"}) ===\n` +
        formatViolations(unexempted),
    );
  }
}

describe("design-system ratchet (#954, #797, #1091, #1092, #1093, #1099)", () => {
  it("records a baseline file for the re-baseline command to write", () => {
    expect(
      existsSync(BASELINE_PATH),
      `missing ${BASELINE_PATH}; recreate it with ${REBASELINE_HINT}`,
    ).toBe(true);
    for (const check of Object.keys(SCANNERS) as CheckId[]) {
      expect(baseline.checks[check], `baseline has no entry for ${check}`).toBeDefined();
      expect(typeof baseline.checks[check].maxViolations).toBe("number");
    }
  });

  it("enforces only btn-* classes that styles/global.css actually defines", () => {
    // Issue #1099: the gate once blessed `btn-icon`, a class the design system
    // did not define, so a component could pass while rendering an unstyled
    // button. A positive list only helps if every entry is real; this pins it
    // to the stylesheet and fails on a future phantom class.
    const css = readFileSync(join(SRC_DIR, "styles", "global.css"), "utf-8");
    const undefinedClasses = CHROME_CLASSES.filter(
      (cls) => !new RegExp(`\\.${cls}(?=[\\s,{:])`).test(css),
    );
    expect(
      undefinedClasses,
      [
        "class(es) in CHROME_CLASSES have no rule in styles/global.css:",
        ...undefinedClasses.map((cls) => `  .${cls}`),
        "",
        "Either add the variant to global.css (with tokens) or drop it from",
        "CHROME_CLASSES. Never bless a class the design system does not define.",
      ].join("\n"),
    ).toEqual([]);
  });

  it("gives every .btn-icon button an accessible name (#1099)", () => {
    // The `.btn-icon` rule carries its accessible-name contract in a comment
    // (see `global.css` above `.btn-icon`) — this is the executable half. It is
    // a plain assertion, not a baselined scanner, because there is no legacy
    // backlog to freeze: the class was introduced in #1099 and every use must
    // satisfy the contract from the start.
    const violations = scanIconButtonsMissingAccessibleName();
    expect(
      violations.map((v) => `${v.file}:${v.line}`),
      [
        "`.btn-icon` button(s) without an accessible name:",
        ...violations.map((v) => `  ${v.file}:${v.line}`),
        "",
        "`.btn-icon` is icon-only, so it has no text content: it MUST carry an",
        "accessible name — `aria-label`, `aria-labelledby` or a visually-hidden",
        "label. `title` alone is NOT sufficient (WCAG 4.1.2). See the contract",
        "above the `.btn-icon` rule in src/styles/global.css.",
      ].join("\n"),
    ).toEqual([]);
  });

  for (const check of Object.keys(SCANNERS) as CheckId[]) {
    it(`does not add new "${check}" violations beyond the frozen baseline`, () => {
      const result = measured.get(check) ?? measure(check, baseline);
      measured.set(check, result);
      const limit = baseline.checks[check].maxViolations;

      // Identity first: this is the assertion that names the offending file,
      // line and element, and vitest stops at the first failure — so putting the
      // bare count first would hide it behind "expected N to be <= M".
      expect(
        result.fresh.map((v) => `${v.file}:${v.line}  <${v.element}>  ${v.reason}`),
        [
          `new "${check}" violation(s) that the baseline does not know about`,
          `(${result.fresh.length} of ${result.unexempted.length} unexempted):`,
          formatViolations(result.fresh),
          "",
          `Issues: ${baseline.checks[check].issue}`,
          "Fix the element (preferred — that is what the ceiling is for), or, if",
          "it is a legitimate exception, add a one-line-justified entry to the",
          "`exemptions` map in design-system-ratchet.baseline.json keyed by:",
          ...result.fresh.map((v) => `  ${v.key}`),
        ].join("\n"),
      ).toEqual([]);

      // The count is the ratchet's headline number, and a consistency guard on
      // the baseline file itself: `maxViolations` and `known` must describe the
      // same set, or the ceiling could be satisfied by a `known` list that is
      // out of step with it.
      expect(
        result.unexempted.length,
        `${result.unexempted.length} unexempted "${check}" violation(s); the ` +
          `baseline allows ${limit}. The per-violation identities all matched, ` +
          "so the baseline's `maxViolations` and `known` disagree — re-baseline.",
      ).toBeLessThanOrEqual(limit);
    });

    it(`has no stale "${check}" baseline entry`, () => {
      if (DUMPING) return;
      const result = measured.get(check) ?? measure(check, baseline);
      measured.set(check, result);
      expect(
        result.fixed,
        [
          `the "${check}" baseline is stale: ${result.fixed.length} recorded`,
          "violation(s) no longer reproduce, i.e. they were fixed without the",
          "baseline being lowered:",
          ...result.fixed.map((key) => `  ${key}`),
          "",
          "Lower the ceiling (or re-baseline wholesale):",
          REBASELINE_HINT,
        ].join("\n"),
      ).toEqual([]);
    });

    it(`has no stale "${check}" exemption`, () => {
      const result = measured.get(check) ?? measure(check, baseline);
      measured.set(check, result);
      expect(
        result.staleExemptions,
        [
          "exemption(s) in design-system-ratchet.baseline.json no longer match a",
          `real "${check}" violation:`,
          ...result.staleExemptions.map((key) => `  ${key}`),
          "",
          "Delete them — an exemption that describes nothing silently widens",
          "the gate for the day the same element comes back.",
        ].join("\n"),
      ).toEqual([]);
    });
  }

  it("justifies every exemption with a real one-line reason", () => {
    const entries = Object.entries(baseline.exemptions);
    // A bare allow-list is the failure mode this whole file exists to prevent,
    // so the reasons are checked, not trusted. 40 characters is long enough to
    // say *why this element is different* rather than restating the rule.
    const MIN_REASON_LENGTH = 40;
    const unjustified = entries
      .filter(([, value]) => (value?.reason ?? "").trim().length < MIN_REASON_LENGTH)
      .map(([key, value]) => `  ${key}  reason=${JSON.stringify(value?.reason)}`);
    expect(
      unjustified,
      [
        "exemption(s) without a substantive one-line reason:",
        ...unjustified,
        "",
        `An exemption must explain why THIS element is legitimately different,`,
        `in at least ${MIN_REASON_LENGTH} characters. If a blanket exemption is`,
        "really what is needed, say so explicitly in the reason and reference the",
        "issue that accepts it.",
      ].join("\n"),
    ).toEqual([]);
  });

  it("keys every exemption by a real check", () => {
    const checks = Object.keys(SCANNERS);
    const misfiled = Object.keys(baseline.exemptions).filter(
      (key) => !checks.some((check) => key.startsWith(`${check}::`)),
    );
    expect(
      misfiled,
      `exemption key(s) not prefixed with a known check id (${checks.join(", ")}):\n  ${misfiled.join("\n  ")}`,
    ).toEqual([]);
  });
});

describe("re-baseline monotonicity policy (#1099)", () => {
  it("allows a re-baseline that keeps the ceiling", () => {
    expect(() =>
      assertBaselineNotRaised("emoji-as-ui-glyph", 5, 5, true),
    ).not.toThrow();
  });

  it("allows a re-baseline that lowers the ceiling", () => {
    expect(() =>
      assertBaselineNotRaised("emoji-as-ui-glyph", 5, 3, true),
    ).not.toThrow();
  });

  it("refuses a re-baseline that would raise the ceiling", () => {
    expect(() => assertBaselineNotRaised("emoji-as-ui-glyph", 5, 6, true)).toThrow(
      /monotonically non-increasing/,
    );
  });

  it("allows the bootstrap run that creates a missing baseline", () => {
    expect(() =>
      assertBaselineNotRaised("emoji-as-ui-glyph", 0, 6, false),
    ).not.toThrow();
  });
});

describe("icon-button accessible-name predicate (#1099)", () => {
  it("accepts aria-label, aria-labelledby and visible/visually-hidden text", () => {
    expect(hasAccessibleName('aria-label="Close"', null)).toBe(true);
    expect(hasAccessibleName("aria-label={label}", null)).toBe(true);
    expect(hasAccessibleName('aria-labelledby="dialog-title"', null)).toBe(true);
    expect(hasAccessibleName("", "Schließen")).toBe(true);
    expect(
      hasAccessibleName("", '<span className="sr-only">Close</span>'),
    ).toBe(true);
  });

  it("rejects an icon-only button and a title-only button", () => {
    // No attributes, no children.
    expect(hasAccessibleName("", null)).toBe(false);
    expect(
      hasAccessibleName("", '<svg viewBox="0 0 16 16"><path /></svg>'),
    ).toBe(false);
    // `title` alone is not the accessible name (WCAG 4.1.2).
    expect(hasAccessibleName('title="Close"', "<Icon />")).toBe(false);
  });

  it("treats an explicitly empty aria-label literal as no name", () => {
    expect(hasAccessibleName('aria-label=""', "<Icon />")).toBe(false);
    expect(hasAccessibleName("aria-label=''", "<Icon />")).toBe(false);
  });
});
