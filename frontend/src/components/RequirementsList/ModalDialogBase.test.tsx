/**
 * Tests for ModalDialogBase component.
 * REQ-L1-040: SE Masks Unification Phase 1
 *
 * Verifies standardized form layout, styling, and state management patterns.
 * Used as base for AdrList, RiskList, and IssueList.
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ModalDialogBase from "./ModalDialogBase";

// Mock i18next translations
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => {
      const translations: Record<string, string> = {
        "actions.new": "New",
        "actions.cancel": "Cancel",
        "actions.save": "Save",
        "actions.saving": "Saving...",
        "editor.empty": "No items yet",
      };
      return translations[key] || key;
    },
  }),
}));

describe("ModalDialogBase (REQ-L1-040)", () => {
  const mockOnSubmit = vi.fn();
  const mockOnCancel = vi.fn();
  const mockOnToggle = vi.fn();

  const defaultProps = {
    title: "Test Items",
    isOpen: false,
    onToggle: mockOnToggle,
    onSubmit: mockOnSubmit,
    onCancel: mockOnCancel,
    itemCount: 5,
    testIdPrefix: "test",
    buttonTestIdPrefix: "test",
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  // =========================================================================
  // Render Tests
  // =========================================================================

  it("renders title and toggle button in header", () => {
    render(
      <ModalDialogBase {...defaultProps}>
        <input type="text" placeholder="Test input" />
      </ModalDialogBase>
    );

    expect(screen.getByRole("heading", { name: "Test Items" })).toBeInTheDocument();
    expect(screen.getByTestId("test-create-btn")).toBeInTheDocument();
  });

  it("renders with custom newButtonLabel", () => {
    render(
      <ModalDialogBase
        {...defaultProps}
        newButtonLabel="+ Add Custom"
      >
        <input type="text" placeholder="Test" />
      </ModalDialogBase>
    );

    const btn = screen.getByTestId("test-create-btn");
    expect(btn).toHaveTextContent("Add Custom");
  });

  it("renders children content when form is open", () => {
    render(
      <ModalDialogBase {...defaultProps} isOpen={true}>
        <label htmlFor="test-input">Test Label</label>
        <input id="test-input" type="text" placeholder="Test" />
      </ModalDialogBase>
    );

    expect(screen.getByLabelText("Test Label")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Test")).toBeInTheDocument();
  });

  it("does not render form when isOpen is false", () => {
    render(
      <ModalDialogBase {...defaultProps} isOpen={false}>
        <input id="test-input" type="text" />
      </ModalDialogBase>
    );

    expect(screen.queryByTestId("test-create-form")).not.toBeInTheDocument();
    expect(screen.queryByTestId("test-save-btn")).not.toBeInTheDocument();
  });

  // =========================================================================
  // Toggle Button Tests
  // =========================================================================

  it("calls onToggle when header button is clicked", async () => {
    const user = userEvent.setup();
    render(
      <ModalDialogBase {...defaultProps} isOpen={false}>
        <input type="text" />
      </ModalDialogBase>
    );

    const btn = screen.getByTestId("test-create-btn");
    await user.click(btn);

    expect(mockOnToggle).toHaveBeenCalledOnce();
  });

  it("shows cancel text on button when form is open", () => {
    render(
      <ModalDialogBase {...defaultProps} isOpen={true}>
        <input type="text" />
      </ModalDialogBase>
    );

    const btn = screen.getByTestId("test-create-btn");
    expect(btn).toHaveTextContent("Cancel");
  });

  it("shows new item text on button when form is closed", () => {
    render(
      <ModalDialogBase {...defaultProps} isOpen={false}>
        <input type="text" />
      </ModalDialogBase>
    );

    const btn = screen.getByTestId("test-create-btn");
    expect(btn).toHaveTextContent("New Test Items");
  });

  // =========================================================================
  // Form Submission Tests
  // =========================================================================

  it("calls onSubmit when form is submitted", async () => {
    const user = userEvent.setup();
    render(
      <ModalDialogBase {...defaultProps} isOpen={true}>
        <input type="text" value="test" />
      </ModalDialogBase>
    );

    const form = screen.getByTestId("test-create-form");
    await user.click(screen.getByTestId("test-save-btn"));

    expect(mockOnSubmit).toHaveBeenCalled();
  });

  it("submits form event to onSubmit handler", async () => {
    const user = userEvent.setup();
    let eventReceived = false;

    const handleSubmit = vi.fn((_e: React.FormEvent<HTMLFormElement>) => {
      eventReceived = true;
    });

    render(
      <ModalDialogBase
        {...defaultProps}
        isOpen={true}
        onSubmit={handleSubmit}
      >
        <input type="text" />
      </ModalDialogBase>
    );

    await user.click(screen.getByTestId("test-save-btn"));

    expect(handleSubmit).toHaveBeenCalled();
    expect(eventReceived).toBe(true);
  });

  // =========================================================================
  // Cancel Button Tests
  // =========================================================================

  it("calls onCancel when cancel button is clicked", async () => {
    const user = userEvent.setup();
    render(
      <ModalDialogBase {...defaultProps} isOpen={true}>
        <input type="text" />
      </ModalDialogBase>
    );

    const cancelBtn = screen.getByTestId("test-cancel-btn");
    await user.click(cancelBtn);

    expect(mockOnCancel).toHaveBeenCalledOnce();
  });

  // =========================================================================
  // Error Display Tests
  // =========================================================================

  it("displays error message when error prop is set", () => {
    render(
      <ModalDialogBase
        {...defaultProps}
        isOpen={true}
        error="Form validation failed"
      >
        <input type="text" />
      </ModalDialogBase>
    );

    const alert = screen.getByRole("alert");
    expect(alert).toBeInTheDocument();
    expect(alert).toHaveTextContent("Form validation failed");
  });

  it("does not display error when error prop is null", () => {
    render(
      <ModalDialogBase {...defaultProps} isOpen={true} error={null}>
        <input type="text" />
      </ModalDialogBase>
    );

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("does not display error when error prop is undefined", () => {
    render(
      <ModalDialogBase {...defaultProps} isOpen={true} error={undefined}>
        <input type="text" />
      </ModalDialogBase>
    );

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("updates error message when prop changes", () => {
    const { rerender } = render(
      <ModalDialogBase
        {...defaultProps}
        isOpen={true}
        error="First error"
      >
        <input type="text" />
      </ModalDialogBase>
    );

    expect(screen.getByText("First error")).toBeInTheDocument();

    rerender(
      <ModalDialogBase
        {...defaultProps}
        isOpen={true}
        error="Second error"
      >
        <input type="text" />
      </ModalDialogBase>
    );

    expect(screen.queryByText("First error")).not.toBeInTheDocument();
    expect(screen.getByText("Second error")).toBeInTheDocument();
  });

  // =========================================================================
  // Loading State Tests
  // =========================================================================

  it("shows 'Saving...' text on save button when isSubmitting is true", () => {
    render(
      <ModalDialogBase
        {...defaultProps}
        isOpen={true}
        isSubmitting={true}
      >
        <input type="text" />
      </ModalDialogBase>
    );

    const saveBtn = screen.getByTestId("test-save-btn");
    expect(saveBtn).toHaveTextContent("Saving...");
  });

  it("shows 'Save' text on button when isSubmitting is false", () => {
    render(
      <ModalDialogBase
        {...defaultProps}
        isOpen={true}
        isSubmitting={false}
      >
        <input type="text" />
      </ModalDialogBase>
    );

    const saveBtn = screen.getByTestId("test-save-btn");
    expect(saveBtn).toHaveTextContent("Save");
  });

  it("disables save button when isSubmitting is true", () => {
    render(
      <ModalDialogBase
        {...defaultProps}
        isOpen={true}
        isSubmitting={true}
      >
        <input type="text" />
      </ModalDialogBase>
    );

    const saveBtn = screen.getByTestId("test-save-btn");
    expect(saveBtn).toBeDisabled();
  });

  it("disables cancel button when isSubmitting is true", () => {
    render(
      <ModalDialogBase
        {...defaultProps}
        isOpen={true}
        isSubmitting={true}
      >
        <input type="text" />
      </ModalDialogBase>
    );

    const cancelBtn = screen.getByTestId("test-cancel-btn");
    expect(cancelBtn).toBeDisabled();
  });

  it("enables save button when isSubmitting is false", () => {
    render(
      <ModalDialogBase
        {...defaultProps}
        isOpen={true}
        isSubmitting={false}
      >
        <input type="text" />
      </ModalDialogBase>
    );

    const saveBtn = screen.getByTestId("test-save-btn");
    expect(saveBtn).not.toBeDisabled();
  });

  it("enables cancel button when isSubmitting is false", () => {
    render(
      <ModalDialogBase
        {...defaultProps}
        isOpen={true}
        isSubmitting={false}
      >
        <input type="text" />
      </ModalDialogBase>
    );

    const cancelBtn = screen.getByTestId("test-cancel-btn");
    expect(cancelBtn).not.toBeDisabled();
  });

  // =========================================================================
  // Empty State Tests
  // =========================================================================

  it("displays empty state message when itemCount is 0 and form is closed", () => {
    render(
      <ModalDialogBase
        {...defaultProps}
        itemCount={0}
        isOpen={false}
      >
        <input type="text" />
      </ModalDialogBase>
    );

    expect(screen.getByText("No items yet")).toBeInTheDocument();
  });

  it("does not display empty state when itemCount is greater than 0", () => {
    render(
      <ModalDialogBase
        {...defaultProps}
        itemCount={5}
        isOpen={false}
      >
        <input type="text" />
      </ModalDialogBase>
    );

    expect(screen.queryByText("No items yet")).not.toBeInTheDocument();
  });

  it("does not display empty state when form is open even with 0 items", () => {
    render(
      <ModalDialogBase
        {...defaultProps}
        itemCount={0}
        isOpen={true}
      >
        <input type="text" />
      </ModalDialogBase>
    );

    expect(screen.queryByText("No items yet")).not.toBeInTheDocument();
  });

  // =========================================================================
  // Integration Tests
  // =========================================================================

  it("handles complete form lifecycle: open → submit → close", async () => {
    const user = userEvent.setup();
    const handleSubmit = vi.fn();
    const handleCancel = vi.fn();
    const handleToggle = vi.fn();

    const { rerender } = render(
      <ModalDialogBase
        {...defaultProps}
        isOpen={false}
        onSubmit={handleSubmit}
        onCancel={handleCancel}
        onToggle={handleToggle}
      >
        <input type="text" id="test-field" />
      </ModalDialogBase>
    );

    // Step 1: Open form
    await user.click(screen.getByTestId("test-create-btn"));
    expect(handleToggle).toHaveBeenCalledTimes(1);

    // Step 2: Verify form appears
    rerender(
      <ModalDialogBase
        {...defaultProps}
        isOpen={true}
        onSubmit={handleSubmit}
        onCancel={handleCancel}
        onToggle={handleToggle}
      >
        <input type="text" id="test-field" />
      </ModalDialogBase>
    );
    expect(screen.getByTestId("test-create-form")).toBeInTheDocument();

    // Step 3: Submit form
    await user.click(screen.getByTestId("test-save-btn"));
    expect(handleSubmit).toHaveBeenCalledTimes(1);
  });

  it("handles complete cancel lifecycle: open → cancel → close", async () => {
    const user = userEvent.setup();
    const handleCancel = vi.fn();
    const handleToggle = vi.fn();

    const { rerender } = render(
      <ModalDialogBase
        {...defaultProps}
        isOpen={false}
        onCancel={handleCancel}
        onToggle={handleToggle}
      >
        <input type="text" />
      </ModalDialogBase>
    );

    // Open form
    await user.click(screen.getByTestId("test-create-btn"));
    expect(handleToggle).toHaveBeenCalledTimes(1);

    // Verify form is open
    rerender(
      <ModalDialogBase
        {...defaultProps}
        isOpen={true}
        onCancel={handleCancel}
        onToggle={handleToggle}
      >
        <input type="text" />
      </ModalDialogBase>
    );
    expect(screen.getByTestId("test-create-form")).toBeInTheDocument();

    // Click cancel button
    await user.click(screen.getByTestId("test-cancel-btn"));
    expect(handleCancel).toHaveBeenCalledTimes(1);
  });

  it("combines error display with form submission flow", async () => {
    const user = userEvent.setup();
    const { rerender } = render(
      <ModalDialogBase
        {...defaultProps}
        isOpen={true}
        isSubmitting={false}
        error={null}
      >
        <input type="text" />
      </ModalDialogBase>
    );

    // Submit form
    await user.click(screen.getByTestId("test-save-btn"));

    // Simulate loading state
    rerender(
      <ModalDialogBase
        {...defaultProps}
        isOpen={true}
        isSubmitting={true}
        error={null}
      >
        <input type="text" />
      </ModalDialogBase>
    );
    expect(screen.getByTestId("test-save-btn")).toHaveTextContent("Saving...");

    // Simulate error state
    rerender(
      <ModalDialogBase
        {...defaultProps}
        isOpen={true}
        isSubmitting={false}
        error="Required field missing"
      >
        <input type="text" />
      </ModalDialogBase>
    );

    expect(screen.getByRole("alert")).toHaveTextContent("Required field missing");
    expect(screen.getByTestId("test-save-btn")).not.toBeDisabled();
  });

  // =========================================================================
  // Test ID and Accessibility Tests
  // =========================================================================

  it("renders form with correct test ID prefix", () => {
    render(
      <ModalDialogBase
        {...defaultProps}
        isOpen={true}
        testIdPrefix="custom"
      >
        <input type="text" />
      </ModalDialogBase>
    );

    expect(screen.getByTestId("custom-create-form")).toBeInTheDocument();
    expect(screen.getByTestId("custom-cancel-btn")).toBeInTheDocument();
    expect(screen.getByTestId("custom-save-btn")).toBeInTheDocument();
  });

  it("renders create button with correct test ID prefix", () => {
    render(
      <ModalDialogBase
        {...defaultProps}
        buttonTestIdPrefix="entity"
      >
        <input type="text" />
      </ModalDialogBase>
    );

    expect(screen.getByTestId("entity-create-btn")).toBeInTheDocument();
  });

  it("renders with proper ARIA attributes for accessibility", () => {
    render(
      <ModalDialogBase
        {...defaultProps}
        isOpen={true}
        error="Test error"
      >
        <input type="text" />
      </ModalDialogBase>
    );

    const alert = screen.getByRole("alert");
    expect(alert).toBeInTheDocument();
  });

  // =========================================================================
  // Props Variation Tests
  // =========================================================================

  it("renders with minimal required props", () => {
    const minimalProps = {
      title: "Items",
      isOpen: false,
      onToggle: vi.fn(),
      onSubmit: vi.fn(),
      onCancel: vi.fn(),
      testIdPrefix: "min",
      buttonTestIdPrefix: "min", itemCount: 0,
      itemCount: 0,
    };

    render(
      <ModalDialogBase {...minimalProps}>
        <input type="text" />
      </ModalDialogBase>
    );

    expect(screen.getByRole("heading", { name: "Items" })).toBeInTheDocument();
  });

  it("renders with all optional props", () => {
    const allProps = {
      title: "Complete",
      isOpen: true,
      onToggle: vi.fn(),
      onSubmit: vi.fn(),
      onCancel: vi.fn(),
      error: "Test error",
      isSubmitting: true,
      itemCount: 3,
      testIdPrefix: "all",
      buttonTestIdPrefix: "all",
      newButtonLabel: "Add Item",
    };

    render(
      <ModalDialogBase {...allProps}>
        <input type="text" />
      </ModalDialogBase>
    );

    expect(screen.getByRole("heading", { name: "Complete" })).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Test error");
    expect(screen.getByTestId("all-save-btn")).toHaveTextContent("Saving...");
  });
});
