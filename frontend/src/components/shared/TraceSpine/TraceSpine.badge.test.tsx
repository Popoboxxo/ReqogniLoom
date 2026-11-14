/**
 * TraceSpine — verification badge at every station with data (spec §2.3
 * rule 3, U-07, M1-9).
 *
 * Verification is a badge, not a station. It used to be rendered only on
 * requirement and architecture stations, although the chain already carries
 * the verification list for every station (`useDerivationChain`). A
 * stakeholder need with three verifying test cases therefore showed nothing.
 */

import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { TraceSpine } from "./TraceSpine";
import type { ChainStation } from "./useDerivationChain";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string, second?: unknown) => (typeof second === "string" ? second : key) }),
}));

function station(
  key: string,
  artifactType: string,
  verifications: number,
): ChainStation {
  return {
    key,
    artifactType,
    level: null,
    direction: "origin",
    isCurrent: false,
    artifacts: [
      {
        id: `${key}-artifact`,
        title: `${key} title`,
        uid: `${key}-uid`,
        artifactType,
        linkType: "derives-from",
      },
    ],
    verifications: Array.from({ length: verifications }, (_, index) => ({
      id: `${key}-test-${index}`,
      title: `Test ${index}`,
      uid: `TC-${index}`,
      artifactType: "TestCase",
      linkType: "verifies",
    })),
  } as ChainStation;
}

describe("TraceSpine — verification badge (M1-9)", () => {
  it("renders the badge on every station with a non-empty verification list", () => {
    render(
      <TraceSpine
        stations={[
          station("need", "StakeholderNeed", 2),
          station("risk", "Risk", 1),
          station("adr", "Adr", 0),
        ]}
        testId="spine"
      />,
    );

    const [need, risk, adr] = screen.getAllByTestId("spine-station");
    expect(within(need!).getByTestId("spine-verification")).toHaveTextContent("·2");
    expect(within(risk!).getByTestId("spine-verification")).toHaveTextContent("·1");
    // No data, no badge on a type that never had one.
    expect(within(adr!).queryByTestId("spine-verification")).not.toBeInTheDocument();
  });

  it("keeps the disabled badge on requirement stations without verifications", () => {
    render(
      <TraceSpine
        stations={[station("requirement", "Requirement", 0)]}
        testId="spine"
      />,
    );

    const badge = screen.getByTestId("spine-verification");
    expect(badge).toBeDisabled();
    expect(badge).toHaveClass("btn-ghost");
  });
});
