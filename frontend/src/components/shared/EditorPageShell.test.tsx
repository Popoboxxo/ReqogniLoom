/**
 * EditorPageShell (F-15) — the shared create-dialog scaffold.
 *
 * The four consumer routes (`Adr/Risk/Issue/TestCaseEditors`) are covered as one
 * class by `AdrEditors.save-shortcut.test.tsx` and the per-page editor suites.
 * This file pins the shell's own contract at the unit level, in particular the
 * two behaviours that were extracted verbatim from the pages and must not
 * drift:
 *   - the `role="alert"` error with the host-supplied CSS-module class,
 *   - the synchronous same-tick submit guard that the Create button and the
 *     `Ctrl`/`Cmd`+`S` chord both funnel through (FR-U5-01).
 */

import React from "react";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: unknown) =>
      typeof fallback === "string" ? fallback : key,
    i18n: { language: "de" },
  }),
}));

import { EditorPageShell } from "./EditorPageShell";
import type { EditorPageShellProps } from "./EditorPageShell";

function renderShell(overrides: Partial<EditorPageShellProps> = {}): {
  props: EditorPageShellProps;
  rerender: (next: Partial<EditorPageShellProps>) => void;
} {
  const props: EditorPageShellProps = {
    open: true,
    title: "New Thing",
    testId: "thing-create-dialog",
    formId: "thing-create-form",
    onClose: vi.fn(),
    onSubmit: vi.fn(),
    isSaving: false,
    canSave: true,
    cancelTestId: "thing-create-cancel-btn",
    saveTestId: "thing-new-save-btn",
    error: null,
    errorClassName: "host-error",
    children: <input data-testid="thing-new-title-input" defaultValue="" />,
    ...overrides,
  };
  const view = render(<EditorPageShell {...props} />);
  return {
    props,
    rerender: (next) =>
      view.rerender(<EditorPageShell {...props} {...next} />),
  };
}

describe("EditorPageShell", () => {
  it("renders nothing while closed", () => {
    renderShell({ open: false });

    expect(screen.queryByTestId("thing-create-dialog")).not.toBeInTheDocument();
  });

  it("renders the shared Dialog, the form and the children while open", () => {
    renderShell();

    const dialog = screen.getByTestId("thing-create-dialog");
    expect(dialog).toHaveAttribute("role", "dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(screen.getByRole("heading", { name: "New Thing" })).toBeInTheDocument();
    expect(screen.getByTestId("thing-new-title-input")).toBeInTheDocument();
    // The submit control targets the form by id.
    expect(screen.getByTestId("thing-new-save-btn")).toHaveAttribute(
      "form",
      "thing-create-form",
    );
  });

  it("cancels through the Cancel button", async () => {
    const { props } = renderShell();
    const user = userEvent.setup();

    await user.click(screen.getByTestId("thing-create-cancel-btn"));

    expect(props.onClose).toHaveBeenCalledTimes(1);
  });

  it("advertises the save chord and mirrors the canSave / isSaving gate", () => {
    const { rerender } = renderShell();

    const save = screen.getByTestId("thing-new-save-btn");
    expect(save).toHaveClass("btn-primary");
    expect(save).toHaveAttribute("aria-keyshortcuts", "Control+S Meta+S");
    expect(save).toBeEnabled();

    rerender({ canSave: false });
    expect(screen.getByTestId("thing-new-save-btn")).toBeDisabled();

    rerender({ canSave: true, isSaving: true });
    expect(screen.getByTestId("thing-new-save-btn")).toBeDisabled();
    expect(screen.getByTestId("thing-create-cancel-btn")).toBeDisabled();
  });

  it("submits once through the Create button", async () => {
    const { props } = renderShell();
    const user = userEvent.setup();

    await user.click(screen.getByTestId("thing-new-save-btn"));

    await waitFor(() => expect(props.onSubmit).toHaveBeenCalledTimes(1));
  });

  it("does not double-submit when two triggers land in one tick (FR-U5-01)", async () => {
    // A never-resolving submit keeps `isSaving` false in the same turn, so only
    // the synchronous guard can swallow the second click.
    let resolve: () => void = () => {};
    const onSubmit = vi.fn(
      () =>
        new Promise<void>((r) => {
          resolve = r;
        }),
    );
    renderShell({ onSubmit });

    const save = screen.getByTestId("thing-new-save-btn");
    await act(async () => {
      save.click();
      save.click();
    });

    expect(onSubmit).toHaveBeenCalledTimes(1);
    await act(async () => resolve());
  });

  it("runs the page's create path from the Ctrl/Cmd+S chord", async () => {
    const { props } = renderShell();
    // Let the document-level listener attach before the chord.
    await act(async () => {});

    act(() => {
      document.dispatchEvent(
        new KeyboardEvent("keydown", {
          key: "s",
          code: "KeyS",
          ctrlKey: true,
          bubbles: true,
          cancelable: true,
        }),
      );
    });

    await waitFor(() => expect(props.onSubmit).toHaveBeenCalledTimes(1));
  });

  it("renders the error as a role=alert with the host-supplied class", () => {
    renderShell({ error: "Title is required" });

    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("Title is required");
    expect(alert).toHaveClass("host-error");
  });

  it("renders no alert without an error", () => {
    renderShell();

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
