/**
 * Regression coverage for #420 — the workspace-create dialog rendered raw
 * i18n keys (`workspace.create.title`, `workspace.create.namePlaceholder`,
 * `workspace.create.preset`, `workspace.create.language`,
 * `workspace.create.cancel`) instead of translated text, because those keys
 * never existed in de.json/en.json. The component now reuses the already
 * fully-translated `workspaceCreate.*` namespace instead.
 *
 * Uses the real i18n resources (not a mocked `t`) so a future regression —
 * a key drifting back out of sync with the JSON files — actually fails this
 * test instead of being silently swallowed by an identity-function mock.
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { i18n } from "../../i18n/index";
import { CreateWorkspaceModal } from "./CreateWorkspaceModal";

vi.mock("../../api/workspaces", () => ({
  workspacesApi: {
    create: vi.fn(),
  },
}));

describe("CreateWorkspaceModal — i18n (#420)", () => {
  it("renders translated German text, not raw workspace.create.* keys", async () => {
    await i18n.changeLanguage("de");

    render(
      <CreateWorkspaceModal isOpen={true} onClose={vi.fn()} onCreated={vi.fn()} />
    );

    // Dialog title (aria-labelledby) must be the translated string.
    expect(screen.getByText("Neuen Workspace erstellen")).toBeInTheDocument();
    expect(screen.queryByText("workspace.create.title")).not.toBeInTheDocument();

    expect(screen.getByTestId("create-workspace-cancel")).toHaveTextContent("Abbrechen");
    expect(screen.queryByText("workspace.create.cancel")).not.toBeInTheDocument();

    expect(screen.getAllByText("Workspace-Name").length).toBeGreaterThan(0);
    expect(screen.queryByText("workspace.create.namePlaceholder")).not.toBeInTheDocument();
    expect(screen.getByTestId("new-workspace-name")).toHaveAttribute(
      "placeholder",
      "Workspace-Name"
    );

    expect(screen.getByText("Preset")).toBeInTheDocument();
    expect(screen.queryByText("workspace.create.preset")).not.toBeInTheDocument();

    expect(screen.getByText("Sprache")).toBeInTheDocument();
    expect(screen.queryByText("workspace.create.language")).not.toBeInTheDocument();
  });

  it("renders translated English text when the active language is English", async () => {
    await i18n.changeLanguage("en");

    render(
      <CreateWorkspaceModal isOpen={true} onClose={vi.fn()} onCreated={vi.fn()} />
    );

    expect(screen.getByText("Create new workspace")).toBeInTheDocument();
    expect(screen.getByTestId("create-workspace-cancel")).toHaveTextContent("Cancel");

    await i18n.changeLanguage("de");
  });
});
