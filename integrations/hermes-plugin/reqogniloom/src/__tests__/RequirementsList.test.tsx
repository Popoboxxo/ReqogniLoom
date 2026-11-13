import * as React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { RequirementsList } from "../RequirementsList";
import { makeAppState, makeRequirement } from "./testHelpers";

vi.mock("../state", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../state")>();
  return {
    ...actual,
    backToConnected: vi.fn(),
    openCreateForm: vi.fn(),
    openRequirements: vi.fn(),
    requirementsPageNext: vi.fn(),
    requirementsPagePrevious: vi.fn(),
    searchRequirements: vi.fn(),
    selectRequirement: vi.fn(),
  };
});
import {
  backToConnected,
  openCreateForm,
  openRequirements,
  requirementsPageNext,
  requirementsPagePrevious,
  searchRequirements,
  selectRequirement,
} from "../state";

function listState(overrides: Parameters<typeof makeAppState>[0] = {}) {
  return makeAppState({ view: "requirements", ...overrides });
}

describe("RequirementsList", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders uid, title, status and tier name for every row", () => {
    const requirement = makeRequirement();

    render(<RequirementsList state={listState({ requirements: [requirement], requirementsCount: 1 })} />);

    expect(screen.getByText("Login must work")).toBeInTheDocument();
    expect(screen.getByText("REQ-1 · draft · System")).toBeInTheDocument();
  });

  it("opens the detail of the clicked row", () => {
    render(<RequirementsList state={listState({ requirements: [makeRequirement()], requirementsCount: 1 })} />);

    fireEvent.click(screen.getByTestId("requirement-row-req-1"));

    expect(selectRequirement).toHaveBeenCalledWith("req-1");
  });

  it("falls back to the id when a requirement has no uid", () => {
    render(
      <RequirementsList
        state={listState({ requirements: [makeRequirement({ uid: null })], requirementsCount: 1 })}
      />
    );

    expect(screen.getByText("req-1 · draft · System")).toBeInTheDocument();
  });

  it("shows an empty state with a New button for an empty workspace", () => {
    render(<RequirementsList state={listState({ requirements: [], requirementsCount: 0 })} />);

    expect(screen.getByText(/No requirements yet/)).toBeInTheDocument();
    expect(screen.getByTestId("requirements-new-button")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("requirements-new-button"));

    expect(openCreateForm).toHaveBeenCalledTimes(1);
  });

  it("shows the network error banner with a retry instead of the empty state", () => {
    render(<RequirementsList state={listState({ requirementError: "Server error" })} />);

    expect(screen.getByTestId("requirement-error")).toHaveTextContent("Server error");
    expect(screen.queryByText(/No requirements yet/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId("requirements-retry-button"));

    expect(openRequirements).toHaveBeenCalledTimes(1);
  });

  it("renders no error banner while there is no error", () => {
    render(<RequirementsList state={listState()} />);

    expect(screen.queryByTestId("requirement-error")).not.toBeInTheDocument();
    expect(screen.queryByTestId("requirements-retry-button")).not.toBeInTheDocument();
  });

  it("searches on Enter", () => {
    render(<RequirementsList state={listState()} />);
    const input = screen.getByTestId("requirements-search-input");

    fireEvent.change(input, { target: { value: "login" } });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(searchRequirements).toHaveBeenCalledWith("login");
  });

  it("searches on blur", () => {
    render(<RequirementsList state={listState()} />);
    const input = screen.getByTestId("requirements-search-input");

    fireEvent.change(input, { target: { value: "login" } });
    fireEvent.blur(input);

    expect(searchRequirements).toHaveBeenCalledWith("login");
  });

  it("does not restart the search when the term did not change", () => {
    render(<RequirementsList state={listState({ requirementsSearch: "login" })} />);

    fireEvent.blur(screen.getByTestId("requirements-search-input"));

    expect(searchRequirements).not.toHaveBeenCalled();
  });

  it("fires no search for a plain keystroke, only on Enter or blur", () => {
    render(<RequirementsList state={listState()} />);

    fireEvent.change(screen.getByTestId("requirements-search-input"), { target: { value: "log" } });

    expect(searchRequirements).not.toHaveBeenCalled();
  });

  it("enables Next only while a next page link exists and follows it", () => {
    const next = "https://x/api/v1/requirements/?workspace_id=ws-1&page=2&page_size=25";

    render(<RequirementsList state={listState({ requirementsNext: next })} />);

    fireEvent.click(screen.getByTestId("requirements-next-button"));

    expect(requirementsPageNext).toHaveBeenCalledTimes(1);
  });

  it("disables Previous on the first page", () => {
    render(<RequirementsList state={listState({ requirementsNext: "https://x/next" })} />);

    expect(screen.getByTestId("requirements-previous-button")).toBeDisabled();
    expect(screen.getByTestId("requirements-next-button")).not.toBeDisabled();
  });

  it("enables Previous on a later page and follows it", () => {
    const previous = "https://x/api/v1/requirements/?workspace_id=ws-1&page=1&page_size=25";

    render(<RequirementsList state={listState({ requirementsPrevious: previous })} />);

    expect(screen.getByTestId("requirements-next-button")).toBeDisabled();
    fireEvent.click(screen.getByTestId("requirements-previous-button"));

    expect(requirementsPagePrevious).toHaveBeenCalledTimes(1);
  });

  it("keeps the page and total count visible", () => {
    render(<RequirementsList state={listState({ requirementsCount: 30, requirementsPage: 2 })} />);

    expect(screen.getByText("30 total · page 2")).toBeInTheDocument();
  });

  it("returns to the hub from the Back button", () => {
    render(<RequirementsList state={listState()} />);

    fireEvent.click(screen.getByTestId("requirements-back-button"));

    expect(backToConnected).toHaveBeenCalledTimes(1);
  });

  it("shows a loading hint while the page is in flight", () => {
    render(<RequirementsList state={listState({ requirementBusy: true })} />);

    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });
});
