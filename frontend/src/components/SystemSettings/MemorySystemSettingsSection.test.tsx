import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { MemorySystemSettingsSection } from "./MemorySystemSettingsSection";
import { systemMemorySettingsApi } from "../../api/system-memory-settings";
// Real i18n singleton, as in MemoryManagementSection.test.tsx — this test
// asserts against rendered copy, so `t()` must actually resolve keys against
// the locale bundles rather than echoing the key back.
import "../../i18n/index";

vi.mock("../../api/system-memory-settings", () => ({
  systemMemorySettingsApi: {
    get: vi.fn(),
    update: vi.fn(),
    reset: vi.fn(),
  },
}));

const SETTINGS = {
  embedding_provider: "sentence-transformers" as const,
  embedding_provider_is_override: false,
  embedding_model_name: null,
  embedding_model_name_is_override: false,
  ollama_base_url: null,
  ollama_base_url_is_override: false,
  embedding_timeout: 10,
  embedding_timeout_is_override: false,
  memory_backend: "pgvector" as const,
  memory_backend_is_override: false,
  honcho_base_url: null,
  honcho_base_url_is_override: false,
  honcho_api_key_is_set: false,
  warning: null,
};

describe("MemorySystemSettingsSection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(systemMemorySettingsApi.get).mockResolvedValue({ ...SETTINGS });
    vi.mocked(systemMemorySettingsApi.update).mockResolvedValue({ ...SETTINGS });
    vi.mocked(systemMemorySettingsApi.reset).mockResolvedValue({ ...SETTINGS });
  });

  it("loads and renders the effective values", async () => {
    render(<MemorySystemSettingsSection />);

    const section = await screen.findByTestId("memory-system-settings-section");
    expect(section).toBeInTheDocument();
    expect(screen.getByTestId("memory-settings-embedding-provider")).toHaveValue(
      "sentence-transformers"
    );
    expect(screen.getByTestId("memory-settings-backend")).toHaveValue("pgvector");
    // No overrides set → no override badges rendered.
    expect(screen.queryByTestId("embedding-provider-override-badge")).not.toBeInTheDocument();
    expect(screen.queryByTestId("memory-backend-override-badge")).not.toBeInTheDocument();
  });

  it("shows override badges when a field is overridden", async () => {
    vi.mocked(systemMemorySettingsApi.get).mockResolvedValue({
      ...SETTINGS,
      embedding_provider: "ollama",
      embedding_provider_is_override: true,
      memory_backend: "honcho",
      memory_backend_is_override: true,
    });

    render(<MemorySystemSettingsSection />);

    expect(await screen.findByTestId("embedding-provider-override-badge")).toBeInTheDocument();
    expect(screen.getByTestId("memory-backend-override-badge")).toBeInTheDocument();
  });

  it("changing the embedding provider and saving shows a confirm dialog instead of calling update() directly", async () => {
    const user = userEvent.setup();
    render(<MemorySystemSettingsSection />);

    await screen.findByTestId("memory-system-settings-section");
    await user.selectOptions(screen.getByTestId("memory-settings-embedding-provider"), "ollama");
    await user.click(screen.getByTestId("memory-settings-save-btn"));

    expect(await screen.findByTestId("memory-settings-confirm-dialog")).toBeInTheDocument();
    expect(systemMemorySettingsApi.update).not.toHaveBeenCalled();
  });

  it("confirming the risky-change dialog calls update() with the pending change", async () => {
    const user = userEvent.setup();
    render(<MemorySystemSettingsSection />);

    await screen.findByTestId("memory-system-settings-section");
    await user.selectOptions(screen.getByTestId("memory-settings-backend"), "honcho");
    await user.click(screen.getByTestId("memory-settings-save-btn"));

    const dialog = await screen.findByTestId("memory-settings-confirm-dialog");
    await user.click(screen.getByTestId("memory-settings-confirm-btn"));

    await waitFor(() => {
      expect(systemMemorySettingsApi.update).toHaveBeenCalledWith({ memory_backend: "honcho" });
    });
    await waitFor(() => {
      expect(screen.queryByTestId("memory-settings-confirm-dialog")).not.toBeInTheDocument();
    });
    void dialog;
  });

  it("changing a non-risky field (honcho_api_key) saves without a confirm dialog", async () => {
    const user = userEvent.setup();
    render(<MemorySystemSettingsSection />);

    await screen.findByTestId("memory-system-settings-section");
    await user.type(screen.getByTestId("memory-settings-honcho-api-key"), "new-secret");
    await user.click(screen.getByTestId("memory-settings-save-btn"));

    await waitFor(() => {
      expect(systemMemorySettingsApi.update).toHaveBeenCalledWith({ honcho_api_key: "new-secret" });
    });
    expect(screen.queryByTestId("memory-settings-confirm-dialog")).not.toBeInTheDocument();
  });

  it("reset button calls reset() after confirming the browser confirm dialog", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<MemorySystemSettingsSection />);

    await screen.findByTestId("memory-system-settings-section");
    await user.click(screen.getByTestId("memory-settings-reset-btn"));

    await waitFor(() => {
      expect(systemMemorySettingsApi.reset).toHaveBeenCalled();
    });
  });

  it("does not call reset() when the browser confirm dialog is dismissed", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<MemorySystemSettingsSection />);

    await screen.findByTestId("memory-system-settings-section");
    await user.click(screen.getByTestId("memory-settings-reset-btn"));

    expect(systemMemorySettingsApi.reset).not.toHaveBeenCalled();
  });
});
