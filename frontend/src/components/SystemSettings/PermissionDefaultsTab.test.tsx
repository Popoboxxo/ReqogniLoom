import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, cleanup } from "@testing-library/react";

import { PermissionDefaultsTab } from "./PermissionDefaultsTab";
import { i18n } from "../../i18n/index";
import { permissionDefaultsApi, normalizeMatrix } from "../../api/permission-defaults";
import type { GlobalPermissionDefinition, EnforcementStatus } from "../../api/permission-defaults";

vi.mock("../../api/permission-defaults", async () => {
  const actual = await vi.importActual<
    typeof import("../../api/permission-defaults")
  >("../../api/permission-defaults");
  return {
    ...actual,
    permissionDefaultsApi: {
      ...actual.permissionDefaultsApi,
      getGlobal: vi.fn(),
      getEnforcement: vi.fn(),
      listMismatches: vi.fn(),
    },
  };
});

function sampleGlobal(): GlobalPermissionDefinition {
  return {
    tenant_id: "t1",
    permission_json: normalizeMatrix({
      admin: { read: true, write: true },
      editor: { read: true, write: false },
      viewer: { read: true, write: false },
      approver: { read: true, write: false },
    }),
    enforcement_mode: "shadow",
  };
}

function sampleEnforcement(): EnforcementStatus {
  return {
    enforcement_mode: "shadow",
    pending_mismatch_count: 0,
    mismatch_window_days: 30,
    ready_for_authoritative: true,
  };
}

describe("PermissionDefaultsTab i18n (#659)", () => {
  beforeEach(() => {
    vi.mocked(permissionDefaultsApi.getGlobal).mockReset();
    vi.mocked(permissionDefaultsApi.getEnforcement).mockReset();
    vi.mocked(permissionDefaultsApi.listMismatches).mockReset();
  });

  afterEach(() => {
    cleanup();
    void i18n.changeLanguage("en");
  });

  it("renders the localized heading, not the raw English fallback text", async () => {
    void i18n.changeLanguage("de");
    vi.mocked(permissionDefaultsApi.getGlobal).mockResolvedValue(sampleGlobal());
    vi.mocked(permissionDefaultsApi.getEnforcement).mockResolvedValue(sampleEnforcement());
    vi.mocked(permissionDefaultsApi.listMismatches).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    });

    render(<PermissionDefaultsTab />);

    expect(await screen.findByText("Globale Berechtigungsmatrix")).toBeInTheDocument();
    expect(screen.queryByText("Global Permission Matrix")).not.toBeInTheDocument();
  });
});
