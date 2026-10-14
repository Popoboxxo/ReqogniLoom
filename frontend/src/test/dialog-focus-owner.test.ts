/**
 * Dialog focus-owner guard (#1264).
 *
 * The gap this suite closes
 * -------------------------
 * The shared `Dialog` primitive owns the initial focus: it focuses the element
 * behind `initialFocusRef`, otherwise the first operable control (see
 * `shared/Dialog/Dialog.tsx` + `shared/Dialog/use-focus-trap.ts`). A form that
 * *also* sets the native `autoFocus` attribute on one of its fields hands the
 * initial focus to a second owner. The two mechanisms race on mount and the
 * result is order-dependent: focus jumps, ESC/Tab behave inconsistently, and a
 * field can end up unreachable — the "komplett defekt" report behind #1264.
 *
 * The rule enforced here is deliberately narrow and mechanical:
 *   A component that passes `initialFocusRef` to a Dialog must NOT also carry
 *   the native `autoFocus` attribute. One dialog, one focus owner.
 *
 * Fields that only use `autoFocus` (no `initialFocusRef`) are *not* flagged by
 * this guard — that is a single owner. Existing "F-08" dialogs already follow
 * the correct pattern (Dialog `initialFocusRef`, no `autoFocus`); this gate
 * keeps them there.
 *
 * How it works
 * ------------
 * Static, source-level scan: walk every non-test `.tsx` under `src/components`,
 * blank out comments, and flag any file that mentions both tokens. Mirrors the
 * file-walker approach of `ui-ratchet.test.ts` / `design-system-ratchet.test.ts`
 * — a CI gate, no browser or dev stack required.
 */
import { readdirSync, readFileSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const SRC_DIR = resolve(__dirname, "..");
const COMPONENTS_DIR = join(SRC_DIR, "components");

/** Remove block and line comments so a prose mention never trips the gate. */
function stripComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/(^|[^:])\/\/.*$/gm, "$1");
}

function collectTsx(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      collectTsx(full, out);
      continue;
    }
    if (!entry.name.endsWith(".tsx")) continue;
    if (entry.name.endsWith(".test.tsx")) continue;
    out.push(full);
  }
  return out;
}

describe("Dialog focus owner (#1264)", () => {
  it("no component mixes Dialog `initialFocusRef` with a native `autoFocus`", () => {
    const offenders: string[] = [];

    for (const file of collectTsx(COMPONENTS_DIR)) {
      const code = stripComments(readFileSync(file, "utf-8"));
      const usesInitialFocusRef = code.includes("initialFocusRef");
      const usesAutoFocus = /(^|\s)autoFocus(\s|>|\/|=)/.test(code);
      if (usesInitialFocusRef && usesAutoFocus) {
        offenders.push(relative(SRC_DIR, file));
      }
    }

    expect(
      offenders,
      offenders.length
        ? `These components hand the Dialog an initialFocusRef AND set a native autoFocus — two focus owners race on mount (#1264). Drop the autoFocus; the Dialog owns the initial focus:\n  ${offenders.join("\n  ")}`
        : undefined
    ).toEqual([]);
  });
});
