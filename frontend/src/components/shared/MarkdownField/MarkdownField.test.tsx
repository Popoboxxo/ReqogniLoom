/**
 * #1287 — <MarkdownField> resolves `ui.markdown.toolbar` and drives the
 * existing MarkdownPreview textarea (no second editor).
 *
 * The toolbar itself is presentational; what this suite pins is the resolution
 * rule (`auto` = three lines or more), that the formatting buttons write
 * through `onChange`, and that the toggle persists the **user** level via the Q1
 * preference route (asserted at the API-client boundary).
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "de" },
  }),
}));

vi.mock("../../../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "ws-1", name: "WS" } }),
  useOptionalWorkspace: () => ({
    activeWorkspace: { id: "ws-1", name: "WS" },
  }),
}));

vi.mock("../../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../api/client")>();
  return {
    ...actual,
    apiClient: { get: vi.fn(), patch: vi.fn() },
  };
});

import { apiClient } from "../../../api/client";
import { MarkdownField } from "./MarkdownField";

function effective(values: Record<string, unknown> = {}): void {
  vi.mocked(apiClient.get).mockResolvedValue({
    workspace_id: "ws-1",
    values: Object.fromEntries(
      Object.entries(values).map(([key, value]) => [
        key,
        { value, source: "user" },
      ])
    ),
  });
}

function renderField(
  value: string,
  onChange = vi.fn()
): { textarea: HTMLTextAreaElement; onChange: ReturnType<typeof vi.fn> } {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <MarkdownField id="field" value={value} onChange={onChange} />
    </QueryClientProvider>
  );
  return {
    textarea: screen.getByRole("textbox") as HTMLTextAreaElement,
    onChange,
  };
}

describe("MarkdownField (#1287)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    effective();
    vi.mocked(apiClient.patch).mockResolvedValue({
      scope: "user",
      workspace_id: null,
      values: {},
    });
  });

  it("hides the toolbar in auto mode for a single-line value", () => {
    renderField("one line");

    expect(screen.queryByTestId("md-toolbar")).not.toBeInTheDocument();
  });

  it("shows the toolbar in auto mode from three lines on", () => {
    renderField("one\ntwo\nthree");

    expect(screen.getByTestId("md-toolbar")).toBeInTheDocument();
    expect(screen.getByTestId("md-toolbar-bold")).toBeInTheDocument();
  });

  it("forces the toolbar on with the stored 'on' preference", async () => {
    effective({ "ui.markdown.toolbar": "on" });

    renderField("one line");

    expect(await screen.findByTestId("md-toolbar")).toBeInTheDocument();
  });

  it("formats the selection through the existing textarea", async () => {
    effective({ "ui.markdown.toolbar": "on" });
    const { textarea, onChange } = renderField("text");
    textarea.setSelectionRange(0, 4);

    fireEvent.click(await screen.findByTestId("md-toolbar-bold"));

    expect(onChange).toHaveBeenCalledWith("**text**");
  });

  it("writes the user-level preference when the toolbar is toggled off", async () => {
    renderField("one\ntwo\nthree");

    fireEvent.click(screen.getByTestId("md-toolbar-toggle"));

    await waitFor(() =>
      expect(apiClient.patch).toHaveBeenCalledWith(
        "/users/me/preference-values/",
        { values: { "ui.markdown.toolbar": "off" } }
      )
    );
  });

  it("hides the toolbar when the stored preference is 'off'", async () => {
    effective({ "ui.markdown.toolbar": "off" });

    renderField("one\ntwo\nthree");

    await waitFor(() =>
      expect(screen.queryByTestId("md-toolbar")).not.toBeInTheDocument()
    );
    expect(apiClient.get).toHaveBeenCalledWith(
      "/workspaces/ws-1/preference-values/effective/"
    );
    expect(screen.getByTestId("md-toolbar-toggle")).toBeInTheDocument();
  });
});
