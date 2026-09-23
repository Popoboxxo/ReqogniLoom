/**
 * ESLint rule: forbid static object literals inline in a JSX `style` attribute.
 *
 * WHY (#876, Option C)
 * --------------------
 * The frontend has two independent UI gates, and a *new* static inline style
 * that carries no color literal slips through both of them:
 *
 *   - `local/no-literal-color-in-inline-style` (the sibling rule in this
 *     directory) only inspects the *values* inside a `style={{...}}` subtree,
 *     and only reports hex/named/functional color literals. A style such as
 *     `style={{ display: "flex", gap: 8 }}` contains no color at all, so the
 *     color rule has nothing to report.
 *   - The `STYLE_BRACE_BASELINE` ratchet in `src/test/ui-ratchet.test.ts`
 *     only freezes the *total sum* of `style={{` occurrences (the constant IS
 *     the baseline — 3 today, all three inside comments). It does not point at
 *     the file, and it cannot tell a legitimate new usage from a net-zero
 *     reshuffle.
 *
 * When this rule was introduced, an unbounded number of new non-color inline
 * styles could be added as long as the sum stayed at the then-frozen baseline
 * (653), and the color gate stayed silent. This rule closes the gap at the
 * point of introduction: any *new* static inline style object in a governed
 * source file is an error, full stop.
 *
 * WHAT
 * ----
 * Reports exactly the literal-object shape — an `ObjectExpression` that is the
 * direct expression of a JSX `style` attribute:
 *
 *     style={{ display: "flex" }}          // reported
 *     style={{ ...base, display: "flex" }} // reported (ObjectExpression with a SpreadElement)
 *
 * The selector is intentionally the exact AST shape, with no manual tree walk
 * (unlike the color rule, which has to descend into arbitrary value shapes to
 * find literals). As a direct consequence, these are NOT reported, matching
 * the ratchet's own `/style=\{\{/g` accounting:
 *
 *     style={rowStyle}                     // Identifier  — no literal in the attribute
 *     style={cond ? {} : {}}               // ConditionalExpression
 *     style={[{}]}                         // ArrayExpression
 *     style={`color: red`}                 // TemplateLiteral
 *     style="display: flex"                // String literal (not an expression)
 *
 * Comments are irrelevant to this rule: the AST never sees them (they are not
 * AST nodes), so — unlike the ratchet test, which scans raw text — no
 * comment-stripping logic is needed or wanted here.
 *
 * MAINTENANCE (same convention as the sibling rule's exemption list)
 * ------------------------------------------------------------------
 * Existing violations are frozen per file in
 * `eslint-rules/legacy-static-inline-style-files.js`. That list is a ratchet
 * too: "never ADD an entry to make a build pass" — fix the style instead —
 * and "DELETE the entry in the same PR that migrates the file".
 *
 * KNOWN GAPS (deliberate, not silently accepted)
 * ----------------------------------------------
 * 1. Per-file exemption is all-or-nothing (`off`). Inside an already-exempted
 *    file, an *additional* static inline style is not seen by ESLint. Within
 *    the ratchet's scope it is still caught: the exact-equality assertion in
 *    `src/test/ui-ratchet.test.ts` ("does not exceed the frozen baseline of
 *    style={{ occurrences (monotonic)") compares the raw-text count against
 *    the `STYLE_BRACE_BASELINE` constant, so ANY net increase anywhere under
 *    `src/components` (every non-test `.tsx` file) turns the ratchet red —
 *    see also the `<=` ceiling test in the same file.
 *    The residual gap is therefore only a *net-zero* reshuffle: add one style
 *    here and delete one there in exempted files, and both the ratchet (sum
 *    unchanged) and this rule (file exempted) stay silent. That gap is
 *    accepted; a per-file counting rule would duplicate the ratchet's job with
 *    68 extra baselines and a large instability surface, so it is deliberately
 *    NOT built.
 * 2. The ratchet backstop only covers `src/components` (every non-test
 *    `.tsx`), while this rule's activation scope is all of `src`
 *    (`.ts`/`.tsx`, tests excluded).
 *    Every carrier file measured at introduction lives under `components/`,
 *    so the scopes coincide today; if a governed non-components file ever
 *    gains a static inline style it would be caught by this rule unless
 *    exempted, and it would have no ratchet backstop.
 * 3. Latent over-catch relative to the ratchet (currently 0 occurrences, left
 *    enabled on purpose — these ARE static inline styles and should be
 *    fixed): an inline comment between the attribute braces (a `style=` whose
 *    opening brace is immediately followed by a comment and only then by the
 *    object) and `style={ {…} }` (whitespace between the braces). The
 *    ratchet's raw-text pattern (a literal `style=` immediately followed by
 *    `{{`) does not count either, but the AST selector does report them.
 *    Documented, not configured away.
 * 4. A hoisted style constant referenced by identifier (`style={rowStyle}`) is
 *    never inspected — same accepted limitation as the sibling color rule.
 *
 * Measured 2026-09-22 on branch main via `npx eslint src -f json` with the
 * exemption list temporarily empty: 702 AST-visible occurrences in 70 files.
 * The ratchet's raw-text count was 705 in 71 files; the difference of exactly
 * 3 is explained by three `style={{` occurrences that exist only inside
 * comments (RequirementTreeNode.tsx, ArchitectureEditors.tsx,
 * WorkspaceSettings.tsx) — the ratchet counts raw text, this rule sees the AST.
 *
 * Issue #876 follow-up (2026-09-23, historical): `TestRuns/TestRunDetailEditor.tsx`
 * and `TestRuns/TestRunsList.tsx` were migrated onto CSS Modules, dropping
 * their entries from the exemption list. Re-measured with the list empty at
 * that point: 650 AST-visible occurrences in 68 files (ratchet raw-text: 653
 * in 69 files, the same 3-comment gap). Both figures have since dropped
 * further — see the current-state note below.
 *
 * Current state (2026-09-23, issue #876 Etappe 7, branch
 * `refactor/876-etappe7-inline-styles`): after the three Etappe 7 batches the
 * exemption list `eslint-rules/legacy-static-inline-style-files.js` is EMPTY,
 * so this rule guards the whole of `src` (all `.ts`/`.tsx`, tests excluded)
 * with no per-file exemptions. Measured with `npx eslint src -f json`: 0
 * AST-visible static inline-style object literals under `components/`. The
 * ratchet's raw-text count in the same scope is 3, all three inside comments
 * (`ArchitectureEditors.tsx`, `RequirementTreeNode.tsx`,
 * `WorkspaceSettings.tsx`) — the raw-vs-AST gap of 3 described above,
 * unchanged.
 *
 * @type {import('eslint').Rule.RuleModule}
 */
export const noStaticInlineStyle = {
  meta: {
    type: "problem",
    docs: {
      description:
        "Disallow static object literals inline in a JSX style attribute; use a CSS class/module (design tokens from src/styles/tokens.css) instead.",
    },
    schema: [],
    messages: {
      staticInlineStyle:
        "Static inline style object. Use a CSS class/module backed by design tokens (see src/styles/tokens.css) instead of style={{...}}.",
    },
  },

  create(context) {
    return {
      // Exact literal-object shape only: a `style` JSX attribute whose
      // expression is directly an ObjectExpression. No manual walk, no
      // Identifier/Conditional/Array/Template, no string literals.
      'JSXAttribute[name.name="style"] > JSXExpressionContainer > ObjectExpression'(
        node,
      ) {
        context.report({ node, messageId: "staticInlineStyle" });
      },
    };
  },
};
