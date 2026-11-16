/**
 * The security boundary of the service worker (plan M2, REQ-214).
 *
 * A cached /api/ response could show another tenant's artifacts on a shared
 * device. These tests read the shipped policy constants and generated worker,
 * so a future "small optimisation" that adds the API to the cache is caught
 * here rather than in production.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import {
  PWA_NAVIGATION_DENYLIST,
  PWA_NETWORK_ONLY_PREFIXES,
  isNetworkOnlyPath,
} from "../config/pwa-config";

const ROOT = join(__dirname, "..", "..");
const VITE_CONFIG = readFileSync(join(ROOT, "vite.config.ts"), "utf-8");

describe("service worker cache policy", () => {
  it("denies the API, MCP, admin and static paths as navigation fallbacks", () => {
    expect(PWA_NAVIGATION_DENYLIST.some((regex) => regex.test("/api/v1/artifacts/"))).toBe(true);
    expect(PWA_NAVIGATION_DENYLIST.some((regex) => regex.test("/mcp/"))).toBe(true);
    expect(PWA_NAVIGATION_DENYLIST.some((regex) => regex.test("/admin/"))).toBe(true);
    expect(PWA_NAVIGATION_DENYLIST.some((regex) => regex.test("/static/x.js"))).toBe(true);
    expect(PWA_NAVIGATION_DENYLIST.some((regex) => regex.test("/requirements"))).toBe(false);
  });

  it("treats authenticated prefixes as network-only", () => {
    expect(isNetworkOnlyPath("/api/v1/artifacts/")).toBe(true);
    expect(isNetworkOnlyPath("/mcp/")).toBe(true);
    expect(isNetworkOnlyPath("/requirements")).toBe(false);
    expect(PWA_NETWORK_ONLY_PREFIXES).toEqual(["/api/", "/mcp/"]);
  });

  it("wires the denylist and NetworkOnly handler into the Vite config", () => {
    expect(VITE_CONFIG).toContain("navigateFallbackDenylist: PWA_NAVIGATION_DENYLIST");
    expect(VITE_CONFIG).toContain('handler: "NetworkOnly"');
    expect(VITE_CONFIG).toContain('url.pathname.startsWith("/api/")');
    expect(VITE_CONFIG).toContain('url.pathname.startsWith("/mcp/")');
    expect(VITE_CONFIG).toContain("registerType: \"prompt\"");
    expect(VITE_CONFIG).not.toContain("registerType: \"autoUpdate\"");
  });

  it("never caches an API response in any runtime rule", () => {
    // Every CacheFirst/StaleWhileRevalidate pattern in the config must be a
    // static asset prefix; the only path-based match for /api/ is NetworkOnly.
    expect(VITE_CONFIG).not.toMatch(/urlPattern:[^\n]*\/api\/[^\n]*CacheFirst/);
    expect(VITE_CONFIG).not.toMatch(/urlPattern:[^\n]*\/api\/[^\n]*StaleWhileRevalidate/);
  });
});
