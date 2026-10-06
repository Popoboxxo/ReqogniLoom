/**
 * ARCH-L1-001 ReactFrontend — MemoryAskPanel unit test (RFC #1002 #1155 A1).
 *
 * Pins the F9 contract of the panel: a successful answer, a degraded answer
 * and an empty answer are three visibly distinct states, a transport failure
 * is a fourth, and a blank question never leaves the client.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { memoryApi, type MemoryAnswer } from "../../api/memory";
import { MemoryAskPanel } from "./MemoryAskPanel";

vi.mock("../../api/memory", () => ({
  memoryApi: { ask: vi.fn() },
  MEMORY_REASONING_LEVELS: ["minimal", "low", "medium", "high", "max"],
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    // Mirrors the real `t(key, "default")` / `t(key, { defaultValue })`
    // shapes the component uses. `ask.*` labels carry no inline default, so
    // they resolve to the key — every assertion below therefore keys off the
    // `data-testid` contract, not on localised copy.
    t: (key: string, options?: unknown) => {
      if (typeof options === "string") return options;
      if (options && typeof options === "object") {
        const opts = options as Record<string, unknown>;
        const template =
          typeof opts.defaultValue === "string" ? opts.defaultValue : key;
        return template.replace(/\{\{(\w+)\}\}/g, (match, name: string) =>
          name in opts ? String(opts[name]) : match
        );
      }
      return key;
    },
  }),
}));

const WS = "ws-1";
const ART = "art-1";

function answer(overrides: Partial<MemoryAnswer> = {}): MemoryAnswer {
  return {
    answer: "The team chose OAuth2.",
    generated_at: "2026-09-01T12:00:00Z",
    backend: "honcho",
    degraded: false,
    detail: "",
    ...overrides,
  };
}

async function ask(question = "what about auth?"): Promise<void> {
  const user = userEvent.setup();
  await user.type(screen.getByTestId("memory-ask-input"), question);
  await user.click(screen.getByTestId("memory-ask-submit"));
}

describe("MemoryAskPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(memoryApi.ask).mockResolvedValue(answer());
  });

  it("renders the engine's answer for a successful ask", async () => {
    render(<MemoryAskPanel workspaceId={WS} />);

    await ask();

    expect(await screen.findByTestId("memory-ask-answer")).toHaveTextContent(
      "The team chose OAuth2."
    );
    expect(memoryApi.ask).toHaveBeenCalledWith(WS, {
      query: "what about auth?",
      artifactId: undefined,
      reasoningLevel: undefined,
    });
    expect(screen.queryByTestId("memory-ask-error")).not.toBeInTheDocument();
  });

  it("renders degraded as a state distinct from an empty answer", async () => {
    vi.mocked(memoryApi.ask).mockResolvedValue(
      answer({ answer: "", degraded: true, detail: "engine_error:Timeout" })
    );
    render(<MemoryAskPanel workspaceId={WS} />);

    await ask();

    expect(await screen.findByTestId("memory-ask-degraded")).toBeInTheDocument();
    expect(screen.getByTestId("memory-ask-detail")).toBeInTheDocument();
    // Degraded must never be folded into the benign "nothing to say" state.
    expect(screen.queryByTestId("memory-ask-empty")).not.toBeInTheDocument();
    expect(screen.queryByTestId("memory-ask-answer")).not.toBeInTheDocument();
  });

  it("renders an empty answer distinct from degraded", async () => {
    vi.mocked(memoryApi.ask).mockResolvedValue(
      answer({ answer: "", degraded: false, detail: "" })
    );
    render(<MemoryAskPanel workspaceId={WS} />);

    await ask();

    expect(await screen.findByTestId("memory-ask-empty")).toBeInTheDocument();
    expect(screen.queryByTestId("memory-ask-degraded")).not.toBeInTheDocument();
    expect(screen.queryByTestId("memory-ask-detail")).not.toBeInTheDocument();
  });

  it("surfaces a transport failure as an error, not as an empty answer", async () => {
    vi.mocked(memoryApi.ask).mockRejectedValue({ error: { message: "boom" } });
    render(<MemoryAskPanel workspaceId={WS} />);

    await ask();

    expect(await screen.findByTestId("memory-ask-error")).toHaveTextContent("boom");
    expect(screen.queryByTestId("memory-ask-result")).not.toBeInTheDocument();
  });

  it("refuses a blank question and sends no request", async () => {
    render(<MemoryAskPanel workspaceId={WS} />);

    // The submit button is disabled while blank; Ctrl+Enter is the reachable
    // path that must explain why instead of silently doing nothing.
    fireEvent.keyDown(screen.getByTestId("memory-ask-input"), {
      key: "Enter",
      ctrlKey: true,
    });

    expect(await screen.findByTestId("memory-ask-validation")).toBeInTheDocument();
    expect(memoryApi.ask).not.toHaveBeenCalled();
  });

  it("forwards the selected reasoning level", async () => {
    const user = userEvent.setup();
    render(<MemoryAskPanel workspaceId={WS} />);

    await user.selectOptions(screen.getByTestId("memory-ask-reasoning"), "high");
    await ask();

    await waitFor(() => {
      expect(memoryApi.ask).toHaveBeenCalledWith(
        WS,
        expect.objectContaining({ reasoningLevel: "high" })
      );
    });
  });

  it("passes the artifact id through when mounted for an artifact", async () => {
    render(<MemoryAskPanel workspaceId={WS} artifactId={ART} />);

    await ask();

    await waitFor(() => {
      expect(memoryApi.ask).toHaveBeenCalledWith(
        WS,
        expect.objectContaining({ artifactId: ART })
      );
    });
  });
});
