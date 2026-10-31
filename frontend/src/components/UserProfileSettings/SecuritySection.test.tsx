/**
 * ARCH-L1-001 ReactFrontend — SecuritySection (two-factor settings).
 * Plan E / WP E3.8 (#1308).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { SecuritySection } from "./SecuritySection";
import type { MfaStatus } from "../../api/mfa";
import {
  confirmTotp,
  disableMfa,
  enrollTotp,
  getMfaStatus,
  regenerateRecoveryCodes,
} from "../../api/mfa";

vi.mock("../../api/mfa", () => ({
  getMfaStatus: vi.fn(),
  enrollTotp: vi.fn(),
  confirmTotp: vi.fn(),
  regenerateRecoveryCodes: vi.fn(),
  disableMfa: vi.fn(),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      options ? `${key}:${JSON.stringify(options)}` : key,
  }),
}));

const NOT_ENROLLED: MfaStatus = {
  enrolled: false,
  confirmed_at: null,
  recovery_codes_remaining: 0,
  enforcement: "optional",
  required: false,
};

const ENROLLED: MfaStatus = {
  enrolled: true,
  confirmed_at: "2026-10-01T10:00:00Z",
  recovery_codes_remaining: 8,
  enforcement: "optional",
  required: false,
};

const ENROLLMENT = {
  secret: "JBSWY3DPEHPK3PXP",
  otpauth_uri: "otpauth://totp/ReqogniLoom:e2e-mfa?secret=JBSWY3DPEHPK3PXP",
  digits: 6,
  period: 30,
};

describe("SecuritySection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getMfaStatus).mockResolvedValue(NOT_ENROLLED);
  });

  it("renders the not-enrolled state with an enroll action", async () => {
    render(<SecuritySection />);

    expect(await screen.findByTestId("mfa-status")).toHaveTextContent(
      "mfa.statusOff"
    );
    expect(screen.getByTestId("mfa-enroll-btn")).toBeInTheDocument();
  });

  it("renders the enrolled state with status and remaining codes", async () => {
    vi.mocked(getMfaStatus).mockResolvedValue(ENROLLED);
    render(<SecuritySection />);

    expect(await screen.findByTestId("mfa-status")).toHaveTextContent(
      "mfa.statusOn"
    );
    expect(screen.getByText(/mfa.remaining/)).toBeInTheDocument();
    expect(screen.getByTestId("mfa-regenerate-btn")).toBeInTheDocument();
    expect(screen.getByTestId("mfa-disable-btn")).toBeInTheDocument();
  });

  it("marks the factor as required by policy", async () => {
    vi.mocked(getMfaStatus).mockResolvedValue({
      ...NOT_ENROLLED,
      required: true,
    });
    render(<SecuritySection />);

    expect(await screen.findByText("mfa.requiredByPolicy")).toBeInTheDocument();
  });

  it("shows the secret and confirms the first code", async () => {
    vi.mocked(getMfaStatus)
      .mockResolvedValueOnce(NOT_ENROLLED)
      .mockResolvedValueOnce(ENROLLED);
    vi.mocked(enrollTotp).mockResolvedValue(ENROLLMENT);
    vi.mocked(confirmTotp).mockResolvedValue({
      confirmed_at: "2026-10-01T10:00:00Z",
      recovery_codes: ["AAAA-BBBB-CCCC-DDDD", "EEEE-FFFF-GGGG-HHHH"],
    });

    render(<SecuritySection />);

    fireEvent.click(await screen.findByTestId("mfa-enroll-btn"));

    expect(await screen.findByTestId("mfa-secret")).toHaveTextContent(
      ENROLLMENT.secret
    );
    expect(screen.getByTestId("mfa-otpauth-link")).toHaveAttribute(
      "href",
      ENROLLMENT.otpauth_uri
    );

    fireEvent.change(screen.getByTestId("mfa-confirm-code-input"), {
      target: { value: "123456" },
    });
    fireEvent.click(screen.getByTestId("mfa-confirm-btn"));

    await waitFor(() => expect(confirmTotp).toHaveBeenCalledWith("123456"));
    expect(await screen.findByTestId("mfa-recovery-codes")).toHaveTextContent(
      "AAAA-BBBB-CCCC-DDDD"
    );
  });

  it("regenerates recovery codes and reveals the disable form", async () => {
    vi.mocked(getMfaStatus).mockResolvedValue(ENROLLED);
    vi.mocked(regenerateRecoveryCodes).mockResolvedValue({
      recovery_codes: ["1111-2222-3333-4444"],
    });

    render(<SecuritySection />);

    fireEvent.click(await screen.findByTestId("mfa-regenerate-btn"));
    fireEvent.change(screen.getByTestId("mfa-regenerate-code-input"), {
      target: { value: "654321" },
    });
    fireEvent.click(screen.getByTestId("mfa-regenerate-submit"));

    await waitFor(() =>
      expect(regenerateRecoveryCodes).toHaveBeenCalledWith("654321")
    );
    expect(await screen.findByTestId("mfa-recovery-codes")).toHaveTextContent(
      "1111-2222-3333-4444"
    );

    fireEvent.click(screen.getByTestId("mfa-disable-btn"));
    expect(screen.getByTestId("mfa-disable-password-input")).toBeInTheDocument();
    expect(screen.getByTestId("mfa-disable-code-input")).toBeInTheDocument();
  });

  it("disables the factor with password and code", async () => {
    vi.mocked(getMfaStatus)
      .mockResolvedValueOnce(ENROLLED)
      .mockResolvedValueOnce(NOT_ENROLLED);
    vi.mocked(disableMfa).mockResolvedValue(undefined);

    render(<SecuritySection />);

    fireEvent.click(await screen.findByTestId("mfa-disable-btn"));
    fireEvent.change(screen.getByTestId("mfa-disable-password-input"), {
      target: { value: "secret-password" },
    });
    fireEvent.change(screen.getByTestId("mfa-disable-code-input"), {
      target: { value: "123456" },
    });
    fireEvent.click(screen.getByTestId("mfa-disable-submit"));

    await waitFor(() =>
      expect(disableMfa).toHaveBeenCalledWith("secret-password", "123456")
    );
    expect(await screen.findByTestId("mfa-status")).toHaveTextContent(
      "mfa.statusOff"
    );
  });

  it("renders the error state when the status cannot be loaded", async () => {
    vi.mocked(getMfaStatus).mockRejectedValue(new Error("boom"));
    render(<SecuritySection />);

    expect(await screen.findByTestId("mfa-error")).toHaveTextContent("mfa.error");
  });
});

describe("SecuritySection — one-time code handling", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getMfaStatus).mockResolvedValue(NOT_ENROLLED);
    vi.mocked(enrollTotp).mockResolvedValue(ENROLLMENT);
    vi.mocked(confirmTotp).mockResolvedValue({
      confirmed_at: "2026-10-01T10:00:00Z",
      recovery_codes: ["AAAA-BBBB-CCCC-DDDD", "EEEE-FFFF-GGGG-HHHH"],
    });
  });

  async function confirmEnrollment(): Promise<void> {
    render(<SecuritySection />);
    fireEvent.click(await screen.findByTestId("mfa-enroll-btn"));
    fireEvent.change(await screen.findByTestId("mfa-confirm-code-input"), {
      target: { value: "123456" },
    });
    fireEvent.click(screen.getByTestId("mfa-confirm-btn"));
    await screen.findByTestId("mfa-recovery-codes");
  }

  it("removes the recovery codes from the DOM after acknowledgement", async () => {
    await confirmEnrollment();
    expect(screen.getByText("AAAA-BBBB-CCCC-DDDD")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("mfa-recovery-dismiss-btn"));

    expect(screen.queryByTestId("mfa-recovery-codes")).toBeNull();
    expect(screen.queryByText("AAAA-BBBB-CCCC-DDDD")).toBeNull();
    expect(screen.queryByText("EEEE-FFFF-GGGG-HHHH")).toBeNull();
    // The secret is not re-rendered either: the enrollment is complete.
    expect(screen.queryByTestId("mfa-secret")).toBeNull();
  });

  it("does not turn a non-otpauth provisioning URI into a link", async () => {
    vi.mocked(enrollTotp).mockResolvedValue({
      ...ENROLLMENT,
      otpauth_uri: "javascript:alert('xss')",
    });

    render(<SecuritySection />);
    fireEvent.click(await screen.findByTestId("mfa-enroll-btn"));

    expect(await screen.findByTestId("mfa-secret")).toHaveTextContent(
      ENROLLMENT.secret
    );
    expect(screen.queryByTestId("mfa-otpauth-link")).toBeNull();
  });
});
