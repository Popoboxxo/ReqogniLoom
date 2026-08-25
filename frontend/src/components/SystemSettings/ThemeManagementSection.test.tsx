/**
 * ThemeManagementSection tests (Theme Presets, Task 9).
 *
 * System-Admin-facing management surface: list palettes, read-only badge
 * for system rows (no delete), delete for custom rows, JSON import/export,
 * per-row export.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ThemeManagementSection } from "./ThemeManagementSection";
import { themePalettesApi } from "../../api/themePalettes";

vi.mock("../../api/themePalettes");

describe("ThemeManagementSection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (themePalettesApi.list as ReturnType<typeof vi.fn>).mockResolvedValue({
      results: [
        {
          key: "default",
          label: "Default",
          is_system: true,
          dark_tokens: {},
          light_tokens: {},
        },
        {
          key: "custom-x",
          label: "Custom X",
          is_system: false,
          dark_tokens: {},
          light_tokens: {},
        },
      ],
    });
    (themePalettesApi.getTenantDefault as ReturnType<typeof vi.fn>).mockResolvedValue({
      palette_key: "default",
      mode: "dark",
    });
  });

  it("shows a read-only badge for system palettes and no delete button", async () => {
    render(<ThemeManagementSection />);
    expect(await screen.findByTestId("theme-row-default")).toBeInTheDocument();
    expect(screen.getByTestId("theme-readonly-badge-default")).toBeInTheDocument();
    expect(screen.queryByTestId("theme-delete-default")).not.toBeInTheDocument();
  });

  it("shows a delete button for custom palettes", async () => {
    render(<ThemeManagementSection />);
    expect(await screen.findByTestId("theme-delete-custom-x")).toBeInTheDocument();
  });

  it("export button downloads the palette", async () => {
    (themePalettesApi.exportPalette as ReturnType<typeof vi.fn>).mockResolvedValue({
      key: "default",
      label: "Default",
      is_system: true,
      dark_tokens: {},
      light_tokens: {},
    });
    render(<ThemeManagementSection />);
    fireEvent.click(await screen.findByTestId("theme-export-default"));
    await waitFor(() =>
      expect(themePalettesApi.exportPalette).toHaveBeenCalledWith("default")
    );
  });

  it("delete button removes a custom palette", async () => {
    (themePalettesApi.deletePalette as ReturnType<typeof vi.fn>).mockResolvedValue(undefined);
    render(<ThemeManagementSection />);
    fireEvent.click(await screen.findByTestId("theme-delete-custom-x"));
    await waitFor(() =>
      expect(themePalettesApi.deletePalette).toHaveBeenCalledWith("custom-x")
    );
  });

  it("import uploads a valid JSON file", async () => {
    (themePalettesApi.importPalette as ReturnType<typeof vi.fn>).mockResolvedValue({
      key: "new-one",
      label: "New One",
      is_system: false,
      dark_tokens: {},
      light_tokens: {},
    });
    render(<ThemeManagementSection />);
    const file = new File(
      [JSON.stringify({ label: "New One", dark_tokens: {}, light_tokens: {} })],
      "theme.json",
      { type: "application/json" }
    );
    const input = screen.getByTestId("theme-import-input");
    fireEvent.change(input, { target: { files: [file] } });
    await waitFor(() => expect(themePalettesApi.importPalette).toHaveBeenCalled());
  });

  describe("tenant default", () => {
    beforeEach(() => {
      (themePalettesApi.getTenantDefault as ReturnType<typeof vi.fn>).mockResolvedValue({
        palette_key: "default",
        mode: "dark",
      });
      (themePalettesApi.setTenantDefault as ReturnType<typeof vi.fn>).mockResolvedValue({
        palette_key: "custom-x",
        mode: "light",
      });
    });

    it("loads and displays the current tenant default", async () => {
      render(<ThemeManagementSection />);
      await waitFor(() =>
        expect(themePalettesApi.getTenantDefault).toHaveBeenCalled()
      );
      expect(screen.getByTestId("tenant-default-picker")).toBeInTheDocument();
    });

    it("saves a new tenant default when changed", async () => {
      render(<ThemeManagementSection />);
      await screen.findByTestId("theme-row-default");

      fireEvent.change(screen.getByTestId("tenant-default-palette-select"), {
        target: { value: "custom-x" },
      });
      fireEvent.change(screen.getByTestId("tenant-default-mode-select"), {
        target: { value: "light" },
      });
      fireEvent.click(screen.getByTestId("tenant-default-save"));

      await waitFor(() =>
        expect(themePalettesApi.setTenantDefault).toHaveBeenCalledWith("custom-x", "light")
      );
      expect(await screen.findByTestId("tenant-default-saved")).toBeInTheDocument();
    });
  });
});
