/**
 * PWA installability contract (plan M1, REQ-213).
 *
 * A manifest can drift silently: the product name is build-time configurable
 * (VITE_APP_NAME) while manifest.webmanifest is static, and theme colors must
 * stay copies of the CSS tokens (a manifest cannot resolve `var()`). These
 * tests are the drift gate for both — they read the shipped files, not a
 * parallel TypeScript constant.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { APP_NAME } from "../config/app-name";

const FRONTEND_ROOT = join(__dirname, "..", "..");
const MANIFEST = JSON.parse(
  readFileSync(join(FRONTEND_ROOT, "public", "manifest.webmanifest"), "utf-8")
) as Record<string, unknown>;
const TOKENS_CSS = readFileSync(join(FRONTEND_ROOT, "src", "styles", "tokens.css"), "utf-8");
const INDEX_HTML = readFileSync(join(FRONTEND_ROOT, "index.html"), "utf-8");

function tokenValue(name: string): string {
  const match = TOKENS_CSS.match(new RegExp(`--${name}\\s*:\\s*(#[0-9a-fA-F]{6})\\s*;`));
  if (!match) throw new Error(`token --${name} not found in tokens.css`);
  return match[1].toLowerCase();
}

describe("web app manifest", () => {
  it("uses the product name and the documented install fields", () => {
    // With a non-default VITE_APP_NAME the static manifest must be updated
    // alongside the build arg; this assertion is the gate for that edit.
    expect(MANIFEST.name).toBe(APP_NAME);
    expect(MANIFEST.short_name).toBe(APP_NAME);
    expect(MANIFEST.start_url).toBe("/");
    expect(MANIFEST.scope).toBe("/");
    expect(MANIFEST.display).toBe("standalone");
    expect(MANIFEST.lang).toBe("de");
    expect(MANIFEST.prefer_related_applications).toBeUndefined();
  });

  it("carries the required 192px and 512px icons plus a maskable variant", () => {
    const icons = MANIFEST.icons as Array<Record<string, string>>;
    expect(icons).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ sizes: "192x192", type: "image/png", purpose: "any" }),
        expect.objectContaining({ sizes: "512x512", type: "image/png", purpose: "any" }),
        expect.objectContaining({ sizes: "512x512", type: "image/png", purpose: "maskable" }),
      ])
    );
  });

  it("copies its colors from the design tokens", () => {
    const navBg = tokenValue("palette-navy-900");
    const lightSurface = tokenValue("palette-slate-50");
    expect(String(MANIFEST.theme_color).toLowerCase()).toBe(navBg);
    expect(String(MANIFEST.background_color).toLowerCase()).toBe(navBg);
    expect(INDEX_HTML).toContain(`content="${navBg}" media="(prefers-color-scheme: dark)"`);
    expect(INDEX_HTML).toContain(`content="${lightSurface}" media="(prefers-color-scheme: light)"`);
  });
});

describe("index.html install meta", () => {
  it("references manifest, icons and the mobile viewport contract", () => {
    expect(INDEX_HTML).toContain('rel="manifest" href="/manifest.webmanifest"');
    expect(INDEX_HTML).toContain('rel="apple-touch-icon" href="/icons/apple-touch-180.png"');
    expect(INDEX_HTML).toContain("viewport-fit=cover");
    expect(INDEX_HTML).toContain("interactive-widget=resizes-content");
    expect(INDEX_HTML).toContain('name="mobile-web-app-capable" content="yes"');
    expect(INDEX_HTML).toContain('name="apple-mobile-web-app-capable" content="yes"');
  });
});
