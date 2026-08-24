import { readFileSync } from "fs";
import { describe, it, expect } from "vitest";

describe("InterviewWidget toggle button style", () => {
  const css = readFileSync("src/components/InterviewWidget/InterviewWidget.module.css", "utf-8");
  const toggleBlock = css.match(/\.toggle\s*\{[^}]*\}/)?.[0] ?? "";

  it("does not use the primary brand color for the floating toggle background", () => {
    expect(toggleBlock).not.toMatch(/background:\s*var\(--color-primary\)/);
  });

  it("does not use the heaviest card shadow token", () => {
    expect(toggleBlock).not.toMatch(/box-shadow:\s*var\(--shadow-card\)/);
  });
});
