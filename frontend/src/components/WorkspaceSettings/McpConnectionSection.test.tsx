/**
 * Tests for McpConnectionSection (workspace MCP connection info).
 *
 * Verifies:
 * - workspace name and id render
 * - both MCP endpoint URLs are derived from the origin (not hardcoded)
 * - the workspace_id hint (explicit tools/call parameter) is present
 * - copy-to-clipboard writes the right value and confirms
 * - the in-app link to the Personal Access Tokens page points at /profile
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { McpConnectionSection } from "./McpConnectionSection";

vi.mock("react-i18next", () => {
  const t = (_key: string, fallback?: unknown): string =>
    typeof fallback === "string" ? fallback : _key;
  return { useTranslation: () => ({ t }) };
});

const WS_ID = "11111111-1111-1111-1111-111111111111";
const WS_NAME = "Demo Workspace";
const ORIGIN = "https://reqlo.example.com";

function renderSection(): void {
  render(
    <MemoryRouter>
      <McpConnectionSection
        workspaceId={WS_ID}
        workspaceName={WS_NAME}
        origin={ORIGIN}
      />
    </MemoryRouter>,
  );
}

describe("McpConnectionSection", () => {
  const writeText = vi.fn().mockResolvedValue(undefined);

  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    });
  });

  it("renders the workspace name and id", () => {
    renderSection();
    expect(
      screen.getByTestId("mcp-copy-workspace-name-value"),
    ).toHaveTextContent(WS_NAME);
    expect(screen.getByTestId("mcp-copy-workspace-id-value")).toHaveTextContent(
      WS_ID,
    );
  });

  it("shows both MCP endpoint URLs built from the current origin", () => {
    renderSection();
    expect(
      screen.getByTestId("mcp-copy-http-endpoint-value"),
    ).toHaveTextContent(`${ORIGIN}/mcp/`);
    expect(screen.getByTestId("mcp-copy-sse-endpoint-value")).toHaveTextContent(
      `${ORIGIN}/mcp/sse/`,
    );
  });

  it("explains that workspace_id must be passed explicitly on tool calls", () => {
    renderSection();
    expect(screen.getByTestId("mcp-workspace-id-hint")).toHaveTextContent(
      /workspace_id/,
    );
  });

  it("copies the workspace id to the clipboard and confirms", async () => {
    renderSection();
    const button = screen.getByTestId("mcp-copy-workspace-id");
    expect(button).toHaveTextContent("Kopieren");

    await userEvent.click(button);

    expect(writeText).toHaveBeenCalledWith(WS_ID);
    expect(button).toHaveTextContent("Kopiert");
  });

  it("copies the SSE endpoint URL", async () => {
    renderSection();
    await userEvent.click(screen.getByTestId("mcp-copy-sse-endpoint"));
    expect(writeText).toHaveBeenCalledWith(`${ORIGIN}/mcp/sse/`);
  });

  it("copies an mcpServers config snippet carrying the X-API-Key header", async () => {
    renderSection();
    await userEvent.click(screen.getByTestId("mcp-copy-config"));

    const [snippet] = writeText.mock.calls[0] as [string];
    const parsed = JSON.parse(snippet) as {
      mcpServers: Record<string, { url: string; headers: Record<string, string> }>;
    };
    expect(parsed.mcpServers.reqogniloom.url).toBe(`${ORIGIN}/mcp/sse/`);
    expect(parsed.mcpServers.reqogniloom.headers["X-API-Key"]).toContain(
      "reqlo_",
    );
  });

  it("links to the Personal Access Tokens page in the profile", () => {
    renderSection();
    expect(
      screen.getByTestId("mcp-personal-access-tokens-link"),
    ).toHaveAttribute("href", "/profile");
  });

  it("survives an unavailable clipboard", async () => {
    Object.defineProperty(navigator, "clipboard", {
      value: undefined,
      configurable: true,
    });
    renderSection();
    await userEvent.click(screen.getByTestId("mcp-copy-workspace-id"));
    // No confirmation, but also no crash — the value stays selectable.
    expect(screen.getByTestId("mcp-copy-workspace-id")).toHaveTextContent(
      "Kopieren",
    );
  });
});
