/**
 * `<AiDerivationDialog>` unit test (issue #1360, W12c).
 *
 * Pins the three-outcome contract the issue asks for, plus the state matrix a
 * data-bound component must handle explicitly:
 *
 *   1. Confirm / "Review later" / Discard are the only exits — and only the
 *      two save actions can hand drafts to the persist callback, while Discard
 *      (and the dialog's own close paths) must never do so.
 *   2. `null` drafts (preview not run), `[]` (provider proposed nothing) and
 *      "loading" are three distinct, rendered states — never conflated with
 *      "ready but silent".
 *   3. With `selectable`, only the checked drafts reach the callback and an
 *      empty selection disables both save actions.
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { AiDerivationDialog } from "./AiDerivationDialog";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      const map: Record<string, string> = {
        "aiDerivation.notice":
          "Nichts wird gespeichert, bis du bestätigst.",
        "aiDerivation.preview": "Vorschau erzeugen",
        "aiDerivation.loading": "Entwürfe werden erzeugt…",
        "aiDerivation.saving": "Wird gespeichert…",
        "aiDerivation.confirm": "Bestätigen",
        "aiDerivation.reviewLater": "Review später",
        "aiDerivation.discard": "Verwerfen",
        "aiDerivation.empty": "Die KI hat keine Entwürfe vorgeschlagen.",
        "aiDerivation.rationale": "Begründung",
        "aiDerivation.selectHint": "Wähle die Entwürfe, die angelegt werden.",
        "aiDerivation.selectDraft": `Entwurf ${opts?.index ?? ""} auswählen`,
        "aiDerivation.caveat": "Gespeicherte Entwürfe sind Vorschläge.",
        "dialog.close": "Schließen",
        "dialog.closeLabel": "Dialog schließen",
      };
      return map[key] ?? key;
    },
    i18n: { language: "de" },
  }),
}));

const DRAFTS = [
  {
    title: "Decomposed requirement 1",
    description: "Subsystem shall refine the parent.",
    rationale: "mock rationale",
  },
  { title: "Decomposed requirement 2" },
];

function renderDialog(overrides: Record<string, unknown> = {}) {
  const props = {
    open: true,
    title: "KI-Ableitung",
    drafts: DRAFTS,
    isLoading: false,
    isSubmitting: false,
    onConfirm: vi.fn(),
    onReviewLater: vi.fn(),
    onDiscard: vi.fn(),
    testIdPrefix: "ai-derive",
    ...overrides,
  } as Parameters<typeof AiDerivationDialog>[0];
  return { ...render(<AiDerivationDialog {...props} />), props };
}

describe("AiDerivationDialog", () => {
  it("renders nothing while closed", () => {
    renderDialog({ open: false });
    expect(screen.queryByTestId("ai-derive-dialog")).not.toBeInTheDocument();
  });

  it("shows every draft of the preview with title, text and rationale", () => {
    renderDialog();

    const list = screen.getByTestId("ai-derive-drafts");
    expect(list).toBeInTheDocument();
    expect(screen.getByTestId("ai-derive-title-0")).toHaveTextContent(
      "Decomposed requirement 1"
    );
    expect(screen.getByTestId("ai-derive-description-0")).toHaveTextContent(
      "Subsystem shall refine the parent."
    );
    expect(screen.getByTestId("ai-derive-rationale-0")).toHaveTextContent(
      "Begründung: mock rationale"
    );
    expect(screen.getByTestId("ai-derive-title-1")).toHaveTextContent(
      "Decomposed requirement 2"
    );
    // The honest "nothing is written without confirmation" contract.
    expect(screen.getByTestId("ai-derive-notice")).toHaveTextContent(
      "Nichts wird gespeichert"
    );
  });

  it("offers the preview trigger while the preview has not run", () => {
    const onPreview = vi.fn();
    renderDialog({ drafts: null, onPreview });

    expect(screen.queryByTestId("ai-derive-confirm")).not.toBeInTheDocument();
    expect(screen.queryByTestId("ai-derive-drafts")).not.toBeInTheDocument();
    expect(screen.getByTestId("ai-derive-preview")).toBeInTheDocument();
  });

  it("renders the loading state as a status, not as an empty result", () => {
    renderDialog({ isLoading: true });

    expect(screen.getByTestId("ai-derive-loading")).toHaveAttribute("role", "status");
    expect(screen.queryByTestId("ai-derive-empty")).not.toBeInTheDocument();
    expect(screen.queryByTestId("ai-derive-drafts")).not.toBeInTheDocument();
  });

  it("renders an empty preview as its own state with both saves disabled", () => {
    renderDialog({ drafts: [] });

    expect(screen.getByTestId("ai-derive-empty")).toBeInTheDocument();
    expect(screen.getByTestId("ai-derive-confirm")).toBeDisabled();
    expect(screen.getByTestId("ai-derive-later")).toBeDisabled();
    // Discard stays available: nothing to persist, the user can still leave.
    expect(screen.getByTestId("ai-derive-discard")).toBeEnabled();
  });

  it("surfaces a preview error in an alert", () => {
    renderDialog({ drafts: null, loadError: "Provider nicht erreichbar" });

    expect(screen.getByTestId("ai-derive-error")).toHaveAttribute("role", "alert");
    expect(screen.getByTestId("ai-derive-error")).toHaveTextContent(
      "Provider nicht erreichbar"
    );
  });

  it("hands the drafts to confirm only through the two save actions", async () => {
    const user = userEvent.setup();
    const { props } = renderDialog();

    await user.click(screen.getByTestId("ai-derive-confirm"));
    expect(props.onConfirm).toHaveBeenCalledWith(DRAFTS);
    expect(props.onReviewLater).not.toHaveBeenCalled();
    expect(props.onDiscard).not.toHaveBeenCalled();
  });

  it("hands the drafts to review-later as well (both park them in the queue)", async () => {
    const user = userEvent.setup();
    const { props } = renderDialog();

    await user.click(screen.getByTestId("ai-derive-later"));
    expect(props.onReviewLater).toHaveBeenCalledWith(DRAFTS);
    expect(props.onConfirm).not.toHaveBeenCalled();
  });

  it("never hands drafts to discard", async () => {
    const user = userEvent.setup();
    const { props } = renderDialog();

    await user.click(screen.getByTestId("ai-derive-discard"));
    expect(props.onDiscard).toHaveBeenCalledTimes(1);
    expect(props.onConfirm).not.toHaveBeenCalled();
    expect(props.onReviewLater).not.toHaveBeenCalled();
  });

  it("passes only the selected drafts when selection is on", async () => {
    const user = userEvent.setup();
    const { props } = renderDialog({ selectable: true });

    await user.click(screen.getByTestId("ai-derive-select-1"));
    await user.click(screen.getByTestId("ai-derive-confirm"));

    expect(props.onConfirm).toHaveBeenCalledWith([DRAFTS[0]]);
  });

  it("disables both save actions when the selection is emptied", async () => {
    const user = userEvent.setup();
    renderDialog({ selectable: true });

    const select0 = screen.getByTestId("ai-derive-select-0");
    const select1 = screen.getByTestId("ai-derive-select-1");
    expect(select0).toBeChecked();
    expect(select1).toBeChecked();

    await user.click(select0);
    await user.click(select1);

    expect(screen.getByTestId("ai-derive-confirm")).toBeDisabled();
    expect(screen.getByTestId("ai-derive-later")).toBeDisabled();
  });

  it("blocks the save actions while a write is in flight", () => {
    renderDialog({ isSubmitting: true });

    expect(screen.getByTestId("ai-derive-confirm")).toBeDisabled();
    expect(screen.getByTestId("ai-derive-later")).toBeDisabled();
    expect(screen.getByTestId("ai-derive-discard")).toBeDisabled();
  });

  it("shows a write failure next to the drafts and keeps them reviewable", () => {
    renderDialog({ submitError: "Serverfehler" });

    expect(screen.getByTestId("ai-derive-submit-error")).toHaveAttribute(
      "role",
      "alert"
    );
    expect(screen.getByTestId("ai-derive-drafts")).toBeInTheDocument();
    expect(screen.getByTestId("ai-derive-confirm")).toBeEnabled();
  });
});
