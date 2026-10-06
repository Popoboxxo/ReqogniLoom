/**
 * Measured top-band inset for the Bluepencil layer (issue #1176).
 *
 * `inset.ts` publishes the viewport bottom of the layer's *visible* top chrome
 * as `--review-layer-bar-bottom` on `<html>`. jsdom has no layout, so geometry
 * is stubbed; the point of these tests is the publish/clear contract and the
 * hidden-chrome / docked-bottom exclusions — the actual overlap is a browser
 * check.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  startBluepencilInsetObserver,
  stopBluepencilInsetObserver,
  updateBluepencilInset,
} from "../bluepencil/inset";

const PROPERTY = "--review-layer-bar-bottom";

interface ChromeSpec {
  className: "bp-bar" | "bp-handle";
  bottom: number;
  height: number;
  hidden?: boolean;
}

interface MountOptions {
  dock?: "top" | "bottom";
  chrome: ChromeSpec[];
}

/** Appends a chrome element with a stubbed rect, in the given order. */
function appendChrome(parent: Element, spec: ChromeSpec): HTMLElement {
  const element = document.createElement("div");
  element.className = spec.className;
  if (spec.hidden === true) element.setAttribute("hidden", "");
  vi.spyOn(element, "getBoundingClientRect").mockReturnValue({
    bottom: spec.bottom,
    height: spec.height,
  } as DOMRect);
  parent.appendChild(element);
  return element;
}

/** Builds the light-DOM shape the vendored layer mounts: the attach element
 * plus the element's own `.bp-root` chrome, both at body level. */
function mountChrome({ dock = "top", chrome }: MountOptions): void {
  document.body.innerHTML = "";
  document.body.appendChild(document.createElement("bluepencil-notes"));
  const root = document.createElement("div");
  root.className = "bp-root";
  root.setAttribute("data-bp-dock", dock);
  document.body.appendChild(root);
  for (const spec of chrome) appendChrome(root, spec);
}

function inset(): string {
  return document.documentElement.style.getPropertyValue(PROPERTY);
}

/** Settles the module's `requestAnimationFrame` scheduling. */
async function flushFrame(): Promise<void> {
  await new Promise<void>((resolve) => {
    if (typeof requestAnimationFrame === "function") {
      requestAnimationFrame(() => resolve());
      return;
    }
    setTimeout(resolve, 0);
  });
}

afterEach(() => {
  stopBluepencilInsetObserver();
  document.body.innerHTML = "";
  document.documentElement.style.removeProperty(PROPERTY);
  vi.restoreAllMocks();
});

describe("bluepencil measured top-band inset (#1176)", () => {
  it("publishes the rounded bottom edge of the visible bar", () => {
    mountChrome({ chrome: [{ className: "bp-bar", bottom: 78.2, height: 29 }] });
    updateBluepencilInset();
    expect(inset()).toBe("79px");
  });

  it("measures the collapsed handle when it is the visible chrome", () => {
    mountChrome({ chrome: [{ className: "bp-handle", bottom: 40, height: 24 }] });
    updateBluepencilInset();
    expect(inset()).toBe("40px");
  });

  it("ignores the hidden chrome element rendered alongside the visible one", () => {
    // The layer keeps BOTH in the DOM: the collapsed handle precedes the bar,
    // but carries `hidden` (zero rect) while the bar is expanded. Selecting it
    // by document order would clear the inset and resurrect the overlap.
    mountChrome({
      chrome: [
        { className: "bp-handle", bottom: 0, height: 0, hidden: true },
        { className: "bp-bar", bottom: 76, height: 29 },
      ],
    });
    updateBluepencilInset();
    expect(inset()).toBe("76px");
  });

  it("clears the inset for bottom-docked chrome", () => {
    mountChrome({
      dock: "bottom",
      chrome: [{ className: "bp-bar", bottom: 800, height: 29 }],
    });
    document.documentElement.style.setProperty(PROPERTY, "80px");
    updateBluepencilInset();
    expect(inset()).toBe("");
  });

  it("clears the inset when the layer is absent", () => {
    document.body.innerHTML = "";
    document.documentElement.style.setProperty(PROPERTY, "80px");
    updateBluepencilInset();
    expect(inset()).toBe("");
  });

  it("clears the inset when every chrome element is hidden", () => {
    mountChrome({ chrome: [{ className: "bp-bar", bottom: 0, height: 0, hidden: true }] });
    document.documentElement.style.setProperty(PROPERTY, "80px");
    updateBluepencilInset();
    expect(inset()).toBe("");
  });

  it("publishes on start and clears on stop", async () => {
    mountChrome({ chrome: [{ className: "bp-bar", bottom: 80, height: 29 }] });
    startBluepencilInsetObserver();
    await flushFrame();
    expect(inset()).toBe("80px");

    stopBluepencilInsetObserver();
    expect(inset()).toBe("");
  });
});
