/**
 * Measured top-band inset for the Bluepencil review layer (issue #1176).
 *
 * The layer renders a viewport-fixed top-right bar (`bp-bar`) — or, collapsed,
 * a smaller handle (`bp-handle`) — that paints above the shell's own top-right
 * primary action row, so a real mouse click on a page's "create" button lands
 * on the overlay. `styles/bluepencil.css` reserves the band by pushing the
 * shell's main region down, but the bar's height is not a constant: it wraps
 * onto a second row once the viewport narrows (observed at 1024px), so a
 * hardcoded inset under-reserves exactly at the boundary the issue cares
 * about.
 *
 * The chrome lives in the layer's own `.bp-root` subtree, which the element
 * mounts at body level (it is not a descendant of the `<bluepencil-notes>`
 * attach element), so the query is document-wide. Both chrome elements exist
 * at all times, but only one is shown — the other carries the `hidden`
 * attribute and has a zero rect, and must not win.
 *
 * This module publishes the maximum viewport bottom edge of the visible top
 * chrome as the `--review-layer-bar-bottom` custom property on `<html>`. The
 * stylesheet owns the clearance gap (`--space-4`) and the default-padding
 * floor; this module only reports runtime geometry, the same pattern as
 * `Dialog`'s `--sheet-viewport-height`.
 *
 * Lifecycle is tied to the loader: `startBluepencilInsetObserver()` is called
 * once the layer is being installed, `stopBluepencilInsetObserver()` on
 * teardown. Both are idempotent and safe when DOM APIs are unavailable (SSR,
 * jsdom without `ResizeObserver`).
 */

const CHROME_SELECTOR = ".bp-bar, .bp-handle";
const DOCKED_BOTTOM_SELECTOR = '.bp-root[data-bp-dock="bottom"]';
const INSET_PROPERTY = "--review-layer-bar-bottom";

let active = false;
let observer: MutationObserver | null = null;
let resizeObserver: ResizeObserver | null = null;
let observedChrome: Element[] = [];
let frame: number | null = null;

function rootElement(): HTMLElement | null {
  return typeof document === "undefined" ? null : document.documentElement;
}

/** All chrome elements currently in the document, visible or hidden. */
function chromeElements(): Element[] {
  return typeof document === "undefined"
    ? []
    : Array.from(document.querySelectorAll(CHROME_SELECTOR));
}

function isDockedBottom(): boolean {
  return typeof document === "undefined"
    ? false
    : document.querySelector(DOCKED_BOTTOM_SELECTOR) !== null;
}

function maxVisibleBottom(): number {
  let bottom = 0;
  for (const chrome of chromeElements()) {
    const rect = chrome.getBoundingClientRect();
    // A hidden chrome element has a zero-size rect and must not clear the
    // inset published by its visible counterpart.
    if (rect.height <= 0) continue;
    if (Number.isFinite(rect.bottom) && rect.bottom > bottom) bottom = rect.bottom;
  }
  return bottom;
}

/**
 * Publishes the visible top-chrome bottom edge, or clears the property when
 * there is no top-docked chrome to reserve space for.
 */
export function updateBluepencilInset(): void {
  const root = rootElement();
  if (root === null) return;

  const bottom = isDockedBottom() ? 0 : maxVisibleBottom();
  if (bottom > 0) {
    root.style.setProperty(INSET_PROPERTY, `${Math.ceil(bottom)}px`);
  } else {
    root.style.removeProperty(INSET_PROPERTY);
  }
}

function scheduleUpdate(): void {
  if (frame !== null) return;
  if (typeof requestAnimationFrame === "function") {
    frame = requestAnimationFrame(() => {
      frame = null;
      updateBluepencilInset();
    });
    return;
  }
  updateBluepencilInset();
}

function sameChrome(a: Element[], b: Element[]): boolean {
  return a.length === b.length && a.every((element, index) => element === b[index]);
}

/** Keeps a `ResizeObserver` on whichever chrome elements currently exist. */
function bindChrome(): void {
  const chrome = chromeElements();
  if (sameChrome(chrome, observedChrome)) return;

  if (resizeObserver !== null) {
    resizeObserver.disconnect();
    resizeObserver = null;
  }
  observedChrome = chrome;
  if (chrome.length > 0 && typeof ResizeObserver !== "undefined") {
    resizeObserver = new ResizeObserver(() => scheduleUpdate());
    for (const element of chrome) resizeObserver.observe(element);
  }
  scheduleUpdate();
}

function onMutations(): void {
  bindChrome();
  scheduleUpdate();
}

/** Starts measuring; safe to call repeatedly. */
export function startBluepencilInsetObserver(): void {
  if (active || typeof document === "undefined") return;
  active = true;

  const probeRoot = document.body ?? document.documentElement;
  if (typeof MutationObserver !== "undefined") {
    observer = new MutationObserver(onMutations);
    observer.observe(probeRoot, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["data-bp-dock", "hidden"],
    });
  }
  if (typeof window !== "undefined") window.addEventListener("resize", scheduleUpdate);
  bindChrome();
}

/** Stops measuring and removes the published inset; safe to call repeatedly. */
export function stopBluepencilInsetObserver(): void {
  active = false;
  if (observer !== null) {
    observer.disconnect();
    observer = null;
  }
  if (resizeObserver !== null) {
    resizeObserver.disconnect();
    resizeObserver = null;
  }
  if (typeof window !== "undefined") window.removeEventListener("resize", scheduleUpdate);
  if (frame !== null && typeof cancelAnimationFrame === "function") {
    cancelAnimationFrame(frame);
  }
  frame = null;
  observedChrome = [];

  const root = rootElement();
  if (root !== null) root.style.removeProperty(INSET_PROPERTY);
}
