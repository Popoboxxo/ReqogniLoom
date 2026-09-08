/**
 * Task 23 fix round 3, N-1 — the sibling `CustomFieldsEditor` NeedsEditors
 * renders next to `NeedArtifactForm` was not wired into the unsaved-changes
 * guard at all: editing only a custom field and then selecting a different
 * need discarded the edit with no confirmation. `NeedArtifactForm` is
 * stubbed to a dirty-inert stub here on purpose — it must NOT be the one
 * reporting dirty for these assertions to actually prove `customFieldsDraft`
 * itself feeds the gate (mirrors the derive-flow scaffold in
 * `needs-editors-derive.test.tsx`).
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
        "needs.selectNeed": "Bedarf wählen",
        "nav.needs": "Bedarfe",
        "loading": "Lädt...",
      };
      return map[key] ?? (typeof opts?.defaultValue === "string" ? opts.defaultValue : key);
    },
    i18n: { language: "de" },
  }),
}));

const navigateMock = vi.fn();
vi.mock("react-router-dom", () => ({
  useParams: () => ({ id: "need-001" }),
  useNavigate: () => navigateMock,
}));

vi.mock("../context/WorkspaceContext", () => ({
  useWorkspace: () => ({
    activeWorkspace: { id: "ws-001", preset: "standard" },
    workspaces: [{ id: "ws-001" }],
  }),
}));

const MOCK_NEED = {
  id: "need-001",
  workspace_id: "ws-001",
  artifact_id: "art-001",
  title: "Als Nutzer möchte ich ...",
  description: "",
  category: "",
  status: "draft",
  moscow_priority: undefined,
  uid: "SN-001",
  suspect: false,
  version: 1,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  custom_fields: {},
} as never;

const refreshMock = vi.fn();
vi.mock("../components/NeedsEditors/useNeedData", () => ({
  useNeedData: () => ({
    needs: [MOCK_NEED],
    need: MOCK_NEED,
    isLoading: false,
    error: null,
    refresh: refreshMock,
  }),
}));

// Dirty-inert stub — deliberately never calls onDirtyChange, so any dirty
// state observed below can only come from customFieldsDraft. Exposes a
// button that fires `onSaved` (F-2), simulating a successful save without
// pulling in the real ArtifactForm machinery.
vi.mock("../components/NeedsEditors/NeedArtifactForm", () => ({
  NeedArtifactForm: (props: { onSaved?: () => void }) => (
    <div data-testid="need-artifact-form-stub">
      <button data-testid="need-artifact-form-stub-save" onClick={() => props.onSaved?.()}>
        save
      </button>
    </div>
  ),
}));

vi.mock("../components/NeedsEditors/NeedList", () => ({
  NeedList: (props: { onSelect?: (id: string) => void }) => (
    <button
      data-testid="need-list-select-other"
      onClick={() => props.onSelect?.("need-002")}
    >
      select need-002
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

vi.mock("../api/stakeholder-need", () => ({
  stakeholderNeedApi: {
    create: vi.fn(),
    deriveRequirements: vi.fn(),
  },
}));

vi.mock("../api/requirements", () => ({
  requirementsApi: { create: vi.fn(), delete: vi.fn() },
}));

vi.mock("../api/architecture", () => ({
  architectureApi: { listAll: vi.fn().mockResolvedValue([]) },
}));

vi.mock("../api/tracelinks", () => ({
  tracelinksApi: {
    listForArtifact: vi
      .fn()
      .mockResolvedValue({ results: [], count: 0, next: null, previous: null }),
    create: vi.fn().mockResolvedValue({}),
    delete: vi.fn().mockResolvedValue(undefined),
  },
}));

vi.mock("../api/artifactRefs", () => ({
  resolveArtifactRefs: vi.fn().mockResolvedValue({}),
}));

// Must import AFTER vi.mock
import NeedsEditors from "../components/NeedsEditors/NeedsEditors";

describe("NeedsEditors — sibling CustomFieldsEditor feeds the unsaved-changes gate (N-1)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("navigates immediately when nothing was edited", async () => {
    const user = userEvent.setup();
    render(<NeedsEditors />);

    await user.click(await screen.findByTestId("need-list-select-other"));

    expect(navigateMock).toHaveBeenCalledWith("/needs/need-002");
    expect(screen.queryByTestId("need-unsaved-changes-dialog")).not.toBeInTheDocument();
  });

  it("shows the unsaved-changes dialog when only a custom field was edited (reviewer's composed probe)", async () => {
    const user = userEvent.setup();
    render(<NeedsEditors />);

    await user.click(await screen.findByTestId("custom-field-add"));
    await user.type(screen.getAllByTestId("custom-field-key")[0], "sap_id");
    await user.type(screen.getAllByTestId("custom-field-value")[0], "S-1");

    await user.click(screen.getByTestId("need-list-select-other"));

    expect(await screen.findByTestId("need-unsaved-changes-dialog")).toBeInTheDocument();
    expect(navigateMock).not.toHaveBeenCalled();
  });

  it("clears back to not-dirty once the custom field is removed again (real value-diff, not a non-empty check)", async () => {
    const user = userEvent.setup();
    render(<NeedsEditors />);

    await user.click(await screen.findByTestId("custom-field-add"));
    await user.type(screen.getAllByTestId("custom-field-key")[0], "sap_id");
    await waitFor(() => expect(screen.getAllByTestId("custom-field-key")[0]).toHaveValue("sap_id"));

    // Undo: remove the row again — customFieldsDraft is back to `{}`, equal
    // to need.custom_fields, so this must NOT still count as dirty.
    await user.click(screen.getByTestId("custom-field-remove"));

    await user.click(screen.getByTestId("need-list-select-other"));

    expect(navigateMock).toHaveBeenCalledWith("/needs/need-002");
    expect(screen.queryByTestId("need-unsaved-changes-dialog")).not.toBeInTheDocument();
  });

  // F-2 (Task 23 fix round 4): handleSaved previously only called refresh(),
  // never markCustomFieldsClean — so a save that touched customFieldsDraft
  // left the dirty flag stuck `true` and the very next need-switch showed a
  // false unsaved-changes dialog. Must clear immediately after save, not
  // just after a subsequent need switch re-anchors via useEntityReset.
  it("clears the dirty flag immediately after a successful save, not just after a later need switch (F-2)", async () => {
    const user = userEvent.setup();
    render(<NeedsEditors />);

    await user.click(await screen.findByTestId("custom-field-add"));
    await user.type(screen.getAllByTestId("custom-field-key")[0], "sap_id");
    await waitFor(() => expect(screen.getAllByTestId("custom-field-key")[0]).toHaveValue("sap_id"));

    // Simulate a successful save (the real NeedArtifactForm would call
    // onSaved after stakeholderNeedApi.update resolves).
    await user.click(screen.getByTestId("need-artifact-form-stub-save"));

    // Dirty must be cleared right away — switching needs now must not
    // trigger the unsaved-changes dialog.
    await user.click(screen.getByTestId("need-list-select-other"));

    expect(navigateMock).toHaveBeenCalledWith("/needs/need-002");
    expect(screen.queryByTestId("need-unsaved-changes-dialog")).not.toBeInTheDocument();
  });
});
