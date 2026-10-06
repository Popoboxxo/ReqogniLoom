/**
 * bluepencil vendored-element integrity guard (issue #988).
 *
 * The review-layer element under `public/bluepencil/latest/` is a vendored
 * third-party artifact. A stale or incomplete re-vendor would silently
 * regress the note-author mapping back to "anonymous" (the element resolves
 * the author via the global-path identity branch, see host.ts). This guard
 * pins the manifest checksum and the branch markers so such a re-vendor
 * turns CI red instead of shipping unnoticed.
 *
 * This is pure file I/O on the Node side and deliberately does not touch
 * the DOM, so it stays deterministic and environment-independent.
 */
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

interface BluepencilManifest {
  version: string;
  element: string;
  sha256: string;
}

/** Vendored-element directory, resolved from the Vitest project root (frontend/). */
const VENDOR_DIR = join(process.cwd(), "public", "bluepencil", "latest");

function readVendorFile(name: string): Buffer {
  return readFileSync(join(VENDOR_DIR, name));
}

function readManifest(): BluepencilManifest {
  return JSON.parse(readVendorFile("latest.json").toString("utf8")) as BluepencilManifest;
}

describe("bluepencil vendored element", () => {
  it("keeps the manifest checksum and the element bytes in sync", () => {
    const manifest = readManifest();
    const element = readVendorFile(manifest.element);
    const digest = createHash("sha256").update(element).digest("hex");

    expect(digest).toBe(manifest.sha256);
  });

  it("ships the global-path identity branch of the element", () => {
    const manifest = readManifest();
    const bundle = readVendorFile(manifest.element).toString("utf8");

    // Without this branch the host bridge's identity.getUser is never read and
    // every note falls back to author "anonymous".
    expect(bundle).toContain("getUser");
    expect(bundle).toContain("global path");
  });
});
