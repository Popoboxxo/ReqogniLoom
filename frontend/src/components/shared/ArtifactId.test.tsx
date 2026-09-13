/**
 * <ArtifactId> unit tests (Attribut v3 WS3, #937).
 *
 * The artifact-specific preset of `<RevealValue>`: still mono, still
 * copyable, now also copyable by double-click and able to forward the generic
 * display properties.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { resolveLocaleKey } from "../../test/i18n-test-helpers";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) => {
      const { defaultValue, ...interpolation } = options ?? {};
      const resolved =
        resolveLocaleKey(key) ??
        (typeof defaultValue === "string" ? defaultValue : key);
      return Object.entries(interpolation).reduce(
        (acc, [name, value]) => acc.replace(`{{${name}}}`, String(value)),
        resolved
      );
    },
    i18n: { language: "de" },
  }),
}));

import { ArtifactId } from "./ArtifactId";

const writeText = vi.fn();

beforeEach(() => {
  writeText.mockReset();
  writeText.mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", {
    value: { writeText },
    configurable: true,
  });
});

describe("ArtifactId", () => {
  it("renders the semantic identifier", () => {
    render(<ArtifactId value="SYS-REQ-001" />);
    expect(screen.getByTestId("artifact-id")).toHaveTextContent("SYS-REQ-001");
  });

  it("falls back to the short handle when no uid is set", () => {
    render(<ArtifactId fallback="a1b2c3d4" />);
    expect(screen.getByTestId("artifact-id")).toHaveTextContent("a1b2c3d4");
  });

  it("copies the label on double-click", () => {
    render(<ArtifactId value="ADR-004" />);
    fireEvent.doubleClick(screen.getByTestId("artifact-id-value"));
    expect(writeText).toHaveBeenCalledWith("ADR-004");
  });

  it("copies the label on a single click", () => {
    render(<ArtifactId value="ADR-004" />);
    fireEvent.click(screen.getByTestId("artifact-id-value"));
    expect(writeText).toHaveBeenCalledWith("ADR-004");
  });

  it("copies the full copyValue while showing the short label", () => {
    const full = "12345678-1234-4abc-8def-1234567890ab";
    render(<ArtifactId fallback={full.slice(0, 8)} copyValue={full} />);
    expect(screen.getByTestId("artifact-id")).toHaveTextContent("12345678");
    fireEvent.doubleClick(screen.getByTestId("artifact-id-value"));
    expect(writeText).toHaveBeenCalledWith(full);
  });

  it("suppresses copying in readOnly mode", () => {
    render(<ArtifactId value="ADR-004" readOnly />);
    expect(screen.queryByTestId("artifact-id-copy")).not.toBeInTheDocument();
    expect(screen.getByTestId("artifact-id")).toHaveTextContent("ADR-004");
  });

  it("reports a copy confirmation", async () => {
    render(<ArtifactId value="ADR-004" />);
    fireEvent.click(screen.getByTestId("artifact-id-copy"));
    expect(await screen.findByTestId("artifact-id-copied")).toBeInTheDocument();
  });
});
