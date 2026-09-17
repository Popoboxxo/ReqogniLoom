# Multi-Palette Theming — Phase 3 (Palette Rollout + WCAG Contrast Tests) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 3 new, fully-designed named themes (`bauhaus`, `nordic`, `sepia`) to the existing 2-theme (`dark`/`light`) registry, each a complete `:root[data-theme="<id>"]` semantic block in `tokens.css` covering all 72 existing `--color-*` tokens, wired into `ThemeContext.tsx`'s `THEMES` array (which the Settings UI already renders automatically, per Phase 1's registry-driven design) — plus automated WCAG AA contrast tests per palette, per the spec's Phase 3 requirement.

**Architecture:** Same two-layer primitive/semantic split every prior phase used. No frontend logic changes — `ThemeContext.tsx`, `WorkspaceContext.tsx`, `SidebarNavigation.tsx`, `WorkspaceSettings.tsx` are all already theme-count-agnostic (confirmed: `THEMES.map(...)` + `t(themeDef.labelKey)`, no hardcoded 2-theme assumption anywhere — this was explicitly verified/fixed in Phase 1 Task 5's review). This phase is pure data: new primitives, new semantic blocks, new registry entries, new i18n labels, new tests.

**Spec:** `docs/superpowers/specs/2026-08-20-multi-palette-theming-design.md` §4.4

**User-approved palette specs (2026-08-21):**

**`bauhaus`** — user-specified exact hex values, do not alter the anchors:
| Role | Hex | Note |
|---|---|---|
| Background (surface) | `#F4F4F0` | Alabaster |
| Text/structure | `#1A2B4C` | Deep Navy |
| Primary action | `#EBB54A` | Mustard |
| Danger | `#C55A4E` | Terracotta |
| Success | `#4A7C72` | Muted Teal |
| Muted/border | `#8E9CA3` | Slate Gray |

**`nordic`** and **`sepia`** — controller-proposed, user-approved; anchors below already include 2 controller-side adjustments (documented under "WCAG adjustments") to the initially-proposed primary shade, made specifically to pass WCAG AA on the primary button (both are the controller's own proposals, not user-specified exact values, so this tuning is in scope):

| Role | `nordic` (dark) | `sepia` (light) |
|---|---|---|
| Background (surface) | `#1B2430` | `#F7F1E3` |
| Text/structure | `#E5E9F0` | `#3B2F2F` |
| Primary action | `#4E6F97`¹ | `#945829`¹ |
| Warning | `#D08770` | `#B8863C` |
| Danger | `#BF616A` | `#A83232` |
| Success | `#A3BE8C` | `#4E7C59` |
| Muted/border | `#4C566A` | `#B8A48A` |

¹ WCAG adjustment: the controller's initial proposal (`nordic` `#5E81AC`, `sepia` `#C97B3D`) failed AA (4.5:1) for on-primary button text at both candidate text colors (white and the palette's own dark text). Both were deepened by 1-2 Tailwind-style ramp steps toward their own hue (nordic: ramp step 500→600; sepia: ramp step 500→700) until white-on-primary passes AA (nordic 5.19:1, sepia 5.70:1). Both remain clearly recognizable as "frost blue" / "burnt orange" — this is a shade adjustment, not a hue change.

## Global Constraints

- Every primitive value for the 3 new palettes lives under a clearly-namespaced primitive block (e.g. `--palette-bauhaus-navy-900`, `--palette-nordic-blue-600`, `--palette-sepia-orange-700` — follow the file's existing `--palette-<family>-<step>` naming convention exactly, generating a 10-step Tailwind-style ramp — 50/100/200/300/400/500/600/700/800/900 — for each of the 5 hue families per palette: primary, danger, warning, success, muted/neutral). Do NOT reuse `--palette-slate-*`/`--palette-indigo-*`/etc. for the new palettes even where visually similar — each new palette gets its own primitive family, so it can be re-tuned independently later without affecting `dark`/`light`.
- Every semantic `--color-*` token in each new theme block must be `var(--palette-<new-family>-*)` — never a fresh raw hex value directly in the semantic block (matches every prior phase's rule).
- The 43 "frozen" tokens (identical in both existing `dark`/`light` blocks — see the exact list in Task 1 below) get the SAME frozen values copied verbatim into all 3 new blocks too — do not re-derive them, do not deviate. (Rationale, confirmed by inspecting the current file: these are status/semantic indicator tokens — diff colors, summary colors, req-type badges, link-type badges, metric colors, diagram-edge colors, gradient, level-badges, on-primary-adjacent tokens, nav chrome — that this codebase's own design already treats as theme-independent branding constants, not re-skinned per theme. This phase does not revisit that design decision.)
- Alpha-variant primitives (e.g. `--palette-indigo-500-a15`, matching the existing `-aXX` suffix convention already used throughout the file) must be added for any new-palette color used in a translucent context (badge backgrounds in a dark-style theme, `card-active-bg`, etc.) — follow the exact existing naming/definition pattern (`rgba(r, g, b, 0.XX)`), don't invent a new convention.
- WCAG contrast tests (new, per spec Phase 3): for each of the 3 new palettes, assert ≥4.5:1 for `text`/`surface`, `on-primary`/`primary`, and every `badge-*-text`/`badge-*-bg` pair. Where a token pair (inherited from the user-specified `bauhaus` anchors) falls slightly short of 4.5:1, the test asserts the ACTUAL measured value as a named, commented exception (matching this codebase's own established ratchet-test philosophy: measure reality, don't assume) — do not silently lower the bar file-wide, and do not alter `bauhaus`'s user-specified anchor hexes to force a pass.
- Commit after each task (standing instruction: every intermediate state gets saved).

---

### Task 1: Add primitive color ramps for 3 new palettes to `tokens.css`

**Files:**
- Modify: `frontend/src/styles/tokens.css` (primitive `:root {}` block only — the one starting at file line 33, per the current file; add new entries near the end of that block, do not touch existing primitives)

Generate a 10-step Tailwind-style ramp (steps 50/100/200/300/400/500/600/700/800/900) for each of these 15 hue families (5 per palette × 3 palettes), using HSL lightness targets `{50:97%, 100:94%, 200:87%, 300:77%, 400:65%, 500:53%, 600:45%, 700:37%, 800:29%, 900:21%}` applied to each anchor's own hue/saturation (reduce saturation ~40% at the 50/100 extremes and ~10% at 900, matching how the existing indigo/emerald/slate ramps taper) — OR, simpler and less error-prone: use the exact pre-computed hex values below (already generated and WCAG-checked by the controller; transcribe them exactly, do not regenerate):

**`bauhaus` primitives** (5 families — navy is the text/structure anchor, not a ramp since it's used directly as `--color-text`, but include it as a single primitive too):
```
--palette-bauhaus-navy: #1A2B4C;
--palette-bauhaus-mustard-50: #fbf9f4;
--palette-bauhaus-mustard-100: #f7f2e8;
--palette-bauhaus-mustard-200: #eee3ce;
--palette-bauhaus-mustard-300: #f3d495;
--palette-bauhaus-mustard-400: #edbd5e;
--palette-bauhaus-mustard-500: #EBB54A; /* user-specified anchor, kept exact */
--palette-bauhaus-mustard-600: #cf9117;
--palette-bauhaus-mustard-700: #aa7713;
--palette-bauhaus-mustard-800: #855d0f;
--palette-bauhaus-mustard-900: #5c420f;
--palette-bauhaus-terracotta-50: #faf5f5;
--palette-bauhaus-terracotta-100: #f4eceb;
--palette-bauhaus-terracotta-200: #e8d6d4;
--palette-bauhaus-terracotta-300: #e2ada7;
--palette-bauhaus-terracotta-400: #d38279;
--palette-bauhaus-terracotta-500: #C55A4E; /* user-specified anchor, kept exact */
--palette-bauhaus-terracotta-600: #ad4439;
--palette-bauhaus-terracotta-700: #8e382f;
--palette-bauhaus-terracotta-800: #6f2c25;
--palette-bauhaus-terracotta-900: #4e221d;
--palette-bauhaus-amber-50: #faf8f4;
--palette-bauhaus-amber-100: #f6f1ea;
--palette-bauhaus-amber-200: #ebe0d1;
--palette-bauhaus-amber-300: #eacc9e;
--palette-bauhaus-amber-400: #e0b16c;
--palette-bauhaus-amber-500: #C98A2B; /* controller-derived warning, distinct hue-step from mustard-500 */
--palette-bauhaus-amber-600: #bd8228;
--palette-bauhaus-amber-700: #9b6b21;
--palette-bauhaus-amber-800: #7a541a;
--palette-bauhaus-amber-900: #553c16;
--palette-bauhaus-teal-50: #f6f9f8;
--palette-bauhaus-teal-100: #edf2f1;
--palette-bauhaus-teal-200: #d9e3e1;
--palette-bauhaus-teal-300: #b6d3cd;
--palette-bauhaus-teal-400: #8fbcb3;
--palette-bauhaus-teal-500: #4A7C72; /* user-specified anchor, kept exact */
--palette-bauhaus-teal-600: #569084;
--palette-bauhaus-teal-700: #47766d;
--palette-bauhaus-teal-800: #375d55;
--palette-bauhaus-teal-900: #29423d;
--palette-bauhaus-slate-50: #f7f8f8;
--palette-bauhaus-slate-100: #eff0f1;
--palette-bauhaus-slate-200: #dcdfe0;
--palette-bauhaus-slate-300: #bec6ca;
--palette-bauhaus-slate-400: #9da9af;
--palette-bauhaus-slate-500: #8E9CA3; /* user-specified anchor, kept exact */
--palette-bauhaus-slate-600: #67777f;
--palette-bauhaus-slate-700: #556268;
--palette-bauhaus-slate-800: #424c52;
--palette-bauhaus-slate-900: #31373a;
--palette-bauhaus-alabaster: #F4F4F0; /* user-specified surface anchor */
```

**`nordic` primitives:**
```
--palette-nordic-frost-50: #f6f7f9;
--palette-nordic-frost-100: #edeff3;
--palette-nordic-frost-200: #d7dde4;
--palette-nordic-frost-300: #b2c2d7;
--palette-nordic-frost-400: #89a3c2;
--palette-nordic-frost-500: #6183ad;
--palette-nordic-frost-600: #4e6f97; /* WCAG-adjusted primary, see plan header note 1 */
--palette-nordic-frost-700: #405b7d;
--palette-nordic-frost-800: #324862;
--palette-nordic-frost-900: #263445;
--palette-nordic-aurora-red-50: #f9f5f6;
--palette-nordic-aurora-red-100: #f4eced;
--palette-nordic-aurora-red-200: #e6d5d7;
--palette-nordic-aurora-red-300: #ddacb0;
--palette-nordic-aurora-red-400: #cc8087;
--palette-nordic-aurora-red-500: #BF616A; /* Nord nord11, anchor */
--palette-nordic-aurora-red-600: #a3424b;
--palette-nordic-aurora-red-700: #86363e;
--palette-nordic-aurora-red-800: #692b31;
--palette-nordic-aurora-red-900: #4a2125;
--palette-nordic-aurora-orange-50: #faf6f5;
--palette-nordic-aurora-orange-100: #f4edeb;
--palette-nordic-aurora-orange-200: #e8d9d4;
--palette-nordic-aurora-orange-300: #e2b5a7;
--palette-nordic-aurora-orange-400: #d38e79;
--palette-nordic-aurora-orange-500: #D08770; /* Nord nord12, anchor */
--palette-nordic-aurora-orange-600: #ad5539;
--palette-nordic-aurora-orange-700: #8e462f;
--palette-nordic-aurora-orange-800: #6f3625;
--palette-nordic-aurora-orange-900: #4e291d;
--palette-nordic-aurora-green-50: #f7f9f6;
--palette-nordic-aurora-green-100: #eff2ed;
--palette-nordic-aurora-green-200: #dde3d8;
--palette-nordic-aurora-green-300: #c3d5b4;
--palette-nordic-aurora-green-400: #a4bf8d;
--palette-nordic-aurora-green-500: #A3BE8C; /* Nord nord14, anchor */
--palette-nordic-aurora-green-600: #709353;
--palette-nordic-aurora-green-700: #5c7944;
--palette-nordic-aurora-green-800: #485e35;
--palette-nordic-aurora-green-900: #344328;
--palette-nordic-polar-50: #f7f7f8;
--palette-nordic-polar-100: #eeeff1;
--palette-nordic-polar-200: #dbdde1;
--palette-nordic-polar-300: #bbc1ce;
--palette-nordic-polar-400: #97a1b4;
--palette-nordic-polar-500: #73819b;
--palette-nordic-polar-600: #606c86;
--palette-nordic-polar-700: #4f596e;
--palette-nordic-polar-800: #3e4656;
--palette-nordic-polar-900: #2e333d;
--palette-nordic-night: #1B2430; /* surface anchor */
--palette-nordic-night-raised: #263344; /* surface-raised */
--palette-nordic-snow: #E5E9F0; /* text anchor */
--palette-nordic-frost-600-rgb: 78, 111, 151;
--palette-nordic-frost-500-a15: rgba(97, 131, 173, 0.15); /* card-active-bg */
--palette-nordic-frost-500-a20: rgba(97, 131, 173, 0.2); /* badge-info-bg */
--palette-nordic-aurora-green-500-a20: rgba(163, 190, 140, 0.2); /* badge-success-bg */
--palette-nordic-aurora-orange-500-a20: rgba(208, 135, 112, 0.2); /* badge-warning-bg */
--palette-nordic-aurora-red-500-a20: rgba(191, 97, 106, 0.2); /* badge-danger-bg */
--palette-nordic-polar-500-a20: rgba(115, 129, 155, 0.2); /* badge-neutral-bg, badge-draft */
```

**`sepia` primitives:**
```
--palette-sepia-orange-50: #faf7f5;
--palette-sepia-orange-100: #f5efeb;
--palette-sepia-orange-200: #e9ddd3;
--palette-sepia-orange-300: #e5c1a3;
--palette-sepia-orange-400: #d8a073;
--palette-sepia-orange-500: #cb7f43;
--palette-sepia-orange-600: #b46b32;
--palette-sepia-orange-700: #945829; /* WCAG-adjusted primary, see plan header note 1 */
--palette-sepia-orange-800: #744520;
--palette-sepia-orange-900: #51321a;
--palette-sepia-brick-50: #faf5f5;
--palette-sepia-brick-100: #f5ebeb;
--palette-sepia-brick-200: #e9d3d3;
--palette-sepia-brick-300: #e4a5a5;
--palette-sepia-brick-400: #d67575;
--palette-sepia-brick-500: #A83232; /* user-adjacent proposal anchor */
--palette-sepia-brick-600: #b13535;
--palette-sepia-brick-700: #912b2b;
--palette-sepia-brick-800: #722222;
--palette-sepia-brick-900: #501b1b;
--palette-sepia-gold-50: #faf8f5;
--palette-sepia-gold-100: #f4f1eb;
--palette-sepia-gold-200: #e8e0d4;
--palette-sepia-gold-300: #e2caa7;
--palette-sepia-gold-400: #d3af78;
--palette-sepia-gold-500: #B8863C;
--palette-sepia-gold-600: #ad7e38;
--palette-sepia-gold-700: #8e682e;
--palette-sepia-gold-800: #705124;
--palette-sepia-gold-900: #4e3a1d;
--palette-sepia-forest-50: #f6f8f7;
--palette-sepia-forest-100: #eef2ef;
--palette-sepia-forest-200: #d9e2db;
--palette-sepia-forest-300: #b7d2bd;
--palette-sepia-forest-400: #91ba9b;
--palette-sepia-forest-500: #4E7C59; /* controller proposal anchor */
--palette-sepia-forest-600: #598d65;
--palette-sepia-forest-700: #497453;
--palette-sepia-forest-800: #395b41;
--palette-sepia-forest-900: #2b4130;
--palette-sepia-taupe-50: #f8f7f6;
--palette-sepia-taupe-100: #f2f0ed;
--palette-sepia-taupe-200: #e3ded9;
--palette-sepia-taupe-300: #d3c6b6;
--palette-sepia-taupe-400: #bca990;
--palette-sepia-taupe-500: #B8A48A; /* controller proposal anchor */
--palette-sepia-taupe-600: #8f7657;
--palette-sepia-taupe-700: #756147;
--palette-sepia-taupe-800: #5c4c38;
--palette-sepia-taupe-900: #41372a;
--palette-sepia-cream: #F7F1E3; /* surface anchor */
--palette-sepia-espresso: #3B2F2F; /* text anchor */
--palette-sepia-orange-700-rgb: 148, 88, 41;
```

- [ ] Add all 3 primitive blocks (above) to `tokens.css`'s primitive `:root {}` block, grouped under a clear comment header per palette (`/* Bauhaus Enterprise palette primitives (#568 Phase 3) */` etc.), placed after the existing primitives (do not interleave).
- [ ] Run `cd frontend && npx vitest run src/test/ui-ratchet.test.ts` — confirm no regression (new primitives are legitimate, not counted against the hex-literal ratchet since primitives are exempt by design — verify this is actually true by checking the ratchet only scans `.tsx`/non-`tokens.css`-primitive CSS; if it somehow flags these, that's a ratchet scanner bug to report, not something to work around).
- [ ] Commit: `feat: add primitive color ramps for bauhaus/nordic/sepia palettes (theming phase 3, task 1)`

---

### Task 2: Add the 3 new semantic theme blocks

**Files:**
- Modify: `frontend/src/styles/tokens.css` (add 3 new `:root[data-theme="bauhaus"] {}`, `:root[data-theme="nordic"] {}`, `:root[data-theme="sepia"] {}` blocks, placed after the existing `:root[data-theme="light"] {}` block)

For EACH of the 3 new theme blocks, define all 72 `--color-*` tokens:

**The 29 tokens that vary per theme** (values below, already WCAG-verified by the controller):

| Token | `bauhaus` | `nordic` | `sepia` |
|---|---|---|---|
| `--color-primary` | `var(--palette-bauhaus-mustard-500)` | `var(--palette-nordic-frost-600)` | `var(--palette-sepia-orange-700)` |
| `--color-primary-dark` | `var(--palette-bauhaus-mustard-600)` | `var(--palette-nordic-frost-700)` | `var(--palette-sepia-orange-800)` |
| `--color-primary-rgb` | `235, 181, 74` | `var(--palette-nordic-frost-600-rgb)` | `var(--palette-sepia-orange-700-rgb)` |
| `--color-surface` | `var(--palette-bauhaus-alabaster)` | `var(--palette-nordic-night)` | `var(--palette-sepia-cream)` |
| `--color-surface-raised` | `#ffffff` (use `var(--palette-white)`) | `var(--palette-nordic-night-raised)` | `#ffffff` (use `var(--palette-white)`) |
| `--color-border` | `var(--palette-bauhaus-slate-300)` | `var(--palette-nordic-polar-700)` | `var(--palette-sepia-taupe-300)` |
| `--color-border-hover` | `var(--palette-bauhaus-slate-400)` | `var(--palette-nordic-polar-600)` | `var(--palette-sepia-taupe-400)` |
| `--color-border-subtle` | `var(--palette-bauhaus-slate-300)` | `var(--palette-nordic-polar-700)` | `var(--palette-sepia-taupe-300)` |
| `--color-text` | `var(--palette-bauhaus-navy)` | `var(--palette-nordic-snow)` | `var(--palette-sepia-espresso)` |
| `--color-text-muted` | `var(--palette-bauhaus-slate-600)` | `var(--palette-nordic-polar-400)` | `var(--palette-sepia-taupe-600)` |
| `--color-on-primary` | `var(--palette-bauhaus-navy)` | `var(--palette-white)` | `var(--palette-white)` |
| `--color-success` | `var(--palette-bauhaus-teal-500)` | `var(--palette-nordic-aurora-green-500)` | `var(--palette-sepia-forest-500)` |
| `--color-warning` | `var(--palette-bauhaus-amber-500)` | `var(--palette-nordic-aurora-orange-500)` | `var(--palette-sepia-gold-500)` |
| `--color-danger` | `var(--palette-bauhaus-terracotta-500)` | `var(--palette-nordic-aurora-red-500)` | `var(--palette-sepia-brick-500)` |
| `--color-danger-dark` | `var(--palette-bauhaus-terracotta-700)` | `var(--palette-nordic-aurora-red-400)` | `var(--palette-sepia-brick-700)` |
| `--color-badge-approved` | `var(--palette-bauhaus-teal-100)` | `var(--palette-nordic-aurora-green-500-a20)` | `var(--palette-sepia-forest-100)` |
| `--color-badge-approved-text` | `var(--palette-bauhaus-teal-800)` | `var(--palette-nordic-aurora-green-300)` | `var(--palette-sepia-forest-800)` |
| `--color-badge-danger-bg` | `var(--palette-bauhaus-terracotta-100)` | `var(--palette-nordic-aurora-red-500-a20)` | `var(--palette-sepia-brick-100)` |
| `--color-badge-danger-text` | `var(--palette-bauhaus-terracotta-800)` | `var(--palette-nordic-aurora-red-300)` | `var(--palette-sepia-brick-800)` |
| `--color-badge-draft` | `var(--palette-bauhaus-slate-100)` | `var(--palette-nordic-polar-500-a20)` | `var(--palette-sepia-taupe-100)` |
| `--color-badge-draft-text` | `var(--palette-bauhaus-slate-800)` | `var(--palette-nordic-polar-300)` | `var(--palette-sepia-taupe-800)` |
| `--color-badge-info-bg` | `var(--palette-bauhaus-mustard-100)` | `var(--palette-nordic-frost-500-a20)` | `var(--palette-sepia-orange-100)` |
| `--color-badge-info-text` | `var(--palette-bauhaus-mustard-800)` | `var(--palette-nordic-frost-300)` | `var(--palette-sepia-orange-800)` |
| `--color-badge-neutral-bg` | `var(--palette-bauhaus-slate-100)` | `var(--palette-nordic-polar-500-a20)` | `var(--palette-sepia-taupe-100)` |
| `--color-badge-neutral-text` | `var(--palette-bauhaus-slate-800)` | `var(--palette-nordic-polar-300)` | `var(--palette-sepia-taupe-800)` |
| `--color-badge-success-bg` | `var(--palette-bauhaus-teal-100)` | `var(--palette-nordic-aurora-green-500-a20)` | `var(--palette-sepia-forest-100)` |
| `--color-badge-success-text` | `var(--palette-bauhaus-teal-800)` | `var(--palette-nordic-aurora-green-300)` | `var(--palette-sepia-forest-800)` |
| `--color-badge-warning-bg` | `var(--palette-bauhaus-amber-100)` | `var(--palette-nordic-aurora-orange-500-a20)` | `var(--palette-sepia-gold-100)` |
| `--color-badge-warning-text` | `var(--palette-bauhaus-amber-800)` | `var(--palette-nordic-aurora-orange-300)` | `var(--palette-sepia-gold-800)` |
| `--color-card-active-bg` | `var(--palette-bauhaus-mustard-100)` | `var(--palette-nordic-frost-500-a15)` | `var(--palette-sepia-orange-100)` |
| `--color-focus` | `var(--palette-bauhaus-mustard-600)` | `var(--palette-nordic-frost-400)` | `var(--palette-sepia-orange-800)` |

**The 43 frozen tokens** — copy verbatim from the existing `:root {}` (dark) block into all 3 new blocks, unchanged. Read the current file to get the exact list/values (do not hand-transcribe from memory — re-read `tokens.css`'s dark `:root{}` block at the time of implementation, since Phase 1/2 may have added a couple more since this plan was written): `--color-danger-banner-bg`, `--color-diagram-edge-default`, `--color-diagram-edge-dependency`, `--color-diagram-edge-primary`, `--color-diff-added-bg`, `--color-diff-added-text`, `--color-diff-modified-bg`, `--color-diff-modified-text`, `--color-diff-note-bg`, `--color-diff-note-text`, `--color-diff-removed-bg`, `--color-diff-removed-text`, `--color-diff-unchanged-bg`, `--color-diff-unchanged-text`, `--color-errorboundary-text`, `--color-gradient-ai-end`, `--color-gradient-ai-start`, `--color-level-l0`, `--color-level-l1`, `--color-level-l3`, `--color-level-l4`, `--color-link-hover`, `--color-linktype-badge-bg`, `--color-linktype-badge-text`, `--color-metric-critical`, `--color-metric-healthy`, `--color-metric-neutral`, `--color-metric-warning`, `--color-nav-active-bg`, `--color-nav-bg`, `--color-nav-border`, `--color-nav-hover-bg`, `--color-nav-text`, `--color-nav-text-muted`, `--color-reqtype-default`, `--color-reqtype-featurereq`, `--color-reqtype-syreq`, `--color-reqtype-usecase`, `--color-summary-failed`, `--color-summary-notrun`, `--color-summary-passed`.

- [ ] Write a failing test first (TDD): add a new `describe` block to `frontend/src/test/design-tokens.test.ts` (or wherever the existing "every `--color-*` used in a `var()` resolves to a real declaration" scanner lives — check `design-tokens.test.ts` first, this may already generically cover new theme blocks with no changes needed) asserting each of `bauhaus`/`nordic`/`sepia` blocks defines all 72 tokens (no missing keys vs. the `dark` block's key set). Run it, confirm it fails (blocks don't exist yet).
- [ ] Add the 3 semantic blocks to `tokens.css`, using the table above for the 29 varying tokens and the exact frozen values (re-read from file) for the 43 frozen ones.
- [ ] Run the new test, confirm it passes.
- [ ] Run `cd frontend && npx vitest run src/test/design-tokens.test.ts` (full file) — confirm no regressions.
- [ ] Commit: `feat: add bauhaus/nordic/sepia semantic theme blocks (theming phase 3, task 2)`

---

### Task 3: WCAG AA contrast tests for the 3 new palettes

**Files:**
- Create: `frontend/src/test/theme-contrast.test.ts` (new file — this is the "Kontrast-Test" the design spec's Phase 3 explicitly requires; no such test exists yet for ANY palette including `dark`/`light`, so this task also covers those 2 for completeness, not just the 3 new ones)
- Test: itself

- [ ] Write the failing test first. Implement a small, self-contained WCAG relative-luminance/contrast-ratio calculator (no new dependency — this is ~15 lines of standard math, see e.g. the algorithm the controller used during design: sRGB→linear, then `0.2126*R + 0.7152*G + 0.0722*B`, then `(L1+0.05)/(L2+0.05)`). Parse the ACTUAL resolved hex values by reading `tokens.css` and resolving each theme's `--color-*` → `--palette-*` chain (a `var(--x)` reference resolver — walk the chain until you hit a literal hex or `rgba(...)`; for `rgba()` alpha-blended tokens used as backgrounds, composite against the theme's own `--color-surface` before computing luminance, matching how a browser would actually render it).
- [ ] For each of the 5 themes (`dark`, `light`, `bauhaus`, `nordic`, `sepia`), assert ≥4.5:1 for these token pairs: `text`/`surface`, `on-primary`/`primary`, `badge-success-text`/`badge-success-bg`, `badge-danger-text`/`badge-danger-bg`, `badge-warning-text`/`badge-warning-bg`, `badge-neutral-text`/`badge-neutral-bg`, `badge-info-text`/`badge-info-bg`.
- [ ] Run it. Expected: `dark`/`light` pass (never independently verified before, but designed carefully in Task 8.1's original rollout — if either unexpectedly fails, that's a real pre-existing bug worth flagging in the report, not silently patching). `bauhaus` is expected to show the 2 controller-identified borderline pairs from the plan's design work (`success`/`surface` ≈4.31:1, `text-muted`/`surface` ≈4.21:1 — NOTE: these 2 specific pairs are NOT in the assertion list above since they're not one of the 5 primary token-pairs being tested project-wide; only add an assertion for them if you decide project consistency calls for it, in which case handle exactly like the ratchet-test philosophy: assert the real measured value with a comment explaining it's a known, accepted, user-specified-anchor tradeoff, not a bug to silently pass around). `nordic`/`sepia` are expected to pass on `on-primary`/`primary` given the Task 1/2 WCAG-adjusted primary shades.
- [ ] If anything unexpected fails, do not force a color change to make the test pass — report it plainly (which pair, which theme, actual ratio) and let the controller decide (this is exactly the kind of judgment call Phase 1/2 established should be surfaced, not silently patched).
- [ ] Commit: `test: add WCAG AA contrast tests for all 5 themes (theming phase 3, task 3)`

---

### Task 4: Extend the `THEMES` registry and add i18n labels

**Files:**
- Modify: `frontend/src/context/ThemeContext.tsx` (`THEMES` array)
- Modify: `frontend/src/i18n/locales/de.json`, `frontend/src/i18n/locales/en.json`

- [ ] Read the current `THEMES` array in `ThemeContext.tsx` (2 entries: `DEFAULT_DARK`/`DEFAULT_LIGHT` with `labelKey: "nav.darkMode"`/`"nav.lightMode"`). Add 3 new entries:
  ```ts
  { id: "bauhaus", labelKey: "nav.bauhausTheme" },
  { id: "nordic", labelKey: "nav.nordicTheme" },
  { id: "sepia", labelKey: "nav.sepiaTheme" },
  ```
  (Match the array's exact existing formatting/style — read the file first, don't guess at whitespace/quote conventions.)
- [ ] Add the 3 new i18n keys to BOTH `de.json` and `en.json`'s `"nav"` block, in the same commit (per Global Constraints — required or `i18n-parity.test.ts` fails the build):
  - `de.json`: `"bauhausTheme": "Bauhaus"`, `"nordicTheme": "Nordisch"`, `"sepiaTheme": "Sepia"`
  - `en.json`: `"bauhausTheme": "Bauhaus"`, `"nordicTheme": "Nordic"`, `"sepiaTheme": "Sepia"`
- [ ] Run `cd frontend && npx vitest run src/test/i18n-parity.test.ts` — confirm passes.
- [ ] Run `cd frontend && npx vitest run src/components/WorkspaceSettings/WorkspaceSettings.test.tsx` — confirm still passes (the Settings UI's Theme section is `THEMES.map(...)`-driven from Phase 1, so it should render 5 options now with zero code change — if it does NOT render correctly, that's a real regression to fix, not something to route around).
- [ ] Run `cd frontend && npx vitest run` (full suite) — confirm no regressions beyond the one documented pre-existing `NeedsEditors.test.tsx` failure.
- [ ] Commit: `feat: register bauhaus/nordic/sepia themes in the Settings UI (theming phase 3, task 4)`

---

### Task 5: Close-out

- [ ] Run the full frontend suite once more (`cd frontend && npx vitest run`) and `tsc --noEmit`.
- [ ] Run `cd frontend && npx eslint src` — confirm no new violations.
- [ ] Manual verification note (cannot be done in this sandbox — no browser): flag in the final report that a human should open Settings → General → Theme and visually confirm all 5 options render correctly and look as designed, since no automated test can substitute for actually looking at the rendered colors.
- [ ] Update `docs/superpowers/specs/2026-08-20-multi-palette-theming-design.md`'s Phase 3 row.
- [ ] Push, open a PR against `main` summarizing all 4 tasks, the final contrast-test results per palette, and the 2 known-accepted `bauhaus` borderline pairs.
