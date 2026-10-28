/**
 * Dialog-consistency ratchet (#1282).
 *
 * The app has exactly one create-flow shape: a modal rendered through the
 * shared `shared/Dialog` primitive (`role="dialog"` + `aria-modal` + focus
 * trap + Escape + focus return). `/baselines` was the single exception — it
 * rendered its create form inline in the right-hand `SplitView` pane, the only
 * create flow with no `role="dialog"` and no Escape handling. That is the
 * defect this ratchet freezes against: it pins every artifact route's create
 * flow to the shared Dialog, so a future route cannot regress to an inline
 * form unnoticed.
 *
 * Static and source-level on purpose (same approach as
 * `design-system-ratchet.test.ts`): no browser, no dev server, no rendering,
 * so it is a real CI gate. It checks two things per host:
 *   1. the file reaches the shared Dialog primitive, and
 *   2. it actually renders it (`<Dialog`).
 * An import-only match would pass while the JSX still used an inline panel.
 *
 * Reachability, not just direct use (F-15, plan Phase 3b)
 * ------------------------------------------------------
 * Four routes (Adr/Risk/Issue/TestCase) used to render `<Dialog>` themselves;
 * they now render the shared `shared/EditorPageShell`, which owns the
 * `<Dialog>` + form + save-shortcut wiring. The host list stays the same and
 * each route may satisfy the contract EITHER directly OR by delegating to the
 * shell — and the shell is pinned as its own host, so the indirect path is
 * covered end to end. Weakening the check to "any host" would let a route drop
 * its create flow entirely and still pass; this keeps every route pinned to a
 * real modal.
 */
import { readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";

// #1392/#1393: the host list moved to a shared fixture so the maxLength /
// required-marker ratchet (`create-dialog-maxlength.test.ts`) enumerates the
// SAME 12 dialogs instead of keeping a second, drifting copy.
import { CREATE_FLOW_HOSTS, CREATE_FLOW_SHELL } from "./fixtures/create-dialog-hosts";

const COMPONENTS_DIR = join(resolve(__dirname, ".."), "components");

/**
 * Every host that must reach the shared Dialog: the routes plus the shell they
 * may delegate to.
 */
const CREATE_FLOW_REACH_HOSTS = [...CREATE_FLOW_HOSTS, CREATE_FLOW_SHELL];

/**
 * True when the source reaches the shared Dialog: it imports `shared/Dialog`
 * directly, or it imports the shared `EditorPageShell` (which is itself pinned
 * to import and render `shared/Dialog`). The `\/Dialog` segment anchor keeps
 * `ConfirmDialog` / `AiDerivationDialog` — different dialogs — from matching.
 */
function reachesSharedDialog(source: string): boolean {
  return (
    /from\s+["'][^"']*\/Dialog["']/.test(source) ||
    /from\s+["'][^"']*\/EditorPageShell["']/.test(source)
  );
}

/** True when the source renders the dialog directly or via the shell. */
function rendersSharedDialog(source: string): boolean {
  return /<Dialog\b/.test(source) || /<EditorPageShell\b/.test(source);
}

describe("every create flow renders through the shared Dialog (#1282)", () => {
  it.each(CREATE_FLOW_REACH_HOSTS)("%s reaches the shared Dialog primitive", (relative) => {
    const source = readFileSync(join(COMPONENTS_DIR, relative), "utf-8");
    expect(
      reachesSharedDialog(source),
      `${relative} does not reach shared/Dialog — its create flow must be a modal ` +
        "(role=dialog, focus trap, Escape), not an inline panel",
    ).toBe(true);
  });

  it.each(CREATE_FLOW_REACH_HOSTS)("%s actually renders <Dialog", (relative) => {
    const source = readFileSync(join(COMPONENTS_DIR, relative), "utf-8");
    expect(
      rendersSharedDialog(source),
      `${relative} reaches the Dialog but never renders it — the create flow is inline`,
    ).toBe(true);
  });
});
