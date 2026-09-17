/**
 * ThemeContext two-axis tests (Theme Presets, Task 5).
 *
 * The context resolves (paletteKey, mode) from user preference >
 * tenant default > built-in fallback and applies the resolved palette's
 * --color-* tokens onto document.documentElement as inline custom
 * properties. All API access goes through ../api/themePalettes (mocked).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { ThemeProvider, useTheme } from "./ThemeContext";
import { themePalettesApi } from "../api/themePalettes";

vi.mock("../api/themePalettes");

describe("ThemeContext two-axis", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    document.documentElement.style.cssText = "";
    delete document.documentElement.dataset.themeMode;
    (themePalettesApi.list as ReturnType<typeof vi.fn>).mockResolvedValue({
      results: [
        {
          key: "default",
          label: "Default",
          is_system: true,
          dark_tokens: { "--color-primary": "#111111" },
          light_tokens: { "--color-primary": "#eeeeee" },
        },
        {
          key: "bauhaus",
          label: "Bauhaus",
          is_system: true,
          dark_tokens: { "--color-primary": "#222222" },
          light_tokens: { "--color-primary": "#dddddd" },
        },
      ],
    });
    (
      themePalettesApi.getPreference as ReturnType<typeof vi.fn>
    ).mockResolvedValue({ palette_key: "bauhaus", mode: "light" });
    (
      themePalettesApi.getTenantDefault as ReturnType<typeof vi.fn>
    ).mockResolvedValue({ palette_key: "default", mode: "dark" });
  });

  it("resolves to the user's own preference when set", async () => {
    render(
      <ThemeProvider>
        <Consumer />
      </ThemeProvider>
    );
    await waitFor(() =>
      expect(screen.getByTestId("palette-key")).toHaveTextContent("bauhaus")
    );
    expect(screen.getByTestId("mode")).toHaveTextContent("light");
  });

  it("applies the resolved palette's tokens onto documentElement", async () => {
    render(
      <ThemeProvider>
        <Consumer />
      </ThemeProvider>
    );
    await waitFor(() =>
      expect(
        document.documentElement.style.getPropertyValue("--color-primary")
      ).toBe("#dddddd")
    );
  });

  it("falls back to tenant default when no user preference is set", async () => {
    (
      themePalettesApi.getPreference as ReturnType<typeof vi.fn>
    ).mockResolvedValue({ palette_key: null, mode: null });
    render(
      <ThemeProvider>
        <Consumer />
      </ThemeProvider>
    );
    await waitFor(() =>
      expect(screen.getByTestId("palette-key")).toHaveTextContent("default")
    );
    expect(screen.getByTestId("mode")).toHaveTextContent("dark");
  });

  it("setPreference updates local state immediately and calls the API", async () => {
    render(
      <ThemeProvider>
        <Consumer />
      </ThemeProvider>
    );
    await waitFor(() =>
      expect(screen.getByTestId("palette-key")).toHaveTextContent("bauhaus")
    );
    fireEvent.click(screen.getByTestId("set-default-dark"));
    expect(screen.getByTestId("palette-key")).toHaveTextContent("default");
    expect(screen.getByTestId("mode")).toHaveTextContent("dark");
    await waitFor(() =>
      expect(themePalettesApi.setPreference).toHaveBeenCalledWith("default", "dark")
    );
  });

  it("keeps the last state when the API fails (offline tolerance)", async () => {
    (themePalettesApi.list as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error("network down")
    );
    render(
      <ThemeProvider>
        <Consumer />
      </ThemeProvider>
    );
    // Initial fallback state survives the failed bootstrap.
    await waitFor(() =>
      expect(themePalettesApi.list).toHaveBeenCalled()
    );
    expect(screen.getByTestId("palette-key")).toHaveTextContent("default");
    expect(screen.getByTestId("mode")).toHaveTextContent("dark");
  });
});

function Consumer() {
  const { paletteKey, mode, setPreference } = useTheme();
  return (
    <div>
      <span data-testid="palette-key">{paletteKey}</span>
      <span data-testid="mode">{mode}</span>
      <button
        data-testid="set-default-dark"
        onClick={() => setPreference("default", "dark")}
      />
    </div>
  );
}
