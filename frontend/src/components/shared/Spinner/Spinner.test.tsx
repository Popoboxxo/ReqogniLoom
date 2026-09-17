import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { Spinner } from "./Spinner";

describe("Spinner", () => {
  it("renders a decorative spinner and an accessible label", () => {
    render(<Spinner label="Sending" />);
    expect(screen.getByTestId("spinner")).toHaveAttribute("aria-hidden", "true");
    expect(screen.getByText("Sending")).toBeInTheDocument();
  });

  it("defaults to the sm size and a generic label", () => {
    render(<Spinner />);
    expect(screen.getByText("Loading")).toBeInTheDocument();
  });
});
