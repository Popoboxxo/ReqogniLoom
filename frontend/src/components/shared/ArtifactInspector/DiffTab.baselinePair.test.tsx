/**
 * DiffTab — one pair line, no navigation (spec §2.2, M1-8).
 *
 * The pair line reports the range `ArtifactDiff` **resolved**, never the
 * shell's request (the M-04 defect). Choosing a different comparison updates
 * the line in place — it must not navigate.
 *
 * **Documented M1 deviation:** the baseline selector
 * (`inspector-baseline-select`) needs `GET /api/v1/artifacts/<pk>/baselines/`
 * (plan task B2.0-1), which is not on `main`. It is therefore not rendered
 * yet; the testid is reserved in the contract so the `data-testid` inventory
 * stays complete (spec §8.4 point 7).
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DiffTab } from "./tabs/DiffTab";

vi.mock("../../ArtifactDiff/ArtifactDiff", async () => {
  const { useState } = await import("react");
  return {
    ArtifactDiff: ({
      onRangeChange,
    }: {
      onRangeChange?: (range: { from: number; to: number; isInitialState: boolean }) => void;
    }) => {
      const [step, setStep] = useState(0);
      const emit = (): void => {
        const next = step + 1;
        setStep(next);
        onRangeChange?.({ from: next, to: 4, isInitialState: false });
      };
      return (
        <button type="button" className="btn-ghost" data-testid="diff-emit" onClick={emit}>
          emit range
        </button>
      );
    },
  };
});

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, second?: unknown): string => {
      if (typeof second === "string") return second;
      if (second && typeof second === "object" && "defaultValue" in second) {
        const options = second as Record<string, unknown>;
        let text = String(options.defaultValue);
        for (const [name, value] of Object.entries(options)) {
          if (name === "defaultValue") continue;
          text = text.replaceAll(`{{${name}}}`, String(value));
        }
        return text;
      }
      return key;
    },
  }),
}));

describe("DiffTab — baseline pair line (M1-8)", () => {
  beforeEach(() => {
    window.history.replaceState({}, "", "/requirements/req-1");
  });

  it("renders exactly one pair line and updates it without navigating", () => {
    render(
      <DiffTab kind="requirement" entityId="req-1" leftVersion={1} rightVersion={4} />,
    );

    const pair = screen.getByTestId("inspector-diff-pair");
    expect(screen.getAllByTestId("inspector-diff-pair")).toHaveLength(1);
    expect(pair).toHaveTextContent("Comparison is being prepared");

    const pathnameBefore = window.location.pathname;

    fireEvent.click(screen.getByTestId("diff-emit"));

    expect(screen.getByTestId("inspector-diff-pair")).toHaveTextContent(
      "Comparison v1 → v4",
    );
    expect(window.location.pathname).toBe(pathnameBefore);
    expect(screen.getAllByTestId("inspector-diff-pair")).toHaveLength(1);
  });

  it("renders the diff panel in tab form — no area heading of its own", () => {
    render(
      <DiffTab kind="requirement" entityId="req-1" leftVersion={1} rightVersion={4} />,
    );

    expect(screen.getByTestId("inspector-diff-panel")).toBeInTheDocument();
    expect(screen.queryByRole("heading")).not.toBeInTheDocument();
  });
});
