/**
 * The create-dialog registry — one source of truth for two ratchets.
 *
 * WHY THIS FILE EXISTS
 * --------------------
 * Two independent gates enumerate *the same* set of create dialogs:
 *
 *   1. `dialog-consistency-ratchet.test.ts` (#1282) pins every create flow to
 *      the shared `shared/Dialog` primitive (role=dialog, focus trap, Escape).
 *   2. `create-dialog-maxlength.test.ts` (#1392/#1393) pins every create
 *      dialog's title/name control to the `useFieldContract` seam, so the
 *      control carries the server's `maxLength` and the required marker.
 *
 * Keeping two hand-maintained lists was the actual risk: the second gate would
 * silently stop covering a 13th dialog the first one had already grown. The
 * list therefore lives here exactly once and both specs import it — a new
 * route has to be registered here, and registration immediately subjects it to
 * both gates.
 *
 * `CREATE_DIALOG_CONTRACTS` carries the per-dialog *wiring* facts on top of the
 * host list, and `CHECKED_HOSTS` asserted against `CREATE_FLOW_HOSTS` keeps the
 * two halves in lockstep (see the coverage test in
 * `create-dialog-maxlength.test.ts`).
 *
 * The checker below is deliberately a pure function over injected source text:
 * the self-tests in `create-dialog-maxlength.test.ts` feed it synthetic
 * sources (a dialog without `maxLength`, a dialog without a required marker, a
 * synthetic "13th dialog") and prove it reports those as violations — so a
 * green enumeration really means "the mechanism is applied", not "the file
 * imports something".
 */

/**
 * The 12 routes that own a create flow, as `src/components`-relative paths.
 * `NeedsEditors` delegates its create dialog to `NeedList` (the component that
 * renders it), so `NeedList` is listed rather than the route shell.
 */
export const CREATE_FLOW_HOSTS = [
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

/**
 * The shared create-dialog scaffold (F-15). Not a route, but the component four
 * routes now delegate their create dialog to — pinned so the delegation
 * resolves to a real `<Dialog>` and cannot silently become an inline panel.
 */
export const CREATE_FLOW_SHELL = "shared/EditorPageShell.tsx";

/**
 * How a dialog gets `maxLength` + the required marker onto its title/name
 * control. Every style is verified structurally; none is a "trust me" label.
 *
 * - `hook`         — the host (or the component it delegates to) calls
 *                    `useFieldContract(<itemType>)` and spreads
 *                    `field("<key>").controlProps` inside a `<FormField>` whose
 *                    `required` comes from the same binding.
 * - `hook-static`  — same, but for an item type with no attribute catalogue
 *                    (`Diagram`): the hook is called with `null` and the
 *                    contract arrives through `staticContracts`, which must
 *                    declare BOTH `required` and a numeric `maxLength`.
 * - `artifact-form`— the control is rendered by the shared definition-driven
 *                    `ArtifactForm`; the degraded (no definition) fallback is
 *                    a hand-written form whose static contract must carry
 *                    `required: true` and a numeric `maxLength`, applied to the
 *                    control and its `<FormField>`.
 * - `static-constant`
 *                  — the entity has no attribute definition (Baseline) and its
 *                    name is OPTIONAL by server design, so there is nothing to
 *                    mark required; the only contract fact is the length cap,
 *                    which must sit on the name control as a named constant.
 */
export type ContractStyle =
  | "hook"
  | "hook-static"
  | "artifact-form"
  | "static-constant";

export interface CreateDialogContract {
  /** Must be a member of `CREATE_FLOW_HOSTS` / `CREATE_FLOW_SHELL`. */
  host: string;
  /** Human label used in failure output. */
  label: string;
  /** `title` / `name` / `term` — the dialog's primary text control. */
  field: string;
  /** Attribute item type the contract resolves; `null` when the hook is static. */
  itemType: string | null;
  /** Where the wiring actually lives (the host itself unless it delegates). */
  contractFiles: readonly string[];
  style: ContractStyle;
  /**
   * Why this dialog needs no required marker at all (only legitimate for
   * `static-constant`, where the server treats the field as optional).
   */
  optionalFieldReason?: string;
}

/**
 * One entry per create dialog. `CHECKED_HOSTS` is derived from this list and
 * asserted equal to the reach set, so the enumeration cannot drift.
 *
 * Render-level coverage already exists for `AdrEditors` and `NeedList` in
 * `create-form-field-contract.test.tsx` (they prove `aria-required` and
 * `maxLength` on the live control). They are still enumerated here: this gate
 * is the *source-level* ratchet that covers all 12 without rendering any of
 * them, and it is what fails when a 13th dialog is added.
 */
export const CREATE_DIALOG_CONTRACTS: readonly CreateDialogContract[] = [
  {
    host: "RequirementEditors/RequirementEditors.tsx",
    label: "Requirement create dialog",
    field: "title",
    itemType: "Requirement",
    contractFiles: [
      "RequirementEditors/RequirementEditors.tsx",
      "RequirementEditors/RequirementCreateFallbackForm.tsx",
    ],
    style: "artifact-form",
  },
  {
    host: "AdrEditors/AdrEditors.tsx",
    label: "ADR create dialog",
    field: "title",
    itemType: "Adr",
    contractFiles: ["AdrEditors/AdrEditors.tsx"],
    style: "hook",
  },
  {
    host: "RiskEditors/RiskEditors.tsx",
    label: "Risk create dialog",
    field: "title",
    itemType: "Risk",
    contractFiles: ["RiskEditors/RiskEditors.tsx"],
    style: "hook",
  },
  {
    host: "IssueEditors/IssueEditors.tsx",
    label: "Issue create dialog",
    field: "title",
    itemType: "Issue",
    contractFiles: ["IssueEditors/IssueEditors.tsx"],
    style: "hook",
  },
  {
    host: "TestCaseEditors/TestCaseEditors.tsx",
    label: "Test case create dialog",
    field: "title",
    itemType: "TestCase",
    contractFiles: ["TestCaseEditors/TestCaseEditors.tsx"],
    style: "hook",
  },
  {
    host: "NeedsEditors/NeedList.tsx",
    label: "Stakeholder need create dialog",
    field: "title",
    itemType: "StakeholderNeed",
    contractFiles: ["NeedsEditors/NeedList.tsx"],
    style: "hook",
  },
  {
    host: "ArchitectureEditors/ArchitectureEditors.tsx",
    label: "Architecture element create dialog",
    field: "title",
    itemType: "ArchitectureElement",
    contractFiles: ["ArchitectureEditors/ArchitectureEditors.tsx"],
    style: "hook",
  },
  {
    // The dialog lives in GlossaryView (it owns the <Dialog>); the field and
    // its contract live in the form component it renders.
    host: "GlossaryView/GlossaryView.tsx",
    label: "Glossary term create dialog",
    field: "term",
    itemType: "GlossaryTerm",
    contractFiles: ["GlossaryView/GlossaryTermForm.tsx"],
    style: "hook",
  },
  {
    host: "IcdView/IcdView.tsx",
    label: "ICD create dialog",
    field: "name",
    itemType: "Icd",
    contractFiles: ["IcdView/IcdView.tsx"],
    style: "hook",
  },
  {
    // `Diagram` is not an attribute-catalogue item type: the hook is called
    // with `null` and the contract comes from `staticContracts`.
    host: "DiagramView/DiagramView.tsx",
    label: "Diagram create dialog",
    field: "name",
    itemType: null,
    contractFiles: ["DiagramView/DiagramCreateForm.tsx"],
    style: "hook-static",
  },
  {
    host: "TestRuns/TestRunsList.tsx",
    label: "Test run create dialog",
    field: "name",
    itemType: null,
    contractFiles: ["TestRuns/TestRunsList.tsx"],
    style: "hook-static",
  },
  {
    // Baseline.name is optional on the server (`blank=True`), and `Baseline`
    // has no attribute definition, so there is no required marker to drive.
    host: "BaselinesView/BaselinesView.tsx",
    label: "Baseline create dialog",
    field: "name",
    itemType: null,
    contractFiles: ["BaselinesView/BaselinesView.tsx"],
    style: "static-constant",
    optionalFieldReason:
      "Baseline.name is optional by server design (`blank=True`); an empty name " +
      "keeps the backend's generated 'Baseline <timestamp>' name.",
  },
];

/** The hosts the contract enumeration actually inspects. */
export const CHECKED_HOSTS: readonly string[] = CREATE_DIALOG_CONTRACTS.map(
  (contract) => contract.host
);

/**
 * The ratchet's explicit red baseline — EMPTY, by design, as of #1392/#1393.
 *
 * Why the mechanism exists at all: a ratchet that silently skipped an unfixed
 * dialog would be a lie, and a ratchet that is permanently red would be
 * ignored. So violations of a *known* dialog are pinned here EXACTLY once the
 * gate reports them, and the gate compares with exact equality: a violation
 * that is not listed here turns it red immediately, and a listed violation that
 * disappeared makes it red too ("the allowance is stale, delete it"). The entry
 * is what forces a fix to close itself instead of leaving a dead exemption
 * behind.
 *
 * WHAT IT FORCED (kept as the record of why this list must stay reachable):
 * `TestRuns/TestRunsList.tsx` was the one dialog with no contract at all — a
 * hand-written name input (`#testrun-name`) with no `useFieldContract` call,
 * so it accepted unlimited text although the column is
 * `TestRun.name = CharField(max_length=255)` (`backend/persistence/models.py`),
 * plus a hardcoded `required` and a literal `*` in the label instead of
 * `FormField`/`RequiredMark`. It was a real defect, it was pinned here exactly
 * (two lines: missing seam, missing `controlProps` spread), and fixing the
 * product code turned this gate red until the entry was deleted — which is
 * precisely the behaviour the list is for. `git log -p` on this file shows the
 * red → empty transition; the fix landed in the same PR.
 *
 * The map is therefore empty rather than gone: the next dialog that cannot be
 * fixed in the PR that finds it gets one entry, with its measured facts, and
 * the exact-equality comparison keeps both directions live.
 */
export const KNOWN_CONTRACT_GAPS: Readonly<Record<string, readonly string[]>> = {};

/** Read one source file by its `src/components`-relative path. */
export type ComponentSourceReader = (relativePath: string) => string;

function quoteVariants(field: string): string {
  return `["']${field.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}["']`;
}

/** `const titleField = field('title')` — an alias the JSX may spread instead. */
function fieldAliases(source: string, field: string): string[] {
  const pattern = new RegExp(
    `(?:const|let)\\s+(\\w+)\\s*=\\s*field\\(\\s*${quoteVariants(field)}\\s*\\)`,
    "g"
  );
  return [...source.matchAll(pattern)].map((match) => match[1]);
}

/** Index of the `{...<field>.controlProps}` spread, or -1. */
function controlPropsSpreadIndex(
  source: string,
  field: string,
  aliases: readonly string[]
): number {
  const direct = new RegExp(
    `\\.\\.\\.\\s*field\\(\\s*${quoteVariants(field)}\\s*\\)\\.controlProps`
  ).exec(source);
  if (direct !== null) return direct.index;

  for (const alias of aliases) {
    const aliased = new RegExp(`\\.\\.\\.\\s*${alias}\\.controlProps`).exec(source);
    if (aliased !== null) return aliased.index;
  }
  return -1;
}

/** The `<FormField ...>` opening region that precedes a JSX spread. */
function enclosingFormFieldRegion(source: string, spreadIndex: number): string | null {
  const openIndex = source.lastIndexOf("<FormField", spreadIndex);
  if (openIndex < 0) return null;
  return source.slice(openIndex, spreadIndex);
}

/**
 * True when `region` binds `required` to the contract for `field` (directly or
 * through an alias) — i.e. `required={field("title").required}`.
 */
function bindsContractRequired(
  region: string,
  field: string,
  aliases: readonly string[]
): boolean {
  const direct = new RegExp(
    `required=\\{\\s*field\\(\\s*${quoteVariants(field)}\\s*\\)\\.required\\s*\\}`
  );
  if (direct.test(region)) return true;
  return aliases.some((alias) =>
    new RegExp(`required=\\{\\s*${alias}\\.required\\s*\\}`).test(region)
  );
}

/** `staticContracts` entry for the field: `{ required: true, maxLength: 500 }`. */
function staticContractViolations(
  source: string,
  field: string,
  file: string,
  label: string
): string[] {
  const key = new RegExp(
    `${field.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s*:\\s*\\{([^}]*)\\}`
  ).exec(source);
  if (key === null) {
    return [
      `${label} (${file}): \`staticContracts\` declares no "${field}" entry — the control has no contract to read`,
    ];
  }
  const body = key[1];
  const violations: string[] = [];
  if (!/required\s*:\s*true/.test(body)) {
    violations.push(
      `${label} (${file}): the "${field}" static contract does not declare \`required: true\` — the required marker can never light up`
    );
  }
  if (!/maxLength\s*:\s*\d+/.test(body)) {
    violations.push(
      `${label} (${file}): the "${field}" static contract declares no numeric \`maxLength\` — the input is unbounded`
    );
  }
  return violations;
}

function hookViolations(
  contract: CreateDialogContract,
  combined: string,
  fileList: string
): string[] {
  const violations: string[] = [];
  const { label, field, itemType } = contract;

  const hookCall =
    itemType === null
      ? /useFieldContract\(\s*null\s*,/
      : new RegExp(`useFieldContract\\(\\s*["']${itemType}["']`);
  const hasHookCall = hookCall.test(combined);
  if (!hasHookCall) {
    violations.push(
      `${label} (${fileList}): no ${
        itemType === null
          ? "`useFieldContract(null, { staticContracts })`"
          : `\`useFieldContract("${itemType}")\``
      } call — the control gets no contract at all`
    );
  }

  const aliases = fieldAliases(combined, field);
  const spreadIndex = controlPropsSpreadIndex(combined, field, aliases);
  if (spreadIndex < 0) {
    violations.push(
      `${label} (${fileList}): the "${field}" control does not spread the contract's \`controlProps\` — maxLength never reaches the input`
    );
  } else {
    const region = enclosingFormFieldRegion(combined, spreadIndex);
    if (region === null) {
      violations.push(
        `${label} (${fileList}): the "${field}" \`controlProps\` spread is not inside a \`<FormField>\` — the marker/label association is bypassed`
      );
    } else if (!bindsContractRequired(region, field, aliases)) {
      violations.push(
        `${label} (${fileList}): no \`<FormField required={...}>` +
          `\` binding for "${field}" — the required marker is not driven by the contract`
      );
    }
  }

  if (contract.style === "hook-static" && hasHookCall) {
    // A static contract is the ONLY source for this item type, so its facts
    // must be declared — otherwise `field()` returns "optional, unbounded".
    // Skipped when the hook is missing entirely: that is one root cause, not
    // two, and the missing-hook line above already names it.
    violations.push(...staticContractViolations(combined, field, fileList, label));
  }

  return violations;
}

function artifactFormViolations(
  contract: CreateDialogContract,
  read: ComponentSourceReader
): string[] {
  const violations: string[] = [];
  const { label, field } = contract;
  const hostFile = contract.contractFiles[0];
  const host = read(hostFile);

  // 1. The definition-driven path: `<ArtifactForm itemType="Requirement" …>`.
  //    That renderer owns maxLength/required while a definition resolves.
  const artifactForm = new RegExp(
    `<ArtifactForm[\\s\\S]{0,400}?itemType=["']${contract.itemType}["']`
  );
  if (!artifactForm.test(host)) {
    violations.push(
      `${label} (${hostFile}): no \`<ArtifactForm itemType="${contract.itemType}">\` — the definition-driven renderer (which applies maxLength/required) is bypassed`
    );
  }

  // 2. The degraded path: the hand-written fallback must still carry the
  //    statically known facts. It renders exactly when no definition resolved,
  //    so it cannot read the contract — but it must not be unbounded either.
  const fallbackFile = contract.contractFiles[1];
  if (fallbackFile === undefined) {
    violations.push(
      `${label} (${hostFile}): contract declares no fallback source — the no-definition path is unverified`
    );
    return violations;
  }
  const fallback = read(fallbackFile);
  const constant = /\bconst\s+([A-Z][A-Z0-9_]*)\s*=\s*\{([^}]*)\}/.exec(fallback);
  const contractBody = constant?.[2] ?? "";
  if (
    constant === null ||
    !/required\s*:\s*true/.test(contractBody) ||
    !/maxLength\s*:\s*\d+/.test(contractBody)
  ) {
    violations.push(
      `${label} (${fallbackFile}): the fallback title contract constant declares no \`required: true\` + numeric \`maxLength\``
    );
  } else {
    const name = constant[1];
    // The fallback form's title control is `#new-req-title`; the regex ties the
    // bound to THAT input, so a `maxLength` on some other field cannot satisfy
    // the check.
    const applied = new RegExp(
      `id="${field === "title" ? "new-req-title" : field}"[\\s\\S]{0,600}?maxLength=\\{${name}\\.maxLength\\}`
    );
    if (!applied.test(fallback)) {
      violations.push(
        `${label} (${fallbackFile}): \`${name}.maxLength\` is not applied to the "${field}" input`
      );
    }
    if (!new RegExp(`required=\\{${name}\\.required\\}`).test(fallback)) {
      violations.push(
        `${label} (${fallbackFile}): \`${name}.required\` does not drive the \`<FormField>\` marker`
      );
    }
  }
  return violations;
}

/**
 * The `static-constant` style is used by exactly one dialog (Baseline), whose
 * entity has no attribute definition and whose name is optional on the server.
 * The check therefore verifies the two facts that DO apply: a positive named
 * length constant, applied to the dialog's own name control.
 */
function staticConstantViolations(
  contract: CreateDialogContract,
  source: string,
  fileList: string
): string[] {
  const violations: string[] = [];
  const { label, field } = contract;
  // A named constant keeps the bound reviewable: `maxLength={MAX_X}` plus
  // `const MAX_X = 500`.
  const applied = /maxLength=\{([A-Z][A-Z0-9_]*)\}/.exec(source);
  if (applied === null) {
    violations.push(
      `${label} (${fileList}): the "${field}" control carries no named \`maxLength\` constant — the input is unbounded`
    );
  } else {
    const declaration = new RegExp(
      `const\\s+${applied[1]}\\s*=\\s*(\\d+)\\s*;`
    ).exec(source);
    if (declaration === null || Number(declaration[1]) <= 0) {
      violations.push(
        `${label} (${fileList}): \`${applied[1]}\` is not declared as a positive numeric constant`
      );
    }
    // Applied to the *name control*, not to some other input in the file.
    const controlIndex = source.indexOf(`data-testid="baseline-name-input"`);
    const spreadIndex = source.indexOf(`maxLength={${applied[1]}}`);
    if (controlIndex < 0 || spreadIndex < 0 || Math.abs(spreadIndex - controlIndex) > 400) {
      violations.push(
        `${label} (${fileList}): the \`maxLength\` constant is not on the baseline name control`
      );
    }
  }

  if (contract.optionalFieldReason === undefined) {
    violations.push(
      `${label} (${fileList}): style \`static-constant\` requires an \`optionalFieldReason\` — an unmarked required field would be a silent contract hole`
    );
  }
  return violations;
}

/**
 * Check ONE dialog. Returns the violations (empty array = the dialog wires the
 * contract), never throws on a missing file (the reader does that).
 */
export function checkCreateDialogContract(
  contract: CreateDialogContract,
  read: ComponentSourceReader
): string[] {
  if (contract.style === "artifact-form") {
    return artifactFormViolations(contract, read);
  }

  const sources = contract.contractFiles.map((file) => ({
    file,
    source: read(file),
  }));
  const combined = sources.map((entry) => entry.source).join("\n");
  const fileList = sources.map((entry) => entry.file).join(", ");

  switch (contract.style) {
    case "hook":
    case "hook-static":
      return hookViolations(contract, combined, fileList);
    case "static-constant":
      return staticConstantViolations(contract, combined, fileList);
  }
}

/**
 * Check EVERY dialog in the registry. This is the enumerating ratchet: adding a
 * 13th entry to `CREATE_DIALOG_CONTRACTS` automatically subjects it to the
 * same check.
 */
export function checkCreateDialogContracts(
  contracts: readonly CreateDialogContract[],
  read: ComponentSourceReader
): string[] {
  return contracts.flatMap((contract) => checkCreateDialogContract(contract, read));
}
