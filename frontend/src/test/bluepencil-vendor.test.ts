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
import { existsSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";

import { describe, expect, it } from "vitest";

interface BluepencilManifest {
  version: string;
  element: string;
  sha256: string;
}

/** The pin the layer is fetched and verified against (fetch-layer.sh). */
interface BluepencilLayerLock {
  version: string;
  release: string;
  assets: Record<string, string>;
}

/** Asset the container healthcheck and this guard both pin by SHA-256. */
const ELEMENT_ASSET = "bluepencil.element.min.js";

/** Vendored-element directory, resolved from the Vitest project root (frontend/). */
const VENDOR_DIR = join(process.cwd(), "public", "bluepencil", "latest");

/**
 * The lock lives outside the frontend project (deploy/bluepencil/), so walk up
 * from the served directory instead of assuming a second cwd.
 * VENDOR_DIR = <repo>/frontend/public/bluepencil/latest
 */
const LOCK_PATH = resolve(
  VENDOR_DIR,
  "..",
  "..",
  "..",
  "..",
  "deploy",
  "bluepencil",
  "layer.lock.json",
);

function readVendorFile(name: string): Buffer {
  const path = join(VENDOR_DIR, name);
  // Fail closed: the layer is no longer committed (plan D / D1.2), so an
  // unfetched checkout is a real configuration error, not a reason to skip.
  if (!existsSync(path)) {
    throw new Error(
      `bluepencil layer file missing: ${path}. The layer is not vendored in the ` +
        `repository any more — run \`make bluepencil-layer\` (i.e. ` +
        `\`bash deploy/bluepencil/fetch-layer.sh --dest frontend/public/bluepencil/latest\`) ` +
        `to fetch the release pinned in deploy/bluepencil/layer.lock.json.`,
    );
  }
  return readFileSync(path);
}

function readManifest(): BluepencilManifest {
  return JSON.parse(readVendorFile("latest.json").toString("utf8")) as BluepencilManifest;
}

function readLock(): BluepencilLayerLock {
  return JSON.parse(readFileSync(LOCK_PATH, "utf8")) as BluepencilLayerLock;
}

describe("bluepencil vendored element", () => {
  it("keeps the manifest checksum and the element bytes in sync", () => {
    const manifest = readManifest();
    const element = readVendorFile(manifest.element);
    const digest = createHash("sha256").update(element).digest("hex");

    expect(digest).toBe(manifest.sha256);
  });

  it("serves the layer release pinned in deploy/bluepencil/layer.lock.json", () => {
    const lock = readLock();
    const manifest = readManifest();
    const lockedElementSha = lock.assets[ELEMENT_ASSET];

    expect(lockedElementSha, `layer.lock.json has no assets["${ELEMENT_ASSET}"]`).toBeTruthy();
    // Provenance: the served bytes must be the release the lock names, so a
    // stale copy left in public/ fails here instead of shipping silently.
    expect(manifest.version).toBe(lock.version);
    expect(manifest.sha256).toBe(lockedElementSha);
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
