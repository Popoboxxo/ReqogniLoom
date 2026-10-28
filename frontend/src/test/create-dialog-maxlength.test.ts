/**
 * Create-dialog maxLength + required-marker ratchet (#1392 / #1393).
 *
 * WHY THIS FILE EXISTS
 * --------------------
 * `create-form-field-contract.test.tsx` proves the *mechanism* works — but only
 * for two dialogs (ADR, StakeholderNeed), because a render-level test needs a
 * full mock graph per dialog. The defect this file freezes against is the one
 * that survived the original fix: the seam exists, while a dialog added later
 * simply never calls it. Nine of the eleven artifact routes' create dialogs
 * were hand-written and read neither the required flag nor the length bound;
 * the "13th dialog" problem is that nothing enumerated the set, so a new one
 * could be unbounded again without a single red test.
 *
 * This is therefore an ENUMERATING, source-level ratchet over ALL 12 create
 * dialogs (plus the shared `EditorPageShell`), not a sample:
 *
 *   - the host list lives in exactly one place
 *     (`fixtures/create-dialog-hosts.ts`), imported here AND by
 *     `dialog-consistency-ratchet.test.ts`, so the two gates cannot drift;
 *   - every dialog's title/name control must spread the contract's
 *     `controlProps` (the only prop bag that carries `maxLength`) inside a
 *     `<FormField>` whose `required` comes from the same binding;
 *   - the few dialogs whose entity has no attribute catalogue are checked for
 *     their equivalent static facts (`staticContracts`, or a named constant
 *     where the field is optional by server design).
 *
 * Render-level coverage that already exists (not duplicated here):
 * `create-form-field-contract.test.tsx` asserts `aria-required` + `maxLength`
 * on the live ADR title input and the Need category/title inputs.
 *
 * PURE-CHECKER SELF-TESTS
 * -----------------------
 * The last describe block proves the gate is falsifiable without touching
 * product code: synthetic sources WITHOUT `maxLength` / WITHOUT the required
 * binding must be reported, a well-formed synthetic source must pass, and a
 * synthetic 13th registry entry pointing at a bad source must turn the
 * enumeration red.
 *
 * KNOWN RED BASELINE — NOW EMPTY
 * -------------------------------
 * The one dialog that did NOT satisfy the contract when this ratchet was added
 * was TestRuns' "Create Run" name input: hand-written, no `maxLength` (server
 * column: `max_length=255`) and a hardcoded `*`. That is a real defect, and it
 * was pinned exactly in `KNOWN_CONTRACT_GAPS` so the gate could ship red-but-
 * honest instead of silently skipping it. Fixing the product code was NOT done
 * in the tests-only task that added this file — and that is exactly how the
 * ratchet proved itself: the moment the dialog was fixed, this file went red
 * ("violations: []" vs the two pinned lines) and stayed red until the entry was
 * deleted. `KNOWN_CONTRACT_GAPS` is now empty *and kept*, so the same mechanism
 * still pins the next unfixable dialog and the exact-equality comparison still
 * fails in both directions (new violation → red; stale exemption → red).
 */
import { readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";

import {
  CHECKED_HOSTS,
  CREATE_DIALOG_CONTRACTS,
  CREATE_FLOW_HOSTS,
  CREATE_FLOW_SHELL,
  KNOWN_CONTRACT_GAPS,
  checkCreateDialogContract,
  checkCreateDialogContracts,
  type ComponentSourceReader,
  type CreateDialogContract,
} from "./fixtures/create-dialog-hosts";

const COMPONENTS_DIR = join(resolve(__dirname, ".."), "components");

/** Read a source file by its `src/components`-relative path. */
const readComponent: ComponentSourceReader = (relative) =>
  readFileSync(join(COMPONENTS_DIR, relative), "utf-8");

/** Read the real component tree, with specific paths overridden (self-tests). */
function readerWith(overrides: Readonly<Record<string, string>>): ComponentSourceReader {
  return (relative) => overrides[relative] ?? readComponent(relative);
}

/** The registry entry for one host (fails loudly if the registry is renamed). */
function contractFor(host: string): CreateDialogContract {
  const contract = CREATE_DIALOG_CONTRACTS.find((entry) => entry.host === host);
  if (contract === undefined) throw new Error(`no registry entry for ${host}`);
  return contract;
}

describe("the create-dialog registry has one source of truth", () => {
  it("enumerates exactly the 12 hosts the dialog-consistency ratchet pins", () => {
    // Both specs import CREATE_FLOW_HOSTS, but the contract list is a second
    // projection of it: if a host is added to one and not the other, this fails
    // instead of the new dialog escaping the maxLength/required gate.
    expect(CHECKED_HOSTS).toEqual([...CREATE_FLOW_HOSTS]);
    // The count is pinned as well: the set may only change deliberately. A 13th
    // create dialog must bump this number — and then it is subject to the very
    // same checks below, which is the point of the enumeration.
    expect(CREATE_FLOW_HOSTS).toHaveLength(12);
  });

  it("has no duplicate host entries", () => {
    expect(new Set(CHECKED_HOSTS).size).toBe(CHECKED_HOSTS.length);
  });

  it("keeps the shared EditorPageShell in scope", () => {
    expect(CREATE_FLOW_HOSTS).not.toContain(CREATE_FLOW_SHELL);
    expect(readComponent(CREATE_FLOW_SHELL)).toBeTruthy();
  });

  it("pins known gaps only for hosts that really exist — and has none open", () => {
    // A stale gap entry would silently keep an exemption alive for a file that
    // no longer owns a create dialog.
    for (const host of Object.keys(KNOWN_CONTRACT_GAPS)) {
      expect(CHECKED_HOSTS, `KNOWN_CONTRACT_GAPS names unknown host ${host}`).toContain(host);
    }
    // Non-vacuity of the loop above: it is empty today, so state that out loud
    // instead of letting "no iteration ran" look like "every host checked". The
    // list is the gate's red baseline; an entry here must be a deliberate,
    // documented exemption, never a leftover from a fix that already landed.
    expect(
      Object.keys(KNOWN_CONTRACT_GAPS),
      "no create dialog may be left in the known-gap baseline: the TestRuns " +
        "dialog this baseline was created for is fixed, and deleting its entry " +
        "is what closed the ratchet"
    ).toEqual([]);
  });
});

describe("every create dialog wires the field contract (#1392/#1393)", () => {
  it.each(CREATE_DIALOG_CONTRACTS)(
    '$label: "$field" carries maxLength + the required marker',
    (contract: CreateDialogContract) => {
      const violations = checkCreateDialogContract(contract, readComponent);
      const expected = KNOWN_CONTRACT_GAPS[contract.host] ?? [];

      // Exact equality on purpose: an unexpected violation is a regression, and
      // a *missing* known one means the dialog was fixed and the pinned gap
      // entry must be deleted (the ratchet closes itself).
      expect(
        violations,
        `${contract.host} violates the create-dialog field contract:\n` +
          violations.map((line) => `  - ${line}`).join("\n")
      ).toEqual([...expected]);
    }
  );

  it("reports no violation beyond the documented baseline across all 12", () => {
    const expected = Object.values(KNOWN_CONTRACT_GAPS).flat();
    expect(checkCreateDialogContracts(CREATE_DIALOG_CONTRACTS, readComponent)).toEqual(
      expected
    );
  });
});

describe("the shared EditorPageShell carries the contract through", () => {
  // The shell renders the caller's controls, so it must (a) be the shared
  // Dialog, (b) forward the caller's `<FormField>` subtree unchanged inside its
  // own `<form>`, and (c) opt out of native validation so a field-bound 400
  // message is not pre-empted by a browser bubble.
  const shell = readComponent(CREATE_FLOW_SHELL);

  it("renders the shared Dialog and one form around the caller's children", () => {
    expect(shell).toMatch(/<Dialog\b/);
    expect(shell).toMatch(/<form\b/);
    expect(shell).toMatch(/\{children\}/);
  });

  it("keeps native validation quiet so the contract's error text is authoritative", () => {
    expect(shell).toMatch(/noValidate/);
  });
});

/**
 * Falsifiability. Every case below runs the SAME functions the enumeration
 * above runs — nothing is re-implemented for the test.
 */
describe("the contract checker itself is falsifiable", () => {
  const HOST = "SyntheticEditors/SyntheticDialog.tsx";

  /** A dialog source with the contract wiring fully in place. */
  const WELL_FORMED = `
    import { useFieldContract } from "../../hooks/useFieldContract";
    import { FormField } from "../shared/FormField";

    export function SyntheticDialog(): JSX.Element {
      const { field } = useFieldContract("Adr", { enabled: true });
      return (
        <FormField htmlFor="synthetic-title" label="Titel" required={field("title").required}>
          <input id="synthetic-title" {...field("title").controlProps} />
        </FormField>
      );
    }
  `;

  /** No `controlProps` spread: the input has no maxLength. */
  const WITHOUT_MAX_LENGTH = `
    import { useFieldContract } from "../../hooks/useFieldContract";
    import { FormField } from "../shared/FormField";

    export function SyntheticDialog(): JSX.Element {
      const { field } = useFieldContract("Adr", { enabled: true });
      return (
        <FormField htmlFor="synthetic-title" label="Titel" required={field("title").required}>
          <input id="synthetic-title" value="" onChange={() => undefined} />
        </FormField>
      );
    }
  `;

  /** No contract-driven required binding: the marker is a hardcoded literal. */
  const WITHOUT_REQUIRED_MARKER = `
    import { useFieldContract } from "../../hooks/useFieldContract";
    import { FormField } from "../shared/FormField";

    export function SyntheticDialog(): JSX.Element {
      const { field } = useFieldContract("Adr", { enabled: true });
      return (
        <FormField htmlFor="synthetic-title" label="Titel *" required={false}>
          <input id="synthetic-title" {...field("title").controlProps} />
        </FormField>
      );
    }
  `;

  const contract: CreateDialogContract = {
    host: HOST,
    label: "Synthetic create dialog",
    field: "title",
    itemType: "Adr",
    contractFiles: [HOST],
    style: "hook",
  };

  it("passes a dialog that spreads controlProps inside a contract-bound FormField", () => {
    expect(checkCreateDialogContract(contract, readerWith({ [HOST]: WELL_FORMED }))).toEqual([]);
  });

  it("fails a dialog whose title control never gets the contract's maxLength", () => {
    const violations = checkCreateDialogContract(
      contract,
      readerWith({ [HOST]: WITHOUT_MAX_LENGTH })
    );

    expect(violations).toHaveLength(1);
    expect(violations[0]).toContain("does not spread the contract's `controlProps`");
    expect(violations[0]).toContain("maxLength never reaches the input");
    expect(violations[0]).toContain(HOST);
  });

  it("fails a dialog whose required marker is not driven by the contract", () => {
    const violations = checkCreateDialogContract(
      contract,
      readerWith({ [HOST]: WITHOUT_REQUIRED_MARKER })
    );

    expect(violations).toHaveLength(1);
    expect(violations[0]).toContain("the required marker is not driven by the contract");
    expect(violations[0]).toContain(HOST);
  });

  it("fails a dialog with no contract seam at all", () => {
    const violations = checkCreateDialogContract(
      contract,
      readerWith({ [HOST]: "<input id=\"synthetic-title\" required />" })
    );

    // Two independent facts are missing: the seam and the spread.
    expect(violations.some((line) => line.includes("no `useFieldContract"))).toBe(true);
    expect(violations.some((line) => line.includes("`controlProps`"))).toBe(true);
  });

  it("turns red when a 13th dialog is added to the registry without the wiring", () => {
    const thirteenth: CreateDialogContract = {
      host: "SyntheticEditors/ThirteenthDialog.tsx",
      label: "13th create dialog",
      field: "title",
      itemType: "Adr",
      contractFiles: ["SyntheticEditors/ThirteenthDialog.tsx"],
      style: "hook",
    };

    const violations = checkCreateDialogContracts(
      [...CREATE_DIALOG_CONTRACTS, thirteenth],
      readerWith({
        "SyntheticEditors/ThirteenthDialog.tsx": WITHOUT_MAX_LENGTH,
      })
    );

    // Everything up to the documented baseline still passes…
    const baseline = Object.values(KNOWN_CONTRACT_GAPS).flat();
    expect(violations.slice(0, baseline.length)).toEqual(baseline);
    // …and the growth is exactly the new dialog's missing wiring.
    expect(violations).toHaveLength(baseline.length + 1);
    expect(
      violations.slice(baseline.length),
      "adding a registry entry without wiring must report that entry"
    ).toEqual([
      '13th create dialog (SyntheticEditors/ThirteenthDialog.tsx): the "title" control ' +
        "does not spread the contract's `controlProps` — maxLength never reaches the input",
    ]);
  });

  /**
   * Non-vacuity against the REAL product source: the synthetic cases above
   * prove the checker's logic, these prove it actually reads the live dialog
   * file (a regex that never matched would otherwise pass every dialog).
   */
  it("reads the live ADR dialog: dropping its controlProps spread turns it red", () => {
    const real = readComponent("AdrEditors/AdrEditors.tsx");
    const mutated = real.replace(/\.controlProps/g, ".notTheContract");

    expect(mutated, "mutation pattern no longer present — update this test").not.toBe(real);
    const violations = checkCreateDialogContract(
      contractFor("AdrEditors/AdrEditors.tsx"),
      readerWith({ "AdrEditors/AdrEditors.tsx": mutated })
    );

    expect(violations).toHaveLength(1);
    expect(violations[0]).toContain("does not spread the contract's `controlProps`");
  });

  it("reads the live ADR dialog: dropping its contract-bound required turns it red", () => {
    const real = readComponent("AdrEditors/AdrEditors.tsx");
    const mutated = real.replace(/\{titleField\.required\}/g, "{false}");

    expect(mutated, "mutation pattern no longer present — update this test").not.toBe(real);
    const violations = checkCreateDialogContract(
      contractFor("AdrEditors/AdrEditors.tsx"),
      readerWith({ "AdrEditors/AdrEditors.tsx": mutated })
    );

    expect(violations).toHaveLength(1);
    expect(violations[0]).toContain("the required marker is not driven by the contract");
  });

  it("requires a static contract to declare both required and a numeric maxLength", () => {
    const staticContract: CreateDialogContract = {
      host: HOST,
      label: "Synthetic static dialog",
      field: "name",
      itemType: null,
      contractFiles: [HOST],
      style: "hook-static",
    };

    const violations = checkCreateDialogContract(
      staticContract,
      readerWith({
        [HOST]: `
          const { field } = useFieldContract(null, { enabled: false, staticContracts: SIGNED });
          <FormField htmlFor="x" label="Name" required={field("name").required}>
            <input id="x" {...field("name").controlProps} />
          </FormField>
        `,
      })
    );

    expect(violations).toEqual([
      'Synthetic static dialog (SyntheticEditors/SyntheticDialog.tsx): `staticContracts` ' +
        'declares no "name" entry — the control has no contract to read',
    ]);
  });
});
