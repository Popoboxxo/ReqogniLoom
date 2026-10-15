/**
 * #1266 — GlossaryReferenceSection switches the workspace reference mode.
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("react-i18next", () => {
  const t = (key: string, fallback?: string): string => fallback ?? key;
  return { useTranslation: () => ({ t }) };
});

vi.mock("../../api/workspaces", () => ({
  workspacesApi: { update: vi.fn() },
}));

import { GlossaryReferenceSection } from "./GlossaryReferenceSection";
import { workspacesApi } from "../../api/workspaces";

const WORKSPACE_ID = "22222222-2222-2222-2222-222222222222";

describe("GlossaryReferenceSection (#1266)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(workspacesApi.update).mockResolvedValue({} as never);
  });

  it("shows the current mode and persists a change, then reloads", async () => {
    const onSaved = vi.fn().mockResolvedValue(undefined);
    render(
      <GlossaryReferenceSection
        workspaceId={WORKSPACE_ID}
        mode="pinned"
        onSaved={onSaved}
      />
    );

    expect(screen.getByTestId("glossary-reference-mode-pinned")).toBeChecked();
    expect(screen.getByTestId("glossary-reference-mode-always_head")).not.toBeChecked();

    await userEvent.click(screen.getByTestId("glossary-reference-mode-always_head"));

    await waitFor(() =>
      expect(workspacesApi.update).toHaveBeenCalledWith(WORKSPACE_ID, {
        glossary_reference_mode: "always_head",
      })
    );
    expect(onSaved).toHaveBeenCalled();
    expect(await screen.findByTestId("glossary-reference-saved")).toBeInTheDocument();
  });

  it("does nothing when the already-active mode is re-selected", async () => {
    render(
      <GlossaryReferenceSection workspaceId={WORKSPACE_ID} mode="pinned" onSaved={vi.fn()} />
    );
    await userEvent.click(screen.getByTestId("glossary-reference-mode-pinned"));
    expect(workspacesApi.update).not.toHaveBeenCalled();
  });
});
