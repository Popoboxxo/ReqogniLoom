/**
 * Task 25 — the same C-2/F-2-class regression the TestCase/StakeholderNeed
 * rollout waves already found and fixed (`testcase-editors-custom-fields-
 * dirty.test.tsx`, Task 22; `needs-editors-custom-fields-dirty.test.tsx`,
 * Task 23), reproduced verbatim for `RequirementEditors`: the sibling
 * `CustomFieldsEditor` feeds the unsaved-changes gate, so `handleSaved` must
 * call `markCustomFieldsClean`, not just `refresh()` — otherwise a save that
 * touched a custom field leaves the dirty flag stuck `true` forever, and the
 * very next requirement switch shows a false unsaved-changes dialog.
 * `RequirementArtifactForm` is stubbed to a dirty-inert stub on purpose — it
 * must NOT be the one reporting dirty, so any dirty state observed below can
 * only come from `customFieldsDraft`.
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
        "editor.selectRequirement": "Anforderung wählen",
        "nav.requirements": "Anforderungen",
      };
      return map[key] ?? (typeof opts?.defaultValue === "string" ? opts.defaultValue : key);
    },
    i18n: { language: "de" },
  }),
}));

const navigateMock = vi.fn();
vi.mock("react-router-dom", () => ({
  useParams: () => ({ id: "req-001" }),
  useNavigate: () => navigateMock,
}));

vi.mock("../context/WorkspaceContext", () => ({
  useWorkspace: () => ({
    activeWorkspace: { id: "ws-001", preset: "standard" },
    workspaces: [{ id: "ws-001" }],
  }),
}));

// RequirementEditors gates several write actions behind useHasRole (R2/T1) —
// not under test here, always resolve to editor/admin.
vi.mock("../hooks/useHasRole", () => ({
  useHasRole: () => () => true,
}));

const MOCK_REQUIREMENT = {
  id: "req-001",
  workspace_id: "ws-001",
  artifact_id: "art-001",
  title: "Login works",
  description: "",
  category: "functional",
  uid: "REQ-001",
  suspect: false,
  status: "draft",
  version: 1,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  custom_fields: {},
} as never;

const refreshMock = vi.fn();
vi.mock("../components/RequirementEditors/useRequirementData", () => ({
  useRequirementData: () => ({
    requirements: [MOCK_REQUIREMENT],
    requirement: MOCK_REQUIREMENT,
    upstreamLinks: [],
    downstreamLinks: [],
    linkedTitles: {},
    linkedRoutes: {},
    isLoading: false,
    error: null,
    refresh: refreshMock,
  }),
}));

// Dirty-inert stub — deliberately never calls onDirtyChange, so any dirty
// state observed below can only come from customFieldsDraft. Exposes a
// button that fires `onSaved`, simulating a successful save without pulling
// in the real ArtifactForm machinery.
vi.mock("../components/RequirementEditors/RequirementArtifactForm", () => ({
  RequirementArtifactForm: (props: { onSaved?: () => void }) => (
    <div data-testid="req-artifact-form-stub">
      <button data-testid="req-artifact-form-stub-save" onClick={() => props.onSaved?.()}>
        save
      </button>
    </div>
  ),
}));

vi.mock("../components/RequirementEditors/RequirementList", () => ({
  RequirementList: (props: { onSelect?: (id: string) => void }) => (
    <button
      data-testid="req-list-select-other"
      onClick={() => props.onSelect?.("req-002")}
    >
      select req-002
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

vi.mock("../components/RequirementEditors/ReqTraceLinkPanel", () => ({
  ReqTraceLinkPanel: () => null,
}));

vi.mock("../components/RequirementEditors/SimilarRequirementsPanel", () => ({
  SimilarRequirementsPanel: () => null,
}));

vi.mock("../api/requirements", () => ({
  requirementsApi: { create: vi.fn(), update: vi.fn(), delete: vi.fn() },
}));

// RequirementEditors reads create/delete via react-query hooks — mocked
// directly so the test does not need a QueryClientProvider wrapper.
vi.mock("../queries/requirements", () => ({
  useCreateRequirement: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeleteRequirement: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

vi.mock("../api/workspaces", () => ({
  workspacesApi: { downloadPdfReport: vi.fn() },
}));

// Must import AFTER vi.mock
import RequirementEditors from "../components/RequirementEditors/RequirementEditors";

describe("RequirementEditors — sibling CustomFieldsEditor feeds the unsaved-changes gate", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("navigates immediately when nothing was edited", async () => {
    const user = userEvent.setup();
    render(<RequirementEditors />);

    await user.click(await screen.findByTestId("req-list-select-other"));

    expect(navigateMock).toHaveBeenCalledWith("/requirements/req-002");
    expect(screen.queryByTestId("req-unsaved-changes-dialog")).not.toBeInTheDocument();
  });

  it("shows the unsaved-changes dialog when only a custom field was edited", async () => {
    const user = userEvent.setup();
    render(<RequirementEditors />);

    await user.click(await screen.findByTestId("custom-field-add"));
    await user.type(screen.getAllByTestId("custom-field-key")[0], "sap_id");
    await user.type(screen.getAllByTestId("custom-field-value")[0], "S-1");

    await user.click(screen.getByTestId("req-list-select-other"));

    expect(await screen.findByTestId("req-unsaved-changes-dialog")).toBeInTheDocument();
    expect(navigateMock).not.toHaveBeenCalled();
  });

  // The regression: handleSaved previously only called refresh(), never
  // markCustomFieldsClean — so a save that touched customFieldsDraft left
  // the dirty flag stuck `true` and the very next requirement switch showed
  // a false unsaved-changes dialog. Must clear immediately after save, not
  // just after a later switch re-anchors via useEntityReset.
  it("clears the dirty flag immediately after a successful save, not just after a later requirement switch", async () => {
    const user = userEvent.setup();
    render(<RequirementEditors />);

    await user.click(await screen.findByTestId("custom-field-add"));
    await user.type(screen.getAllByTestId("custom-field-key")[0], "sap_id");
    await waitFor(() => expect(screen.getAllByTestId("custom-field-key")[0]).toHaveValue("sap_id"));

    // Simulate a successful save (the real RequirementArtifactForm would
    // call onSaved after requirementsApi.update resolves).
    await user.click(screen.getByTestId("req-artifact-form-stub-save"));

    // Dirty must be cleared right away — switching requirements now must not
    // trigger the unsaved-changes dialog.
    await user.click(screen.getByTestId("req-list-select-other"));

    expect(navigateMock).toHaveBeenCalledWith("/requirements/req-002");
    expect(screen.queryByTestId("req-unsaved-changes-dialog")).not.toBeInTheDocument();
  });
});
