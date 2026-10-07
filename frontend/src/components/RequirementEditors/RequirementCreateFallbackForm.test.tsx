/**
 * Issue #1087 — `RequirementCreateFallbackForm` Ctrl/Cmd+S.
 *
 * This is the hand-written Requirement create form `ArtifactForm` falls back to
 * when the attribute definition cannot be loaded. The shared renderer disables
 * its own shortcut in that branch, so the fallback has to own the chord — and
 * it has to advertise it on the save control (a11y, #1100).
 */

import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: string) => fallback ?? key,
    i18n: { language: "de" },
  }),
}));

import { RequirementCreateFallbackForm } from "./RequirementCreateFallbackForm";

function baseProps() {
  return {
    title: "Neue Anforderung",
    description: "",
    category: "",
    createError: null,
    isCreating: false,
    onTitleChange: vi.fn(),
    onDescriptionChange: vi.fn(),
    onCategoryChange: vi.fn(),
    onSubmit: vi.fn(),
    onCancel: vi.fn(),
    focusTitle: vi.fn(),
  };
}

async function pressCtrlS(): Promise<KeyboardEvent> {
  // Drain the passive effect that attaches the document listener.
  await act(async () => {});
  const event = new KeyboardEvent("keydown", {
    key: "s",
    code: "KeyS",
    ctrlKey: true,
    bubbles: true,
    cancelable: true,
  });
  act(() => {
    document.dispatchEvent(event);
  });
  return event;
}

describe("RequirementCreateFallbackForm Ctrl/Cmd+S (#1087)", () => {
  it("saves through the shortcut and prevents the browser default", async () => {
    const props = baseProps();
    render(<RequirementCreateFallbackForm {...props} />);

    const event = await pressCtrlS();

    expect(props.onSubmit).toHaveBeenCalledTimes(1);
    // Without this the browser's own "Save page as…" opens over the draft.
    expect(event.defaultPrevented).toBe(true);
  });

  it("does not submit an empty required title, but still swallows the chord (#1100)", async () => {
    const props = { ...baseProps(), title: "" };
    render(<RequirementCreateFallbackForm {...props} />);

    const event = await pressCtrlS();

    // The form's own submit path would early-return silently; the shortcut
    // must not call it at all (WCAG 3.3.1). The browser dialog stays suppressed.
    expect(props.onSubmit).not.toHaveBeenCalled();
    expect(event.defaultPrevented).toBe(true);
  });

  it("advertises the binding on the save control", () => {
    render(<RequirementCreateFallbackForm {...baseProps()} />);

    const save = screen.getByTestId("req-new-save-btn");
    expect(save).toHaveAttribute("aria-keyshortcuts", "Control+S Meta+S");
    expect(save).toHaveAttribute("title", "Speichern (Strg/Cmd+S)");
  });

  it("uses the form's own submit path for the button too", () => {
    const props = baseProps();
    render(<RequirementCreateFallbackForm {...props} />);

    fireEvent.submit(screen.getByTestId("create-req-form"));

    expect(props.onSubmit).toHaveBeenCalledTimes(1);
  });
});
