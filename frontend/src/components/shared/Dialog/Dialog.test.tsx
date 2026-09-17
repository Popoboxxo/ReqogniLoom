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

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { useRef, useState } from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
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

    // Issue #800: the close button precedes the content in DOM order but
    // carries tabIndex={-1} — a destructive, unconfirmed action must not be
    // the first (or any) Tab stop — so the first *tabbable* control is the
    // first element inside the panel content.
    expect(document.activeElement).toBe(screen.getByTestId("inner-first"));
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

    // Issue #800: the close button (tabIndex={-1}) is excluded from the
    // cycle, so wrapping lands back on the first tabbable content element.
    expect(document.activeElement).toBe(screen.getByTestId("inner-first"));
  });

  it("cycles Shift+Tab from the first element back to the last", async () => {
    const user = userEvent.setup();
    render(<DialogHost />);
    await user.click(screen.getByTestId("trigger"));

    // Focus already sits on the first tabbable element (the close button
    // is excluded from the cycle — issue #800).
    await user.tab({ shift: true });

    expect(document.activeElement).toBe(screen.getByTestId("inner-last"));
  });

  it("keeps focus inside when it is moved to the page behind", async () => {
    const user = userEvent.setup();
    render(<DialogHost />);
    await user.click(screen.getByTestId("trigger"));

    screen.getByTestId("outside-button").focus();

    // Issue #800: the safety net re-runs focusInitial(), which now lands on
    // the first tabbable content element, not the (tabIndex={-1}) close
    // button.
    expect(document.activeElement).toBe(screen.getByTestId("inner-first"));
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

  it("keeps focus on a controlled input while typing, even with a fresh inline onClose every render", async () => {
    // Regression test for the bug where the focus-trap setup effect
    // depended on `onEscape` (== the caller's `onClose`) by identity.
    // `onClose={() => setShowX(false)}` — a very common inline arrow at
    // Dialog call sites — gets a new identity on every render of the
    // parent. Typing into a controlled input inside the dialog re-renders
    // the parent on every keystroke, so before the fix the effect tore
    // down and re-ran `focusInitial()` each time, yanking focus back to
    // the dialog's first focusable element (the close button) mid-word.
    function HostWithControlledInput(): JSX.Element {
      const [open, setOpen] = useState(true);
      const [value, setValue] = useState("");
      if (!open) return <div data-testid="closed" />;
      return (
        // Inline arrow on purpose: a fresh function identity every render.
        <Dialog title="Neu anlegen" onClose={() => setOpen(false)}>
          <input
            data-testid="title-input"
            value={value}
            onChange={(event) => setValue(event.target.value)}
          />
        </Dialog>
      );
    }

    const user = userEvent.setup();
    render(<HostWithControlledInput />);

    const input = screen.getByTestId("title-input");
    input.focus();
    expect(document.activeElement).toBe(input);

    await user.keyboard("Hello");

    expect(input).toHaveValue("Hello");
    expect(document.activeElement).toBe(input);
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

// ---------------------------------------------------------------------------
// Bottom sheet on smartphones — issue #874
// ---------------------------------------------------------------------------
//
// The sheet *shape* is CSS only, so it is asserted against the stylesheet's
// source the same way `src/test/ui-ratchet.test.ts` asserts its structural
// rules: jsdom applies no stylesheets, so there is no rendered geometry to
// query here, but the contract that matters — "below 640px this moves to the
// bottom, above it nothing changes" — is exactly a difference between two
// text regions of one file. The JavaScript half (gesture + viewport mirror)
// is exercised normally, through the DOM.

const DIALOG_CSS = readFileSync(join(__dirname, "Dialog.module.css"), "utf-8");
const TOKENS_CSS = readFileSync(
  join(__dirname, "..", "..", "..", "styles", "tokens.css"),
  "utf-8",
);

/** The one query that switches the primitive from modal to bottom sheet. */
const SHEET_QUERY = "@media (max-width: 640px) {";
const [MODAL_CSS, SHEET_CSS] = DIALOG_CSS.split(SHEET_QUERY);

/**
 * jsdom ships no `PointerEvent` (hence no `clientY` on the event testing-library
 * would synthesise), so pointer gestures are only testable with a minimal
 * MouseEvent-backed stand-in — `MouseEvent` is what carries the coordinates.
 */
interface PointerEventInitLike extends MouseEventInit {
  pointerId?: number;
  pointerType?: string;
}

class TestPointerEvent
  extends MouseEvent
  implements Pick<PointerEvent, "pointerId" | "pointerType">
{
  readonly pointerId: number;
  readonly pointerType: string;

  constructor(type: string, init: PointerEventInitLike = {}) {
    super(type, init);
    this.pointerId = init.pointerId ?? 1;
    this.pointerType = init.pointerType ?? "touch";
  }
}

/** Drag the grabber from `from` through `waypoints` and release. */
function dragHandle(
  handle: HTMLElement,
  from: number,
  ...waypoints: number[]
): void {
  fireEvent.pointerDown(handle, { clientY: from, pointerId: 1 });
  for (const clientY of waypoints) {
    fireEvent.pointerMove(handle, { clientY, pointerId: 1 });
  }
  fireEvent.pointerUp(handle, {
    clientY: waypoints[waypoints.length - 1] ?? from,
    pointerId: 1,
  });
}

interface VisualViewportStub {
  height: number;
  addEventListener: (type: string, listener: () => void) => void;
  removeEventListener: (type: string, listener: () => void) => void;
}

/** Installs a `window.visualViewport` stand-in and returns its listener count. */
function installVisualViewport(height: number, innerHeight: number) {
  const listeners = new Set<() => void>();
  const viewport: VisualViewportStub = {
    height,
    addEventListener: (_type, listener) => {
      listeners.add(listener);
    },
    removeEventListener: (_type, listener) => {
      listeners.delete(listener);
    },
  };
  Object.defineProperty(window, "visualViewport", {
    value: viewport,
    configurable: true,
    writable: true,
  });
  Object.defineProperty(window, "innerHeight", {
    value: innerHeight,
    configurable: true,
    writable: true,
  });
  return {
    listeners,
    resize: (nextHeight: number): void => {
      viewport.height = nextHeight;
      for (const listener of listeners) listener();
    },
  };
}

describe("<Dialog> — bottom sheet on smartphones (issue #874)", () => {
  beforeEach(() => {
    Object.defineProperty(window, "PointerEvent", {
      value: TestPointerEvent,
      configurable: true,
      writable: true,
    });
  });

  afterEach(() => {
    Reflect.deleteProperty(window, "PointerEvent");
    Reflect.deleteProperty(window, "visualViewport");
  });

  it("keeps the centred modal above the sheet breakpoint", () => {
    // The split is only meaningful while the stylesheet has exactly one sheet
    // query; a second one would silently move rules between the two halves.
    expect(SHEET_CSS).toBeTruthy();
    expect(MODAL_CSS).toContain("align-items: center");
    expect(MODAL_CSS).toContain("border-radius: var(--radius-lg);");
    // ...and nothing in the modal half may anchor to the bottom or reserve
    // keyboard space.
    expect(MODAL_CSS).not.toContain("align-items: flex-end");
    expect(MODAL_CSS).not.toContain("--sheet-keyboard-inset");
    expect(MODAL_CSS).toMatch(/\.handle\s*\{[^}]*display: none/);
  });

  it("anchors the panel to the bottom edge, full-bleed and top-rounded", () => {
    expect(SHEET_CSS).toContain("align-items: flex-end");
    expect(SHEET_CSS).toContain("padding: 0;");
    expect(SHEET_CSS).toContain(
      "border-radius: var(--radius-lg) var(--radius-lg) 0 0;",
    );
    expect(SHEET_CSS).toMatch(/\.handle\s*\{[^}]*display: block/);
  });

  it("caps the sheet at 90dvh of the live visual viewport and scrolls its body", () => {
    // 90dvh cap (DoD 1) + the visualViewport height (DoD 3), whichever is
    // smaller, and the keyboard inset pushing the sheet up.
    expect(SHEET_CSS).toContain(
      "max-height: min(var(--sheet-max-height), var(--sheet-viewport-height));",
    );
    expect(SHEET_CSS).toContain("margin-bottom: var(--sheet-keyboard-inset);");
    // Safe-area padding keeps the footer's buttons off the home indicator.
    expect(SHEET_CSS).toContain("env(safe-area-inset-bottom, 0px)");
    // The content is the single scrolling region: pinned header/footer above
    // and below it, and `min-height: 0` so a long body scrolls instead of
    // stretching the panel.
    expect(SHEET_CSS).toMatch(/\.content\s*\{[^}]*flex: 1 1 auto;/);
    expect(SHEET_CSS).toMatch(/\.content\s*\{[^}]*min-height: 0;/);
  });

  it("sizes the sheet from tokens instead of hardcoded values", () => {
    // 40x4px grabber per the issue's DoD, 90dvh cap, plus the two runtime
    // defaults the CSS falls back to when `visualViewport` is unavailable.
    expect(TOKENS_CSS).toContain("--sheet-handle-width: 40px;");
    expect(TOKENS_CSS).toContain("--sheet-handle-height: 4px;");
    expect(TOKENS_CSS).toContain("--sheet-max-height: 90dvh;");
    expect(TOKENS_CSS).toContain("--sheet-viewport-height: 100dvh;");
    expect(TOKENS_CSS).toContain("--sheet-keyboard-inset: 0px;");
  });

  it("renders the grabber as a decorative, non-focusable affordance", async () => {
    const user = userEvent.setup();
    render(<DialogHost />);
    await user.click(screen.getByTestId("trigger"));

    const handle = screen.getByTestId("dialog-handle");
    expect(handle).toHaveAttribute("aria-hidden", "true");
    expect(handle).not.toHaveAttribute("tabindex");
    expect(handle.className).toContain("handle");
    // #800/#954 contract: the extra element must not become the focus target.
    expect(document.activeElement).toBe(screen.getByTestId("inner-first"));
  });

  it("dismisses the sheet when the handle is dragged down past the threshold", async () => {
    const user = userEvent.setup();
    render(<DialogHost />);
    await user.click(screen.getByTestId("trigger"));

    dragHandle(screen.getByTestId("dialog-handle"), 100, 164);

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("keeps the sheet open on a short drag", async () => {
    const user = userEvent.setup();
    render(<DialogHost />);
    await user.click(screen.getByTestId("trigger"));

    dragHandle(screen.getByTestId("dialog-handle"), 100, 130);

    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("evaluates the drag on release, so pulling the sheet back up keeps it open", async () => {
    const user = userEvent.setup();
    render(<DialogHost />);
    await user.click(screen.getByTestId("trigger"));

    // Down past the threshold, then back up before letting go.
    dragHandle(screen.getByTestId("dialog-handle"), 100, 220, 110);

    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("ignores an upward drag", async () => {
    const user = userEvent.setup();
    render(<DialogHost />);
    await user.click(screen.getByTestId("trigger"));

    dragHandle(screen.getByTestId("dialog-handle"), 200, 40);

    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("does not let a swipe dismiss a dialog that must not be dismissed", async () => {
    const user = userEvent.setup();
    render(<DialogHost closeOnBackdropClick={false} />);
    await user.click(screen.getByTestId("trigger"));

    dragHandle(screen.getByTestId("dialog-handle"), 100, 400);

    // Same dismissibility decision as Escape and the backdrop (#800/UI-24).
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("publishes the visual viewport as CSS custom properties (keyboard compensation)", () => {
    const viewport = installVisualViewport(500, 800);

    render(
      <Dialog title="Titel" onClose={vi.fn()}>
        <button type="button">Knopf</button>
      </Dialog>,
    );

    const panel = screen.getByTestId("dialog");
    expect(panel.style.getPropertyValue("--sheet-viewport-height")).toBe(
      "500px",
    );
    // 800px layout viewport - 500px visible = a 300px keyboard.
    expect(panel.style.getPropertyValue("--sheet-keyboard-inset")).toBe("300px");

    viewport.resize(620);
    expect(panel.style.getPropertyValue("--sheet-viewport-height")).toBe(
      "620px",
    );
    expect(panel.style.getPropertyValue("--sheet-keyboard-inset")).toBe("180px");
  });

  it("drops the viewport properties and its listener on unmount", () => {
    const viewport = installVisualViewport(500, 800);

    const { unmount } = render(
      <Dialog title="Titel" onClose={vi.fn()}>
        <button type="button">Knopf</button>
      </Dialog>,
    );
    const panel = screen.getByTestId("dialog");
    expect(viewport.listeners.size).toBe(1);

    unmount();

    expect(viewport.listeners.size).toBe(0);
    expect(panel.style.getPropertyValue("--sheet-viewport-height")).toBe("");
    expect(panel.style.getPropertyValue("--sheet-keyboard-inset")).toBe("");
  });

  it("stays a no-op where visualViewport does not exist", () => {
    expect(window.visualViewport).toBeUndefined();

    render(
      <Dialog title="Titel" onClose={vi.fn()}>
        <button type="button">Knopf</button>
      </Dialog>,
    );

    const panel = screen.getByTestId("dialog");
    expect(panel.style.getPropertyValue("--sheet-viewport-height")).toBe("");
    expect(panel.style.getPropertyValue("--sheet-keyboard-inset")).toBe("");
  });
});
