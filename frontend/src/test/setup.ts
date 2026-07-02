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
