/**
 * Unit tests for SignatureDialog (REQ-144 signature-gated transitions).
 *
 * req_id: REQ-144
 *
 * Verifies:
 *   - Renders nothing when isOpen is false
 *   - Blocks submit client-side when the credential field is empty
 *   - Blocks submit client-side when change_reason is required but empty
 *   - Calls onSubmit(credential, reason) with the entered values
 *   - Surfaces a rejected onSubmit's error message inline (wrong credential /
 *     missing role) instead of closing the dialog
 *   - Cancel calls onClose without calling onSubmit
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("react-i18next", () => {
  const t = (key: string, fallbackOrOptions?: string | Record<string, unknown>): string =>
    typeof fallbackOrOptions === "string" ? fallbackOrOptions : key;
  return { useTranslation: () => ({ t }) };
});

import { ForbiddenError } from "../../api/errors";
import { SignatureDialog } from "./SignatureDialog";

describe("SignatureDialog (REQ-144)", () => {
  it("renders nothing when isOpen is false", () => {
    const { container } = render(
      <SignatureDialog
        isOpen={false}
        targetState="approved"
        requiresChangeReason={false}
        onClose={vi.fn()}
        onSubmit={vi.fn()}
      />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("blocks submit when the credential field is empty", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup();

    render(
      <SignatureDialog
        isOpen
        targetState="approved"
        requiresChangeReason={false}
        onClose={vi.fn()}
        onSubmit={onSubmit}
      />
    );

    await user.click(screen.getByTestId("signature-dialog-submit"));

    await waitFor(() => {
      expect(screen.getByTestId("signature-dialog-error")).toBeInTheDocument();
    });
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("blocks submit when change_reason is required but empty", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup();

    render(
      <SignatureDialog
        isOpen
        targetState="approved"
        requiresChangeReason
        onClose={vi.fn()}
        onSubmit={onSubmit}
      />
    );

    await user.type(screen.getByTestId("signature-dialog-credential-input"), "s3cr3t");
    await user.click(screen.getByTestId("signature-dialog-submit"));

    await waitFor(() => {
      expect(screen.getByTestId("signature-dialog-error")).toBeInTheDocument();
    });
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("calls onSubmit with the entered credential and reason", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup();

    render(
      <SignatureDialog
        isOpen
        targetState="approved"
        requiresChangeReason={false}
        onClose={vi.fn()}
        onSubmit={onSubmit}
      />
    );

    await user.type(screen.getByTestId("signature-dialog-credential-input"), "s3cr3t");
    await user.type(screen.getByTestId("signature-dialog-reason-input"), "looks good");
    await user.click(screen.getByTestId("signature-dialog-submit"));

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith("s3cr3t", "looks good");
    });
  });

  it("surfaces a wrong-credential rejection inline instead of closing", async () => {
    const onClose = vi.fn();
    const onSubmit = vi.fn().mockRejectedValue({ error: { message: "Signature invalid" } });
    const user = userEvent.setup();

    render(
      <SignatureDialog
        isOpen
        targetState="approved"
        requiresChangeReason={false}
        onClose={onClose}
        onSubmit={onSubmit}
      />
    );

    await user.type(screen.getByTestId("signature-dialog-credential-input"), "wrong");
    await user.click(screen.getByTestId("signature-dialog-submit"));

    await waitFor(() => {
      expect(screen.getByTestId("signature-dialog-error")).toHaveTextContent("Signature invalid");
    });
    expect(onClose).not.toHaveBeenCalled();
  });

  it("surfaces a missing-role (403) rejection with the ForbiddenError message", async () => {
    const onSubmit = vi.fn().mockRejectedValue(new ForbiddenError("Missing approver role"));
    const user = userEvent.setup();

    render(
      <SignatureDialog
        isOpen
        targetState="approved"
        requiresChangeReason={false}
        onClose={vi.fn()}
        onSubmit={onSubmit}
      />
    );

    await user.type(screen.getByTestId("signature-dialog-credential-input"), "s3cr3t");
    await user.click(screen.getByTestId("signature-dialog-submit"));

    await waitFor(() => {
      expect(screen.getByTestId("signature-dialog-error")).toHaveTextContent(
        "Missing approver role"
      );
    });
  });

  it("Cancel calls onClose without calling onSubmit", async () => {
    const onClose = vi.fn();
    const onSubmit = vi.fn();
    const user = userEvent.setup();

    render(
      <SignatureDialog
        isOpen
        targetState="approved"
        requiresChangeReason={false}
        onClose={onClose}
        onSubmit={onSubmit}
      />
    );

    await user.click(screen.getByTestId("signature-dialog-cancel"));

    expect(onClose).toHaveBeenCalledTimes(1);
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
