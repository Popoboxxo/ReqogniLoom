import { describe, expect, it } from "vitest";
import {
  buildArtifact,
  boundedMessage,
  classifyFailure,
  errorLocation,
  ERROR_MESSAGE_LIMIT,
  testNameFrom,
  type FlakyTestInput,
} from "./flaky-artifact";

/** Build a failed-test record with sensible defaults, overriding what matters. */
function failed(overrides: Partial<FlakyTestInput> = {}): FlakyTestInput {
  return {
    file: "a.test.ts",
    fullName: "some describe block > nested",
    name: "nested",
    error: { name: "Error", message: "boom", stack: "    at a (src/x.ts:1:1)" },
    durationMs: 12,
    ...overrides,
  };
}

describe("classifyFailure (#1117)", () => {
  it("puts vitest timeout phrasings in the timeout bucket", () => {
    expect(classifyFailure({ message: "test timed out in 5000ms." })).toBe("timeout");
    expect(classifyFailure({ message: "Test timed out in 5000ms" })).toBe("timeout");
    expect(classifyFailure({ message: "hook timed out in 1000ms" })).toBe("timeout");
    expect(classifyFailure({ name: "TimeoutError", message: "operation timed out" })).toBe("timeout");
  });

  it("puts assertion mismatches in the assertion bucket", () => {
    expect(classifyFailure({ name: "AssertionError", message: "boom" })).toBe("assertion");
    expect(classifyFailure({ message: "expected 1 to equal 2" })).toBe("assertion");
  });

  it("puts a thrown error from the test body in the runtime bucket", () => {
    expect(classifyFailure({ name: "Error", message: "body failure" })).toBe("runtime");
    // no name at all - still a runtime failure, not a dropped record
    expect(classifyFailure({ message: "unhandled rejection in test body" })).toBe("runtime");
  });

  it("never classifies a record with no error as anything but other", () => {
    expect(classifyFailure(null)).toBe("other");
    expect(classifyFailure(undefined)).toBe("other");
    expect(classifyFailure({})).toBe("other");
  });
});

describe("boundedMessage", () => {
  it("collapses whitespace and trims", () => {
    expect(boundedMessage("  a \n\n b  ")).toBe("a \n\n b");
  });

  it("truncates an over-long message to the documented limit", () => {
    const result = boundedMessage("x".repeat(ERROR_MESSAGE_LIMIT + 10));
    expect(result).not.toBeNull();
    expect(result!.length).toBe(ERROR_MESSAGE_LIMIT + 1);
    expect(result!.endsWith("…")).toBe(true);
  });

  it("returns null when there is nothing to keep", () => {
    expect(boundedMessage(undefined)).toBeNull();
    expect(boundedMessage("")).toBeNull();
  });
});

describe("errorLocation", () => {
  it("prefers the first frame outside node_modules", () => {
    const stack = [
      "Error: boom",
      "    at eval (/workspace/src/components/Foo.tsx:10:5)",
      "    at Object.<anonymous> (node_modules/vitest/dist/index.js:1:1)",
    ].join("\n");
    expect(errorLocation(stack)).toBe("at eval (/workspace/src/components/Foo.tsx:10:5)");
  });

  it("falls back to the first frame when every frame is vendor code", () => {
    const stack = ["Error: boom", "    at Object.<anonymous> (node_modules/vitest/dist/index.js:1:1)"].join("\n");
    expect(errorLocation(stack)).toBe("at Object.<anonymous> (node_modules/vitest/dist/index.js:1:1)");
  });

  it("returns null without a stack", () => {
    expect(errorLocation(undefined)).toBeNull();
    expect(errorLocation("Error: boom")).toBeNull();
  });
});

describe("testNameFrom", () => {
  it("takes the last segment of vitest's `a > b > c` full name", () => {
    expect(testNameFrom("some describe block > nested", null)).toBe("nested");
  });

  it("prefers an explicit name over the parsed full name", () => {
    expect(testNameFrom("suite > renamed", "renamed")).toBe("renamed");
  });

  it("returns null when neither is available", () => {
    expect(testNameFrom(null, null)).toBeNull();
    expect(testNameFrom("", "")).toBeNull();
  });
});

describe("buildArtifact", () => {
  it("reports a green run without any file entries", () => {
    const artifact = buildArtifact([], "2026-10-13T00:00:00.000Z");

    expect(artifact.failed).toBe(0);
    expect(artifact.files).toBe(0);
    expect(artifact.files_failures).toHaveLength(0);
    expect(artifact.byCategory).toEqual({ timeout: 0, assertion: 0, runtime: 0, other: 0 });
  });

  it("keeps a nested suite's full name and derives the test name", () => {
    const artifact = buildArtifact([failed()], "2026-10-13T00:00:00.000Z");

    expect(artifact.failed).toBe(1);
    const record = artifact.files_failures[0].failures[0];
    expect(record.namePath).toBe("some describe block > nested");
    expect(record.testName).toBe("nested");
    expect(record.file).toBe("a.test.ts");
    expect(record.category).toBe("runtime");
    expect(record.errorLocation).toBe("at a (src/x.ts:1:1)");
    expect(record.durationMs).toBe(12);
  });

  it("counts categories across files so the timeout class is visible at a glance", () => {
    const artifact = buildArtifact(
      [
        failed({ file: "a.test.ts", fullName: "t1", name: "t1", error: { message: "test timed out in 5000ms." } }),
        failed({ file: "a.test.ts", fullName: "t2", name: "t2", error: { message: "expected 1 to equal 2" } }),
        failed({ file: "b.test.ts", fullName: "t3", name: "t3", error: { message: "hook timed out in 1000ms" } }),
        failed({ file: "b.test.ts", fullName: "t4", name: "t4", error: { message: "weird" } }),
      ],
      "2026-10-13T00:00:00.000Z",
    );

    expect(artifact.failed).toBe(4);
    expect(artifact.files).toBe(2);
    expect(artifact.byCategory).toEqual({ timeout: 2, assertion: 1, runtime: 1, other: 0 });
  });

  it("groups failures by file, preserving one entry per file", () => {
    const artifact = buildArtifact(
      [
        failed({ file: "a.test.ts", fullName: "t1", name: "t1" }),
        failed({ file: "a.test.ts", fullName: "t2", name: "t2" }),
        failed({ file: "b.test.ts", fullName: "t3", name: "t3" }),
      ],
      "2026-10-13T00:00:00.000Z",
    );

    expect(artifact.files).toBe(2);
    expect(artifact.files_failures[0].failures).toHaveLength(2);
    expect(artifact.files_failures[1].failures).toHaveLength(1);
  });

  it("treats a missing input as a green run rather than throwing", () => {
    expect(buildArtifact(undefined).failed).toBe(0);
    expect(buildArtifact(null).failed).toBe(0);
  });

  it("keeps a record for a failure with no error object, bucketed as other", () => {
    const artifact = buildArtifact(
      [failed({ error: null, fullName: "mystery", name: "mystery" })],
      "2026-10-13T00:00:00.000Z",
    );
    expect(artifact.failed).toBe(1);
    expect(artifact.files_failures[0].failures[0].category).toBe("other");
    expect(artifact.files_failures[0].failures[0].errorMessage).toBeNull();
  });
});
