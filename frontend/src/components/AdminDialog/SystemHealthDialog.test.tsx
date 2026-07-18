/**
 * Unit tests for SystemHealthDialog — build/commit version indicator.
 *
 * Verifies:
 *   - Renders nothing when isOpen is false
 *   - Fetches and displays commit_short + build_time once the version
 *     endpoint resolves
 *   - Falls back to just the commit_short when build_time is null
 *   - Shows an "unavailable" marker (without crashing the dialog) when the
 *     version fetch fails, while the health snapshot still renders
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

vi.mock("../../api/admin-ops");
vi.mock("../../api/version");
vi.mock("react-i18next", () => {
  const t = (key: string, fallbackOrOptions?: string | Record<string, unknown>): string => {
    if (typeof fallbackOrOptions === "string") return fallbackOrOptions;
    if (fallbackOrOptions && typeof fallbackOrOptions === "object") {
      const { defaultValue, ...vars } = fallbackOrOptions as Record<string, unknown> & {
        defaultValue?: string;
      };
      let out = defaultValue ?? key;
      for (const [k, v] of Object.entries(vars)) {
        out = out.replace(`{{${k}}}`, String(v));
      }
      return out;
    }
    return key;
  };
  return { useTranslation: () => ({ t }) };
});

import * as adminOpsModule from "../../api/admin-ops";
import * as versionModule from "../../api/version";
import { SystemHealthDialog } from "./SystemHealthDialog";

const mockSnapshot = {
  components: [{ name: "database", status: "ok" as const, detail: "reachable" }],
  recent_events: [],
};

describe("SystemHealthDialog — version indicator", () => {
  beforeEach(() => {
    vi.mocked(adminOpsModule.adminOpsApi.getSystemHealth).mockResolvedValue(mockSnapshot);
  });

  it("renders nothing when isOpen is false", () => {
    const { container } = render(
      <SystemHealthDialog isOpen={false} onClose={vi.fn()} />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("displays commit_short and formatted build_time once resolved", async () => {
    vi.mocked(versionModule.versionApi.getVersion).mockResolvedValue({
      app_version: "0.2.0",
      commit: "abcdef1234567890",
      commit_short: "abcdef1",
      build_time: "2026-07-16T12:00:00Z",
    });

    render(<SystemHealthDialog isOpen onClose={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByTestId("system-health-version")).toHaveTextContent("abcdef1");
    });
    expect(screen.getByTestId("system-health-version")).toHaveTextContent("built");
    expect(screen.getByTestId("system-health-version")).toHaveTextContent("v0.2.0");
  });

  it("displays only commit_short when build_time is null", async () => {
    vi.mocked(versionModule.versionApi.getVersion).mockResolvedValue({
      app_version: "unknown",
      commit: "abcdef1234567890",
      commit_short: "abcdef1",
      build_time: null,
    });

    render(<SystemHealthDialog isOpen onClose={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByTestId("system-health-version")).toHaveTextContent(
        "Version: abcdef1"
      );
    });
    expect(screen.getByTestId("system-health-version")).not.toHaveTextContent("built");
  });

  it("shows an unavailable marker without crashing when the version fetch fails", async () => {
    vi.mocked(versionModule.versionApi.getVersion).mockRejectedValue(
      new Error("network error")
    );

    render(<SystemHealthDialog isOpen onClose={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByTestId("system-health-version")).toHaveTextContent(
        "Version: unavailable"
      );
    });
    // Health snapshot (independent fetch) still renders normally.
    await waitFor(() => {
      expect(screen.getByTestId("system-health-components")).toBeInTheDocument();
    });
  });

  it("omits the version indicator entirely while the fetch is still pending", () => {
    vi.mocked(versionModule.versionApi.getVersion).mockReturnValue(
      new Promise(() => {
        // Never resolves within this test — asserts the pre-fetch state.
      })
    );

    render(<SystemHealthDialog isOpen onClose={vi.fn()} />);

    expect(screen.queryByTestId("system-health-version")).not.toBeInTheDocument();
  });
});
