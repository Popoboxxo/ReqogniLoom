/**
 * Tests for LlmSettingsSection (REQ-L2-LLM-001).
 *
 * Verifies:
 * - form renders after the settings load
 * - the api_key field is type=password
 * - base_url input only appears for the ollama provider
 * - Save omits api_key when the user did not type a new one (write-only field)
 * - an unrecognized server-side provider is never silently replaced (#274)
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LlmSettingsSection } from "./LlmSettingsSection";
import * as llmSettingsModule from "../../api/llm-settings";

vi.mock("../../api/llm-settings");
vi.mock("react-i18next", () => {
  const t = (_key: string, fallback?: string): string => fallback ?? _key;
  return { useTranslation: () => ({ t }) };
});

describe("LlmSettingsSection (REQ-L2-LLM-001)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(llmSettingsModule.llmSettingsApi.get).mockResolvedValue({
      provider: "mock",
      base_url: "",
      model_name: "",
      api_key_is_set: false,
    });
    vi.mocked(llmSettingsModule.llmSettingsApi.update).mockResolvedValue({
      provider: "anthropic",
      base_url: "",
      model_name: "claude-x",
      api_key_is_set: true,
    });
    // Provide the real LLM_PROVIDERS constant (mock replaces the module).
    (llmSettingsModule as { LLM_PROVIDERS: readonly string[] }).LLM_PROVIDERS = [
      "anthropic",
      "openai",
      "ollama",
      "mock",
    ];
  });

  it("renders the form once settings are loaded", async () => {
    render(<LlmSettingsSection />);
    await waitFor(() =>
      expect(screen.getByTestId("llm-settings-save")).toBeInTheDocument()
    );
    expect(screen.getByTestId("llm-provider-select")).toBeInTheDocument();
    expect(screen.getByTestId("llm-model-name-input")).toBeInTheDocument();
  });

  it("renders the api_key field as a password input", async () => {
    render(<LlmSettingsSection />);
    const apiKeyInput = await screen.findByTestId("llm-api-key-input");
    expect(apiKeyInput).toHaveAttribute("type", "password");
  });

  it("shows the base_url input only for the ollama provider", async () => {
    render(<LlmSettingsSection />);
    await screen.findByTestId("llm-provider-select");
    expect(screen.queryByTestId("llm-base-url-input")).not.toBeInTheDocument();

    await userEvent.selectOptions(
      screen.getByTestId("llm-provider-select"),
      "ollama"
    );
    expect(screen.getByTestId("llm-base-url-input")).toBeInTheDocument();
  });

  it("omits api_key from the payload when left blank", async () => {
    render(<LlmSettingsSection />);
    const saveBtn = await screen.findByTestId("llm-settings-save");
    await userEvent.click(saveBtn);

    await waitFor(() =>
      expect(llmSettingsModule.llmSettingsApi.update).toHaveBeenCalled()
    );
    const payload = vi.mocked(llmSettingsModule.llmSettingsApi.update).mock
      .calls[0][0];
    expect(payload).not.toHaveProperty("api_key");
  });

  it("includes api_key in the payload when the user types one", async () => {
    render(<LlmSettingsSection />);
    const apiKeyInput = await screen.findByTestId("llm-api-key-input");
    await userEvent.type(apiKeyInput, "sk-new-secret");
    await userEvent.click(screen.getByTestId("llm-settings-save"));

    await waitFor(() =>
      expect(llmSettingsModule.llmSettingsApi.update).toHaveBeenCalled()
    );
    const payload = vi.mocked(llmSettingsModule.llmSettingsApi.update).mock
      .calls[0][0];
    expect(payload).toMatchObject({ api_key: "sk-new-secret" });
  });

  // -------------------------------------------------------------------------
  // Unknown server-side provider (#274)
  //
  // `LLM_PROVIDERS` is stubbed above WITHOUT "opencode_go", reproducing a
  // frontend build that predates a backend enum value.
  // -------------------------------------------------------------------------
  describe("unrecognized server provider (#274)", () => {
    beforeEach(() => {
      vi.mocked(llmSettingsModule.llmSettingsApi.get).mockResolvedValue({
        provider: "opencode_go" as never,
        base_url: "",
        model_name: "gpt-oss",
        api_key_is_set: true,
      });
    });

    it("renders the server value instead of falling back to the first option", async () => {
      render(<LlmSettingsSection />);
      const select = (await screen.findByTestId(
        "llm-provider-select"
      )) as HTMLSelectElement;
      expect(select.value).toBe("opencode_go");
      expect(select.value).not.toBe("anthropic");
      expect(
        screen.getByTestId("llm-provider-unsupported-hint")
      ).toBeInTheDocument();
    });

    it("omits provider from the payload when the user did not change it", async () => {
      render(<LlmSettingsSection />);
      const saveBtn = await screen.findByTestId("llm-settings-save");
      await userEvent.click(saveBtn);

      await waitFor(() =>
        expect(llmSettingsModule.llmSettingsApi.update).toHaveBeenCalled()
      );
      const payload = vi.mocked(llmSettingsModule.llmSettingsApi.update).mock
        .calls[0][0];
      // Neither the wrong value nor the unknown one is echoed back: leaving
      // `provider` out keeps the working server-side configuration intact.
      expect(payload).not.toHaveProperty("provider");
      expect(payload).toMatchObject({ model_name: "gpt-oss" });
    });

    it("sends the provider once the user explicitly picks a known one", async () => {
      render(<LlmSettingsSection />);
      const select = await screen.findByTestId("llm-provider-select");
      await userEvent.selectOptions(select, "ollama");
      expect(
        screen.queryByTestId("llm-provider-unsupported-hint")
      ).not.toBeInTheDocument();

      await userEvent.click(screen.getByTestId("llm-settings-save"));
      await waitFor(() =>
        expect(llmSettingsModule.llmSettingsApi.update).toHaveBeenCalled()
      );
      const payload = vi.mocked(llmSettingsModule.llmSettingsApi.update).mock
        .calls[0][0];
      expect(payload).toMatchObject({ provider: "ollama" });
    });
  });

  it("exposes opencode_go as a selectable provider", async () => {
    const actual = await vi.importActual<typeof llmSettingsModule>(
      "../../api/llm-settings"
    );
    expect(actual.LLM_PROVIDERS).toContain("opencode_go");
  });
});
