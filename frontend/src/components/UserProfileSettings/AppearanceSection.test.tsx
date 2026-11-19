/**
 * Task 2 — AppearanceSection (UserProfileSettings) unit tests.
 *
 * The two user-owned display toggles live HERE, in the user profile — not in
 * the WorkspaceSettings "Darstellung" tab. They are independent, use the APG
 * switch pattern (`<button role="switch" aria-checked>`), are keyboard
 * operable with a visible focus ring, and round-trip through the two snake_case
 * fields on `displayPreferencesApi`.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { resolveLocaleKey } from "../../test/i18n-test-helpers";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) => {
      const { defaultValue, ...interpolation } = options ?? {};
      const resolved =
        resolveLocaleKey(key) ??
        (typeof defaultValue === "string" ? defaultValue : key);
      return Object.entries(interpolation).reduce(
        (acc, [name, value]) => acc.replace(`{{${name}}}`, String(value)),
        resolved
      );
    },
    i18n: { language: "de" },
  }),
}));

vi.mock("../../api/display-preferences", () => ({
  displayPreferencesApi: { get: vi.fn(), update: vi.fn() },
}));

import { AppearanceSection } from "./AppearanceSection";
import { displayPreferencesApi } from "../../api/display-preferences";
import {
  INSPECTOR_VISIBLE_DEFAULT,
  setInspectorVisible,
} from "../../hooks/useInspectorVisible";
import {
  TRACE_FOOTER_VISIBLE_DEFAULT,
  setTraceFooterVisible,
} from "../../hooks/useTraceFooterVisible";

const SERVER_PREFS = {
  show_readable_ids: true,
  visible_metrics: null,
  trace_footer_enabled: true,
  inspector_enabled: true,
};

async function renderSettled(): Promise<void> {
  // Flush the mount-time GET inside act so its store/state updates are not
  // reported as unwrapped updates by React 19.
  await act(async () => {
    render(<AppearanceSection />);
  });
  expect(screen.queryByTestId("appearance-loading")).not.toBeInTheDocument();
}

beforeEach(() => {
  vi.clearAllMocks();
  setTraceFooterVisible(TRACE_FOOTER_VISIBLE_DEFAULT);
  setInspectorVisible(INSPECTOR_VISIBLE_DEFAULT);
  vi.mocked(displayPreferencesApi.get).mockResolvedValue(SERVER_PREFS);
  vi.mocked(displayPreferencesApi.update).mockImplementation(async (changes) => ({
    ...SERVER_PREFS,
    ...changes,
  }));
});

afterEach(() => {
  setTraceFooterVisible(TRACE_FOOTER_VISIBLE_DEFAULT);
  setInspectorVisible(INSPECTOR_VISIBLE_DEFAULT);
});

describe("AppearanceSection (Task 2)", () => {
  it("renders exactly two switches in the user profile with correct aria-checked", async () => {
    await renderSettled();

    expect(screen.getByTestId("appearance-section")).toBeInTheDocument();
    const switches = screen.getAllByRole("switch");
    expect(switches).toHaveLength(2);
    expect(switches[0]).toHaveAttribute("aria-checked", "true");
    expect(switches[1]).toHaveAttribute("aria-checked", "true");
    expect(displayPreferencesApi.get).toHaveBeenCalledTimes(1);
  });

  it("reflects a server value of false for either flag on load", async () => {
    vi.mocked(displayPreferencesApi.get).mockResolvedValue({
      ...SERVER_PREFS,
      trace_footer_enabled: false,
      inspector_enabled: false,
    });

    await renderSettled();

    const switches = screen.getAllByRole("switch");
    expect(switches[0]).toHaveAttribute("aria-checked", "false");
    expect(switches[1]).toHaveAttribute("aria-checked", "false");
  });

  it("saves only the toggled field — the other flag is independent", async () => {
    await renderSettled();
    const [footerSwitch, inspectorSwitch] = screen.getAllByRole("switch");

    fireEvent.click(footerSwitch);

    await waitFor(() => {
      expect(displayPreferencesApi.update).toHaveBeenCalledWith({
        trace_footer_enabled: false,
      });
    });
    expect(footerSwitch).toHaveAttribute("aria-checked", "false");
    // The inspector has not been touched at all.
    expect(inspectorSwitch).toHaveAttribute("aria-checked", "true");
    expect(displayPreferencesApi.update).toHaveBeenCalledTimes(1);

    // The component deliberately serializes saves (a toggle is ignored while
    // `saving` is set). waitFor above only sees the call, not its resolution —
    // wait for the switch to leave its disabled/busy state so the second,
    // independent toggle is never dropped under CI load. This hardens timing
    // only; every behavioural assertion stays exactly as strict.
    await waitFor(() => expect(footerSwitch).not.toBeDisabled());

    fireEvent.click(inspectorSwitch);
    await waitFor(() => {
      expect(displayPreferencesApi.update).toHaveBeenLastCalledWith({
        inspector_enabled: false,
      });
    });
    expect(inspectorSwitch).toHaveAttribute("aria-checked", "false");
    expect(footerSwitch).toHaveAttribute("aria-checked", "false");
  });

  it("rolls back and shows an alert when a save is rejected", async () => {
    await renderSettled();
    vi.mocked(displayPreferencesApi.update).mockRejectedValue({
      error: { message: "nope" },
    });

    fireEvent.click(screen.getAllByRole("switch")[0]);

    expect(await screen.findByTestId("appearance-error")).toHaveTextContent("nope");
    expect(screen.getAllByRole("switch")[0]).toHaveAttribute("aria-checked", "true");
  });

  it("shows an explicit loading state and disables both switches until the GET settles", async () => {
    let resolveGet: (value: typeof SERVER_PREFS) => void = () => undefined;
    vi.mocked(displayPreferencesApi.get).mockReturnValue(
      new Promise((resolve) => {
        resolveGet = resolve;
      })
    );

    render(<AppearanceSection />);

    expect(screen.getByTestId("appearance-loading")).toHaveAttribute("role", "status");
    for (const toggle of screen.getAllByRole("switch")) {
      expect(toggle).toBeDisabled();
    }

    await act(async () => {
      resolveGet({ ...SERVER_PREFS, inspector_enabled: false });
    });
    expect(screen.queryByTestId("appearance-loading")).not.toBeInTheDocument();
    expect(screen.getAllByRole("switch")[1]).toHaveAttribute("aria-checked", "false");
  });

  it("is keyboard operable and carries a visible focus ring", async () => {
    const user = userEvent.setup();
    await renderSettled();
    const switches = screen.getAllByRole("switch");

    await user.tab();
    expect(switches[0]).toHaveFocus();
    await user.keyboard(" ");
    await waitFor(() =>
      expect(switches[0]).toHaveAttribute("aria-checked", "false")
    );
    await user.tab();
    expect(switches[1]).toHaveFocus();

    // jsdom does not apply CSS-module styles; the focus ring is provided by the
    // global `:focus-visible` rule, asserted here as the binding contract.
    const globalCss = readFileSync(
      resolve(__dirname, "../../styles/global.css"),
      "utf8"
    );
    expect(globalCss).toContain(":focus-visible");
    expect(globalCss).toContain("outline: 2px solid var(--color-focus");
  });

  it("lives in UserProfileSettings and NOT in the WorkspaceSettings appearance tab", () => {
    const profileSource = readFileSync(
      resolve(__dirname, "./UserProfileSettings.tsx"),
      "utf8"
    );
    const workspaceSource = readFileSync(
      resolve(__dirname, "../WorkspaceSettings/WorkspaceSettings.tsx"),
      "utf8"
    );

    expect(profileSource).toContain("<AppearanceSection />");
    expect(workspaceSource).not.toContain("AppearanceSection");
    expect(workspaceSource).not.toContain("aria-checked");
  });
});
