/**
 * Tests for the component hotspot analysis (#598 S2).
 *
 * The two fixtures are the smallest inputs that pin the cluster rule:
 * a component whose declarations are all connected must yield one cluster, a
 * component with three mutually independent state groups must yield three.
 */

import { describe, it, expect } from "vitest";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { analyzeFile } from "./analyze-component-hotspots.mjs";

// Vite statically rewrites `new URL("./fixtures/x", import.meta.url)` into an
// asset URL ("/scripts/fixtures/x") when this file runs under Vitest, which
// then misses the real file. Resolving through `dirname` keeps the filesystem
// path intact in both the test runner and plain Node.
const FIXTURES = join(dirname(fileURLToPath(import.meta.url)), "fixtures");

function fixture(name) {
  return join(FIXTURES, name);
}

describe("analyzeFile", () => {
  it("cohesive component yields one cluster", () => {
    const result = analyzeFile(fixture("cohesive.tsx"));

    expect(result.clusters).toHaveLength(1);
    expect(result.clusters[0].kinds).toContain("state");
    expect(result.lines).toBeGreaterThan(0);
    expect(result.cyclomatic).toBeGreaterThan(0);
    expect(result.hooks).toBeGreaterThan(0);
  });

  it("component with three unrelated state groups yields three clusters", () => {
    const result = analyzeFile(fixture("three-concerns.tsx"));

    expect(result.clusters).toHaveLength(3);
    // Every concern owns its own state: that is the split criterion, not the
    // mere cluster count.
    expect(
      result.clusters.filter((cluster) => cluster.kinds.includes("state")),
    ).toHaveLength(3);
    expect(result.clusters.flatMap((cluster) => cluster.names)).toEqual(
      expect.arrayContaining(["users", "dialogOpen", "toast"]),
    );
  });
});
