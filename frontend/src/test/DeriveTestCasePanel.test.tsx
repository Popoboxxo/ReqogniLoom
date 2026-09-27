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
 *
 * Issue #1091 adds the design-system assertions: every control carries a
 * global `.btn-*` class, the per-row "Entfernen" is an icon-only control with
 * a UNIQUE accessible name inside its own step row (it used to be four
 * identically-labelled text buttons in the panel's action area), and the AI
 * "generate" control carries the shared flat AI icon.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { DeriveTestCasePanel } from "../components/TestCaseEditors/DeriveTestCasePanel";
import type { TestCase } from "../api/testcases";

/**
 * t() returns the key so assertions can rely on data-testid, not copy — with
 * one exception (#1091): `deriveTestcase.removeStep` carries a `{{index}}`
 * placeholder, and the whole point of the fix is that the four controls get
 * four DIFFERENT names. An identity mock would collapse them back into one,
 * so this one key is resolved for real (same pattern as
 * `needs-editors-derive.test.tsx`).
 */
const INDEXED_TRANSLATIONS: Record<string, string> = {
  "deriveTestcase.removeStep": "Schritt {{index}} entfernen",
};
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      const template = INDEXED_TRANSLATIONS[key];
      return template
        ? template.replace("{{index}}", String(opts?.index ?? ""))
        : key;
    },
  }),
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
      // #424 (spec section 4.6): this LLM-driven path declares its provenance
      // explicitly. `reviewed` is read-only and derived server-side from
      // `origin` — it must NOT appear in the payload.
      origin: "ai_generated",
      scenario_kind: "nominal",
    });
    expect(onCreated).toHaveBeenCalledWith(CREATED_TEST_CASE);
    // Draft view is cleared after a successful create.
    expect(screen.queryByTestId("derive-testcase-draft")).toBeNull();
  });

  it("shows the AI-generated/unreviewed notice wherever a draft is on screen (#424)", async () => {
    aiDeriveTestcase.mockResolvedValue(DRAFT_RESULT);
    const user = userEvent.setup();
    renderPanel();

    expect(screen.queryByTestId("derive-testcase-ai-notice")).toBeNull();

    await user.click(screen.getByTestId("derive-testcase-generate"));
    await screen.findByTestId("derive-testcase-draft");

    expect(screen.getByTestId("derive-testcase-ai-notice")).toHaveTextContent(
      "deriveTestcase.aiNotice"
    );
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

/**
 * Issue #1091 — the panel was measured with seven unstyled browser-default
 * buttons ("Entfernen" ×4, "Schritt hinzufügen", "Testfall anlegen",
 * "Verwerfen") forming one flex row.
 */
describe("DeriveTestCasePanel — design system (#1091)", () => {
  beforeEach(() => {
    aiDeriveTestcase.mockReset();
    create.mockReset();
  });

  it("puts every control of the idle panel on a global btn-* class", () => {
    renderPanel();

    const buttons = screen.getAllByRole("button");
    expect(buttons.length).toBeGreaterThan(0);
    for (const button of buttons) {
      expect(button.className).toMatch(/(^|\s)btn-(primary|secondary|ghost|danger)(\s|$)/);
    }
  });

  it("marks the generate control as the primary action and the AI icon", () => {
    renderPanel();

    const generate = screen.getByTestId("derive-testcase-generate");
    expect(generate).toHaveClass("btn-primary");
    // #1092: a flat, single-colour icon from the repo's existing set
    // (lucide `Sparkles`) — not an emoji, which renders platform-dependently.
    const icon = generate.querySelector("svg.lucide-sparkles");
    expect(icon).not.toBeNull();
    expect(icon).toHaveAttribute("width", "16");
    expect(icon).toHaveAttribute("stroke", "currentColor");
  });

  it("gives the four per-step remove controls four unique accessible names", async () => {
    const fourSteps = {
      ...DRAFT_RESULT,
      draft: {
        ...DRAFT_RESULT.draft,
        steps: [
          { step: "A", expected_result: "a" },
          { step: "B", expected_result: "b" },
          { step: "C", expected_result: "c" },
          { step: "D", expected_result: "d" },
        ],
      },
    };
    aiDeriveTestcase.mockResolvedValue(fourSteps);
    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getByTestId("derive-testcase-generate"));
    await screen.findByTestId("derive-testcase-draft");

    const names = fourSteps.draft.steps.map(
      (_, i) => screen.getByTestId(`derive-testcase-step-remove-${i}`).getAttribute("aria-label")
    );
    expect(names).toEqual([
      "Schritt 1 entfernen",
      "Schritt 2 entfernen",
      "Schritt 3 entfernen",
      "Schritt 4 entfernen",
    ]);
    // Four screen-reader users must not hear the same name four times.
    expect(new Set(names).size).toBe(4);
    for (const name of names) {
      expect(screen.getByRole("button", { name: name as string })).toBeInTheDocument();
    }
  });

  it("keeps each remove control inside its own step row, out of the action row", async () => {
    const fourSteps = {
      ...DRAFT_RESULT,
      draft: {
        ...DRAFT_RESULT.draft,
        steps: [
          { step: "A", expected_result: "a" },
          { step: "B", expected_result: "b" },
          { step: "C", expected_result: "c" },
          { step: "D", expected_result: "d" },
        ],
      },
    };
    aiDeriveTestcase.mockResolvedValue(fourSteps);
    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getByTestId("derive-testcase-generate"));
    await screen.findByTestId("derive-testcase-draft");

    for (let i = 0; i < 4; i += 1) {
      const row = screen.getByTestId(`derive-testcase-step-${i}`);
      const remove = screen.getByTestId(`derive-testcase-step-remove-${i}`);
      // The remove control belongs to its row…
      expect(row).toContainElement(remove);
      // …and to no other row.
      for (let j = 0; j < 4; j += 1) {
        if (j === i) continue;
        expect(screen.getByTestId(`derive-testcase-step-${j}`)).not.toContainElement(remove);
      }
    }

    // The action row holds exactly the two dialog actions — no per-row remove.
    const create = screen.getByTestId("derive-testcase-create");
    const discard = screen.getByTestId("derive-testcase-discard");
    const actionRow = create.parentElement as HTMLElement;
    expect(actionRow).toContainElement(discard);
    expect(within(actionRow).getAllByRole("button")).toHaveLength(2);
    for (let i = 0; i < 4; i += 1) {
      expect(actionRow).not.toContainElement(
        screen.getByTestId(`derive-testcase-step-remove-${i}`)
      );
    }
  });

  it("keeps the destructive per-row remove off the primary hierarchy and the draft actions on it", async () => {
    aiDeriveTestcase.mockResolvedValue(DRAFT_RESULT);
    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getByTestId("derive-testcase-generate"));
    await screen.findByTestId("derive-testcase-draft");

    // "Entfernen" is destructive and per-row → not primary.
    const remove = screen.getByTestId("derive-testcase-step-remove-0");
    expect(remove).toHaveClass("btn-ghost");
    expect(remove).not.toHaveClass("btn-primary");
    // "Testfall anlegen" is the dialog's one primary action; "Verwerfen" is
    // its secondary — the same pair every other dialog in the app uses.
    expect(screen.getByTestId("derive-testcase-create")).toHaveClass("btn-primary");
    expect(screen.getByTestId("derive-testcase-discard")).toHaveClass("btn-secondary");
    expect(screen.getByTestId("derive-testcase-add-step")).toHaveClass("btn-secondary");
  });
});

