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
 *   1. the file imports the shared Dialog primitive, and
 *   2. it actually renders it (`<Dialog`).
 * An import-only match would pass while the JSX still used an inline panel.
 */
import { readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const COMPONENTS_DIR = join(resolve(__dirname, ".."), "components");

/**
 * The 12 routes that own a create flow, as `src/components`-relative paths.
 * `NeedsEditors` delegates its create dialog to `NeedList` (the component that
 * renders it), so `NeedList` is listed rather than the route shell.
 */
const CREATE_FLOW_HOSTS = [
  "RequirementEditors/RequirementEditors.tsx",
  "AdrEditors/AdrEditors.tsx",
  "RiskEditors/RiskEditors.tsx",
  "IssueEditors/IssueEditors.tsx",
  "TestCaseEditors/TestCaseEditors.tsx",
  "NeedsEditors/NeedList.tsx",
  "ArchitectureEditors/ArchitectureEditors.tsx",
  "GlossaryView/GlossaryView.tsx",
  "IcdView/IcdView.tsx",
  "DiagramView/DiagramView.tsx",
  "TestRuns/TestRunsList.tsx",
  "BaselinesView/BaselinesView.tsx",
] as const;

/** True when the source imports the shared Dialog from any relative depth. */
function importsSharedDialog(source: string): boolean {
  return /from\s+["'][^"']*shared\/Dialog["']/.test(source);
}

describe("every create flow renders through the shared Dialog (#1282)", () => {
  it.each(CREATE_FLOW_HOSTS)("%s imports the shared Dialog primitive", (relative) => {
    const source = readFileSync(join(COMPONENTS_DIR, relative), "utf-8");
    expect(
      importsSharedDialog(source),
      `${relative} does not import shared/Dialog — its create flow must be a modal ` +
        "(role=dialog, focus trap, Escape), not an inline panel",
    ).toBe(true);
  });

  it.each(CREATE_FLOW_HOSTS)("%s actually renders <Dialog", (relative) => {
    const source = readFileSync(join(COMPONENTS_DIR, relative), "utf-8");
    expect(
      /<Dialog\b/.test(source),
      `${relative} imports the Dialog but never renders it — the create flow is inline`,
    ).toBe(true);
  });
});
