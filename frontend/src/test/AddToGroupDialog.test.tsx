/**
 * G2 (spec 2026-11-08 §4.5.3, plan 2026-11-15 G2.1) — `AddToGroupDialog`.
 *
 * The dialog is the requirement-side half of group membership: it starts from
 * one requirement and lists the workspace's groups, so assigning does not
 * require finding the requirement again by search inside every group.
 *
 * Contract covered here:
 *  - an existing membership renders **checked and disabled** (unticking would
 *    be a removal, which belongs to the group manager),
 *  - ticking a checkbox hands the requirement's **entity id** to `onAdd` — the
 *    id every membership write keys on (`requirement_artifact_id` is a
 *    different id space),
 *  - a rejected add keeps the dialog open and announces the failure via
 *    `role="alert"`,
 *  - an empty group list keeps the *existing* create path reachable instead of
 *    dead-ending in a hint.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { AddToGroupDialog } from "../components/RequirementEditors/AddToGroupDialog";
import type { GroupManagerGroup } from "../components/RequirementEditors/useRequirementGroups";
import { resolveLocaleKey } from "./i18n-test-helpers";

/** Real German copy, with `{{placeholder}}` interpolation (the dialog title names the requirement). */
function t(key: string, opts?: Record<string, unknown>): string {
  const template = resolveLocaleKey(key) ?? key;
  if (!opts) return template;
  return template.replace(/\{\{(\w+)\}\}/g, (_match, name: string) =>
    String(opts[name] ?? "")
  );
}

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t }),
}));

const REQ_ID = "req-1";

const GROUPS: GroupManagerGroup[] = [
  {
    id: "grp-1",
    title: "Brake system",
    description: "",
    members: [{ requirementId: REQ_ID, label: "Brake pressure", uid: "REQ-001" }],
  },
  {
    id: "grp-2",
    title: "Chassis",
    description: "Body and frame",
    members: [],
  },
];

function renderDialog(overrides: Partial<Parameters<typeof AddToGroupDialog>[0]> = {}) {
  const props = {
    requirementId: REQ_ID,
    requirementTitle: "Brake pressure",
    groups: GROUPS,
    onAdd: vi.fn().mockResolvedValue(undefined),
    onClose: vi.fn(),
    onCreateGroup: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };
  const view = render(<AddToGroupDialog {...props} />);
  return { ...view, props };
}

describe("AddToGroupDialog (G2)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders inside the shared dialog and names the requirement", () => {
    renderDialog();

    const dialog = screen.getByTestId("add-to-group-dialog");
    expect(dialog).toHaveAttribute("role", "dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(
      within(dialog).getByText("Zu Gruppe hinzufügen: Brake pressure"),
    ).toBeInTheDocument();
  });

  it("existing_membership_is_disabled_and_checked", () => {
    renderDialog();

    const memberCheckbox = screen.getByTestId("group-add-member-grp-1");
    expect(memberCheckbox).toBeChecked();
    expect(memberCheckbox).toBeDisabled();
    expect(screen.getByTestId("group-add-ismember-grp-1")).toBeInTheDocument();

    // A group the requirement is *not* in stays operable — the dialog's whole
    // point is assigning to it.
    const openCheckbox = screen.getByTestId("group-add-member-grp-2");
    expect(openCheckbox).not.toBeChecked();
    expect(openCheckbox).toBeEnabled();
  });

  it("on_add_receives_requirement_entity_id", async () => {
    const user = userEvent.setup();
    const { props } = renderDialog();

    await user.click(screen.getByTestId("group-add-member-grp-2"));

    await waitFor(() => {
      expect(props.onAdd).toHaveBeenCalledWith("grp-2", REQ_ID);
    });
    // The dialog stays open: assigning a second group is one click away, and
    // the membership flip belongs to the caller's reload, not a local guess.
    expect(screen.getByTestId("add-to-group-dialog")).toBeInTheDocument();
    expect(props.onClose).not.toHaveBeenCalled();
  });

  it("error_keeps_dialog_open_with_alert", async () => {
    const user = userEvent.setup();
    const onAdd = vi.fn().mockRejectedValue(new Error("Membership refused"));
    renderDialog({ onAdd });

    await user.click(screen.getByTestId("group-add-member-grp-2"));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveAttribute("data-testid", "group-add-error");
    expect(alert).toHaveTextContent("Membership refused");
    // No silent close on a rejected write.
    expect(screen.getByTestId("add-to-group-dialog")).toBeInTheDocument();
    expect(screen.getByTestId("group-add-member-grp-2")).not.toBeChecked();
  });

  it("empty_group_list_shows_empty_text_and_create_form", async () => {
    const user = userEvent.setup();
    const { props } = renderDialog({ groups: [] });

    expect(screen.getByTestId("group-add-empty")).toHaveTextContent(
      "Noch keine Gruppen vorhanden.",
    );
    // The existing create path (same two fields as the group manager) instead
    // of a dead end that only points at another dialog.
    expect(screen.queryByTestId("group-add-list")).not.toBeInTheDocument();
    await user.type(screen.getByTestId("group-add-create-title"), "Chassis");
    await user.click(screen.getByTestId("group-add-create-btn"));

    await waitFor(() => {
      expect(props.onCreateGroup).toHaveBeenCalledWith("Chassis", "");
    });
  });

  it("shows the loading state instead of an empty list while groups are read", () => {
    renderDialog({ groups: [], isLoading: true });

    expect(screen.getByTestId("group-add-loading")).toBeInTheDocument();
    expect(screen.queryByTestId("group-add-empty")).not.toBeInTheDocument();
  });

  it("surfaces a failed group read as an alert", () => {
    renderDialog({ groups: [], groupsError: "Gruppen konnten nicht geladen werden." });

    expect(screen.getByTestId("group-add-load-error")).toHaveAttribute("role", "alert");
    expect(screen.queryByTestId("group-add-list")).not.toBeInTheDocument();
  });

  it("closes through the shared dialog controls", async () => {
    const user = userEvent.setup();
    const { props } = renderDialog();

    await user.click(screen.getByTestId("group-add-done-btn"));
    expect(props.onClose).toHaveBeenCalledTimes(1);
  });
});
