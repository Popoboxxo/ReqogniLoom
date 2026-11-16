/**
 * Icon dimensions and opacity contract (plan M1, REQ-213).
 *
 * Chrome requires 192px and 512px PNGs; iOS uses a 180px apple-touch-icon
 * without alpha (transparent icons render black there). Reading the PNG IHDR
 * keeps this test independent of any image decoder dependency.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const ICONS = join(__dirname, "..", "..", "public", "icons");
const PNG_SIGNATURE = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);

function header(name: string): { width: number; height: number; colorType: number } {
  const bytes = readFileSync(join(ICONS, name));
  expect(bytes.subarray(0, 8)).toEqual(PNG_SIGNATURE);
  return {
    width: bytes.readUInt32BE(16),
    height: bytes.readUInt32BE(20),
    colorType: bytes[25], // 2 = RGB (opaque), 6 = RGBA
  };
}

describe("PWA icons", () => {
  it.each([
    ["icon-192.png", 192, 6],
    ["icon-512.png", 512, 6],
    ["maskable-512.png", 512, 2],
    ["apple-touch-180.png", 180, 2],
  ])("%s has the right size and color mode", (name, size, colorType) => {
    const png = header(name);
    expect(png.width).toBe(size);
    expect(png.height).toBe(size);
    expect(png.colorType).toBe(colorType);
  });

  it("keeps the SVG master as the editable source", () => {
    const svg = readFileSync(join(ICONS, "icon.svg"), "utf-8");
    expect(svg).toContain("RL");
    expect(svg).toContain("#1a1f2e");
  });
});
