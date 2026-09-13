/**
 * <RevealValue> unit tests (Attribut v3 WS3, #937).
 *
 * Covers the four generic display properties from the implementation spec
 * section 5: reveal (always/click/shortcut), copyable (button + double-click,
 * full value while masked), mask="short", and display_format (mono/chips).
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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

import { RevealValue, SHORT_MASK_LENGTH } from "./RevealValue";

const UUID = "12345678-1234-4abc-8def-1234567890ab";

const writeText = vi.fn();

beforeEach(() => {
  writeText.mockReset();
  writeText.mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", {
    value: { writeText },
    configurable: true,
  });
});

describe("RevealValue", () => {
  it("renders the value permanently with reveal=always (the default)", () => {
    render(<RevealValue value="SYS-REQ-001" testId="rv" />);
    expect(screen.getByTestId("rv-value")).toHaveTextContent("SYS-REQ-001");
    expect(screen.queryByTestId("rv-reveal")).not.toBeInTheDocument();
  });

  it("masks the label while copying the full value (mask=short + copyable)", async () => {
    render(
      <RevealValue
        value={UUID}
        copyValue={UUID}
        mask="short"
        copyable
        testId="rv"
      />
    );
    const shown = screen.getByTestId("rv-value");
    expect(shown).toHaveTextContent(`${UUID.slice(0, SHORT_MASK_LENGTH)}…`);
    expect(shown).not.toHaveTextContent(UUID);

    fireEvent.click(screen.getByTestId("rv-copy"));
    await waitFor(() =>
      expect(screen.getByTestId("rv-copied")).toBeInTheDocument()
    );
    expect(writeText).toHaveBeenCalledWith(UUID);
  });

  it("copies the full value on double-click", () => {
    render(<RevealValue value={UUID} mask="short" copyable testId="rv" />);
    fireEvent.doubleClick(screen.getByTestId("rv-value"));
    expect(writeText).toHaveBeenCalledWith(UUID);
  });

  it("hides the value until clicked with reveal=click", () => {
    render(<RevealValue value="geheim" reveal="click" testId="rv" />);
    expect(screen.queryByTestId("rv-value")).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId("rv-reveal"));
    expect(screen.getByTestId("rv-value")).toHaveTextContent("geheim");
    // Announced through the aria-live region.
    expect(screen.getByTestId("rv-revealed")).toBeInTheDocument();
  });

  it("hides the value until the shortcut is pressed with reveal=shortcut", () => {
    render(<RevealValue value="geheim" reveal="shortcut" testId="rv" />);
    expect(screen.queryByTestId("rv-value")).not.toBeInTheDocument();

    fireEvent.keyDown(window, { key: "R", code: "KeyR", altKey: true, shiftKey: true });
    expect(screen.getByTestId("rv-value")).toHaveTextContent("geheim");
  });

  it("does not reveal on an unrelated key", () => {
    render(<RevealValue value="geheim" reveal="shortcut" testId="rv" />);
    fireEvent.keyDown(window, { key: "r", code: "KeyR" });
    expect(screen.queryByTestId("rv-value")).not.toBeInTheDocument();
  });

  it("renders display_format=chips as one chip per entry", () => {
    render(
      <RevealValue
        value="a, b"
        chips={["a", "b"]}
        displayFormat="chips"
        testId="rv"
      />
    );
    expect(screen.getByTestId("rv-chips")).toBeInTheDocument();
    expect(screen.getAllByTestId("rv-chip")).toHaveLength(2);
  });

  it("applies the mono class for display_format=mono", () => {
    const { rerender } = render(<RevealValue value="x" testId="rv" />);
    expect(screen.getByTestId("rv-value").classList.length).toBe(1);

    rerender(<RevealValue value="x" displayFormat="mono" testId="rv" />);
    expect(screen.getByTestId("rv-value").classList.length).toBe(2);
  });

  it("suppresses the copy affordance in readOnly mode", () => {
    render(<RevealValue value="x" copyable readOnly testId="rv" />);
    expect(screen.queryByTestId("rv-copy")).not.toBeInTheDocument();
  });
});
