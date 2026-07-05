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

// jsdom does not implement HTMLFormElement.prototype.requestSubmit
if (typeof HTMLFormElement !== "undefined" && !HTMLFormElement.prototype.requestSubmit) {
  HTMLFormElement.prototype.requestSubmit = function () {
    if (this.reportValidity()) {
      this.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    }
  };
}
