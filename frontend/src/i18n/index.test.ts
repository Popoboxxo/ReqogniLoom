/** FE-005 regression guard: missing-key diagnostics are dev-only. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { createMissingKeyDiagnostics, i18n } from "./index";

describe("i18n missing-key diagnostics", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("warns when a key is missing in the current test (DEV) build", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const key = "__s31_missing_key__";

    expect(i18n.t(key)).toBe(key);
    expect(warn).toHaveBeenCalledWith(expect.stringContaining(key));
  });

  it("builds a warning handler when enabled", () => {
    const diagnostics = createMissingKeyDiagnostics(true);
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});

    expect(diagnostics.saveMissing).toBe(true);
    expect(diagnostics.missingKeyHandler).toBeTypeOf("function");
    diagnostics.missingKeyHandler?.(["de"], "translation", "__dev_key__");
    expect(warn).toHaveBeenCalledWith(expect.stringContaining("__dev_key__"));
  });

  it("registers no handler and no saveMissing outside dev", () => {
    const diagnostics = createMissingKeyDiagnostics(false);

    expect(diagnostics.missingKeyHandler).toBeUndefined();
    expect(diagnostics.saveMissing).toBeUndefined();
  });
});
