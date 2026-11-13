import * as React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { RequirementDetail } from "../RequirementDetail";
import { makeAppState, makeRequirement } from "./testHelpers";

vi.mock("../state", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../state")>();
  return { ...actual, backToList: vi.fn(), openEditForm: vi.fn() };
});
import { backToList, openEditForm } from "../state";

function detailState(overrides: Parameters<typeof makeAppState>[0] = {}) {
  return makeAppState({ view: "requirement-detail", activeRequirement: makeRequirement(), ...overrides });
}

describe("RequirementDetail", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows level, tier name, level source and the suspect flag read-only", () => {
    const { container } = render(
      <RequirementDetail state={detailState({ activeRequirement: makeRequirement({ suspect: true }) })} />
    );

    expect(screen.getByTestId("requirement-detail-level")).toHaveTextContent("2");
    expect(screen.getByTestId("requirement-detail-tier")).toHaveTextContent("System");
    expect(screen.getByTestId("requirement-detail-level-source")).toHaveTextContent("derived");
    expect(screen.getByTestId("requirement-detail-suspect")).toHaveTextContent("Yes");

    // Read-only: nothing on this view can write level/tier/level_source.
    expect(container.querySelectorAll("input, textarea, select")).toHaveLength(0);
    expect(screen.queryByTestId("requirement-form-level")).toBeNull();
  });

  it("renders a missing level as a dash instead of an empty field", () => {
    render(
      <RequirementDetail
        state={detailState({
          activeRequirement: makeRequirement({ level: null, tier_name: null, suspect: false }),
        })}
      />
    );

    expect(screen.getByTestId("requirement-detail-level")).toHaveTextContent("—");
    expect(screen.getByTestId("requirement-detail-tier")).toHaveTextContent("—");
    expect(screen.getByTestId("requirement-detail-suspect")).toHaveTextContent("No");
  });

  it("shows the remaining requirement fields", () => {
    render(<RequirementDetail state={detailState()} />);

    expect(screen.getByTestId("requirement-detail-uid")).toHaveTextContent("REQ-1");
    expect(screen.getByTestId("requirement-detail-title")).toHaveTextContent("Login must work");
    expect(screen.getByTestId("requirement-detail-status")).toHaveTextContent("draft");
    expect(screen.getByTestId("requirement-detail-type")).toHaveTextContent("SyReq");
    expect(screen.getByTestId("requirement-detail-description")).toHaveTextContent("Users sign in with SSO.");
    expect(screen.getByTestId("requirement-detail-acceptance")).toHaveTextContent(
      "A valid token grants access."
    );
    expect(screen.getByTestId("requirement-detail-category")).toHaveTextContent("security");
  });

  it("opens the edit form", () => {
    render(<RequirementDetail state={detailState()} />);

    fireEvent.click(screen.getByTestId("requirement-edit-button"));

    expect(openEditForm).toHaveBeenCalledTimes(1);
  });

  it("returns to the list from the Back button", () => {
    render(<RequirementDetail state={detailState()} />);

    fireEvent.click(screen.getByTestId("requirements-back-button"));

    expect(backToList).toHaveBeenCalledTimes(1);
  });

  it("shows the load error in the banner and keeps Edit disabled", () => {
    render(
      <RequirementDetail
        state={makeAppState({
          view: "requirement-detail",
          activeRequirement: null,
          requirementError: "Requirement not found",
        })}
      />
    );

    expect(screen.getByTestId("requirement-error")).toHaveTextContent("Requirement not found");
    expect(screen.queryByText("No requirement selected.")).not.toBeInTheDocument();
    expect(screen.getByTestId("requirement-edit-button")).toBeDisabled();
  });

  it("shows a loading hint while the detail request is in flight", () => {
    render(
      <RequirementDetail
        state={makeAppState({ view: "requirement-detail", activeRequirement: null, requirementBusy: true })}
      />
    );

    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });
});
