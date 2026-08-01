/**
 * <Dialog> + useFocusTrap unit tests — UI concept ch. 12.8.
 *
 * One test per obligation of the contract:
 *   - role="dialog" + aria-modal + aria-labelledby together
 *   - focus lands on the first operable element on open
 *   - Tab and Shift+Tab cycle inside the dialog
 *   - Escape closes
 *   - focus returns to the trigger on close
 *   - portal target is document.body
 *
 * The hook is exercised separately through a bare harness so it stays
 * usable outside <Dialog>.
 */

import { useRef, useState } from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// The shared i18next instance is not initialised in unit tests; keep the
// literal default of every t(key, default) call.
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (_key: string, fallback?: string) => fallback ?? _key,
    i18n: { language: "de", changeLanguage: vi.fn() },
  }),
}));

import { Dialog } from "./Dialog";
import { useFocusTrap, getFocusableElements } from "./use-focus-trap";

// ---------------------------------------------------------------------------
// Harness: a page with a trigger, mirroring the real open/close cycle
// ---------------------------------------------------------------------------

function DialogHost({
  onClose,
  closeOnBackdropClick,
}: {
  onClose?: () => void;
  closeOnBackdropClick?: boolean;
}): JSX.Element {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button type="button" data-testid="trigger" onClick={() => setOpen(true)}>
        Legende
      </button>
      <button type="button" data-testid="outside-button">
        Außerhalb
      </button>
      {open && (
        <Dialog
          title="Legende"
          description="Was die Farben bedeuten"
          closeOnBackdropClick={closeOnBackdropClick}
          onClose={() => {
            setOpen(false);
            onClose?.();
          }}
        >
          <button type="button" data-testid="inner-first">
            Erster
          </button>
          <button type="button" data-testid="inner-last">
            Letzter
          </button>
        </Dialog>
      )}
    </div>
  );
}

beforeEach(() => {
  document.body.style.overflow = "";
});

describe("<Dialog> — UI concept ch. 12.8", () => {
  it("carries role, aria-modal and aria-labelledby together", async () => {
    const user = userEvent.setup();
    render(<DialogHost />);
    await user.click(screen.getByTestId("trigger"));

    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");

    const labelledBy = dialog.getAttribute("aria-labelledby");
    expect(labelledBy).toBeTruthy();
    expect(document.getElementById(labelledBy as string)).toHaveTextContent(
      "Legende",
    );

    const describedBy = dialog.getAttribute("aria-describedby");
    expect(document.getElementById(describedBy as string)).toHaveTextContent(
      "Was die Farben bedeuten",
    );
  });

  it("renders into document.body, not next to its trigger", async () => {
    const user = userEvent.setup();
    const { container } = render(<DialogHost />);
    await user.click(screen.getByTestId("trigger"));

    const overlay = screen.getByTestId("dialog-overlay");
    expect(overlay.parentElement).toBe(document.body);
    expect(container.contains(overlay)).toBe(false);
  });

  it("moves focus to the first operable element on open", async () => {
    const user = userEvent.setup();
    render(<DialogHost />);
    await user.click(screen.getByTestId("trigger"));

    // The close button is the first control in the DOM order of the panel.
    expect(document.activeElement).toBe(screen.getByTestId("dialog-close"));
  });

  it("honours initialFocusRef over the first element", () => {
    function WithInitialFocus(): JSX.Element {
      const ref = useRef<HTMLInputElement | null>(null);
      return (
        <Dialog title="Titel" onClose={vi.fn()} initialFocusRef={ref}>
          <button type="button">Knopf</button>
          <input data-testid="target" ref={ref} />
        </Dialog>
      );
    }
    render(<WithInitialFocus />);
    expect(document.activeElement).toBe(screen.getByTestId("target"));
  });

  it("cycles Tab from the last element back to the first", async () => {
    const user = userEvent.setup();
    render(<DialogHost />);
    await user.click(screen.getByTestId("trigger"));

    screen.getByTestId("inner-last").focus();
    await user.tab();

    expect(document.activeElement).toBe(screen.getByTestId("dialog-close"));
  });

  it("cycles Shift+Tab from the first element back to the last", async () => {
    const user = userEvent.setup();
    render(<DialogHost />);
    await user.click(screen.getByTestId("trigger"));

    // Focus already sits on the first element (the close button).
    await user.tab({ shift: true });

    expect(document.activeElement).toBe(screen.getByTestId("inner-last"));
  });

  it("keeps focus inside when it is moved to the page behind", async () => {
    const user = userEvent.setup();
    render(<DialogHost />);
    await user.click(screen.getByTestId("trigger"));

    screen.getByTestId("outside-button").focus();

    expect(document.activeElement).toBe(screen.getByTestId("dialog-close"));
  });

  it("closes on Escape", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(<DialogHost onClose={onClose} />);
    await user.click(screen.getByTestId("trigger"));

    await user.keyboard("{Escape}");

    expect(onClose).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("returns focus to the triggering element on close", async () => {
    const user = userEvent.setup();
    render(<DialogHost />);
    const trigger = screen.getByTestId("trigger");
    await user.click(trigger);
    await user.keyboard("{Escape}");

    expect(document.activeElement).toBe(trigger);
  });

  it("closes on the close button and on a backdrop click", async () => {
    const user = userEvent.setup();
    render(<DialogHost />);

    await user.click(screen.getByTestId("trigger"));
    await user.click(screen.getByTestId("dialog-close"));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    await user.click(screen.getByTestId("trigger"));
    fireEvent.mouseDown(screen.getByTestId("dialog-overlay"));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("keeps the dialog open on a backdrop click when disabled", async () => {
    const user = userEvent.setup();
    render(<DialogHost closeOnBackdropClick={false} />);
    await user.click(screen.getByTestId("trigger"));

    fireEvent.mouseDown(screen.getByTestId("dialog-overlay"));

    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("locks page scrolling while open and restores it on close", async () => {
    const user = userEvent.setup();
    render(<DialogHost />);

    await user.click(screen.getByTestId("trigger"));
    expect(document.body.style.overflow).toBe("hidden");

    await user.keyboard("{Escape}");
    expect(document.body.style.overflow).toBe("");
  });
});

// ---------------------------------------------------------------------------
// The hook on its own — usable by any other modal overlay
// ---------------------------------------------------------------------------

function TrapHarness({
  enabled = true,
  onEscape,
  empty = false,
}: {
  enabled?: boolean;
  onEscape?: () => void;
  empty?: boolean;
}): JSX.Element {
  const ref = useRef<HTMLDivElement | null>(null);
  useFocusTrap({ containerRef: ref, enabled, onEscape });
  return (
    <div>
      <button type="button" data-testid="before">
        Davor
      </button>
      <div ref={ref} data-testid="trap" tabIndex={-1}>
        {!empty && (
          <>
            <button type="button" data-testid="a">
              A
            </button>
            <button type="button" data-testid="b" disabled>
              B (disabled)
            </button>
            <button type="button" data-testid="c">
              C
            </button>
          </>
        )}
      </div>
    </div>
  );
}

describe("useFocusTrap", () => {
  it("focuses the first focusable child on activation", () => {
    render(<TrapHarness />);
    expect(document.activeElement).toBe(screen.getByTestId("a"));
  });

  it("does nothing while disabled", () => {
    render(<TrapHarness enabled={false} />);
    expect(document.activeElement).toBe(document.body);
  });

  it("focuses the container itself when it holds no control", () => {
    render(<TrapHarness empty />);
    expect(document.activeElement).toBe(screen.getByTestId("trap"));
  });

  it("skips disabled controls when cycling", async () => {
    const user = userEvent.setup();
    render(<TrapHarness />);

    screen.getByTestId("c").focus();
    await user.tab();
    expect(document.activeElement).toBe(screen.getByTestId("a"));

    await user.tab({ shift: true });
    expect(document.activeElement).toBe(screen.getByTestId("c"));
  });

  it("reports Escape to the owner", async () => {
    const user = userEvent.setup();
    const onEscape = vi.fn();
    render(<TrapHarness onEscape={onEscape} />);

    await user.keyboard("{Escape}");

    expect(onEscape).toHaveBeenCalledTimes(1);
  });

  it("restores focus to the previously focused element on unmount", async () => {
    const user = userEvent.setup();

    function Toggle(): JSX.Element {
      const [on, setOn] = useState(false);
      return (
        <div>
          <button type="button" data-testid="opener" onClick={() => setOn(true)}>
            Auf
          </button>
          {on && <TrapHarness />}
          <button type="button" data-testid="closer" onClick={() => setOn(false)}>
            Zu
          </button>
        </div>
      );
    }

    render(<Toggle />);
    const opener = screen.getByTestId("opener");
    await user.click(opener);
    expect(document.activeElement).toBe(screen.getByTestId("a"));

    fireEvent.click(screen.getByTestId("closer"));

    expect(document.activeElement).toBe(opener);
  });

  it("getFocusableElements ignores disabled, hidden and tabindex=-1 nodes", () => {
    const container = document.createElement("div");
    container.innerHTML = `
      <button id="ok">ok</button>
      <button disabled>no</button>
      <input type="hidden" />
      <a>no href</a>
      <a id="link" href="#x">link</a>
      <div tabindex="-1">programmatic only</div>
      <div aria-hidden="true"><button>hidden subtree</button></div>
      <span tabindex="0" id="span">custom stop</span>
    `;
    document.body.appendChild(container);

    expect(getFocusableElements(container).map((el) => el.id)).toEqual([
      "ok",
      "link",
      "span",
    ]);

    container.remove();
  });
});
