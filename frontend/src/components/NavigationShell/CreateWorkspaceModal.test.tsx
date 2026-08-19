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
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { i18n } from "../../i18n/index";
import { CreateWorkspaceModal } from "./CreateWorkspaceModal";
import { workspacesApi } from "../../api/workspaces";

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

/**
 * BUG-08 (Systemaudit 2026-08-18, §4, Hoch) — a failed client-side validation
 * (empty required "Name" field) previously surfaced only as a text banner
 * elsewhere in the dialog; the input itself carried no error indication at
 * all (no border color, no icon, no `aria-invalid`), so a screen-reader user
 * had no association between the field and the message, and a sighted user
 * scanning the field itself saw nothing wrong with it.
 */
describe("CreateWorkspaceModal — field-level validation error visibility (BUG-08)", () => {
  it("marks the name input as invalid (border/icon/aria) when submitted empty", async () => {
    const user = userEvent.setup();
    render(<CreateWorkspaceModal isOpen={true} onClose={vi.fn()} onCreated={vi.fn()} />);

    const nameInput = screen.getByTestId("new-workspace-name");
    // Not yet touched — no error state before the first submit attempt.
    expect(nameInput).toHaveAttribute("aria-invalid", "false");

    await user.click(screen.getByTestId("new-workspace-submit"));

    // The field itself must carry the error, not just a page-level banner:
    // aria-invalid (screen readers), a dedicated field-error element the
    // input references via aria-describedby (text), and a visible marker
    // class that renders an icon + red border (see .module.css).
    expect(nameInput).toHaveAttribute("aria-invalid", "true");
    const describedBy = nameInput.getAttribute("aria-describedby");
    expect(describedBy).toBeTruthy();

    const fieldError = screen.getByTestId("new-workspace-name-field-error");
    expect(fieldError).toHaveAttribute("id", describedBy);
    expect(fieldError).toHaveAttribute("role", "alert");
    // Icon (non-text, aria-hidden) + text — WCAG: color alone is not enough.
    expect(fieldError.querySelector('[aria-hidden="true"]')).not.toBeNull();
    expect(fieldError.textContent).toMatch(/name/i);
  });

  it("clears the field-level invalid state once the user starts typing a name", async () => {
    const user = userEvent.setup();
    render(<CreateWorkspaceModal isOpen={true} onClose={vi.fn()} onCreated={vi.fn()} />);

    await user.click(screen.getByTestId("new-workspace-submit"));
    expect(screen.getByTestId("new-workspace-name")).toHaveAttribute("aria-invalid", "true");

    await user.type(screen.getByTestId("new-workspace-name"), "My Workspace");

    expect(screen.getByTestId("new-workspace-name")).toHaveAttribute("aria-invalid", "false");
    expect(screen.queryByTestId("new-workspace-name-field-error")).not.toBeInTheDocument();
  });

  /**
   * F-01 / F-03 (code review, 2026-08-19) — an empty-name submit used to set
   * BOTH the page-level `createError` banner AND the field marker with the
   * identical message: a screen reader announced "Name is required" twice,
   * and once the field was fixed the (stale) banner kept contradicting it.
   * Client-side validation must surface at the field ONLY.
   */
  it("never shows the page-level banner for a client-side empty-name error (F-03)", async () => {
    const user = userEvent.setup();
    render(<CreateWorkspaceModal isOpen={true} onClose={vi.fn()} onCreated={vi.fn()} />);

    await user.click(screen.getByTestId("new-workspace-submit"));

    expect(screen.getByTestId("new-workspace-name")).toHaveAttribute("aria-invalid", "true");
    expect(screen.queryByTestId("create-workspace-error")).not.toBeInTheDocument();
    expect(screen.getAllByRole("alert")).toHaveLength(1);
  });

  it("clears a stale banner from a previous server-side rejection as soon as the name is edited (F-01)", async () => {
    vi.mocked(workspacesApi.create).mockRejectedValueOnce({
      error: { message: "A workspace with this name already exists." },
    });
    const user = userEvent.setup();
    render(<CreateWorkspaceModal isOpen={true} onClose={vi.fn()} onCreated={vi.fn()} />);

    await user.type(screen.getByTestId("new-workspace-name"), "Duplicate");
    await user.click(screen.getByTestId("new-workspace-submit"));

    const banner = await screen.findByTestId("create-workspace-error");
    expect(banner).toHaveTextContent("A workspace with this name already exists.");

    // The user edits the name — the banner describes a *previous* attempt
    // and must not keep contradicting the field being corrected.
    await user.type(screen.getByTestId("new-workspace-name"), " v2");

    await waitFor(() => {
      expect(screen.queryByTestId("create-workspace-error")).not.toBeInTheDocument();
    });
  });
});
