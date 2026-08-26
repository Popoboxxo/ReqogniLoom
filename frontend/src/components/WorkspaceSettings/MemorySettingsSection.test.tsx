import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemorySettingsSection } from "./MemorySettingsSection";
import { memorySettingsApi } from "../../api/memory-settings";

vi.mock("../../api/memory-settings", () => ({
  memorySettingsApi: { get: vi.fn(), update: vi.fn() },
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (_key: string, fallback?: string) => fallback ?? _key }),
}));

describe("MemorySettingsSection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows the current enabled state", async () => {
    vi.mocked(memorySettingsApi.get).mockResolvedValue({ enabled: true });
    render(<MemorySettingsSection workspaceId="ws-1" />);
    const toggle = await screen.findByTestId("memory-settings-toggle");
    expect(toggle).toBeChecked();
    expect(memorySettingsApi.get).toHaveBeenCalledWith("ws-1");
  });

  it("reflects a disabled state from the backend", async () => {
    vi.mocked(memorySettingsApi.get).mockResolvedValue({ enabled: false });
    render(<MemorySettingsSection workspaceId="ws-1" />);
    const toggle = await screen.findByTestId("memory-settings-toggle");
    expect(toggle).not.toBeChecked();
  });

  it("toggling calls the update endpoint and shows the saved indicator", async () => {
    vi.mocked(memorySettingsApi.get).mockResolvedValue({ enabled: true });
    vi.mocked(memorySettingsApi.update).mockResolvedValue({ enabled: false });
    render(<MemorySettingsSection workspaceId="ws-1" />);
    const toggle = await screen.findByTestId("memory-settings-toggle");
    fireEvent.click(toggle);
    await waitFor(() => expect(memorySettingsApi.update).toHaveBeenCalledWith("ws-1", false));
    expect(await screen.findByTestId("memory-settings-saved")).toBeInTheDocument();
    expect(toggle).not.toBeChecked();
  });

  it("shows an error and reverts the toggle when the update fails (e.g. 403 for a viewer)", async () => {
    vi.mocked(memorySettingsApi.get).mockResolvedValue({ enabled: true });
    vi.mocked(memorySettingsApi.update).mockRejectedValue({
      error: { message: "editor or admin role required." },
    });
    render(<MemorySettingsSection workspaceId="ws-1" />);
    const toggle = await screen.findByTestId("memory-settings-toggle");
    fireEvent.click(toggle);
    expect(
      await screen.findByText("editor or admin role required.")
    ).toBeInTheDocument();
    await waitFor(() => expect(toggle).toBeChecked());
  });
});
