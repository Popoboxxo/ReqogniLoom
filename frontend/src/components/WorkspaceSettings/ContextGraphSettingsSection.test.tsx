/**
 * Tests for ContextGraphSettingsSection (Issue #377, Task 9).
 *
 * Verifies:
 * - status renders after load (node_count/edge_count/last_projected_at)
 * - toggling the checkbox calls update() with the current enabled_generators
 * - a last_error is rendered when present
 * - "Rebuild now" calls the rebuild endpoint and shows a queued confirmation
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ContextGraphSettingsSection } from "./ContextGraphSettingsSection";
import * as contextGraphSettingsModule from "../../api/context-graph-settings";

vi.mock("../../api/context-graph-settings");
vi.mock("react-i18next", () => {
  const t = (_key: string, fallback?: string): string => fallback ?? _key;
  return { useTranslation: () => ({ t }) };
});

const WORKSPACE_ID = "11111111-1111-1111-1111-111111111111";

describe("ContextGraphSettingsSection (Issue #377, Task 9)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(contextGraphSettingsModule.contextGraphSettingsApi.get).mockResolvedValue({
      enabled: false,
      enabled_generators: [],
      provider: "embedded",
      last_projected_at: null,
      last_refresh_at: null,
      last_error: "",
      node_count: 0,
      edge_count: 0,
    });
    vi.mocked(contextGraphSettingsModule.contextGraphSettingsApi.update).mockResolvedValue({
      enabled: true,
      enabled_generators: ["glossary"],
      provider: "embedded",
      last_projected_at: null,
      last_refresh_at: null,
      last_error: "",
      node_count: 0,
      edge_count: 0,
    });
    vi.mocked(contextGraphSettingsModule.contextGraphSettingsApi.rebuild).mockResolvedValue(
      undefined
    );
  });

  it("renders status once settings are loaded", async () => {
    render(<ContextGraphSettingsSection workspaceId={WORKSPACE_ID} />);
    await waitFor(() =>
      expect(screen.getByTestId("context-graph-enabled-toggle")).toBeInTheDocument()
    );
    expect(screen.getByTestId("context-graph-node-count")).toHaveTextContent("0");
    expect(screen.getByTestId("context-graph-edge-count")).toHaveTextContent("0");
    expect(screen.getByTestId("context-graph-last-projected-at")).toHaveTextContent("Never");
  });

  it("toggling the checkbox calls update() with enabled=true and a default generator", async () => {
    render(<ContextGraphSettingsSection workspaceId={WORKSPACE_ID} />);
    const toggle = await screen.findByTestId("context-graph-enabled-toggle");
    await userEvent.click(toggle);

    await waitFor(() =>
      expect(contextGraphSettingsModule.contextGraphSettingsApi.update).toHaveBeenCalledWith(
        WORKSPACE_ID,
        { enabled: true, enabled_generators: ["glossary"] }
      )
    );
    expect(await screen.findByTestId("context-graph-settings-saved")).toBeInTheDocument();
  });

  it("renders last_error when present", async () => {
    vi.mocked(contextGraphSettingsModule.contextGraphSettingsApi.get).mockResolvedValue({
      enabled: true,
      enabled_generators: ["glossary"],
      provider: "embedded",
      last_projected_at: "2026-08-19T12:00:00Z",
      last_refresh_at: null,
      last_error: "boom",
      node_count: 3,
      edge_count: 1,
    });
    render(<ContextGraphSettingsSection workspaceId={WORKSPACE_ID} />);
    expect(await screen.findByTestId("context-graph-last-error")).toHaveTextContent("boom");
  });

  it("Rebuild now calls the rebuild endpoint and shows a queued confirmation", async () => {
    render(<ContextGraphSettingsSection workspaceId={WORKSPACE_ID} />);
    const button = await screen.findByTestId("context-graph-rebuild-button");
    await userEvent.click(button);

    await waitFor(() =>
      expect(contextGraphSettingsModule.contextGraphSettingsApi.rebuild).toHaveBeenCalledWith(
        WORKSPACE_ID
      )
    );
    expect(await screen.findByTestId("context-graph-rebuild-queued")).toBeInTheDocument();
  });
});
