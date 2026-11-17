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
  PWA_PRECACHE_GLOBS,
  PWA_PRECACHE_JS_MAX_BYTES,
  isNetworkOnlyPath,
  shouldKeepPrecacheEntry,
} from "../config/pwa-config";

const ROOT = join(__dirname, "..", "..");
const VITE_CONFIG = readFileSync(join(ROOT, "vite.config.ts"), "utf-8");

/** Minimal Workbox/minimatch-style glob matcher for the constructs we use. */
function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function globToRegExp(glob: string): RegExp {
  let source = "";
  for (let i = 0; i < glob.length; i += 1) {
    const char = glob[i];
    if (char === "*") {
      if (glob[i + 1] === "*") {
        source += ".*";
        i += 1;
      } else {
        source += "[^/]*";
      }
    } else if (char === "?") {
      source += "[^/]";
    } else if (char === "{") {
      const end = glob.indexOf("}", i + 1);
      if (end === -1) {
        source += "\\{";
      } else {
        source += `(?:${glob.slice(i + 1, end).split(",").map(escapeRegExp).join("|")})`;
        i = end;
      }
    } else {
      source += escapeRegExp(char);
    }
  }
  return new RegExp(`^${source}$`);
}

/**
 * Full precache decision for a path: glob match AND the size filter applied
 * to the generated manifest. The default size is deliberately just over the
 * threshold, so a JS path without an explicit size is treated as a heavy lazy
 * chunk (the hashed entry chunk is exempt). Assertions about shell assets are
 * unaffected because the size filter only touches assets/*.js.
 */
function precacheMatches(path: string, size = PWA_PRECACHE_JS_MAX_BYTES + 1): boolean {
  const matchedByGlob = PWA_PRECACHE_GLOBS.some((glob) => globToRegExp(glob).test(path));
  return matchedByGlob && shouldKeepPrecacheEntry({ url: path, size });
}

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

describe("PWA precache scope (PERF-007)", () => {
  it("precache globs match the app shell", () => {
    expect(precacheMatches("index.html")).toBe(true);
    expect(precacheMatches("assets/index-a1b2c3.js")).toBe(true);
    expect(precacheMatches("assets/index-a1b2c3.css")).toBe(true);
    expect(precacheMatches("assets/geist-latin-a1b2c3.woff2")).toBe(true);
    expect(precacheMatches("icons/icon-192.png")).toBe(true);
    expect(precacheMatches("manifest.webmanifest")).toBe(true);
  });

  it("does NOT precache heavy lazy chunks", () => {
    expect(precacheMatches("assets/Mermaid-a1b2c3.js")).toBe(false);
    expect(precacheMatches("assets/fabric-a1b2c3.js")).toBe(false);
    expect(precacheMatches("assets/codemirror-a1b2c3.js")).toBe(false);
    expect(precacheMatches("assets/vendor-codemirror-a1b2c3.js")).toBe(false);
    expect(precacheMatches("assets/elk-a1b2c3.js")).toBe(false);
    expect(precacheMatches("assets/cytoscape-a1b2c3.js")).toBe(false);
    expect(precacheMatches("assets/katex-a1b2c3.js")).toBe(false);
  });

  it("precache manifest transform keeps exactly the entry + small chunks", () => {
    // Synthetic Workbox manifest: 13 initial-load chunks (the entry is
    // deliberately over the threshold) plus one heavy lazy chunk. Applying
    // the production filter must yield only the entry + the small chunks.
    const manifest = [
      { url: "assets/index-a1b2c3.js", size: 720_182 },
      { url: "assets/react-dom-a1b2c3.js", size: 3_908 },
      { url: "assets/rolldown-runtime-a1b2c3.js", size: 1_106 },
      { url: "assets/AuthContext-a1b2c3.js", size: 25_759 },
      { url: "assets/WorkspaceContext-a1b2c3.js", size: 49_916 },
      { url: "assets/useQuery-a1b2c3.js", size: 22_844 },
      { url: "assets/useMutation-a1b2c3.js", size: 2_410 },
      { url: "assets/mutation-a1b2c3.js", size: 3_444 },
      { url: "assets/traceEndpoints-a1b2c3.js", size: 1_355 },
      { url: "assets/preload-helper-a1b2c3.js", size: 1_519 },
      { url: "assets/link-types-a1b2c3.js", size: 836 },
      { url: "assets/preference-values-a1b2c3.js", size: 627 },
      { url: "assets/createLucideIcon-a1b2c3.js", size: 3_132 },
      { url: "assets/lazy-HugeChart-a1b2c3.js", size: 900_000 },
    ];

    const kept = manifest.filter(shouldKeepPrecacheEntry).map((entry) => entry.url);

    expect(kept).toEqual(manifest.slice(0, 13).map((entry) => entry.url));
    expect(kept).not.toContain("assets/lazy-HugeChart-a1b2c3.js");
  });

  it("honours the size boundary for non-entry chunks", () => {
    expect(shouldKeepPrecacheEntry({ url: "assets/small-a1b2c3.js", size: PWA_PRECACHE_JS_MAX_BYTES })).toBe(true);
    expect(shouldKeepPrecacheEntry({ url: "assets/big-a1b2c3.js", size: PWA_PRECACHE_JS_MAX_BYTES + 1 })).toBe(false);
    expect(shouldKeepPrecacheEntry({ url: "assets/index-a1b2c3.js", size: 720_182 })).toBe(true);
  });

  it("pins a positive precache size threshold", () => {
    expect(PWA_PRECACHE_JS_MAX_BYTES).toBeGreaterThan(0);
    expect(PWA_PRECACHE_JS_MAX_BYTES).toBe(200_000);
  });

  it("wires precise globs, the manifest transform and an on-demand /assets/ rule", () => {
    expect(VITE_CONFIG).toContain("globPatterns: [...PWA_PRECACHE_GLOBS]");
    expect(VITE_CONFIG).toContain("manifestTransforms:");
    expect(VITE_CONFIG).toContain("shouldKeepPrecacheEntry");
    expect(VITE_CONFIG).toContain('url.pathname.startsWith("/assets/")');
    expect(VITE_CONFIG).toContain('handler: "CacheFirst"');
  });
});
