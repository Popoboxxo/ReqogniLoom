/**
 * C-2 (attribute-definitions Task 22 review round 1) — the exact Task 23 F-2
 * regression (`needs-editors-custom-fields-dirty.test.tsx`), reintroduced
 * verbatim in `TestCaseEditors`: the sibling `CustomFieldsEditor` feeds the
 * unsaved-changes gate, but `handleSaved` never called
 * `markCustomFieldsClean` — so a save that touched a custom field left the
 * dirty flag stuck `true` forever, and the very next test-case switch showed
 * a false unsaved-changes dialog. `TestCaseArtifactForm` is stubbed to a
 * dirty-inert stub on purpose — it must NOT be the one reporting dirty, so
 * any dirty state observed below can only come from `customFieldsDraft`
 * (mirrors the NeedsEditors scaffold).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      const map: Record<string, string> = {
        "editor.unsavedChangesTitle": "Ungesicherte Änderungen",
        "editor.unsavedChangesMessage": "Du hast ungesicherte Änderungen.",
        "editor.discardChanges": "Verwerfen",
        "customFields.section": "Freie Felder",
        "customFields.empty": "Keine freien Felder.",
        "customFields.addField": "Feld hinzufügen",
        "testcases.selectTestCase": "Testfall wählen",
        "nav.testCases": "Testfälle",
        "loading": "Lädt...",
      };
      return map[key] ?? (typeof opts?.defaultValue === "string" ? opts.defaultValue : key);
    },
    i18n: { language: "de" },
  }),
}));

const navigateMock = vi.fn();
vi.mock("react-router-dom", () => ({
  useParams: () => ({ id: "tc-001" }),
  useNavigate: () => navigateMock,
}));

vi.mock("../context/WorkspaceContext", () => ({
  useWorkspace: () => ({
    activeWorkspace: { id: "ws-001", preset: "standard" },
    workspaces: [{ id: "ws-001" }],
  }),
}));

const MOCK_TEST_CASE = {
  id: "tc-001",
  workspace_id: "ws-001",
  title: "Login works",
  description: "",
  uid: "TC-001",
  suspect: false,
  steps: [],
  test_type: null,
  status: "draft",
  version: 1,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  custom_fields: {},
} as never;

const refreshMock = vi.fn();
vi.mock("../components/TestCaseEditors/useTestCaseData", () => ({
  useTestCaseData: () => ({
    items: [MOCK_TEST_CASE],
    item: MOCK_TEST_CASE,
    isLoading: false,
    error: null,
    refresh: refreshMock,
  }),
}));

// Dirty-inert stub — deliberately never calls onDirtyChange, so any dirty
// state observed below can only come from customFieldsDraft. Exposes a
// button that fires `onSaved` (C-2), simulating a successful save without
// pulling in the real ArtifactForm machinery.
vi.mock("../components/TestCaseEditors/TestCaseArtifactForm", () => ({
  TestCaseArtifactForm: (props: { onSaved?: () => void }) => (
    <div data-testid="testcase-artifact-form-stub">
      <button data-testid="testcase-artifact-form-stub-save" onClick={() => props.onSaved?.()}>
        save
      </button>
    </div>
  ),
}));

vi.mock("../components/TestCaseEditors/TestCaseList", () => ({
  TestCaseList: (props: { onSelect?: (id: string) => void }) => (
    <button
      data-testid="tc-list-select-other"
      onClick={() => props.onSelect?.("tc-002")}
    >
      select tc-002
    </button>
  ),
}));

vi.mock("../components/SplitView/SplitView", () => ({
  SplitView: ({
    leftPanel,
    rightPanel,
  }: {
    leftPanel: React.ReactNode;
    rightPanel: React.ReactNode;
  }) => (
    <div>
      {leftPanel}
      {rightPanel}
    </div>
  ),
}));

vi.mock("../components/shared/ArtifactInspector", () => ({
  RightSidebar: () => null,
}));

vi.mock("../components/shared/TraceSpine", () => ({
  TraceSpine: () => null,
  useDerivationChain: () => ({
    stations: [],
    isLoading: false,
    error: null,
    isOpenable: false,
    resolveEntry: () => null,
  }),
}));

vi.mock("../api/testcases", () => ({
  testcasesApi: { create: vi.fn(), update: vi.fn(), delete: vi.fn() },
}));

// Must import AFTER vi.mock
import TestCaseEditors from "../components/TestCaseEditors/TestCaseEditors";

describe("TestCaseEditors — sibling CustomFieldsEditor feeds the unsaved-changes gate (C-2)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("navigates immediately when nothing was edited", async () => {
    const user = userEvent.setup();
    render(<TestCaseEditors />);

    await user.click(await screen.findByTestId("tc-list-select-other"));

    expect(navigateMock).toHaveBeenCalledWith("/testcases/tc-002");
    expect(screen.queryByTestId("tc-unsaved-changes-dialog")).not.toBeInTheDocument();
  });

  it("shows the unsaved-changes dialog when only a custom field was edited", async () => {
    const user = userEvent.setup();
    render(<TestCaseEditors />);

    await user.click(await screen.findByTestId("custom-field-add"));
    await user.type(screen.getAllByTestId("custom-field-key")[0], "sap_id");
    await user.type(screen.getAllByTestId("custom-field-value")[0], "S-1");

    await user.click(screen.getByTestId("tc-list-select-other"));

    expect(await screen.findByTestId("tc-unsaved-changes-dialog")).toBeInTheDocument();
    expect(navigateMock).not.toHaveBeenCalled();
  });

  // C-2: handleSaved previously only called refresh(), never
  // markCustomFieldsClean — so a save that touched customFieldsDraft left
  // the dirty flag stuck `true` and the very next test-case switch showed a
  // false unsaved-changes dialog. Must clear immediately after save, not
  // just after a later switch re-anchors via useEntityReset.
  it("clears the dirty flag immediately after a successful save, not just after a later test-case switch (C-2)", async () => {
    const user = userEvent.setup();
    render(<TestCaseEditors />);

    await user.click(await screen.findByTestId("custom-field-add"));
    await user.type(screen.getAllByTestId("custom-field-key")[0], "sap_id");
    await waitFor(() => expect(screen.getAllByTestId("custom-field-key")[0]).toHaveValue("sap_id"));

    // Simulate a successful save (the real TestCaseArtifactForm would call
    // onSaved after testcasesApi.update resolves).
    await user.click(screen.getByTestId("testcase-artifact-form-stub-save"));

    // Dirty must be cleared right away — switching test cases now must not
    // trigger the unsaved-changes dialog.
    await user.click(screen.getByTestId("tc-list-select-other"));

    expect(navigateMock).toHaveBeenCalledWith("/testcases/tc-002");
    expect(screen.queryByTestId("tc-unsaved-changes-dialog")).not.toBeInTheDocument();
  });
});
