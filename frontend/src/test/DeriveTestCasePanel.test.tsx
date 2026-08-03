/**
 * ARCH-L1-001 ReactFrontend — DeriveTestCasePanel unit test.
 *
 * SysEng 2.0 N5 (test.derive_from_requirement), UMSETZUNGSPLAN_SYSENG_2.0.md
 * Phase 4a.
 *
 * Covers the Draft/Accept flow: generate stages an editable draft (nothing
 * persisted yet), the draft can be edited (title/description/steps), create
 * persists it via the existing TestCase creation path and auto-links it to
 * the source requirement, and discard clears the draft without creating
 * anything.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { DeriveTestCasePanel } from "../components/TestCaseEditors/DeriveTestCasePanel";
import type { TestCase } from "../api/testcases";

// t() returns the key so assertions can rely on data-testid, not copy.
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock("../api/client", () => ({
  extractErrorMessage: (e: unknown) => (e instanceof Error ? e.message : "error"),
}));

const aiDeriveTestcase = vi.fn();
vi.mock("../api/requirements", () => ({
  requirementsApi: {
    aiDeriveTestcase: (...args: unknown[]) => aiDeriveTestcase(...args),
  },
}));

const create = vi.fn();
vi.mock("../api/testcases", () => ({
  testcasesApi: {
    create: (...args: unknown[]) => create(...args),
  },
}));

const DRAFT_RESULT = {
  requirement_id: "req-1",
  draft: {
    title: "Test: The system shall log in users",
    description: "Verifies that the system satisfies 'The system shall log in users'.",
    steps: [
      { step: "Set up preconditions.", expected_result: "System is ready." },
      { step: "Exercise the login behaviour.", expected_result: "User is logged in." },
    ],
  },
};

const CREATED_TEST_CASE: TestCase = {
  id: "tc-1",
  workspace_id: "ws-1",
  title: "Test: The system shall log in users",
  description: "Verifies that the system satisfies 'The system shall log in users'.",
  uid: "TC-1",
  status: "draft",
  suspect: false,
  steps: DRAFT_RESULT.draft.steps,
  version: 1,
  created_at: "2026-07-20T00:00:00Z",
  updated_at: "2026-07-20T00:00:00Z",
} as TestCase;

function renderPanel(onCreated = vi.fn()) {
  return render(
    <DeriveTestCasePanel
      workspaceId="ws-1"
      requirement={{ id: "req-1", title: "The system shall log in users" }}
      onCreated={onCreated}
    />
  );
}

describe("DeriveTestCasePanel", () => {
  beforeEach(() => {
    aiDeriveTestcase.mockReset();
    create.mockReset();
  });

  it("stages a draft on generate without creating a TestCase", async () => {
    aiDeriveTestcase.mockResolvedValue(DRAFT_RESULT);
    const user = userEvent.setup();
    renderPanel();

    // Nothing staged initially.
    expect(screen.queryByTestId("derive-testcase-draft")).toBeNull();

    await user.click(screen.getByTestId("derive-testcase-generate"));

    await waitFor(() =>
      expect(screen.getByTestId("derive-testcase-draft")).toBeInTheDocument()
    );
    expect(aiDeriveTestcase).toHaveBeenCalledWith("req-1");
    expect(screen.getByTestId("derive-testcase-title-input")).toHaveValue(
      DRAFT_RESULT.draft.title
    );
    expect(screen.getByTestId("derive-testcase-step-0")).toBeInTheDocument();
    expect(screen.getByTestId("derive-testcase-step-1")).toBeInTheDocument();
    expect(create).not.toHaveBeenCalled();
  });

  it("creates the (possibly edited) draft and links it to the requirement", async () => {
    aiDeriveTestcase.mockResolvedValue(DRAFT_RESULT);
    create.mockResolvedValue(CREATED_TEST_CASE);
    const onCreated = vi.fn();
    const user = userEvent.setup();
    renderPanel(onCreated);

    await user.click(screen.getByTestId("derive-testcase-generate"));
    await screen.findByTestId("derive-testcase-draft");

    // Edit the title before creating.
    const titleInput = screen.getByTestId("derive-testcase-title-input");
    await user.clear(titleInput);
    await user.type(titleInput, "Edited title");

    await user.click(screen.getByTestId("derive-testcase-create"));

    await waitFor(() =>
      expect(screen.getByTestId("derive-testcase-result")).toBeInTheDocument()
    );
    expect(create).toHaveBeenCalledWith({
      workspace_id: "ws-1",
      title: "Edited title",
      description: DRAFT_RESULT.draft.description,
      steps: DRAFT_RESULT.draft.steps,
      linked_requirement_id: "req-1",
    });
    expect(onCreated).toHaveBeenCalledWith(CREATED_TEST_CASE);
    // Draft view is cleared after a successful create.
    expect(screen.queryByTestId("derive-testcase-draft")).toBeNull();
  });

  it("adds and removes steps in the draft", async () => {
    aiDeriveTestcase.mockResolvedValue(DRAFT_RESULT);
    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getByTestId("derive-testcase-generate"));
    await screen.findByTestId("derive-testcase-draft");

    await user.click(screen.getByTestId("derive-testcase-add-step"));
    expect(screen.getByTestId("derive-testcase-step-2")).toBeInTheDocument();

    await user.click(screen.getByTestId("derive-testcase-step-remove-2"));
    expect(screen.queryByTestId("derive-testcase-step-2")).toBeNull();
  });

  it("shows an error and keeps the draft when create fails", async () => {
    aiDeriveTestcase.mockResolvedValue(DRAFT_RESULT);
    create.mockRejectedValue(new Error("validation failed"));
    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getByTestId("derive-testcase-generate"));
    await screen.findByTestId("derive-testcase-draft");
    await user.click(screen.getByTestId("derive-testcase-create"));

    await waitFor(() =>
      expect(screen.getByTestId("derive-testcase-error")).toHaveTextContent(
        "validation failed"
      )
    );
    // Draft stays so the user can retry / discard.
    expect(screen.getByTestId("derive-testcase-draft")).toBeInTheDocument();
  });

  it("discards a staged draft without creating a TestCase", async () => {
    aiDeriveTestcase.mockResolvedValue(DRAFT_RESULT);
    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getByTestId("derive-testcase-generate"));
    await screen.findByTestId("derive-testcase-draft");
    await user.click(screen.getByTestId("derive-testcase-discard"));

    expect(screen.queryByTestId("derive-testcase-draft")).toBeNull();
    expect(create).not.toHaveBeenCalled();
  });
});
