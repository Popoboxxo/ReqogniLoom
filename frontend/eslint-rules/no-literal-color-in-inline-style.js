/**
 * ESLint rule: forbid hardcoded color literals inside JSX inline styles.
 *
 * Originally `no-hex-color-in-inline-style` (Task 7.3, UI-Konzept-Vollrollout,
 * enforcement gates) — hex-only. Contrast-audit follow-up (#140/#161
 * blast-radius analysis, 2026-08-28) found the hex-only scope let two whole
 * classes of hardcoded color slip through undetected: named CSS colors
 * (`color: "white"`, 41+ real occurrences found by grep, several with a
 * genuine WCAG AA contrast failure baked in — see tokens.css's
 * `--color-on-danger`/`-on-success`/`-on-warning` comments) and
 * `rgb()`/`rgba()`/`hsl()`/`hsla()` calls with plain numeric arguments (16
 * more occurrences). Renamed to `no-literal-color-in-inline-style` to match
 * the widened scope; the old rule id is kept as a plugin-level alias in
 * `eslint-rules/index.js` for backward compatibility (nothing outside this
 * package currently references it, but flat-config rule ids are cheap to
 * keep stable).
 *
 * The UI concept requires every color to come from a design token in
 * `src/styles/tokens.css` (`var(--color-...)`), never a literal baked into a
 * component. Scope is deliberately narrow: only `style={{ ... }}` (and any
 * expression passed to a JSX `style` attribute) is inspected. Hex/color
 * literals in `.css` / `.module.css` files are a different violation class,
 * tracked by the `HEX_LITERAL_CSS_*` ratchet in `src/test/ui-ratchet.test.ts`
 * — this rule does not duplicate that.
 *
 * Detected value shapes (anything reachable from the attribute expression):
 *   - hex literals:               style={{ color: "#fff" }}
 *   - named CSS colors:           style={{ color: "white" }}
 *   - rgb()/rgba()/hsl()/hsla()
 *     with plain numeric args:    style={{ background: "rgba(16,185,129,0.12)" }}
 *   - template literals:          style={{ border: `1px solid #ff0000` }}
 *   - conditional branches:       style={{ color: on ? "#0f0" : "#f00" }}
 *   - spread-composed objects:    style={{ ...base, color: "#abc" }}
 * A hoisted style constant referenced by identifier (`style={rowStyle}`) is
 * NOT inspected — there is no literal in the attribute's own subtree. That is
 * a known, accepted limitation: this rule guards the inline-literal case the
 * ratchet counts, not every possible indirection. (This is also why
 * `canvas/CanvasEditor.tsx`'s Fabric.js `fillStyle`/`strokeStyle` hex values
 * and `DiagramGraphEditor/GraphEdge.tsx`'s hoisted `pathStyle` are naturally
 * out of this rule's reach — neither is a literal inside a `style={{...}}`
 * attribute — so widening the detected value shapes above does not newly
 * break either file; no exemption-list entry was needed.)
 *
 * `rgba(var(--color-primary-rgb), 0.08)` (the established pattern for
 * theme-reactive translucent fills, see tokens.css's `--color-primary-rgb`
 * comment) MUST stay allowed — any functional-color argument list containing
 * `var(` is treated as token-backed, not a literal, and skipped.
 *
 * @type {import('eslint').Rule.RuleModule}
 */

// #rgb | #rgba | #rrggbb | #rrggbbaa, with a negative lookahead so longer
// hex-ish runs (e.g. "#abcdefg", "#1234567") are not partially matched.
const HEX_COLOR_PATTERN = /#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})(?![0-9a-fA-F])/;

// rgb()/rgba()/hsl()/hsla(), with at most one level of nested parens so
// `rgba(var(--color-primary-rgb), 0.08)` is captured whole (its `var(...)`
// argument is itself parenthesized) rather than truncated at the first `)`.
const FUNCTIONAL_COLOR_PATTERN = /\b(rgb|rgba|hsl|hsla)\(((?:[^()]|\([^()]*\))*)\)/gi;

// A function-color argument list is "plain numeric" (and therefore a raw
// literal, not a token reference) if, once `var(...)` calls are stripped
// out, only digits/percent/dot/comma/whitespace/sign characters remain.
const PLAIN_NUMERIC_ARGS_PATTERN = /^[\d%.,\s+-]+$/;

// CSS keywords that resolve to a color but are not a "hardcoded color choice"
// in the sense this rule cares about — they defer to inheritance/an existing
// property/an explicit "no color" state, not a specific RGB value.
const NAMED_COLOR_WHITELIST = new Set([
  "transparent",
  "none",
  "inherit",
  "currentcolor",
  "unset",
  "initial",
]);

// CSS Color Module Level 4 extended keyword set (the standard 148 named
// colors, lowercase). Matched case-insensitively, on word boundaries, so a
// color name occurring as *part* of a longer identifier/word (e.g. "instant"
// containing "tan") is not a false positive.
const CSS_NAMED_COLORS = [
  "aliceblue", "antiquewhite", "aqua", "aquamarine", "azure", "beige",
  "bisque", "black", "blanchedalmond", "blue", "blueviolet", "brown",
  "burlywood", "cadetblue", "chartreuse", "chocolate", "coral",
  "cornflowerblue", "cornsilk", "crimson", "cyan", "darkblue", "darkcyan",
  "darkgoldenrod", "darkgray", "darkgreen", "darkgrey", "darkkhaki",
  "darkmagenta", "darkolivegreen", "darkorange", "darkorchid", "darkred",
  "darksalmon", "darkseagreen", "darkslateblue", "darkslategray",
  "darkslategrey", "darkturquoise", "darkviolet", "deeppink", "deepskyblue",
  "dimgray", "dimgrey", "dodgerblue", "firebrick", "floralwhite",
  "forestgreen", "fuchsia", "gainsboro", "ghostwhite", "gold", "goldenrod",
  "gray", "grey", "green", "greenyellow", "honeydew", "hotpink", "indianred",
  "indigo", "ivory", "khaki", "lavender", "lavenderblush", "lawngreen",
  "lemonchiffon", "lightblue", "lightcoral", "lightcyan",
  "lightgoldenrodyellow", "lightgray", "lightgreen", "lightgrey", "lightpink",
  "lightsalmon", "lightseagreen", "lightskyblue", "lightslategray",
  "lightslategrey", "lightsteelblue", "lightyellow", "lime", "limegreen",
  "linen", "magenta", "maroon", "mediumaquamarine", "mediumblue",
  "mediumorchid", "mediumpurple", "mediumseagreen", "mediumslateblue",
  "mediumspringgreen", "mediumturquoise", "mediumvioletred", "midnightblue",
  "mintcream", "mistyrose", "moccasin", "navajowhite", "navy", "oldlace",
  "olive", "olivedrab", "orange", "orangered", "orchid", "palegoldenrod",
  "palegreen", "paleturquoise", "palevioletred", "papayawhip", "peachpuff",
  "peru", "pink", "plum", "powderblue", "purple", "rebeccapurple", "red",
  "rosybrown", "royalblue", "saddlebrown", "salmon", "sandybrown", "seagreen",
  "seashell", "sienna", "silver", "skyblue", "slateblue", "slategray",
  "slategrey", "snow", "springgreen", "steelblue", "tan", "teal", "thistle",
  "tomato", "turquoise", "violet", "wheat", "white", "whitesmoke", "yellow",
  "yellowgreen",
];
const NAMED_COLOR_PATTERN = new RegExp(`\\b(${CSS_NAMED_COLORS.join("|")})\\b`, "i");

/** First hex color literal in `text`, or `null`. */
function findHexColor(text) {
  const match = HEX_COLOR_PATTERN.exec(text);
  return match ? match[0] : null;
}

/** First `rgb()`/`rgba()`/`hsl()`/`hsla()` call with plain numeric args, or `null`. */
function findFunctionalColor(text) {
  FUNCTIONAL_COLOR_PATTERN.lastIndex = 0;
  let match;
  while ((match = FUNCTIONAL_COLOR_PATTERN.exec(text)) !== null) {
    const [whole, , rawArgs] = match;
    if (rawArgs.includes("var(")) continue; // token-backed, e.g. rgba(var(--color-primary-rgb), 0.08)
    const withoutNestedCalls = rawArgs.replace(/\([^()]*\)/g, "");
    if (PLAIN_NUMERIC_ARGS_PATTERN.test(withoutNestedCalls)) return whole;
  }
  return null;
}

/**
 * First non-whitelisted named CSS color in `text`, or `null`.
 *
 * `var(...)` calls are stripped before matching — a token name can
 * legitimately contain a color word bounded by `-` (e.g.
 * `var(--palette-black-a04)`, `var(--color-on-danger)`), and `-`/`(`/`)` are
 * non-word characters, so the naive `\b`-bounded pattern below would
 * otherwise false-positive on the token name itself, not a real literal.
 */
function findNamedColor(text) {
  const withoutVarCalls = text.replace(/\bvar\([^()]*\)/g, "");
  NAMED_COLOR_PATTERN.lastIndex = 0;
  const match = NAMED_COLOR_PATTERN.exec(withoutVarCalls);
  if (!match) return null;
  const name = match[1].toLowerCase();
  return NAMED_COLOR_WHITELIST.has(name) ? null : match[1];
}

/** True if `text` contains any detected literal-color shape. */
function findLiteralColor(text) {
  if (typeof text !== "string") return null;
  return findHexColor(text) ?? findFunctionalColor(text) ?? findNamedColor(text);
}

export const noLiteralColorInInlineStyle = {
  meta: {
    type: "problem",
    docs: {
      description:
        "Disallow hardcoded color literals (hex, named CSS colors, rgb()/rgba()/hsl()/hsla() with plain numeric args) inside JSX inline style attributes; use a design token from styles/tokens.css instead.",
    },
    schema: [],
    messages: {
      literalColorInInlineStyle:
        'Hardcoded color "{{value}}" in an inline style. Use a design token instead, e.g. style={{ color: "var(--color-text)" }} (see src/styles/tokens.css).',
    },
  },

  create(context) {
    /** Report `node` if its raw text carries a literal color. */
    function check(node, text) {
      const value = findLiteralColor(text);
      if (!value) return;
      context.report({ node, messageId: "literalColorInInlineStyle", data: { value } });
    }

    /**
     * Depth-first walk over every child node of the style expression. A manual
     * walk (rather than a second set of selectors) keeps the rule scoped to
     * the `style` attribute subtree only — selectors would need to re-derive
     * that ancestry for every string literal in the file.
     */
    function walk(node, seen) {
      if (node === null || typeof node !== "object" || seen.has(node)) return;
      seen.add(node);

      if (Array.isArray(node)) {
        for (const item of node) walk(item, seen);
        return;
      }
      if (typeof node.type !== "string") return;

      if (node.type === "Literal") {
        check(node, node.value);
      } else if (node.type === "TemplateElement") {
        check(node, node.value?.cooked ?? node.value?.raw);
      }

      for (const key of Object.keys(node)) {
        if (key === "parent") continue;
        const child = node[key];
        if (child && typeof child === "object") walk(child, seen);
      }
    }

    return {
      'JSXAttribute[name.name="style"]'(node) {
        if (node.value?.type !== "JSXExpressionContainer") return;
        walk(node.value.expression, new Set());
      },
    };
  },
};
