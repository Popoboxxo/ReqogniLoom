/**
 * ESLint rule: forbid hardcoded hex color literals inside JSX inline styles.
 *
 * Part of Task 7.3 (UI-Konzept-Vollrollout, enforcement gates). The UI concept
 * requires every color to come from a design token in `src/styles/tokens.css`
 * (`var(--color-...)`), never from a literal hex value baked into a component.
 *
 * Scope is deliberately narrow: only `style={{ ... }}` (and any expression
 * passed to a JSX `style` attribute) is inspected. Hex literals in `.css` /
 * `.module.css` files are a different violation class and are tracked by the
 * `HEX_LITERAL_CSS_*` ratchet in `src/test/ui-ratchet.test.ts` — this rule
 * does not duplicate that.
 *
 * Detected value shapes (anything reachable from the attribute expression):
 *   - string literals:            style={{ color: "#fff" }}
 *   - template literals:          style={{ border: `1px solid #ff0000` }}
 *   - conditional branches:       style={{ color: on ? "#0f0" : "#f00" }}
 *   - spread-composed objects:    style={{ ...base, color: "#abc" }}
 * A hoisted style constant referenced by identifier (`style={rowStyle}`) is
 * NOT inspected — there is no literal in the attribute's own subtree. That is
 * a known, accepted limitation: this rule guards the inline-literal case the
 * ratchet counts, not every possible indirection.
 *
 * @type {import('eslint').Rule.RuleModule}
 */

// #rgb | #rgba | #rrggbb | #rrggbbaa, with a negative lookahead so longer
// hex-ish runs (e.g. "#abcdefg", "#1234567") are not partially matched.
const HEX_COLOR_PATTERN = /#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})(?![0-9a-fA-F])/;

/** True if `text` contains something that looks like a CSS hex color. */
function containsHexColor(text) {
  return typeof text === "string" && HEX_COLOR_PATTERN.test(text);
}

export const noHexColorInInlineStyle = {
  meta: {
    type: "problem",
    docs: {
      description:
        "Disallow hardcoded hex color literals inside JSX inline style attributes; use a design token from styles/tokens.css instead.",
    },
    schema: [],
    messages: {
      hexInInlineStyle:
        'Hardcoded hex color "{{hex}}" in an inline style. Use a design token instead, e.g. style={{ color: "var(--color-text)" }} (see src/styles/tokens.css).',
    },
  },

  create(context) {
    /** Report `node` if its raw text carries a hex color. */
    function check(node, text) {
      if (!containsHexColor(text)) return;
      const [hex] = text.match(HEX_COLOR_PATTERN);
      context.report({ node, messageId: "hexInInlineStyle", data: { hex } });
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
