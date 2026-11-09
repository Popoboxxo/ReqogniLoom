/**
 * #1732 — an empty required field explains itself instead of disabling Submit.
 *
 * Before: `<button disabled={isSubmitting || !title.trim()}>` — a greyed-out
 * button with no message and no focus target. After: the button stays active,
 * a click validates, the field is marked `aria-invalid`, a single
 * `role="alert"` message appears at the field, and focus moves there.
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import React from "react";

import { GoalFormDialog } from "./GoalFormDialog";

vi.mock("../../hooks/useFieldContract", () => ({
  useFieldContract: () => ({
    field: () => ({ required: true, controlProps: { required: true, "aria-required": "true" } }),
    isLoading: false,
    error: null,
  }),
}));

function renderDialog() {
  const onSubmit = vi.fn();
  render(
    <GoalFormDialog
      editing={null}
      isSubmitting={false}
      onSubmit={onSubmit}
      onClose={vi.fn()}
    />,
  );
  return { onSubmit };
}

describe("GoalFormDialog required validation (#1732)", () => {
  it("keeps the submit button active while the title is empty", () => {
    renderDialog();

    const submit = screen.getByTestId("goal-create-button");
    expect(submit).toBeEnabled();
  });

  it("explains the empty field and focuses it instead of submitting", async () => {
    const user = userEvent.setup();
    const { onSubmit } = renderDialog();

    await user.click(screen.getByTestId("goal-create-button"));

    const alerts = screen.getAllByRole("alert");
    expect(alerts).toHaveLength(1);
    expect(alerts[0]).toHaveTextContent(/required/i);

    const title = screen.getByTestId("goal-title-input");
    expect(title).toHaveAttribute("aria-invalid", "true");
    expect(title).toHaveAttribute(
      "aria-describedby",
      expect.stringContaining("goal-title-error"),
    );
    expect(title).toHaveFocus();

    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("submits once the title is filled, and the message disappears", async () => {
    const user = userEvent.setup();
    const { onSubmit } = renderDialog();

    await user.click(screen.getByTestId("goal-create-button"));
    expect(screen.getAllByRole("alert")).toHaveLength(1);

    await user.type(screen.getByTestId("goal-title-input"), "Ship beta.29");

    // Typing clears the message; the field is no longer marked invalid.
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByTestId("goal-title-input")).not.toHaveAttribute(
      "aria-invalid",
    );

    await user.click(screen.getByTestId("goal-create-button"));
    expect(onSubmit).toHaveBeenCalledWith({ title: "Ship beta.29", description: "" });
  });
});
