/**
 * ImpactDrawer — Task 10 (Schnitt 4a) unit tests.
 *
 * The drawer is the on-demand replacement for the permanent Impact column on
 * /traceability. It is a REAL modal (`role=dialog`, `aria-modal`), reusing the
 * shared `useFocusTrap` primitive: Escape closes, focus returns to the trigger,
 * and Tab cycles inside. Unlike the trace-footer station popover (non-modal)
 * this overlay deliberately takes focus away from the page behind it.
 *
 * Tests are written first (RED) against the contract in
 * docs/plans/2026-11-19-trace-spine-footer-plan.md §6 Task 10 / §3.5.
 */

import { useRef, useState } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

// The drawer calls useTranslation for its own labels; keep the tests independent
// of a real i18n instance (same minimal stand-in as TraceabilityView.smoke.test).
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: string): string => fallback ?? key,
  }),
}));

import ImpactDrawer from "./ImpactDrawer";
import type { ImpactPreset } from "../ImpactView/impact-preset";

const PRESET: ImpactPreset = {
  id: "art-req-001",
  title: "Login must be possible",
  artifactType: "Requirement",
};

/** A trigger that mounts/unmounts the drawer, so focus-return is observable. */
function Harness({ children }: { children?: React.ReactNode }) {
  const triggerRef = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        data-testid="impact-open-btn"
        onClick={() => setOpen(true)}
      >
        Open Impact Analysis
      </button>
      {open && (
        <ImpactDrawer preset={PRESET} onClose={() => setOpen(false)} triggerRef={triggerRef}>
          {children}
        </ImpactDrawer>
      )}
    </>
  );
}

describe("ImpactDrawer (Task 10)", () => {
  it("is closed initially and opens only on trigger click", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    expect(screen.queryByTestId("impact-drawer")).not.toBeInTheDocument();

    await user.click(screen.getByTestId("impact-open-btn"));

    expect(screen.getByTestId("impact-drawer")).toBeInTheDocument();
  });

  it("has real modal dialog semantics (role, aria-modal, labelledby, testid)", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByTestId("impact-open-btn"));

    const drawer = screen.getByTestId("impact-drawer");
    expect(drawer).toHaveAttribute("role", "dialog");
    expect(drawer).toHaveAttribute("aria-modal", "true");
    expect(drawer).toHaveAttribute("data-testid", "impact-drawer");

    const labelledBy = drawer.getAttribute("aria-labelledby");
    expect(labelledBy).toBeTruthy();
    expect(document.getElementById(labelledBy!)).toHaveTextContent(/impact/i);
  });

  it("opens with the correct impact data (title, type, id)", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByTestId("impact-open-btn"));

    const data = screen.getByTestId("impact-drawer-data");
    expect(data).toHaveTextContent(PRESET.title);
    expect(data).toHaveTextContent(PRESET.artifactType);
    expect(data).toHaveTextContent(PRESET.id);
  });

  it("Escape closes the drawer and returns focus to the trigger button", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const trigger = screen.getByTestId("impact-open-btn");

    await user.click(trigger);
    expect(screen.getByTestId("impact-drawer")).toBeInTheDocument();
    // Focus has left the trigger and moved into the modal.
    expect(document.activeElement).not.toBe(trigger);

    await user.keyboard("{Escape}");

    await waitFor(() => {
      expect(screen.queryByTestId("impact-drawer")).not.toBeInTheDocument();
    });
    expect(trigger).toHaveFocus();
  });

  it("traps Tab inside the drawer while it is open", async () => {
    const user = userEvent.setup();
    render(
      <Harness>
        <button type="button" data-testid="drawer-child-btn">
          Child control
        </button>
      </Harness>
    );
    await user.click(screen.getByTestId("impact-open-btn"));

    const drawer = screen.getByTestId("impact-drawer");
    // Close button + child control are the only tab stops; cycling must never
    // leave the dialog (document.body / trigger must never take focus).
    for (let i = 0; i < 5; i += 1) {
      await user.tab();
      expect(drawer.contains(document.activeElement)).toBe(true);
    }
  });
});
