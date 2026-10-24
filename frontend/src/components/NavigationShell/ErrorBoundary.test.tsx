/**
 * ErrorBoundary — #598 W4a regression guard.
 *
 * The boundary used to render `error.message` verbatim, which leaks hostnames,
 * user names and driver output into the UI. These tests pin the fix: a neutral
 * hint plus a reference id, with the raw message confined to the console.
 *
 * Deliberately a real render (no component mock) — the leak lived in `render`,
 * so a shallow test could not have caught it.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { resolveLocaleKey } from "../../test/i18n-test-helpers";
import { ErrorBoundary } from "./ErrorBoundary";

/** Contains a credential and an internal host — both must never reach the DOM. */
const LEAKY_MESSAGE =
  "FATAL: password authentication failed for user reqogniloom at 10.0.0.5";

const REFERENCE_TEXT = /^Referenz: [a-z0-9]+-[a-z0-9]{6}$/;
const REFERENCE_ID = /^[a-z0-9]+-[a-z0-9]{6}$/;

function translate(key: string): string {
  return resolveLocaleKey(key) ?? key;
}

/** Mirrors how NavigationShell wires the boundary, using the real German copy. */
function renderBoundary(children: ReactNode) {
  return render(
    <ErrorBoundary
      errorTitle={translate("errors.generic")}
      reloadLabel={translate("actions.reload")}
      backLabel={translate("actions.back")}
      hintLabel={translate("errors.boundaryHint")}
      referenceLabel={translate("errors.reference")}
    >
      {children}
    </ErrorBoundary>
  );
}

/**
 * A child that throws while `control.armed` is true. The component identity is
 * created once per test (not per render), so the boundary's recovery render
 * reconciles the same subtree instead of remounting a fresh one.
 */
function makeBomb(control: { armed: boolean }) {
  return function Bomb() {
    if (control.armed) {
      throw new Error(LEAKY_MESSAGE);
    }
    return <div data-testid="recovered">recovered</div>;
  };
}

describe("ErrorBoundary", () => {
  let errorSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    // React also logs the caught error; silence the whole channel so the test
    // output stays readable and the assertions below own the call inspection.
    errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("never renders the raw error message", () => {
    const Bomb = makeBomb({ armed: true });

    renderBoundary(<Bomb />);

    expect(screen.queryByText(/password/i)).toBeNull();
    expect(screen.queryByText(/10\.0\.0\.5/)).toBeNull();
    expect(screen.queryByText(/FATAL/i)).toBeNull();
    // Sanity check that the boundary itself rendered: the neutral hint is there.
    expect(screen.getByText(translate("errors.boundaryHint"))).toBeInTheDocument();
  });

  it("shows a localised reference id", () => {
    const Bomb = makeBomb({ armed: true });

    renderBoundary(<Bomb />);

    expect(screen.getByTestId("error-reference")).toHaveTextContent(REFERENCE_TEXT);
  });

  it("logs the displayed reference id alongside the error", () => {
    const Bomb = makeBomb({ armed: true });

    renderBoundary(<Bomb />);

    const shownReference =
      screen.getByTestId("error-reference").querySelector("code")?.textContent ?? "";
    expect(shownReference).toMatch(REFERENCE_ID);

    const boundaryCall = errorSpy.mock.calls.find(
      ([message]) => message === "[ErrorBoundary] Unhandled error"
    );
    expect(boundaryCall).toBeDefined();
    expect(boundaryCall?.[1]).toEqual({ referenceId: shownReference });
    expect(boundaryCall?.[2]).toBeInstanceOf(Error);
  });

  it("recovers and keeps its back action wired", () => {
    const control = { armed: true };
    const Bomb = makeBomb(control);
    const backSpy = vi.spyOn(window.history, "back").mockImplementation(() => {});

    renderBoundary(<Bomb />);
    expect(screen.queryByTestId("recovered")).toBeNull();

    control.armed = false;
    fireEvent.click(screen.getByTestId("error-back-btn"));

    expect(screen.getByTestId("recovered")).toBeInTheDocument();
    expect(backSpy).toHaveBeenCalledTimes(1);
  });
});
