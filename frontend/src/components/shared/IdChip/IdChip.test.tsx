/**
 * Issue #1094 — `<IdChip>` unit tests.
 *
 * The contract under test is the one the issue fixes:
 *   - SHOWS the readable `uid` by default, the system id on request, with the
 *     other identity as a fallback;
 *   - COPIES the system id (UUID) — never the readable one — and says which of
 *     the two landed on the clipboard, including the "no system id available"
 *     fallback and a refused clipboard;
 *   - ANNOUNCES that result through an `aria-live` region, not only visually;
 *   - can hide the readable identifier while keeping the copy affordance.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { resolveLocaleKey } from "../../../test/i18n-test-helpers";

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

import { IdChip } from "./IdChip";

const UID = "ARCH-001";
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

describe("IdChip display", () => {
  it("shows the readable uid by default", () => {
    render(<IdChip uid={UID} systemId={UUID} testId="chip" />);
    expect(screen.getByTestId("chip-value")).toHaveTextContent(UID);
  });

  it("shows the system id when asked to", () => {
    render(<IdChip uid={UID} systemId={UUID} display="system" testId="chip" />);
    expect(screen.getByTestId("chip-value")).toHaveTextContent(UUID);
  });

  it("falls back to the other identity rather than rendering empty", () => {
    // A chip that renders nothing because the caller asked for the "wrong"
    // kind is worse than one that shows what it does have.
    const { rerender } = render(<IdChip uid={null} systemId={UUID} testId="chip" />);
    expect(screen.getByTestId("chip-value")).toHaveTextContent(UUID);

    rerender(<IdChip uid={UID} systemId={null} display="system" testId="chip" />);
    expect(screen.getByTestId("chip-value")).toHaveTextContent(UID);
  });

  it("falls back to the placeholder for a row whose uid is not allocated yet", () => {
    render(<IdChip uid="" fallback="a1b2c3d4" testId="chip" />);
    expect(screen.getByTestId("chip-value")).toHaveTextContent("a1b2c3d4");
    // A display placeholder is not an identity and is never copied.
    expect(screen.queryByTestId("chip-copy")).not.toBeInTheDocument();
  });

  it("renders the placeholder when there is no identifier at all", () => {
    render(<IdChip placeholder="Keine Kennung" testId="chip" />);
    expect(screen.getByTestId("chip-value")).toHaveTextContent("Keine Kennung");
  });

  it("renders nothing when there is neither an identifier nor a placeholder", () => {
    const { container } = render(<IdChip testId="chip" />);
    expect(container).toBeEmptyDOMElement();
  });

  it("hides the identifier text while keeping the copy control", () => {
    render(<IdChip uid={UID} systemId={UUID} hideReadable testId="chip" />);
    expect(screen.queryByTestId("chip-value")).not.toBeInTheDocument();
    // Hiding is a display preference; copying the system id stays available.
    expect(screen.getByTestId("chip-copy")).toBeInTheDocument();
  });
});

describe("IdChip copy", () => {
  it("copies the SYSTEM id even though the readable uid is what it shows", async () => {
    render(<IdChip uid={UID} systemId={UUID} testId="chip" />);
    expect(screen.getByTestId("chip-value")).toHaveTextContent(UID);

    fireEvent.click(screen.getByTestId("chip-copy"));

    expect(writeText).toHaveBeenCalledWith(UUID);
    expect(writeText).not.toHaveBeenCalledWith(UID);
  });

  it("announces 'UUID kopiert' through a live region", async () => {
    render(<IdChip uid={UID} systemId={UUID} testId="chip" />);

    const status = screen.getByTestId("chip-status");
    expect(status).toHaveAttribute("aria-live", "polite");
    expect(status).toHaveAttribute("role", "status");
    // Mounted from the start, so assistive tech has a region to observe.
    expect(status).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("chip-copy"));

    await waitFor(() => expect(screen.getByTestId("chip-status")).toHaveTextContent("UUID kopiert"));
  });

  it("copies the uid and says so when there is no system id", async () => {
    // The issue's fallback wording: the user must not be left guessing which
    // of the two strings is now on their clipboard.
    render(<IdChip uid={UID} testId="chip" />);

    fireEvent.click(screen.getByTestId("chip-copy"));

    expect(writeText).toHaveBeenCalledWith(UID);
    await waitFor(() =>
      expect(screen.getByTestId("chip-status")).toHaveTextContent(
        "UID kopiert, weil keine System-ID vorhanden"
      )
    );
  });

  it("reports a refused clipboard instead of claiming success", async () => {
    // `navigator.clipboard` is undefined on insecure origins and can reject
    // outright; "copied" would be a lie the user only discovers later.
    writeText.mockRejectedValue(new Error("denied"));
    render(<IdChip uid={UID} systemId={UUID} testId="chip" />);

    fireEvent.click(screen.getByTestId("chip-copy"));

    await waitFor(() =>
      expect(screen.getByTestId("chip-status")).toHaveTextContent("Kopieren fehlgeschlagen")
    );
  });

  it("reports the outcome and the exact string to onCopyResult", async () => {
    const onCopyResult = vi.fn();
    render(<IdChip uid={UID} systemId={UUID} onCopyResult={onCopyResult} testId="chip" />);

    fireEvent.click(screen.getByTestId("chip-copy"));

    await waitFor(() =>
      expect(onCopyResult).toHaveBeenCalledWith({ status: "system", value: UUID })
    );
  });

  it("reports the uid fallback through onCopyResult too", async () => {
    const onCopyResult = vi.fn();
    render(<IdChip uid={UID} onCopyResult={onCopyResult} testId="chip" />);

    fireEvent.click(screen.getByTestId("chip-copy"));

    await waitFor(() =>
      expect(onCopyResult).toHaveBeenCalledWith({ status: "uid", value: UID })
    );
  });

  it("gives the copy control an accessible name that says which identity it copies", () => {
    render(<IdChip uid={UID} systemId={UUID} label="Architekturelement" testId="chip" />);

    const button = screen.getByRole("button", {
      name: "Architekturelement: System-ID kopieren",
    });
    // Interactive element → the repo-wide E2E selector convention.
    expect(button).toHaveAttribute("data-testid", "chip-copy");
  });

  it("names the uid in the accessible name when that is what would be copied", () => {
    render(<IdChip uid={UID} testId="chip" />);

    expect(
      screen.getByRole("button", { name: "Lesbare ID kopieren" })
    ).toBeInTheDocument();
  });

  it("does not clear a previous announcement before the next copy", async () => {
    // The live region is mounted unconditionally (see IdChip.tsx): mounting it
    // only while a message exists means a screen reader has nothing to observe
    // at the moment the copy happens.
    render(<IdChip uid={UID} systemId={UUID} testId="chip" />);
    const status = screen.getByTestId("chip-status");
    expect(status).toBeInTheDocument();
    expect(status).toHaveTextContent("");

    fireEvent.click(screen.getByTestId("chip-copy"));
    await waitFor(() => expect(status).toHaveTextContent("UUID kopiert"));
  });
});
