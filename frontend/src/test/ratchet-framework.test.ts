/**
 * Proof that the TypeScript mirror enforces the shared ratchet contract
 * (#1103 / REQ-193).
 *
 * These are the mirror's own tests, and the one that carries the issue's
 * acceptance criterion is "cannot re-baseline a regression away": a re-baseline
 * must never be a way to make a real regression disappear.
 *
 * Everything runs against a fresh `os.tmpdir()` directory. No test here ever
 * touches a committed baseline — `frontend/src/test/design-system-ratchet.baseline.json`
 * is read by the design-system suite, not by this one, and a suite that rewrote
 * its own fixture while proving the framework refuses to rewrite fixtures would
 * prove nothing.
 */
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import {
  GAP_MIN_REASON_LENGTH,
  GapSchemaError,
  UnjustifiedDumpError,
  assertCeilingNotRaised,
  assertDumpJustified,
  assertNoStaleEntries,
  assertNoUndocumentedGaps,
  gapKeys,
  loadGapEntries,
  loadJustifications,
  rebaselineCommand,
  resolveRebaselineTarget,
  splitBaseline,
  validateGapEntry,
  type BaselineDiff,
  type Justification,
} from "./ratchet-framework";

/** A gap the previous baseline does not accept — i.e. a genuine regression. */
const REGRESSION = "components/CsvImport/CsvImport.tsx::button[data-testid=csv-export-btn]";

/** Long enough to satisfy the reason rule, and specific to the element. */
const ACCEPTED_REASON =
  "This export button keeps its ad-hoc fill until the design-system pass lands; " +
  "agents see it in the report export until #1103 is closed";

/** Too short to say anything — the shape the rule exists to reject. */
const LAZY_REASON = "too hard";

let workdir = "";

afterEach(() => {
  if (workdir !== "") rmSync(workdir, { recursive: true, force: true });
  workdir = "";
});

function tempdir(): string {
  workdir = mkdtempSync(join(tmpdir(), "ratchet-framework-"));
  return workdir;
}

/** Justifications as `$RATCHET_JUSTIFY` may supply them. */
function justified(): Record<string, Justification> {
  return { [REGRESSION]: { reason: ACCEPTED_REASON, issue: "#1103" } };
}

/**
 * A minimal frontend dump, in the shape the design-system ratchet uses: write
 * the candidate, but only once every widened entry is justified.
 */
function dumpCandidate(
  target: string,
  measured: readonly string[],
  previous: readonly string[],
  justifications?: Record<string, Justification>,
): BaselineDiff {
  const known = new Set(previous);
  const diff = splitBaseline(measured, known);
  assertDumpJustified(diff, "design-system", justifications);
  writeFileSync(
    target,
    `${JSON.stringify(
      {
        violations: [...measured]
          .sort()
          .map((key) =>
            known.has(key) ? key : { gap: key, ...justifications?.[key] },
          ),
      },
      null,
      2,
    )}\n`,
    "utf-8",
  );
  return diff;
}

describe("a genuine regression cannot be re-baselined away (#1103)", () => {
  it("refuses an unjustified widening and writes nothing", () => {
    const target = join(tempdir(), "candidate.json");

    expect(() =>
      dumpCandidate(target, [REGRESSION], [], {}),
    ).toThrow(UnjustifiedDumpError);
    expect(() => dumpCandidate(target, [REGRESSION], [], {})).toThrow(
      new RegExp(String(GAP_MIN_REASON_LENGTH)),
    );
    // Nothing written means the regression is still a gap the next run fails on.
    expect(existsSync(target)).toBe(false);
    expect(() => assertNoUndocumentedGaps(splitBaseline([REGRESSION], []), "design-system")).toThrow(
      /not accepted by the design-system baseline/,
    );
    expect(rebaselineCommand("design-system")).toMatch(/DESIGN_SYSTEM_REBASELINE=/);
  });

  it("writes a justified widening with the justification recorded", () => {
    const target = join(tempdir(), "candidate.json");
    dumpCandidate(target, [REGRESSION], [], justified());

    const written = JSON.parse(readFileSync(target, "utf-8")) as {
      violations: Array<string | { gap: string; reason: string; issue: string }>;
    };
    expect(written.violations).toEqual([
      { gap: REGRESSION, reason: ACCEPTED_REASON, issue: "#1103" },
    ]);
    // The following run accepts what the justified dump wrote.
    expect(gapKeys(written.violations)).toEqual(new Set([REGRESSION]));
  });

  it("reads the justifications from $RATCHET_JUSTIFY as inline JSON", () => {
    expect(loadJustifications({ RATCHET_JUSTIFY: JSON.stringify(justified()) })).toEqual(
      justified(),
    );
    // A short reason is a reason nobody can audit.
    expect(() => dumpCandidate(target(), [REGRESSION], [], { [REGRESSION]: LAZY_REASON })).toThrow(
      /reason is 8 characters/,
    );
  });
});

describe("the stale half of the contract", () => {
  it("fails loudly and names the entry and the command", () => {
    const stale = "components/MermaidEditor.tsx::button[data-testid=mermaid-save-btn]";
    const diff = splitBaseline(["still-reproducing"], [stale, "still-reproducing"]);
    expect(diff).toEqual({ new: [], rotated: [stale] });
    // Substring assertions: the keys carry regex metacharacters.
    const failing = () => assertNoStaleEntries(diff, "design-system");
    expect(failing).toThrow(stale);
    expect(failing).toThrow("no longer reproduce");
    expect(failing).toThrow("DESIGN_SYSTEM_REBASELINE=1");
    // An empty rotation is fine — that is the normal, strict-shrinking state.
    expect(() =>
      assertNoStaleEntries(splitBaseline(["live"], ["live"]), "design-system"),
    ).not.toThrow();
  });

  it("keeps the two halves independent", () => {
    const diff = splitBaseline(["new-gap"], ["rotated-gap"]);
    expect(() => assertNoUndocumentedGaps(diff, "design-system")).toThrow(/not accepted/);
    expect(() => assertNoStaleEntries(diff, "design-system")).toThrow(/no longer reproduce/);
  });
});

describe("the gap schema", () => {
  it("takes the gap identity from the map key", () => {
    const gap = validateGapEntry({ reason: ACCEPTED_REASON, issue: "#1099" }, {
      key: REGRESSION,
    });
    expect(gap).toEqual({ key: REGRESSION, reason: ACCEPTED_REASON, issue: "#1099", legacy: false });
  });

  it("rejects a short reason, a missing reason and a missing issue link", () => {
    const key = "components/TagInput.tsx::button";
    for (const bad of [
      { reason: LAZY_REASON, issue: "#1099" },
      { reason: "   ", issue: "#1099" },
      { issue: "#1099" },
      { reason: LAZY_REASON },
      { reason: ACCEPTED_REASON, issue: "see the wiki" },
      {},
      "no issue marker in this legacy string",
      17,
    ] as unknown[]) {
      expect(() => validateGapEntry(bad as never, { key }), JSON.stringify(bad)).toThrow(
        GapSchemaError,
      );
    }
    // A structured entry with no key anywhere is a key nobody can match on.
    expect(() => validateGapEntry({ reason: ACCEPTED_REASON, issue: "#1099" })).toThrow(
      GapSchemaError,
    );
  });

  it("accepts the legacy shape whose reason carries its own marker", () => {
    // The Python side accepts a plain string that references a tracker item;
    // the TS analogue is an entry with no separate `issue` field, whose reason
    // carries the '#NNN' marker. Both are the legacy shape, and both still
    // have to satisfy the reason floor.
    const key = "components/TagInput.tsx::button";
    expect(validateGapEntry({ reason: ACCEPTED_REASON }, { key })).toEqual({
      key,
      reason: ACCEPTED_REASON,
      issue: "#1103",
      legacy: true,
    });
    expect(validateGapEntry(`tag input is exempt by design (${"#1099"})`, { key })).toEqual({
      key,
      reason: `tag input is exempt by design (#1099)`,
      issue: `tag input is exempt by design (#1099)`,
      legacy: true,
    });
  });

  it("reports every problem in a list, not just the first", () => {
    expect(() =>
      loadGapEntries(
        [
          { reason: LAZY_REASON, issue: "#1099" },
          { reason: ACCEPTED_REASON, issue: "see the wiki" },
        ],
        { source: "design-system-ratchet.baseline.json" },
      ),
    ).toThrow(/2 invalid accepted gap\(s\) in design-system-ratchet\.baseline\.json/);
  });
});

describe("the named re-baseline entry points", () => {
  it("resolves the canonical var and the documented legacy alias", () => {
    const canonical = resolveRebaselineTarget("design-system", undefined, {
      DESIGN_SYSTEM_REBASELINE: "/tmp/candidate.json",
    });
    expect(canonical).toBe("/tmp/candidate.json");
    expect(
      resolveRebaselineTarget("design-system", undefined, {
        DESIGN_SYSTEM_RATCHET_DUMP: "/tmp/candidate.json",
      }),
    ).toBe("/tmp/candidate.json");
    // The canonical var wins when both are set.
    expect(
      resolveRebaselineTarget("design-system", undefined, {
        DESIGN_SYSTEM_REBASELINE: "/tmp/canonical.json",
        DESIGN_SYSTEM_RATCHET_DUMP: "/tmp/legacy.json",
      }),
    ).toBe("/tmp/canonical.json");
    // `1` means "the committed file this ratchet guards".
    expect(
      resolveRebaselineTarget("design-system", "/repo/baseline.json", {
        DESIGN_SYSTEM_REBASELINE: "1",
      }),
    ).toBe("/repo/baseline.json");
    // A normal run resolves nothing.
    expect(resolveRebaselineTarget("design-system", "/repo/baseline.json", {})).toBeNull();
    // `1` with no default to point at is an error, not a silent no-op.
    expect(() =>
      resolveRebaselineTarget("design-system", undefined, {
        DESIGN_SYSTEM_REBASELINE: "1",
      }),
    ).toThrow(/declares no default path/);
    expect(() => resolveRebaselineTarget("no-such-ratchet" as never)).toThrow(
      /unknown ratchet/,
    );
  });
});

describe("the ceiling-shaped variant", () => {
  it("cannot be raised by a re-baseline", () => {
    expect(() => assertCeilingNotRaised("emoji-as-ui-glyph", 5, 5, true)).not.toThrow();
    expect(() => assertCeilingNotRaised("emoji-as-ui-glyph", 5, 3, true)).not.toThrow();
    // The bootstrap run that creates a missing baseline may raise it.
    expect(() => assertCeilingNotRaised("emoji-as-ui-glyph", 0, 6, false)).not.toThrow();
    expect(() => assertCeilingNotRaised("emoji-as-ui-glyph", 5, 6, true)).toThrow(
      /monotonically non-increasing/,
    );
  });
});

/** A target path inside the current temp directory. */
function target(): string {
  return join(tempdir(), "candidate.json");
}
