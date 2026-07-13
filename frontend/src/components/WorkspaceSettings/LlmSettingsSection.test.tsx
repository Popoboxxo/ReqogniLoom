/**
 * Tests for LlmSettingsSection (REQ-L2-LLM-001).
 *
 * Verifies:
 * - form renders after the settings load
 * - the api_key field is type=password
 * - base_url input only appears for the ollama provider
 * - Save omits api_key when the user did not type a new one (write-only field)
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
});
