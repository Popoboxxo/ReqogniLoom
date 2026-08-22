/**
 * REQ-187 — EnforcementFlipDialog i18n regression (review-findings-remediation
 * Task 13, GESAMTTEST_BERICHT_2026-08-21.md §10.1).
 *
 * The dialog used to hardcode English text unconditionally, inside an
 * otherwise fully German UI (also a WCAG 3.1.2 "Language of Parts" issue,
 * since a screen reader would read unmarked English text with German
 * pronunciation rules). The fix translates every string via
 * `systemSettings.enforcementFlip.*` — this test asserts the dialog actually
 * renders the correct locale-specific copy per the active i18next language,
 * not just that a `t()` call was made (that would pass even against a
 * missing key, since i18next falls back to printing the key itself).
 *
 * Deliberately does NOT mock `react-i18next` (unlike most component tests in
 * this suite) — the whole point here is to exercise the real de.json/en.json
 * resources through the real i18next singleton.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, cleanup } from "@testing-library/react";

import { EnforcementFlipDialog } from "../components/SystemSettings/EnforcementFlipDialog";
import { i18n } from "../i18n/index";
import { permissionDefaultsApi } from "../api/permission-defaults";
import type { EnforcementStatus } from "../api/permission-defaults";

vi.mock("../api/permission-defaults", async () => {
  const actual = await vi.importActual<
    typeof import("../api/permission-defaults")
  >("../api/permission-defaults");
  return {
    ...actual,
    permissionDefaultsApi: {
      ...actual.permissionDefaultsApi,
      getEnforcement: vi.fn(),
      flipEnforcement: vi.fn(),
    },
  };
});

function statusWith(count: number): EnforcementStatus {
  return {
    enforcement_mode: "shadow",
    pending_mismatch_count: count,
    mismatch_window_days: 30,
    ready_for_authoritative: count === 0,
  };
}

function renderDialog(): void {
  render(
    <EnforcementFlipDialog
      windowDays={30}
      onClose={vi.fn()}
      onFlipped={vi.fn()}
    />
  );
}

describe("EnforcementFlipDialog i18n (Task 13)", () => {
  beforeEach(() => {
    vi.mocked(permissionDefaultsApi.getEnforcement).mockReset();
    vi.mocked(permissionDefaultsApi.flipEnforcement).mockReset();
  });

  afterEach(() => {
    cleanup();
    void i18n.changeLanguage("en");
  });

  it("renders German copy (plural) when the active language is German", async () => {
    void i18n.changeLanguage("de");
    vi.mocked(permissionDefaultsApi.getEnforcement).mockResolvedValue(
      statusWith(3)
    );

    renderDialog();

    expect(await screen.findByText("Wechsel zu autoritativer Durchsetzung")).toBeInTheDocument();

    await waitFor(() => {
      expect(
        screen.getByText(
          "Es gibt aktuell 3 ausstehende Abweichungen in den letzten 30 Tagen. Der Wechsel zu autoritativer Durchsetzung macht das neue Berechtigungsmodell zur alleinigen Instanz für Zugriffskontrolle."
        )
      ).toBeInTheDocument();
    });

    expect(screen.getByText("3 Abweichungen anzeigen")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Ich habe die ausstehenden Abweichungen geprüft und akzeptiere die aktuelle Anzahl von 3 vor dem Wechsel zu autoritativer Durchsetzung."
      )
    ).toBeInTheDocument();
    expect(screen.getByText("Bestätigen & wechseln")).toBeInTheDocument();

    // No leftover hardcoded English text anywhere in the dialog.
    expect(screen.queryByText(/Flip to Authoritative/i)).not.toBeInTheDocument();
  });

  it("renders German copy (singular) for exactly one pending mismatch", async () => {
    void i18n.changeLanguage("de");
    vi.mocked(permissionDefaultsApi.getEnforcement).mockResolvedValue(
      statusWith(1)
    );

    renderDialog();

    await waitFor(() => {
      expect(
        screen.getByText(
          "Es gibt aktuell 1 ausstehende Abweichung in den letzten 30 Tagen. Der Wechsel zu autoritativer Durchsetzung macht das neue Berechtigungsmodell zur alleinigen Instanz für Zugriffskontrolle."
        )
      ).toBeInTheDocument();
    });
    expect(screen.getByText("1 Abweichung anzeigen")).toBeInTheDocument();
  });

  it("renders English copy when the active language is English", async () => {
    void i18n.changeLanguage("en");
    vi.mocked(permissionDefaultsApi.getEnforcement).mockResolvedValue(
      statusWith(3)
    );

    renderDialog();

    expect(await screen.findByText("Flip to Authoritative Enforcement")).toBeInTheDocument();

    await waitFor(() => {
      expect(
        screen.getByText(
          "There are currently 3 pending mismatches in the last 30 days. Switching to authoritative enforcement makes the new permission model the sole access-control authority."
        )
      ).toBeInTheDocument();
    });
    expect(screen.getByText("View the 3 mismatches")).toBeInTheDocument();
    expect(screen.getByText("Confirm & Flip")).toBeInTheDocument();

    // No leftover German text.
    expect(screen.queryByText(/autoritativer Durchsetzung/i)).not.toBeInTheDocument();
  });

  it("shows the translated stale-count message per active language on a 409 MISMATCH_COUNT_STALE", async () => {
    void i18n.changeLanguage("de");
    vi.mocked(permissionDefaultsApi.getEnforcement).mockResolvedValue(
      statusWith(3)
    );
    vi.mocked(permissionDefaultsApi.flipEnforcement).mockRejectedValue({
      error: { details: [{ current_count: 5 }] },
    });

    renderDialog();

    const checkbox = await screen.findByTestId("flip-acknowledge");
    const { default: userEvent } = await import("@testing-library/user-event");
    const user = userEvent.setup();
    await user.click(checkbox);
    await user.click(screen.getByTestId("workflow-confirm-submit"));

    await waitFor(() => {
      expect(
        screen.getByText(
          "Die Anzahl ausstehender Abweichungen hat sich während der Prüfung auf 5 geändert. Bitte erneut prüfen und die neue Anzahl bestätigen."
        )
      ).toBeInTheDocument();
    });
  });
});
