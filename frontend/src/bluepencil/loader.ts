/**
 * ARCH-L1-001 ReactFrontend — bluepencil review-layer runtime gate (issue #972).
 *
 * Option B of `docs/bluepencil-integration.md`: bluepencil runs as a
 * self-hosted sidecar and is mounted as a layer over the SPA. It is globally
 * activatable/deactivatable on two independent levels:
 *
 *   1. build guard   — only an explicit `VITE_BLUEPENCIL_ENABLED="1"` arms the
 *                      layer; unset means it never probes and never loads;
 *   2. runtime probe — with the guard armed, the layer is injected only when the
 *                      sidecar answers its `/health` endpoint, so a down sidecar
 *                      degrades to "no review layer" instead of broken UI.
 *
 * Everything here is best-effort: a review layer must never break or delay the
 * host app, so every failure degrades to `false` plus a single debug line.
 */

/** Vendored loader and manifest (see `frontend/public/bluepencil/latest/`). */
export const LOADER_SRC = "/bluepencil/latest/attach.js";
export const MANIFEST_URL = "/bluepencil/latest/latest.json";
/** Sidecar base path; the Vite dev proxy forwards it same-origin (vite.config.ts). */
export const HEALTH_URL = "/bluepencil/api/health";
/** Root-relative on purpose: same origin, so no CORS and cookies ride along. */
const ENDPOINT = "/bluepencil/api";
/** Marker attribute identifying our injected loader (idempotency + teardown). */
const LOADER_MARKER = "data-bluepencil-loader";

declare global {
  interface Window {
    /**
     * Exposed by the vendored `attach.js`. Typed loosely on purpose — the host
     * only reads `version` and calls `check()`/`destroy()`.
     */
    bluepencilAttach?: {
      version?: string;
      check?: () => void;
      destroy?: () => void;
    };
    /** Reserved for the host bridge; teardown clears it. */
    rfBluepencil?: unknown;
  }
}

/**
 * Build-time guard. The layer is strictly **opt-in**: only an explicit
 * `VITE_BLUEPENCIL_ENABLED="1"` arms the runtime probe, in every environment.
 *
 * Opt-in rather than auto-detect on purpose: the probe is a real `fetch` to
 * `/bluepencil/api/health`. Where no sidecar runs, that path answers 404/502 and
 * the browser logs it as a console error — and this repo's E2E suite asserts a
 * clean console, so an unconfigured deployment must never probe at all.
 */
export function isBluepencilEnabledByBuild(): boolean {
  return import.meta.env.VITE_BLUEPENCIL_ENABLED === "1";
}

/**
 * Map the app's current i18next language onto bluepencil's `de`/`en`.
 *
 * Imported lazily on purpose: a static import of `../i18n` would make importing
 * this module (e.g. via `AuthContext` for teardown) initialize i18n — which
 * breaks unit tests that mock `react-i18next` without its full surface. The
 * language is only needed at injection time anyway.
 */
async function currentLanguage(): Promise<"de" | "en"> {
  try {
    const { i18n } = await import("../i18n/index");
    const language = i18n.resolvedLanguage ?? i18n.language;
    return language.toLowerCase().startsWith("de") ? "de" : "en";
  } catch {
    return "en";
  }
}

/**
 * The sidecar is bound to ONE environment and refuses mismatching writes, so
 * the deployment must keep this in sync with its `BLUEPENCIL_ENVIRONMENT`.
 */
function sidecarEnvironment(): string {
  const value: unknown = import.meta.env.VITE_BLUEPENCIL_ENVIRONMENT;
  return typeof value === "string" && value !== "" ? value : "dev";
}

/**
 * Asks the sidecar whether it is alive. Never throws: a timeout, a network
 * error, a non-2xx status or a body without `ok: true` all mean "not there".
 */
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

/**
 * The single entry point. Fire-and-forget from bootstrap — never awaited before
 * render. Returns `true` only when a loader script was actually injected.
 */
export async function installBluepencilReviewLayer(): Promise<boolean> {
  try {
    if (!isBluepencilEnabledByBuild()) return false;
    if (typeof document === "undefined") return false;
    if (document.querySelector(`script[${LOADER_MARKER}]`) !== null) return false;
    if (!(await probeSidecar())) return false;
    // The probe is async: a concurrent caller may have injected while we waited.
    if (document.querySelector(`script[${LOADER_MARKER}]`) !== null) return false;

    const script = document.createElement("script");
    script.src = LOADER_SRC;
    script.async = true;
    script.setAttribute(LOADER_MARKER, "1");
    script.setAttribute("data-endpoint", ENDPOINT);
    // `route="url"` is the SPA-correct store key: pathname + search.
    script.setAttribute("data-route", "url");
    script.setAttribute("data-manifest", MANIFEST_URL);
    script.setAttribute("data-integrity", "true");
    script.setAttribute("data-language", await currentLanguage());
    script.setAttribute("data-environment", sidecarEnvironment());
    // Deliberately NOT set (bluepencil defaults are already correct for this
    // repo): `data-anchor-hooks` (`data-bluepencil,data-testid`) and
    // `data-version` (the manifest is the single source of the version).
    document.head.append(script);
    return true;
  } catch (error) {
    // Never surface into the host app; a missing layer is the safe default.
    console.debug("[bluepencil] review layer not installed:", error);
    return false;
  }
}

/**
 * Removes the layer again — used on logout (and safe to call any time). The
 * injected script, the mounted `<bluepencil-notes>` element and the attach
 * handle are torn down; `window.bluepencilAttach` is dropped so no stale handle
 * outlives the session. Idempotent and silent by contract.
 */
export function teardownBluepencilReviewLayer(): void {
  try {
    if (typeof document !== "undefined") {
      document.querySelectorAll(`script[${LOADER_MARKER}]`).forEach((node) => node.remove());
      document.querySelectorAll("bluepencil-notes").forEach((node) => node.remove());
    }
    if (typeof window === "undefined") return;
    const attach = window.bluepencilAttach;
    if (attach && typeof attach.destroy === "function") {
      attach.destroy();
    }
    delete window.bluepencilAttach;
    delete window.rfBluepencil;
  } catch {
    // Idempotent and silent by contract — teardown must never throw.
  }
}
