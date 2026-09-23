/**
 * Local ESLint plugin for ReqogniLoom frontend-specific rules.
 *
 * Consumed by `eslint.config.js` as the `local` plugin, so rules are
 * addressed as `local/<rule-name>`.
 */
import { noLiteralColorInInlineStyle } from "./no-literal-color-in-inline-style.js";
import { noStaticInlineStyle } from "./no-static-inline-style.js";

export const localRulesPlugin = {
  meta: { name: "eslint-plugin-local", version: "1.0.0" },
  rules: {
    "no-literal-color-in-inline-style": noLiteralColorInInlineStyle,
    // #876, Option C: second local UI rule — forbids static inline style
    // object literals (`style={{...}}`) that carry no color literal and thus
    // pass the color rule above untouched. No alias: there is no prior rule
    // id to keep stable.
    "no-static-inline-style": noStaticInlineStyle,
    // Contrast-audit follow-up (#140/#161, 2026-08-28): kept as an alias of
    // the renamed rule above (widened from hex-only to also catch named CSS
    // colors and rgb()/rgba()/hsl()/hsla() literals) purely for backward
    // compatibility of the rule id — nothing outside this package currently
    // references it. Never diverge the two entries.
    "no-hex-color-in-inline-style": noLiteralColorInInlineStyle,
  },
};
