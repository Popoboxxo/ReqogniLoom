import * as React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { RequirementForm } from "../RequirementForm";
import { makeAppState, makeRequirement, makeRequirementForm } from "./testHelpers";

vi.mock("../state", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../state")>();
  return { ...actual, backToList: vi.fn(), submitForm: vi.fn(), updateFormField: vi.fn() };
});
import { backToList, submitForm, updateFormField } from "../state";

const editedValues = {
  title: "Login must work",
  description: "Users sign in with SSO.",
  acceptance_criteria: "A valid token grants access.",
  category: "security",
  type: "SyReq" as const,
};

function editState(overrides: Parameters<typeof makeAppState>[0] = {}) {
  return makeAppState({
    view: "requirement-form",
    activeRequirement: makeRequirement(),
    requirementForm: makeRequirementForm({ mode: "edit", values: { ...editedValues } }),
    ...overrides,
  });
}

describe("RequirementForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("prefills the writable values in edit mode and has no level field", () => {
    render(<RequirementForm state={editState()} />);

    expect(screen.getByTestId("requirement-form-title")).toHaveValue("Login must work");
    expect(screen.getByTestId("requirement-form-description")).toHaveValue("Users sign in with SSO.");
    expect(screen.getByTestId("requirement-form-acceptance")).toHaveValue("A valid token grants access.");
    expect(screen.getByTestId("requirement-form-category")).toHaveValue("security");
    expect(screen.getByTestId("requirement-form-type")).toHaveValue("SyReq");

    // `level` is derived and read-only (ADR-005/027): no control may exist for it.
    expect(screen.queryByTestId("requirement-form-level")).toBeNull();
    expect(screen.queryByLabelText(/Level/i)).toBeNull();
  });

  it("does not offer a change reason while creating", () => {
    render(
      <RequirementForm
        state={makeAppState({ view: "requirement-form", requirementForm: makeRequirementForm() })}
      />
    );

    expect(screen.queryByTestId("requirement-form-change-reason")).toBeNull();
  });

  it("offers a change reason on edit without demanding it", () => {
    render(<RequirementForm state={editState()} />);

    expect(screen.getByTestId("requirement-form-change-reason")).not.toBeRequired();
    expect(screen.queryByText(/Change Reason \(required\)/)).not.toBeInTheDocument();
  });

  it("marks change reason as required once the server demanded one", () => {
    render(
      <RequirementForm
        state={editState({
          requirementForm: makeRequirementForm({
            mode: "edit",
            values: { ...editedValues },
            fieldErrors: { change_reason: "This workspace's preset requires a change reason for updates." },
          }),
        })}
      />
    );

    expect(screen.getByTestId("requirement-form-change-reason")).toBeRequired();
    expect(screen.getByText("Change Reason (required)")).toBeInTheDocument();
    expect(screen.getByTestId("requirement-form-error-change_reason")).toHaveTextContent(
      "requires a change reason"
    );
  });

  it("shows a field error next to the field", () => {
    render(
      <RequirementForm
        state={editState({
          requirementForm: makeRequirementForm({
            mode: "edit",
            values: { ...editedValues },
            fieldErrors: { title: "Title may not be blank." },
          }),
        })}
      />
    );

    expect(screen.getByTestId("requirement-form-error-title")).toHaveTextContent("Title may not be blank.");
    expect(screen.queryByTestId("requirement-form-error-description")).not.toBeInTheDocument();
  });

  it("writes edits through to the form state", () => {
    render(<RequirementForm state={editState()} />);

    fireEvent.change(screen.getByTestId("requirement-form-title"), { target: { value: "Login v2" } });
    fireEvent.change(screen.getByTestId("requirement-form-type"), { target: { value: "UseCase" } });
    fireEvent.change(screen.getByTestId("requirement-form-change-reason"), { target: { value: "typo" } });

    expect(updateFormField).toHaveBeenCalledWith("title", "Login v2");
    expect(updateFormField).toHaveBeenCalledWith("type", "UseCase");
    expect(updateFormField).toHaveBeenCalledWith("change_reason", "typo");
  });

  it("submits the form", () => {
    const { container } = render(<RequirementForm state={editState()} />);

    const form = container.querySelector("form");
    expect(form).not.toBeNull();
    fireEvent.submit(form as HTMLFormElement);

    expect(submitForm).toHaveBeenCalledTimes(1);
  });

  it("shows a generic save error in the requirement-error banner", () => {
    render(
      <RequirementForm
        state={editState({ requirementError: "This requirement was changed elsewhere." })}
      />
    );

    expect(screen.getByTestId("requirement-error")).toHaveTextContent("changed elsewhere");
  });

  it("disables Save while a submit is in flight", () => {
    render(<RequirementForm state={editState({ requirementBusy: true })} />);

    expect(screen.getByTestId("requirement-form-submit")).toBeDisabled();
    expect(screen.getByTestId("requirement-form-submit")).toHaveTextContent("Saving…");
  });

  it("leaves a clean form without asking", () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);

    render(<RequirementForm state={editState()} />);
    fireEvent.click(screen.getByTestId("requirement-form-cancel"));

    expect(confirmSpy).not.toHaveBeenCalled();
    expect(backToList).toHaveBeenCalledTimes(1);
  });

  it("asks before discarding a dirty form and keeps the draft when declined", () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);

    render(
      <RequirementForm
        state={editState({
          requirementForm: makeRequirementForm({
            mode: "edit",
            values: { ...editedValues, title: "Login must work (changed)" },
          }),
        })}
      />
    );

    fireEvent.click(screen.getByTestId("requirement-form-cancel"));

    expect(confirmSpy).toHaveBeenCalledWith("Discard unsaved changes?");
    expect(backToList).not.toHaveBeenCalled();
    expect(screen.getByTestId("requirement-form-title")).toHaveValue("Login must work (changed)");

    confirmSpy.mockReturnValue(true);
    fireEvent.click(screen.getByTestId("requirement-form-cancel"));

    expect(backToList).toHaveBeenCalledTimes(1);
  });

  it("asks before discarding a dirty create form", () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);

    render(
      <RequirementForm
        state={makeAppState({
          view: "requirement-form",
          requirementForm: makeRequirementForm({
            values: { title: "Draft title", description: "", acceptance_criteria: "", category: "", type: "SyReq" },
          }),
        })}
      />
    );

    fireEvent.click(screen.getByTestId("requirement-form-cancel"));

    expect(confirmSpy).toHaveBeenCalledTimes(1);
    expect(backToList).not.toHaveBeenCalled();
  });

  it("treats a change reason alone as unsaved input", () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);

    render(
      <RequirementForm
        state={editState({
          requirementForm: makeRequirementForm({
            mode: "edit",
            values: { ...editedValues },
            changeReason: "because",
          }),
        })}
      />
    );

    fireEvent.click(screen.getByTestId("requirement-form-cancel"));

    expect(confirmSpy).toHaveBeenCalledTimes(1);
    expect(backToList).not.toHaveBeenCalled();
  });
});
