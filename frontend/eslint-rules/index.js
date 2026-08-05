/**
 * Local ESLint plugin for ReqogniLoom frontend-specific rules.
 *
 * Consumed by `eslint.config.js` as the `local` plugin, so rules are
 * addressed as `local/<rule-name>`.
 */
import { noHexColorInInlineStyle } from "./no-hex-color-in-inline-style.js";

export const localRulesPlugin = {
  meta: { name: "eslint-plugin-local", version: "1.0.0" },
  rules: {
    "no-hex-color-in-inline-style": noHexColorInInlineStyle,
  },
};
