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
import { installBluepencilHost } from "../bluepencil/host";
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

function completeAttach(): void {
  document.dispatchEvent(new Event("bp-attach-ready"));
}

async function resetLayer(): Promise<void> {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  completeAttach();
  teardownBluepencilReviewLayer();
  await new Promise<void>((resolve) => setTimeout(resolve, 0));
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
  afterEach(async () => {
    await resetLayer();
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
    expect(script.getAttribute("data-identity")).toBe("rfBluepencil.identity");
    expect(script.getAttribute("data-headers-from")).toBe("rfBluepencil.headers");
    expect(script.getAttribute("data-gate")).toBe("rfBluepencil.gate");
    expect(script.getAttribute("data-route-from")).toBe("rfBluepencil.routeFor");
    expect(script.hasAttribute("data-anchor-hooks")).toBe(false);
    expect(script.hasAttribute("data-build-ref")).toBe(false);
  });

  it("skips the integrity attribute and warns once when WebCrypto is unavailable (#981)", async () => {
    // No `crypto.subtle` — a plain-HTTP non-localhost origin.
    vi.stubGlobal("crypto", {});
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});

    await expect(installBluepencilReviewLayer()).resolves.toBe(true);

    const script = loaderScripts()[0];
    // Requesting the integrity check here would abort the whole attach, so
    // the layer must load without it instead of silently never mounting.
    expect(script.hasAttribute("data-integrity")).toBe(false);
    expect(warn).toHaveBeenCalledWith(expect.stringContaining("crypto.subtle"));

    warn.mockRestore();
  });

  it("defaults the sidecar environment to dev", async () => {
    vi.unstubAllEnvs();
    enableLayer();
    completeAttach();
    teardownBluepencilReviewLayer();

    await installBluepencilReviewLayer();
    expect(loaderScripts()[0].getAttribute("data-environment")).toBe("dev");
  });

  it("is idempotent — a second call adds nothing", async () => {
    await expect(installBluepencilReviewLayer()).resolves.toBe(true);
    await expect(installBluepencilReviewLayer()).resolves.toBe(false);
    expect(loaderScripts()).toHaveLength(1);
  });

  it("shares one in-flight probe and binds one loader", async () => {
    let resolveHealth!: (response: Response) => void;
    const healthResponse = new Promise<Response>((resolve) => {
      resolveHealth = resolve;
    });
    const fetchMock = vi.fn(() => healthResponse);
    vi.stubGlobal("fetch", fetchMock);

    const first = installBluepencilReviewLayer();
    const second = installBluepencilReviewLayer();

    expect(second).toBe(first);
    resolveHealth({ ok: true, status: 200, json: async () => ({ ok: true }) } as Response);
    await expect(Promise.all([first, second])).resolves.toEqual([true, true]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
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
  afterEach(resetLayer);

  it("removes the script and element, destroys the handle and clears globals", async () => {
    await installBluepencilReviewLayer();
    const element = document.createElement("bluepencil-notes");
    document.body.append(element);
    const destroy = vi.fn();
    window.bluepencilAttach = { destroy, version: "0.1.0-alpha.1" };
    installBluepencilHost({ getUser: () => ({ name: "Ada Lovelace" }) });

    completeAttach();
    teardownBluepencilReviewLayer();

    expect(loaderScripts()).toHaveLength(0);
    expect(document.querySelector("bluepencil-notes")).toBeNull();
    expect(destroy).toHaveBeenCalledTimes(1);
    expect(window.bluepencilAttach).toBeUndefined();
    expect(window.rfBluepencil).toBeUndefined();
  });

  it("invalidates an in-flight install when teardown happens", async () => {
    let resolveHealth!: (response: Response) => void;
    const healthResponse = new Promise<Response>((resolve) => {
      resolveHealth = resolve;
    });
    vi.stubGlobal("fetch", vi.fn(() => healthResponse));

    const installing = installBluepencilReviewLayer();
    teardownBluepencilReviewLayer();
    resolveHealth({ ok: true, status: 200, json: async () => ({ ok: true }) } as Response);

    await expect(installing).resolves.toBe(false);
    expect(loaderScripts()).toHaveLength(0);
    expect(window.rfBluepencil).toBeUndefined();
  });

  it("starts a fresh install after invalidating an older one", async () => {
    let firstResolve!: (response: Response) => void;
    let secondResolve!: (response: Response) => void;
    const firstHealth = new Promise<Response>((resolve) => {
      firstResolve = resolve;
    });
    const secondHealth = new Promise<Response>((resolve) => {
      secondResolve = resolve;
    });
    const fetchMock = vi
      .fn()
      .mockImplementationOnce(() => firstHealth)
      .mockImplementationOnce(() => secondHealth);
    vi.stubGlobal("fetch", fetchMock);

    const stale = installBluepencilReviewLayer();
    teardownBluepencilReviewLayer();
    const fresh = installBluepencilReviewLayer();
    firstResolve({ ok: true, status: 200, json: async () => ({ ok: true }) } as Response);
    secondResolve({ ok: true, status: 200, json: async () => ({ ok: true }) } as Response);

    await expect(stale).resolves.toBe(false);
    await expect(fresh).resolves.toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(loaderScripts()).toHaveLength(1);
  });

  it("cleans a late handle and element after teardown", async () => {
    await installBluepencilReviewLayer();
    teardownBluepencilReviewLayer();

    const lateElement = document.createElement("bluepencil-notes");
    document.body.append(lateElement);
    const destroy = vi.fn();
    window.bluepencilAttach = { destroy };

    completeAttach();
    await new Promise<void>((resolve) => setTimeout(resolve, 0));

    expect(destroy).toHaveBeenCalledTimes(1);
    expect(window.bluepencilAttach).toBeUndefined();
    expect(document.querySelector("bluepencil-notes")).toBeNull();
  });

  it("removes the script after an attach error", async () => {
    await installBluepencilReviewLayer();
    document.dispatchEvent(new Event("bp-attach-error"));
    await new Promise<void>((resolve) => setTimeout(resolve, 0));

    expect(loaderScripts()).toHaveLength(0);
    expect(window.rfBluepencil).toBeDefined();
  });

  it("waits for a retired attach before starting a fresh install", async () => {
    const fetchMock = vi.fn(
      async () =>
        ({
          ok: true,
          status: 200,
          json: async () => ({ ok: true }),
        }) as Response,
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(installBluepencilReviewLayer()).resolves.toBe(true);
    teardownBluepencilReviewLayer();
    const fresh = installBluepencilReviewLayer();

    await Promise.resolve();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(loaderScripts()).toHaveLength(0);

    completeAttach();
    await expect(fresh).resolves.toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(loaderScripts()).toHaveLength(1);
  });

  it("is idempotent and never throws without any injected nodes", () => {
    expect(() => {
      teardownBluepencilReviewLayer();
      teardownBluepencilReviewLayer();
    }).not.toThrow();
  });
});
