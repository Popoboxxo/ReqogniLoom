import { installBluepencilHost, resetBluepencilHost } from "./host";

/** Vendored loader URL. */
export const LOADER_SRC = "/bluepencil/latest/attach.js";
/** Vendored manifest URL. */
export const MANIFEST_URL = "/bluepencil/latest/latest.json";
/** Same-origin sidecar health endpoint. */
export const HEALTH_URL = "/bluepencil/api/health";

const ENDPOINT = "/bluepencil/api";
const LOADER_MARKER = "data-bluepencil-loader";
const ATTACH_READY_EVENT = "bp-attach-ready";
const ATTACH_ERROR_EVENT = "bp-attach-error";
const ATTACH_SETTLE_TIMEOUT_MS = 5_000;
const RETIRED_HANDLE_GUARD_MS = 30_000;

declare global {
  interface Window {
    bluepencilAttach?: {
      version?: string;
      check?: () => void | Promise<boolean>;
      destroy?: () => void;
      element?: Element | null;
      instances?: Element[];
    };
  }
}

let warnedMissingWebCrypto = false;
let lifecycleGeneration = 0;
let installPromise: Promise<boolean> | null = null;
let activeAttachRecord: AttachRecord | null = null;
let retirementBarrier: Promise<void> | null = null;
let attachReattachBlocked = false;
let retiredLayerObserver: MutationObserver | null = null;
let retiredHandleDescriptor: PropertyDescriptor | null = null;
let retiredHandleTimer: ReturnType<typeof setTimeout> | null = null;
let retiredHandleGuardActive = false;
const suppressedAttachHandles = new WeakSet<object>();

interface AttachRecord {
  readonly generation: number;
  readonly script: HTMLScriptElement;
  readonly done: Promise<void>;
  retired: boolean;
  settled: boolean;
  completionScheduled: boolean;
  completionTimer: ReturnType<typeof setTimeout> | null;
  fallbackTimer: ReturnType<typeof setTimeout> | null;
  resolveDone: () => void;
  onReady: () => void;
  onError: () => void;
  onScriptError: () => void;
}

/** Returns whether the build-time Bluepencil guard is enabled. */
export function isBluepencilEnabledByBuild(): boolean {
  return import.meta.env.VITE_BLUEPENCIL_ENABLED === "1";
}

function hasWebCrypto(): boolean {
  return typeof crypto !== "undefined" && crypto.subtle !== undefined;
}

async function currentLanguage(): Promise<"de" | "en"> {
  try {
    const { i18n } = await import("../i18n/index");
    const language = i18n.resolvedLanguage ?? i18n.language;
    return language.toLowerCase().startsWith("de") ? "de" : "en";
  } catch {
    return "en";
  }
}

function sidecarEnvironment(): string {
  const value: unknown = import.meta.env.VITE_BLUEPENCIL_ENVIRONMENT;
  return typeof value === "string" && value !== "" ? value : "dev";
}

/** Probes the optional sidecar without throwing. */
export async function probeSidecar(timeoutMs = 1500): Promise<boolean> {
  try {
    if (typeof fetch !== "function") return false;
    const signal =
      typeof AbortSignal !== "undefined" && typeof AbortSignal.timeout === "function"
        ? AbortSignal.timeout(timeoutMs)
        : undefined;
    const response = await fetch(HEALTH_URL, {
      signal,
      credentials: "same-origin",
    });
    if (!response.ok) return false;
    const body = (await response.json()) as { ok?: unknown } | null;
    return body !== null && body.ok === true;
  } catch {
    return false;
  }
}

function removeLayerNodes(): void {
  if (typeof document === "undefined") return;
  document.querySelectorAll(`script[${LOADER_MARKER}]`).forEach((node) => node.remove());
  document.querySelectorAll("bluepencil-notes").forEach((node) => node.remove());
}

function destroyAttachValue(attach: unknown): void {
  if ((typeof attach !== "object" && typeof attach !== "function") || attach === null) return;
  if (suppressedAttachHandles.has(attach)) return;
  suppressedAttachHandles.add(attach);
  const destroy = (attach as { destroy?: () => void }).destroy;
  if (typeof destroy !== "function") return;
  try {
    destroy.call(attach);
  } catch (error) {
    void error;
  }
}

function destroyAttachHandle(): void {
  if (typeof window === "undefined") return;
  destroyAttachValue(window.bluepencilAttach);
  try {
    delete window.bluepencilAttach;
  } catch (error) {
    void error;
  }
}

function resetHostSafely(): void {
  try {
    resetBluepencilHost();
  } catch (error) {
    void error;
  }
}

function endRetiredHandleGuard(): void {
  if (typeof window === "undefined") return;
  if (retiredHandleTimer !== null) clearTimeout(retiredHandleTimer);
  retiredHandleTimer = null;
  const descriptor = retiredHandleDescriptor;
  retiredHandleDescriptor = null;
  retiredHandleGuardActive = false;
  try {
    if (descriptor === null) delete window.bluepencilAttach;
    else Object.defineProperty(window, "bluepencilAttach", descriptor);
  } catch (error) {
    void error;
  }
}

function guardRetiredHandleAssignments(): void {
  if (typeof window === "undefined" || retiredHandleGuardActive) return;
  retiredHandleDescriptor = Object.getOwnPropertyDescriptor(window, "bluepencilAttach") ?? null;
  retiredHandleGuardActive = true;
  try {
    Object.defineProperty(window, "bluepencilAttach", {
      configurable: true,
      get: () => undefined,
      set: (value: unknown) => {
        destroyAttachValue(value);
      },
    });
  } catch (error) {
    void error;
    retiredHandleDescriptor = null;
    retiredHandleGuardActive = false;
    return;
  }
  retiredHandleTimer = setTimeout(endRetiredHandleGuard, RETIRED_HANDLE_GUARD_MS);
}

function observeRetiredLayer(): void {
  if (retiredLayerObserver !== null || typeof MutationObserver === "undefined") return;
  retiredLayerObserver = new MutationObserver(() => {
    if (document.querySelector("bluepencil-notes") === null) return;
    removeLayerNodes();
    destroyAttachHandle();
  });
  retiredLayerObserver.observe(document.documentElement, { childList: true, subtree: true });
}

function blockReattachAfterTimeout(): void {
  attachReattachBlocked = true;
  guardRetiredHandleAssignments();
  observeRetiredLayer();
}

function finishAttachRecord(record: AttachRecord): void {
  if (record.settled) return;
  record.settled = true;
  if (record.completionTimer !== null) clearTimeout(record.completionTimer);
  if (record.fallbackTimer !== null) clearTimeout(record.fallbackTimer);
  document.removeEventListener(ATTACH_READY_EVENT, record.onReady);
  document.removeEventListener(ATTACH_ERROR_EVENT, record.onError);
  record.script.removeEventListener("error", record.onScriptError);
  if (activeAttachRecord === record) activeAttachRecord = null;
  if (record.retired) {
    removeLayerNodes();
    destroyAttachHandle();
  }
  if (retirementBarrier === record.done) retirementBarrier = null;
  record.resolveDone();
}

function scheduleAttachCompletion(record: AttachRecord): void {
  if (record.generation !== lifecycleGeneration) record.retired = true;
  if (record.settled || record.completionScheduled) return;
  record.completionScheduled = true;
  record.completionTimer = setTimeout(() => finishAttachRecord(record), 0);
}

function createAttachRecord(script: HTMLScriptElement, generation: number): AttachRecord {
  let resolveDone!: () => void;
  const done = new Promise<void>((resolve) => {
    resolveDone = resolve;
  });
  const record: AttachRecord = {
    generation,
    script,
    done,
    retired: false,
    settled: false,
    completionScheduled: false,
    completionTimer: null,
    fallbackTimer: null,
    resolveDone,
    onReady: () => undefined,
    onError: () => undefined,
    onScriptError: () => undefined,
  };
  record.onReady = () => scheduleAttachCompletion(record);
  record.onError = () => {
    record.retired = true;
    scheduleAttachCompletion(record);
  };
  record.onScriptError = record.onError;
  document.addEventListener(ATTACH_READY_EVENT, record.onReady);
  document.addEventListener(ATTACH_ERROR_EVENT, record.onError);
  script.addEventListener("error", record.onScriptError);
  activeAttachRecord = record;
  record.fallbackTimer = setTimeout(() => {
    if (record.settled) return;
    record.retired = true;
    finishAttachRecord(record);
    blockReattachAfterTimeout();
  }, ATTACH_SETTLE_TIMEOUT_MS);
  return record;
}

function appendLoaderScript(script: HTMLScriptElement, generation: number): void {
  const record = createAttachRecord(script, generation);
  try {
    (document.head ?? document.documentElement).append(script);
  } catch (error) {
    record.retired = true;
    finishAttachRecord(record);
    throw error;
  }
}

async function installBluepencilReviewLayerAt(generation: number): Promise<boolean> {
  try {
    if (attachReattachBlocked) return false;
    if (generation !== lifecycleGeneration) return false;
    if (!isBluepencilEnabledByBuild()) return false;
    if (typeof document === "undefined") return false;
    if (document.querySelector(`script[${LOADER_MARKER}]`) !== null) return false;
    if (!(await probeSidecar())) return false;
    if (
      generation !== lifecycleGeneration ||
      document.querySelector(`script[${LOADER_MARKER}]`) !== null
    ) {
      return false;
    }

    const integrity = hasWebCrypto();
    if (!integrity && !warnedMissingWebCrypto) {
      warnedMissingWebCrypto = true;
      console.warn(
        "[bluepencil] crypto.subtle is unavailable; loading without the bundle integrity check.",
      );
    }

    const language = await currentLanguage();
    if (generation !== lifecycleGeneration) return false;
    if (document.querySelector(`script[${LOADER_MARKER}]`) !== null) return false;

    installBluepencilHost();

    const script = document.createElement("script");
    script.src = LOADER_SRC;
    script.async = true;
    script.setAttribute(LOADER_MARKER, "1");
    script.setAttribute("data-endpoint", ENDPOINT);
    script.setAttribute("data-route", "url");
    script.setAttribute("data-manifest", MANIFEST_URL);
    if (integrity) script.setAttribute("data-integrity", "true");
    script.setAttribute("data-language", language);
    script.setAttribute("data-environment", sidecarEnvironment());
    script.setAttribute("data-identity", "rfBluepencil.identity");
    script.setAttribute("data-headers-from", "rfBluepencil.headers");
    script.setAttribute("data-gate", "rfBluepencil.gate");
    script.setAttribute("data-route-from", "rfBluepencil.routeFor");
    appendLoaderScript(script, generation);
    return true;
  } catch (error) {
    console.debug("[bluepencil] review layer not installed:", error);
    return false;
  }
}

/** Installs the optional review layer, sharing one in-flight attempt. */
export function installBluepencilReviewLayer(): Promise<boolean> {
  if (attachReattachBlocked) return Promise.resolve(false);
  if (installPromise !== null) return installPromise;
  const generation = lifecycleGeneration;
  const barrier = retirementBarrier;
  const promise =
    barrier === null
      ? installBluepencilReviewLayerAt(generation)
      : barrier.then(() => {
          if (attachReattachBlocked) return false;
          if (generation !== lifecycleGeneration) return false;
          return installBluepencilReviewLayerAt(generation);
        });
  installPromise = promise;
  void promise.then(
    () => {
      if (installPromise === promise) installPromise = null;
    },
    () => {
      if (installPromise === promise) installPromise = null;
    },
  );
  return promise;
}

/** Removes the layer and invalidates pending attach/install work. */
export function teardownBluepencilReviewLayer(): void {
  lifecycleGeneration += 1;
  installPromise = null;
  const record = activeAttachRecord;
  if (record !== null && !record.settled) {
    record.retired = true;
    retirementBarrier = record.done;
  }
  removeLayerNodes();
  destroyAttachHandle();
  resetHostSafely();
}
