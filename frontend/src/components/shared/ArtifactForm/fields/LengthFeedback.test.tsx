/**
 * #1282 — length feedback on definition-bounded text fields.
 *
 * The counter must appear only once the value reaches 80% of the definition's
 * `validation.length`, must read `used / max`, and must render nothing at all
 * for an unbounded attribute (so it can never invent a limit the backend does
 * not enforce).
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { LengthFeedback } from "./LengthFeedback";

describe("LengthFeedback (#1282)", () => {
  it("renders nothing below 80% of the limit", () => {
    render(
      <LengthFeedback value={"a".repeat(79)} maxLength={100} testId="field" />,
    );
    expect(screen.queryByTestId("field-length")).not.toBeInTheDocument();
  });

  it("renders 'used / max' at exactly 80% of the limit", () => {
    render(
      <LengthFeedback value={"a".repeat(80)} maxLength={100} testId="field" />,
    );
    expect(screen.getByTestId("field-length")).toHaveTextContent("80 / 100");
  });

  it("renders nothing when the attribute is unbounded", () => {
    render(<LengthFeedback value={"a".repeat(5000)} maxLength={undefined} testId="field" />);
    expect(screen.queryByTestId("field-length")).not.toBeInTheDocument();
  });

  it("treats a null value as empty", () => {
    render(<LengthFeedback value={null} maxLength={100} testId="field" />);
    expect(screen.queryByTestId("field-length")).not.toBeInTheDocument();
  });
});
