/**
 * Vitest test setup — configures @testing-library/jest-dom matchers.
 *
 * req_id: REQ-L2-RF-010, REQ-L2-RF-004
 */
import "@testing-library/jest-dom";

// Polyfill ResizeObserver for jsdom (not implemented natively in jsdom).
// Required by CanvasEditor (COMP-RF-005, REQ-L2-DS-006) which observes
// the canvas wrapper element for resize events.
if (typeof globalThis.ResizeObserver === "undefined") {
  globalThis.ResizeObserver = class ResizeObserver {
    observe(): void {}
    unobserve(): void {}
    disconnect(): void {}
  };
}

// jsdom does not implement HTMLFormElement.prototype.requestSubmit. Dispatch a
// SubmitEvent when available so handlers can read `event.submitter`; fall back
// to a plain Event on runtimes that lack the constructor (FE-008).
if (typeof HTMLFormElement !== "undefined" && !HTMLFormElement.prototype.requestSubmit) {
  HTMLFormElement.prototype.requestSubmit = function (
    this: HTMLFormElement,
    submitter?: HTMLElement | null
  ): void {
    if (!this.reportValidity()) return;
    const init = { bubbles: true, cancelable: true };
    const event =
      typeof SubmitEvent !== "undefined"
        ? new SubmitEvent("submit", { ...init, submitter: submitter ?? null })
        : Object.assign(new Event("submit", init), { submitter: submitter ?? null });
    this.dispatchEvent(event);
  };
}
