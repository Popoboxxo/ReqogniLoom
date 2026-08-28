// ESLint 9 flat config for ReqogniLoom frontend.
// Uses typescript-eslint v7 in legacy plugin+parser mode (ESLint 9 compatible).

import js from '@eslint/js';
import tsParser from '@typescript-eslint/parser';
import tsPlugin from '@typescript-eslint/eslint-plugin';
import reactHooksPlugin from 'eslint-plugin-react-hooks';
import jsxA11y from 'eslint-plugin-jsx-a11y';
import globals from 'globals';

import { localRulesPlugin } from './eslint-rules/index.js';
import { LEGACY_INLINE_STYLE_HEX_FILES } from './eslint-rules/legacy-inline-style-hex-files.js';

export default [
  js.configs.recommended,
  {
    files: ['src/**/*.{ts,tsx}'],
    languageOptions: {
      parser: tsParser,
      parserOptions: {
        ecmaVersion: 'latest',
        sourceType: 'module',
        ecmaFeatures: { jsx: true },
      },
      globals: {
        ...globals.browser,
        ...globals.node,
      },
    },
    plugins: {
      '@typescript-eslint': tsPlugin,
      'react-hooks': reactHooksPlugin,
      'jsx-a11y': jsxA11y,
      local: localRulesPlugin,
    },
    rules: {
      ...tsPlugin.configs.recommended.rules,
      'no-undef': 'off',
      '@typescript-eslint/no-undef': 'off',
      'no-unused-vars': 'off',
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', ignoreRestSiblings: true },
      ],
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'warn',
      // Accessibility linting (REQ-056). Warn level so existing violations
      // do not break the build; tighten to 'error' incrementally.
      'jsx-a11y/alt-text': 'warn',
      'jsx-a11y/anchor-is-valid': 'warn',
      'jsx-a11y/click-events-have-key-events': 'warn',
      'jsx-a11y/no-static-element-interactions': 'warn',
      'jsx-a11y/role-has-required-aria-props': 'warn',
      'jsx-a11y/label-has-associated-control': 'warn',

      // --- UI concept enforcement gates (Task 7.3) -------------------------
      // Both at 'error' deliberately: unlike the jsx-a11y rules above (which
      // are 'warn' because they have many pre-existing violations spread over
      // the whole tree), these two are enforceable today — see below.

      // (1) No hardcoded color literals in JSX inline styles; use tokens.css.
      // 'error' project-wide, with a frozen per-file exemption list applied
      // in a later config block for the 21 pre-existing violators. Renamed
      // from 'no-hex-color-in-inline-style' (contrast-audit follow-up
      // #140/#161, 2026-08-28): the hex-only rule let named CSS colors
      // (`color: "white"`) and rgb()/rgba()/hsl()/hsla() literals slip
      // through undetected — both are now covered too. The old rule id is
      // kept as a plugin-level alias in eslint-rules/index.js.
      'local/no-literal-color-in-inline-style': 'error',

      // (2) `aria-modal` is only valid on an element that is actually a
      // dialog. jsx-a11y has no built-in rule for this pairing
      // (`role-supports-aria-props` only checks props against an *explicit*
      // role, so `<div aria-modal>` with no role at all slips through), so it
      // is expressed as an AST selector. Verified violation-free before
      // enabling: `aria-modal` occurs in exactly one production JSX position,
      // `shared/Dialog/Dialog.tsx`, which sets `role="dialog"` alongside it —
      // Task 1.3 migrated all eleven hand-built modals onto that component.
      // A dynamic `role={...}` expression is also reported: this rule cannot
      // prove it evaluates to "dialog", and the shared Dialog is the intended
      // path for every modal anyway.
      'no-restricted-syntax': [
        'error',
        {
          selector:
            'JSXOpeningElement:has(JSXAttribute[name.name="aria-modal"]):not(:has(JSXAttribute[name.name="role"][value.value="dialog"]))',
          message:
            'aria-modal requires role="dialog" on the same element. Prefer the shared <Dialog> component (src/components/shared/Dialog) instead of hand-building a modal.',
        },
      ],
    },
  },
  // Frozen exemption list for the hex-in-inline-style rule — see
  // `eslint-rules/legacy-inline-style-hex-files.js` for why these files are
  // exempt and how the list is meant to shrink. ESLint 9's flat config
  // rejects an empty `files` array (`Expected value to be a non-empty
  // array`), so this whole block is conditionally spread in only while the
  // list still has entries — checkpoint 4's fix round (2026-08-21) emptied
  // it, since `ImpactView.tsx`/`ReviewsView.tsx` (the last 2 entries) turned
  // out to have zero real hex literals. If the list is ever non-empty again
  // (a future file gaining a legacy exemption), this block reactivates
  // automatically with no further config change needed.
  ...(LEGACY_INLINE_STYLE_HEX_FILES.length > 0
    ? [
        {
          files: LEGACY_INLINE_STYLE_HEX_FILES,
          rules: {
            'local/no-literal-color-in-inline-style': 'off',
          },
        },
      ]
    : []),
  {
    files: ['src/**/*.test.{ts,tsx}', 'src/test/**/*.{ts,tsx}'],
    rules: {
      // Test doubles/mocks routinely need loose typing; keep signal for
      // production code (still 'error' there) without blocking CI on tests.
      '@typescript-eslint/no-explicit-any': 'warn',
    },
  },
  {
    ignores: ['dist/**', 'node_modules/**', 'coverage/**'],
  },
];
