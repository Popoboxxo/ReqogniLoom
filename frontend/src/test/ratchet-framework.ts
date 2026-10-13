/**
 * TypeScript mirror of the shared ratchet contract (#1103 / REQ-193).
 *
 * The contract itself lives in `backend/mcp_server/tests/ratchet_framework.py`
 * (see `PYTHON_CONTRACT_PATH`), at `CONTRACT_VERSION = 1.0.0`; this file
 * mirrors that contract for the frontend ratchets and names both in its source,
 * so a drift between the two is visible in a diff. It is a **mirror of the
 * contract**, not a cross-language bridge framework: there is no shared
 * runtime, no codegen, and no dual implementation of any measurement. Each
 * ratchet keeps measuring for itself; only the *bookkeeping* — the named
 * re-baseline entry point, the stale detector, the gap schema and the
 * justification guard — is shared.
 *
 * `backend/mcp_server/tests/test_ratchet_framework.py` pins the mirror to that
 * module (path, contract version and every canonical env var must appear here),
 * so the mirror cannot silently fall behind.
 *
 * The one shape difference
 * -----------------------
 * A TypeScript exemption carries its gap identity in the **map key** (the
 * design-system baseline stores `exemptions: { "<gap key>": { reason } }`), so
 * the structured form is `{reason, issue}` where the Python form is
 * `{gap, reason, issue}`. `validateGapEntry` accepts both: pass `options.key`
 * when the identity lives in the map key, or store it inline in `gap`. The rule
 * behind both is identical.
 *
 * Two seams to the host, on purpose
 * ---------------------------------
 * `npm run build` compiles this file without `@types/node` (package.json
 * declares none), so the mirror imports neither `node:fs` nor `process`: the
 * environment is read through `globalThis`, and a caller that has a filesystem
 * (vitest, or the design-system suite) passes a `readFile` function in. That is
 * what keeps a contract mirror from dragging a build dependency behind it.
 */

/** Version of the mirrored contract; the Python module names the same number. */
export const CONTRACT_VERSION = "1.0.0";

/** The Python module that owns this contract. */
export const PYTHON_CONTRACT_PATH = "backend/mcp_server/tests/ratchet_framework.py";

/** Where this mirror lives, relative to the repo root. */
export const TS_MIRROR_PATH = "frontend/src/test/ratchet-framework.ts";

/** An accepted gap must say WHY it is acceptable, in at least this many characters. */
export const GAP_MIN_REASON_LENGTH = 40;

/** An accepted gap must point at a tracker item. Search, not fullmatch. */
export const ISSUE_PATTERN = /#\d+/;

/** Inline JSON (or a path to a JSON file) mapping gap key -> justification. */
export const JUSTIFICATION_ENV_VAR = "RATCHET_JUSTIFY";

/** The widening direction for a *list-shaped* baseline. */
export const JUSTIFY_NEW = "new";

/** The widening direction for a baseline that is a derived mirror of a live registry. */
export const JUSTIFY_ROTATED = "rotated";

/** A process environment (the shape of `process.env`). */
export type Env = Record<string, string | undefined>;

/** Env var values that mean "the committed file this ratchet guards". */
const SENTINELS: readonly string[] = ["1", "true", "yes"];

/**
 * Node's `process.env`, resolved at runtime.
 *
 * The frontend build has no `@types/node`, so the mirror reaches the
 * environment through `globalThis` rather than importing `process`. At runtime
 * (vitest) this is the real `process.env`; a caller may pass its own mapping to
 * stay hermetic.
 */
function defaultEnv(): Env {
  const host = globalThis as { process?: { env?: Env } };
  return host.process?.env ?? {};
}

/** Reads a file, or returns null when it cannot be read. */
export type FileReader = (path: string) => string | null;

/** The default: no filesystem, so a `$RATCHET_JUSTIFY` value is inline JSON. */
function noFileReader(): null {
  return null;
}

/** Base class for every failure this mirror raises on its own. */
export class RatchetError extends Error {}

/** A baseline entry (or a justification) does not carry reason + issue. */
export class GapSchemaError extends RatchetError {}

/** A re-baseline tried to widen the accepted set without a justification. */
export class UnjustifiedDumpError extends RatchetError {}

/** The ratchets this contract governs — the ONE table (`REBASELINE_ENTRY_POINTS`). */
export type RatchetId = "entity-surface-parity" | "design-system" | "tool-manifest-drift";

/** Which direction of the diff is a widening for a given ratchet. */
export type JustifyDirection = typeof JUSTIFY_NEW | typeof JUSTIFY_ROTATED;

/** One ratchet's named re-baseline command. */
export interface RebaselineEntryPoint {
  /** Short id, used to look the entry point up. */
  readonly ratchet: RatchetId;
  /** The suite that implements the ratchet, for error messages. */
  readonly suite: string;
  /** Canonical env var name (without the `=<value>` part). */
  readonly canonicalEnv: string;
  /** What the canonical env var's value means. */
  readonly placeholder: string;
  /** Legacy env var name that keeps working, or `""`. */
  readonly legacyEnv: string;
  /** The exact command, copy-pasteable, that re-baselines this ratchet. */
  readonly command: string;
  /** What that command writes, and what the reader has to do with it. */
  readonly writes: string;
  /** `JUSTIFY_NEW` or `JUSTIFY_ROTATED`. */
  readonly justifyDirection: JustifyDirection;
}

/**
 * The re-baseline entry points, straight from the Python table. Add a ratchet
 * here and there — nowhere else.
 */
export const REBASELINE_ENTRY_POINTS: readonly RebaselineEntryPoint[] = [
  {
    ratchet: "entity-surface-parity",
    suite: "backend/mcp_server/tests/test_entity_surface_parity.py",
    canonicalEnv: "ENTITY_SURFACE_REBASELINE",
    placeholder: "<path>",
    legacyEnv: "ENTITY_SURFACE_DUMP",
    command:
      "ENTITY_SURFACE_REBASELINE=/tmp/entity-surface.json " +
      "pytest mcp_server/tests/test_entity_surface_parity.py -q",
    writes:
      "/tmp/entity-surface.json -- a CANDIDATE entity_surface_baseline.json; " +
      "the committed file is only ever replaced by a deliberate copy",
    justifyDirection: JUSTIFY_NEW,
  },
  {
    ratchet: "design-system",
    suite: "frontend/src/test/design-system-ratchet.test.ts",
    canonicalEnv: "DESIGN_SYSTEM_REBASELINE",
    placeholder: "<path|1>",
    legacyEnv: "DESIGN_SYSTEM_RATCHET_DUMP",
    command:
      "DESIGN_SYSTEM_REBASELINE=1 npx vitest run src/test/design-system-ratchet.test.ts",
    writes:
      "frontend/src/test/design-system-ratchet.baseline.json, in place; " +
      "a <path> value writes a candidate instead",
    justifyDirection: JUSTIFY_NEW,
  },
  {
    ratchet: "tool-manifest-drift",
    suite: "backend/mcp_server/tests/test_tool_manifest_drift.py",
    canonicalEnv: "TOOL_MANIFEST_REBASELINE",
    placeholder: "<path|1>",
    legacyEnv: "",
    command:
      "TOOL_MANIFEST_REBASELINE=1 pytest mcp_server/tests/test_tool_manifest_drift.py -q",
    writes:
      "docs/agent-templates/tool-manifest.json, regenerated from the live " +
      "registry via export_tool_manifest; in Docker docs/ is mounted " +
      "read-only, so write a <path> candidate and copy it in",
    justifyDirection: JUSTIFY_ROTATED,
  },
];

/** Resolve a ratchet id (or pass through an entry point). */
export function entryPoint(
  id: RatchetId | RebaselineEntryPoint,
): RebaselineEntryPoint {
  if (typeof id !== "string") return id;
  const found = REBASELINE_ENTRY_POINTS.find((point) => point.ratchet === id);
  if (found === undefined) {
    const known = REBASELINE_ENTRY_POINTS.map((point) => point.ratchet).join(", ");
    throw new RatchetError(`unknown ratchet '${id}'; known ratchets: ${known}`);
  }
  return found;
}

/** The copy-pasteable command, for failure messages that offer a way out. */
export function rebaselineCommand(
  id: RatchetId | RebaselineEntryPoint,
): string {
  return entryPoint(id).command;
}

/**
 * Return where a re-baseline should write, or `null` for a normal run.
 *
 * The canonical env var wins; the documented legacy alias is honoured so the
 * recipes already committed in the repo keep working. A value of `1` (or `true`
 * / `yes`) means "the committed file this ratchet guards" and needs
 * *defaultPath*.
 */
export function resolveRebaselineTarget(
  id: RatchetId | RebaselineEntryPoint,
  defaultPath?: string,
  env: Env = defaultEnv(),
): string | null {
  const point = entryPoint(id);
  let raw = "";
  for (const name of [point.canonicalEnv, point.legacyEnv]) {
    const value = name === "" ? undefined : env[name];
    if (value !== undefined && value !== "") {
      raw = value;
      break;
    }
  }
  if (raw.trim() === "") return null;
  if (SENTINELS.includes(raw.trim().toLowerCase())) {
    if (defaultPath === undefined) {
      throw new RatchetError(
        `${point.canonicalEnv}=${point.placeholder} asks for the committed ` +
          "file, but this ratchet declares no default path. Point the " +
          `variable at an explicit path instead: ${point.canonicalEnv}=${point.placeholder}`,
      );
    }
    return defaultPath;
  }
  return raw.trim();
}

/** A measured set split against a baselined set. */
export interface BaselineDiff {
  /** Measured now, absent from the baseline -- a gap nobody has accepted. */
  readonly new: readonly string[];
  /** Baselined, absent from the measurement -- a claim that is no longer true. */
  readonly rotated: readonly string[];
}

/** Split *measured* against *baselined* into (new, rotated). */
export function splitBaseline(
  measured: Iterable<string>,
  baselined: Iterable<string>,
): BaselineDiff {
  const live = new Set(measured);
  const known = new Set(baselined);
  return {
    new: [...live].filter((key) => !known.has(key)).sort(),
    rotated: [...known].filter((key) => !live.has(key)).sort(),
  };
}

/** Fail when the measurement produced a gap the baseline does not accept. */
export function assertNoUndocumentedGaps(
  diff: BaselineDiff,
  id: RatchetId | RebaselineEntryPoint,
): void {
  const point = entryPoint(id);
  if (diff.new.length === 0) return;
  const listed = diff.new.map((key) => `    ${key}`).join("\n");
  throw new Error(
    `${diff.new.length} gap(s) not accepted by the ${point.ratchet} baseline:\n` +
      `${listed}\n` +
      "Fix the defect (that is what the ratchet is for), or accept the gap " +
      "deliberately with\n" +
      `    ${point.command}\n` +
      "and justify it in the baseline that command produces.",
  );
}

/**
 * Fail when an accepted gap no longer reproduces.
 *
 * The strict-shrink half of a ratchet: an entry that can no longer happen has
 * to be deleted, because a baseline entry nobody checks is how a gate stops
 * being a gate.
 */
export function assertNoStaleEntries(
  diff: BaselineDiff,
  id: RatchetId | RebaselineEntryPoint,
): void {
  const point = entryPoint(id);
  if (diff.rotated.length === 0) return;
  const listed = diff.rotated.map((key) => `    ${key}`).join("\n");
  throw new Error(
    `${diff.rotated.length} baselined gap(s) no longer reproduce in the ` +
      `${point.ratchet} ratchet:\n${listed}\n` +
      "Delete them from the baseline -- a claim nobody is checking is worse " +
      "than no claim. Re-baseline wholesale with:\n" +
      `    ${point.command}`,
  );
}

/** One accepted gap, normalised out of whatever shape the baseline stored. */
export interface Gap {
  /** The measurement key the gap is accepted under. */
  readonly key: string;
  /** Why it is acceptable (>= GAP_MIN_REASON_LENGTH characters). */
  readonly reason: string;
  /** The tracker item that accepts it. */
  readonly issue: string;
  /** True when the entry still carries its issue inside its reason. */
  readonly legacy: boolean;
}

/** The structured form: `gap` is optional because the map key can carry it. */
export interface GapEntryObject {
  /** Why it is acceptable (>= GAP_MIN_REASON_LENGTH characters). */
  reason: string;
  /** The tracker item that accepts it. */
  issue?: string;
  /** Only in the Python-shaped form; a TS exemption uses the map key instead. */
  gap?: string;
}

/** What a caller may hand over as one accepted gap. */
export type GapEntry = string | GapEntryObject;

/** Where the identity of a structured entry comes from. */
export interface GapEntryOptions {
  /** The gap key, when it lives in a map key rather than in the entry. */
  readonly key?: string;
  /** File the entry came from, for error messages. */
  readonly source?: string;
}

/** Options for validating a whole gap list. */
export interface LoadGapOptions {
  readonly source?: string;
}

/** Human-readable type name, for the "wrong shape" failures. */
function describeType(value: unknown): string {
  if (value === null) return "null";
  if (Array.isArray(value)) return "array";
  return typeof value;
}

/** Return a problem string, or null when *reason* is substantive enough. */
function reasonProblem(reason: unknown, label: string): string | null {
  if (typeof reason !== "string" || reason.trim() === "") {
    return `${label}: reason must be a non-empty string`;
  }
  const length = reason.trim().length;
  if (length < GAP_MIN_REASON_LENGTH) {
    return (
      `${label}: reason is ${length} characters and must be at least ` +
      `${GAP_MIN_REASON_LENGTH} — it has to say why THIS gap is acceptable, ` +
      "not restate the rule"
    );
  }
  return null;
}

/** Return a problem string, or null when *issue* references a tracker item. */
function issueProblem(issue: unknown, label: string): string | null {
  if (typeof issue !== "string" || !ISSUE_PATTERN.test(issue)) {
    return `${label}: issue must reference a tracker item (e.g. '#1103')`;
  }
  return null;
}

/** Classify one entry as `{gap}` or `{problem}` — no source, no key default. */
function classifyGapEntry(
  entry: unknown,
  key: string,
): { gap: Gap } | { problem: string } {
  if (typeof entry === "string") {
    if (!ISSUE_PATTERN.test(entry)) {
      return {
        problem:
          "legacy string entry carries no issue marker (expected an '#NNN' " +
          "reference in the text); rewrite it as {reason, issue}",
      };
    }
    return {
      gap: {
        key: key === "" ? entry : key,
        reason: entry,
        issue: entry,
        legacy: true,
      },
    };
  }
  if (typeof entry !== "object" || entry === null || Array.isArray(entry)) {
    return {
      problem: `entry must be a string or an object with a reason, got ${describeType(entry)}`,
    };
  }
  const record = entry as Record<string, unknown>;
  const gapKey =
    key !== "" ? key : typeof record.gap === "string" ? record.gap : "";
  if (gapKey.trim() === "") {
    return {
      problem:
        "structured entry needs a non-empty 'gap' key — pass options.key when " +
        "the identity lives in the map key",
    };
  }
  const label = `gap '${gapKey}'`;
  const withReason = reasonProblem(record.reason, label);
  if (withReason !== null) return { problem: withReason };
  const reason = (record.reason as string).trim();
  // The structured form separates reason and issue; the legacy shape lets the
  // reason carry the marker, exactly as a plain Python string does.
  const hasIssue = typeof record.issue === "string";
  const issue = hasIssue ? (record.issue as string).trim() : reason;
  const withIssue = issueProblem(issue, label);
  if (withIssue !== null) return { problem: withIssue };
  return {
    gap: {
      key: gapKey,
      reason,
      issue: hasIssue ? issue : (ISSUE_PATTERN.exec(issue) ?? [issue])[0],
      legacy: !hasIssue,
    },
  };
}

/** Validate one baseline entry and return it as a :class:`Gap`. */
export function validateGapEntry(
  entry: GapEntry,
  options: GapEntryOptions = {},
): Gap {
  const source = options.source ?? "";
  const where = source === "" ? "" : `${source}: `;
  const classified = classifyGapEntry(entry, options.key ?? "");
  if ("problem" in classified) {
    throw new GapSchemaError(`${where}${classified.problem}`);
  }
  return classified.gap;
}

/**
 * Validate every entry of a baseline's gap list, reporting all problems at once.
 *
 * Enforced on LOAD: a baseline that carries an unjustified accepted gap fails
 * here, before any comparison runs.
 */
export function loadGapEntries(
  entries: readonly GapEntry[],
  options: LoadGapOptions = {},
): Gap[] {
  const gaps: Gap[] = [];
  const problems: string[] = [];
  entries.forEach((entry, index) => {
    const classified = classifyGapEntry(entry, "");
    if ("problem" in classified) {
      const where = options.source ? `${options.source} entry ${index}` : `entry ${index}`;
      problems.push(`  ${where}: ${classified.problem}`);
      return;
    }
    gaps.push(classified.gap);
  });
  if (problems.length > 0) {
    throw new GapSchemaError(
      `${problems.length} invalid accepted gap(s) in ${options.source ?? "the baseline"}:\n` +
        `${problems.join("\n")}\n` +
        `Every accepted gap needs a reason of at least ${GAP_MIN_REASON_LENGTH} ` +
        "characters and an '#NNN' issue reference.",
    );
  }
  return gaps;
}

/** The set of accepted gap keys in a baseline's gap list. */
export function gapKeys(
  entries: readonly GapEntry[],
  options: LoadGapOptions = {},
): Set<string> {
  return new Set(loadGapEntries(entries, options).map((gap) => gap.key));
}

/** What a caller may hand over as "why this gap is acceptable". */
export type Justification = string | { reason: string; issue?: string };

/** Return a problem string, or null when the justification is usable. */
function justificationProblem(value: Justification): string | null {
  if (typeof value === "string") {
    return (
      reasonProblem(value, "justification") ??
      issueProblem(value, "justification")
    );
  }
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return `justification must be a string or an object with a reason, got ${describeType(value)}`;
  }
  const record = value as Record<string, unknown>;
  return (
    reasonProblem(record.reason, "justification") ??
    issueProblem(
      typeof record.issue === "string" ? record.issue : record.reason,
      "justification",
    )
  );
}

/**
 * Read `$RATCHET_JUSTIFY` — the justifications a dump has to carry.
 *
 * The value is either a path to a JSON file or inline JSON; both must decode to
 * an object mapping gap key -> justification. The file form is read through
 * *readFile*, which the caller supplies: the mirror itself has no filesystem
 * dependency (see the header), so `node:fs`'s `readFileSync` is passed in by
 * whoever has it.
 */
export function loadJustifications(
  env: Env = defaultEnv(),
  readFile: FileReader = noFileReader,
): Record<string, Justification> {
  const raw = (env[JUSTIFICATION_ENV_VAR] ?? "").trim();
  if (raw === "") return {};
  // A long value is inline JSON, not a filename; ENAMETOOLONG must not be
  // mistaken for "this file does not exist".
  const text = readFile(raw) ?? raw;
  let data: unknown;
  try {
    data = JSON.parse(text);
  } catch (error) {
    throw new GapSchemaError(
      `$${JUSTIFICATION_ENV_VAR} is neither a readable JSON file nor inline ` +
        `JSON: ${(error as Error).message}`,
    );
  }
  if (typeof data !== "object" || data === null || Array.isArray(data)) {
    throw new GapSchemaError(
      `$${JUSTIFICATION_ENV_VAR} must decode to an object mapping gap key -> ` +
        `justification, got ${describeType(data)}`,
    );
  }
  return data as Record<string, Justification>;
}

/**
 * The widening entries that lack a usable justification.
 *
 * "Widening" is `JUSTIFY_NEW` for a ratchet whose baseline lists accepted gaps,
 * and `JUSTIFY_ROTATED` for one whose baseline is a derived mirror of a live
 * registry.
 */
export function unjustifiedKeys(
  diff: BaselineDiff,
  id: RatchetId | RebaselineEntryPoint,
  justifications?: Record<string, Justification>,
): string[] {
  const point = entryPoint(id);
  const supplied = justifications ?? loadJustifications();
  const widening =
    point.justifyDirection === JUSTIFY_ROTATED ? diff.rotated : diff.new;
  const problems: string[] = [];
  for (const key of widening) {
    if (!Object.prototype.hasOwnProperty.call(supplied, key)) {
      problems.push(`    ${key}: no justification supplied`);
      continue;
    }
    const problem = justificationProblem(supplied[key]);
    if (problem !== null) problems.push(`    ${key}: ${problem}`);
  }
  return problems;
}

/**
 * Refuse a dump that widens the accepted set without justification.
 *
 * This is the guard #1103 asks for: "just re-baseline it" is never a way to
 * make a genuine regression disappear.
 */
export function assertDumpJustified(
  diff: BaselineDiff,
  id: RatchetId | RebaselineEntryPoint,
  justifications?: Record<string, Justification>,
): void {
  const point = entryPoint(id);
  const problems = unjustifiedKeys(diff, point, justifications);
  if (problems.length === 0) return;
  throw new UnjustifiedDumpError(
    `refusing to re-baseline ${point.ratchet}: ${problems.length} widened ` +
      `entr${problems.length === 1 ? "y" : "ies"} without a justification\n` +
      `${problems.join("\n")}\n` +
      "A re-baseline is how a widening becomes auditable, so it must state why " +
      `each new entry is acceptable — in at least ${GAP_MIN_REASON_LENGTH} ` +
      "characters, with an '#NNN' issue reference.\n" +
      `Supply them via $${JUSTIFICATION_ENV_VAR} (inline JSON or a path to a ` +
      "JSON file), one entry per widened key:\n" +
      `    ${JUSTIFICATION_ENV_VAR}='{"<gap key>": {"reason": "...", "issue": "#NNN"}}' \\\n` +
      `        ${point.command}\n` +
      "Or fix the defect instead — that is what the ratchet is for.",
  );
}

/**
 * Monotonicity guard for a ceiling-shaped baseline (`maxViolations`).
 *
 * A re-baseline may keep or lower a ceiling, never raise it: a fresh violation
 * is fixed or explicitly exempted, so it can never be silently absorbed into
 * the number. The one legal increase is the bootstrap run that creates a
 * missing baseline file, otherwise the gate could never be installed.
 */
export function assertCeilingNotRaised(
  check: string,
  previousMax: number,
  measured: number,
  baselineExists: boolean,
): void {
  if (!baselineExists) return;
  if (measured > previousMax) {
    throw new Error(
      `refusing to raise the "${check}" baseline from ${previousMax} to ` +
        `${measured}: the ratchet is monotonically non-increasing ` +
        "(#1103 / REQ-193).\n" +
        "Fix the new violation(s), or exempt them individually with a " +
        "substantive reason. Never raise the ceiling.",
    );
  }
}
