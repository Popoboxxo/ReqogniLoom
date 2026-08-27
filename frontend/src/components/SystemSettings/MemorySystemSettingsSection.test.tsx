import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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
      memory_backend: "pgvector",
      memory_backend_is_override: true,
    });

    render(<MemorySystemSettingsSection />);

    expect(await screen.findByTestId("embedding-provider-override-badge")).toBeInTheDocument();
    expect(screen.getByTestId("memory-backend-override-badge")).toBeInTheDocument();
  });

  it("offers openai as a selectable embedding provider and does NOT offer the honcho backend", async () => {
    render(<MemorySystemSettingsSection />);

    await screen.findByTestId("memory-system-settings-section");
    const providerOptions = Array.from(
      screen.getByTestId("memory-settings-embedding-provider").querySelectorAll("option")
    ).map((o) => o.value);
    expect(providerOptions).toEqual(["sentence-transformers", "ollama", "openai", "mock"]);

    // C-2: only backends that are really registered on the server may be
    // offered — picking an unregistered one breaks memory deployment-wide.
    // "honcho" qualifies now that HonchoMemoryBackend is fully implemented.
    // Keep in sync with SystemMemorySettingsWriteSerializer.memory_backend.
    const backendOptions = Array.from(
      screen.getByTestId("memory-settings-backend").querySelectorAll("option")
    ).map((o) => o.value);
    expect(backendOptions).toEqual(["pgvector", "honcho"]);
  });

  it("renders the 4 connection-detail fields with their loaded effective values", async () => {
    vi.mocked(systemMemorySettingsApi.get).mockResolvedValue({
      ...SETTINGS,
      embedding_model_name: "all-MiniLM-L6-v2",
      ollama_base_url: "http://ollama:11434",
      embedding_timeout: 30,
      honcho_base_url: "http://honcho:8000",
    });

    render(<MemorySystemSettingsSection />);

    await screen.findByTestId("memory-system-settings-section");
    expect(screen.getByTestId("memory-settings-embedding-model-name")).toHaveValue(
      "all-MiniLM-L6-v2"
    );
    expect(screen.getByTestId("memory-settings-ollama-base-url")).toHaveValue(
      "http://ollama:11434"
    );
    expect(screen.getByTestId("memory-settings-embedding-timeout")).toHaveValue(30);
    expect(screen.getByTestId("memory-settings-honcho-base-url")).toHaveValue(
      "http://honcho:8000"
    );
  });

  it("shows override badges for the 4 connection-detail fields when overridden", async () => {
    vi.mocked(systemMemorySettingsApi.get).mockResolvedValue({
      ...SETTINGS,
      embedding_model_name_is_override: true,
      ollama_base_url_is_override: true,
      embedding_timeout_is_override: true,
      honcho_base_url_is_override: true,
    });

    render(<MemorySystemSettingsSection />);

    expect(await screen.findByTestId("embedding-model-name-override-badge")).toBeInTheDocument();
    expect(screen.getByTestId("ollama-base-url-override-badge")).toBeInTheDocument();
    expect(screen.getByTestId("embedding-timeout-override-badge")).toBeInTheDocument();
    expect(screen.getByTestId("honcho-base-url-override-badge")).toBeInTheDocument();
  });

  it("changing the 4 connection-detail fields stages them and saves without a confirm dialog", async () => {
    const user = userEvent.setup();
    render(<MemorySystemSettingsSection />);

    await screen.findByTestId("memory-system-settings-section");
    await user.type(
      screen.getByTestId("memory-settings-embedding-model-name"),
      "all-MiniLM-L6-v2"
    );
    await user.type(screen.getByTestId("memory-settings-ollama-base-url"), "http://ollama:11434");
    // A single direct value change (e.g. paste, or the browser's numeric
    // stepper) rather than clear()+type() char-by-char: clearing a
    // controlled number input to "" round-trips through `undefined` (the
    // "no pending change" sentinel), which the display's `?? settings...`
    // fallback then redraws as the still-loaded effective value — so
    // simulating a full backspace-then-retype here would concatenate onto
    // that redrawn value instead of really starting from empty.
    fireEvent.change(screen.getByTestId("memory-settings-embedding-timeout"), {
      target: { value: "45" },
    });
    await user.type(screen.getByTestId("memory-settings-honcho-base-url"), "http://honcho:8000");
    await user.click(screen.getByTestId("memory-settings-save-btn"));

    expect(screen.queryByTestId("memory-settings-confirm-dialog")).not.toBeInTheDocument();
    await waitFor(() => {
      expect(systemMemorySettingsApi.update).toHaveBeenCalledWith({
        embedding_model_name: "all-MiniLM-L6-v2",
        ollama_base_url: "http://ollama:11434",
        embedding_timeout: 45,
        honcho_base_url: "http://honcho:8000",
      });
    });
  });

  it("clearing an overridden text field stages null (clear the override), not an empty string", async () => {
    const user = userEvent.setup();
    vi.mocked(systemMemorySettingsApi.get).mockResolvedValue({
      ...SETTINGS,
      ollama_base_url: "http://ollama:11434",
      ollama_base_url_is_override: true,
    });
    render(<MemorySystemSettingsSection />);

    await screen.findByTestId("memory-system-settings-section");
    const input = screen.getByTestId("memory-settings-ollama-base-url");
    await user.clear(input);
    // The cleared input must stay empty, not redraw the loaded value.
    expect(input).toHaveValue("");

    await user.click(screen.getByTestId("memory-settings-save-btn"));
    await waitFor(() => {
      expect(systemMemorySettingsApi.update).toHaveBeenCalledWith({ ollama_base_url: null });
    });
  });

  it("clearing the honcho_api_key field back to empty removes it from the pending change instead of staging a no-op empty string", async () => {
    const user = userEvent.setup();
    render(<MemorySystemSettingsSection />);

    await screen.findByTestId("memory-system-settings-section");
    const input = screen.getByTestId("memory-settings-honcho-api-key");
    await user.type(input, "temp-secret");
    expect(screen.getByTestId("memory-settings-save-btn")).toBeEnabled();

    await user.clear(input);
    expect(screen.getByTestId("memory-settings-save-btn")).toBeDisabled();
  });

  it("switching the memory backend to honcho stages the change and confirms before saving", async () => {
    const user = userEvent.setup();
    render(<MemorySystemSettingsSection />);

    await screen.findByTestId("memory-system-settings-section");
    await user.selectOptions(screen.getByTestId("memory-settings-backend"), "honcho");
    await user.click(screen.getByTestId("memory-settings-save-btn"));

    // Swapping the memory backend repoints every read/write at another store,
    // so it must go through the same confirm gate as an embedding change.
    expect(await screen.findByTestId("memory-settings-confirm-dialog")).toBeInTheDocument();
    expect(systemMemorySettingsApi.update).not.toHaveBeenCalled();

    await user.click(screen.getByTestId("memory-settings-confirm-btn"));
    await waitFor(() => {
      expect(systemMemorySettingsApi.update).toHaveBeenCalledWith({ memory_backend: "honcho" });
    });
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
    // Staged via the embedding provider rather than the backend select; the
    // backend select has its own risky-change coverage below.
    await user.selectOptions(screen.getByTestId("memory-settings-embedding-provider"), "openai");
    await user.click(screen.getByTestId("memory-settings-save-btn"));

    const dialog = await screen.findByTestId("memory-settings-confirm-dialog");
    await user.click(screen.getByTestId("memory-settings-confirm-btn"));

    await waitFor(() => {
      expect(systemMemorySettingsApi.update).toHaveBeenCalledWith({
        embedding_provider: "openai",
      });
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
