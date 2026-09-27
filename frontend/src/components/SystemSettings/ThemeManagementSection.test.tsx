/**
 * ThemeManagementSection tests (Theme Palettes, Task 9).
 *
 * System-Admin-facing management surface: list palettes, read-only state for
 * system rows, delete for custom rows, JSON import/export, per-row export.
 *
 * Issue #1093 adds the design-system and label-clarity assertions: every
 * control is on a global `.btn-*`/`.field-select` class, the export control
 * names what it exports, the read-only state is a state ON the control, and
 * "Als Standard speichern" states its target.
 */
import { describe, it, expect, vi, beforeAll, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ThemeManagementSection } from "./ThemeManagementSection";
import { themePalettesApi } from "../../api/themePalettes";
// Real i18n singleton (same pattern as MemoryManagementSection.test.tsx): the
// wording IS the fix in #1093, so `t()` must resolve against the real locale
// bundles rather than echoing keys back.
import { i18n } from "../../i18n/index";

vi.mock("../../api/themePalettes");

/**
 * The assertions below pin the ACTUAL German user-visible wording, so the
 * suite runs with the catalogue the user sees.
 */
beforeAll(async () => {
  await i18n.changeLanguage("de");
});

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

  it("shows the read-only state on the system palette's control, not only as a badge", async () => {
    render(<ThemeManagementSection />);
    expect(await screen.findByTestId("theme-row-default")).toBeInTheDocument();
    expect(screen.getByTestId("theme-readonly-badge-default")).toBeInTheDocument();

    // #1093: the read-only state is a state ON the control — disabled, with the
    // explanation as its accessible name. It used to be prose in the section
    // hint plus a silently missing button, which made "not applicable here"
    // indistinguishable from "not permitted for you".
    const deleteControl = screen.getByTestId("theme-delete-default");
    expect(deleteControl).toBeDisabled();
    expect(deleteControl).toHaveAttribute(
      "aria-label",
      "System-Palette kann nicht geändert werden"
    );
    expect(deleteControl).toHaveAttribute(
      "title",
      "System-Palette kann nicht geändert werden"
    );
  });

  it("shows an enabled delete button for custom palettes", async () => {
    render(<ThemeManagementSection />);
    const deleteControl = await screen.findByTestId("theme-delete-custom-x");
    expect(deleteControl).toBeEnabled();
    expect(deleteControl).toHaveAccessibleName("Custom X löschen");
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
    // UI-09 (system audit P4): deleting a palette is destructive — requires
    // an explicit confirmation before the API call fires.
    fireEvent.click(await screen.findByTestId("theme-delete-confirm-confirm"));
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

    it("states the save's target visibly and in its accessible name", async () => {
      render(<ThemeManagementSection />);
      await screen.findByTestId("theme-row-default");

      // Before a change: the loaded default.
      expect(screen.getByTestId("tenant-default-target")).toHaveTextContent(
        "Standard: Default · Dunkler Modus"
      );
      expect(screen.getByTestId("tenant-default-save")).toHaveAccessibleName(
        "Default · Dunkler Modus als Standard speichern"
      );

      fireEvent.change(screen.getByTestId("tenant-default-palette-select"), {
        target: { value: "custom-x" },
      });
      fireEvent.change(screen.getByTestId("tenant-default-mode-select"), {
        target: { value: "light" },
      });

      // #1093: the button's target follows the selects, so it is impossible to
      // save the wrong default without being able to see which one you'd save.
      expect(screen.getByTestId("tenant-default-target")).toHaveTextContent(
        "Standard: Custom X · Heller Modus"
      );
      expect(screen.getByTestId("tenant-default-save")).toHaveAccessibleName(
        "Custom X · Heller Modus als Standard speichern"
      );
    });
  });
});

/**
 * Issue #1093 — the section was measured with no design-system classes on any
 * control and seven identically-labelled "Exportieren" buttons.
 */
describe("ThemeManagementSection — design system and label clarity (#1093)", () => {
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

  it("puts every button and select on a design-system class", async () => {
    render(<ThemeManagementSection />);
    await screen.findByTestId("theme-row-default");

    const buttons = screen.getAllByRole("button");
    expect(buttons.length).toBeGreaterThan(0);
    for (const button of buttons) {
      expect(button.className).toMatch(
        /(^|\s)btn-(primary|secondary|ghost|danger)(\s|$)/
      );
    }
    for (const select of screen.getAllByRole("combobox")) {
      expect(select).toHaveClass("field-select");
    }
  });

  it("names what each export control exports, not just 'Exportieren'", async () => {
    render(<ThemeManagementSection />);
    await screen.findByTestId("theme-row-default");

    // The visible label states the format; the accessible name states the
    // object. The accessible name contains the visible label, so WCAG 2.5.3
    // "Label in Name" holds for speech-input users.
    for (const [key, label] of [
      ["default", "Default"],
      ["custom-x", "Custom X"],
    ]) {
      const control = screen.getByTestId(`theme-export-${key}`);
      expect(control).toHaveTextContent("JSON exportieren");
      expect(control).toHaveAccessibleName(`${label} als JSON exportieren`);
    }

    // The old bare "Exportieren" is gone — the two rows are distinguishable.
    expect(screen.queryByText("Exportieren")).not.toBeInTheDocument();
  });

  it("exposes a visible, labelled design-system trigger for the import", async () => {
    render(<ThemeManagementSection />);
    // Wait for the initial load so the component's state settles before the
    // assertions (no act() warning, no race on the mocked list result).
    await screen.findByTestId("theme-row-default");

    // The user clicks a real `.btn-secondary`, not a native file input that
    // cannot be styled — and that button names its object.
    const trigger = screen.getByTestId("theme-import-btn");
    expect(trigger).toHaveClass("btn-secondary");
    expect(trigger).toHaveTextContent("JSON-Datei auswählen");

    // The picker itself stays in the DOM (E2E + a11y wiring) but is driven by
    // the trigger, so it is not a second Tab stop.
    const input = screen.getByTestId("theme-import-input");
    expect(input).toHaveAttribute("type", "file");
    expect(input).toHaveAttribute("accept", "application/json");
    // No second, unstyled native picker in the accessibility tree.
    expect(screen.getAllByTestId("theme-import-input")).toHaveLength(1);
  });

  it("opens the file picker when the import trigger is clicked", async () => {
    render(<ThemeManagementSection />);
    await screen.findByTestId("theme-row-default");

    const input = screen.getByTestId("theme-import-input") as HTMLInputElement;
    const clicked = vi.fn();
    input.click = clicked;

    fireEvent.click(screen.getByTestId("theme-import-btn"));
    expect(clicked).toHaveBeenCalledTimes(1);
  });
});
