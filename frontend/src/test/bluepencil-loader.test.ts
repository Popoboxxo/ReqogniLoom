/**
 * bluepencil review-layer runtime gate (issue #972).
 *
 * Covers the two independent switches from docs/bluepencil-integration.md §1/§2
 * — the build guard (`VITE_BLUEPENCIL_ENABLED`) and the sidecar health probe —
 * plus idempotency and teardown. `fetch` is stubbed throughout; no test touches
 * the network.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  HEALTH_URL,
  LOADER_SRC,
  MANIFEST_URL,
  installBluepencilReviewLayer,
  isBluepencilEnabledByBuild,
  probeSidecar,
  teardownBluepencilReviewLayer,
} from "../bluepencil/loader";
import { i18n } from "../i18n/index";

/** Stubs the loader env as on, optionally pinning the sidecar environment. */
function enableLayer(environment?: string): void {
  vi.stubEnv("VITE_BLUEPENCIL_ENABLED", "1");
  if (environment !== undefined) {
    vi.stubEnv("VITE_BLUEPENCIL_ENVIRONMENT", environment);
  }
}

/** Stubs `fetch` with a health response; returns the mock for assertions. */
function stubHealth(payload: unknown, statusOk = true): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn(
    async () =>
      ({
        ok: statusOk,
        status: statusOk ? 200 : 500,
        json: async () => payload,
      }) as unknown as Response
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

/** The injected loader scripts (our marker attribute). */
function loaderScripts(): HTMLScriptElement[] {
  return Array.from(document.querySelectorAll<HTMLScriptElement>("script[data-bluepencil-loader]"));
}

/** Full env/global/DOM reset between tests. */
function resetLayer(): void {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  teardownBluepencilReviewLayer();
}

describe("bluepencil loader — build guard", () => {
  afterEach(resetLayer);

  it("is off unless explicitly enabled — an unconfigured deployment never probes", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    expect(isBluepencilEnabledByBuild()).toBe(false);
    await expect(installBluepencilReviewLayer()).resolves.toBe(false);
    // The decisive assertion: no request, so no console error in E2E.
    expect(fetchMock).not.toHaveBeenCalled();
    expect(loaderScripts()).toHaveLength(0);
  });

  it("is hard-off and never probes when VITE_BLUEPENCIL_ENABLED=0", async () => {
    vi.stubEnv("VITE_BLUEPENCIL_ENABLED", "0");
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    await expect(installBluepencilReviewLayer()).resolves.toBe(false);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(loaderScripts()).toHaveLength(0);
  });
});

describe("bluepencil loader — health probe", () => {
  beforeEach(() => enableLayer());
  afterEach(resetLayer);

  it("probes the sidecar health endpoint same-origin", async () => {
    const fetchMock = stubHealth({ ok: true });
    await expect(probeSidecar()).resolves.toBe(true);
    expect(fetchMock).toHaveBeenCalledWith(
      HEALTH_URL,
      expect.objectContaining({ credentials: "same-origin" })
    );
  });

  it("treats a rejected fetch as a failed probe", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("offline"))));
    await expect(probeSidecar()).resolves.toBe(false);
  });

  it("treats a non-ok response as a failed probe", async () => {
    stubHealth({ ok: true }, false);
    await expect(probeSidecar()).resolves.toBe(false);
  });

  it("treats a payload without ok:true as a failed probe", async () => {
    stubHealth({ ok: false });
    await expect(probeSidecar()).resolves.toBe(false);
  });

  it("never throws when fetch is unavailable", async () => {
    vi.stubGlobal("fetch", undefined);
    await expect(probeSidecar()).resolves.toBe(false);
    await expect(installBluepencilReviewLayer()).resolves.toBe(false);
    expect(loaderScripts()).toHaveLength(0);
  });

  it("does not inject the loader when the probe fails", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("offline"))));
    await expect(installBluepencilReviewLayer()).resolves.toBe(false);
    expect(loaderScripts()).toHaveLength(0);
  });
});

describe("bluepencil loader — injection", () => {
  beforeEach(() => {
    enableLayer("staging");
    void i18n.changeLanguage("de");
    stubHealth({ ok: true });
  });
  afterEach(() => {
    resetLayer();
    void i18n.changeLanguage("en");
  });

  it("injects exactly one loader script with the documented data-* contract", async () => {
    await expect(installBluepencilReviewLayer()).resolves.toBe(true);

    const scripts = loaderScripts();
    expect(scripts).toHaveLength(1);
    const script = scripts[0];
    expect(script.getAttribute("src")).toBe(LOADER_SRC);
    expect(script.getAttribute("data-endpoint")).toBe("/bluepencil/api");
    expect(script.getAttribute("data-route")).toBe("url");
    expect(script.getAttribute("data-manifest")).toBe(MANIFEST_URL);
    expect(script.getAttribute("data-integrity")).toBe("true");
    expect(script.getAttribute("data-language")).toBe("de");
    expect(script.getAttribute("data-environment")).toBe("staging");
    // This repo's default anchor hooks already are data-bluepencil/data-testid.
    expect(script.hasAttribute("data-anchor-hooks")).toBe(false);
  });

  it("defaults the sidecar environment to dev", async () => {
    vi.unstubAllEnvs();
    enableLayer();
    teardownBluepencilReviewLayer();

    await installBluepencilReviewLayer();
    expect(loaderScripts()[0].getAttribute("data-environment")).toBe("dev");
  });

  it("is idempotent — a second call adds nothing", async () => {
    await expect(installBluepencilReviewLayer()).resolves.toBe(true);
    await expect(installBluepencilReviewLayer()).resolves.toBe(false);
    expect(loaderScripts()).toHaveLength(1);
  });

  it("maps the app language to de/en", async () => {
    await i18n.changeLanguage("en");
    await installBluepencilReviewLayer();
    expect(loaderScripts()[0].getAttribute("data-language")).toBe("en");
  });
});

describe("bluepencil loader — teardown", () => {
  beforeEach(() => {
    enableLayer();
    stubHealth({ ok: true });
  });
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("removes the script and element, destroys the handle and clears globals", async () => {
    await installBluepencilReviewLayer();
    const element = document.createElement("bluepencil-notes");
    document.body.append(element);
    const destroy = vi.fn();
    window.bluepencilAttach = { destroy, version: "0.1.0-alpha.1" };
    window.rfBluepencil = {};

    teardownBluepencilReviewLayer();

    expect(loaderScripts()).toHaveLength(0);
    expect(document.querySelector("bluepencil-notes")).toBeNull();
    expect(destroy).toHaveBeenCalledTimes(1);
    expect(window.bluepencilAttach).toBeUndefined();
    expect(window.rfBluepencil).toBeUndefined();
  });

  it("is idempotent and never throws without any injected nodes", () => {
    expect(() => {
      teardownBluepencilReviewLayer();
      teardownBluepencilReviewLayer();
    }).not.toThrow();
  });
});
