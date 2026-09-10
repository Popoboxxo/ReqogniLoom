/**
 * REQ-008 / REQ-L2-AI-001 / REQ-L2-AI-002: NeedsEditors — AI derive
 * feedback + Draft/Accept flow.
 *
 * Task 23 (rollout wave 2c): migrated from `need-form.test.tsx` /
 * `need-derive-requirements.test.tsx`, which exercised this behaviour on the
 * now-deleted `NeedForm`. The manual/AI-derive UI (`TraceLinkPanel`'s
 * "Ableiten" trigger, the derive status region, `DeriveRequirementsPanel`)
 * moved up into `NeedsEditors` itself (scope boundary: not an attribute, see
 * `NeedArtifactForm.tsx`'s own docstring), so this coverage now targets
 * `NeedsEditors` directly. `NeedArtifactForm` is stubbed out — it has its
 * own dedicated test file (`NeedArtifactForm.test.tsx`).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      const map: Record<string, string> = {
        "needs.deriveStarting": "KI-Ableitung wird gestartet...",
        "needs.deriveFailed": "Ableitung fehlgeschlagen.",
        "needs.deriveEmpty": "Keine Vorschläge erhalten.",
        "actions.derive": "Ableiten",
        "actions.deriving": "Leitet ab...",
        "deriveRequirements.title": "Systemanforderungen (Entwurf)",
        "deriveRequirements.accept": "Ausgewählte anlegen",
        "deriveRequirements.accepting": "Wird angelegt...",
        "deriveRequirements.discard": "Verwerfen",
        "deriveRequirements.created": `${opts?.count ?? 0} Anforderungen angelegt.`,
        "tracelinks.panelTitle": "Trace Links",
        "actions.newLink": "Neuen Link erstellen",
        "actions.showAll": "Alle anzeigen",
        "tracelinks.upstream": "Upstream",
        "tracelinks.downstream": "Downstream",
        "tracelinks.empty": "Keine Links.",
        "needs.selectNeed": "Bedarf wählen",
        "nav.needs": "Bedarfe",
        "loading": "Lädt...",
      };
      return map[key] ?? key;
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

vi.mock("../components/NeedsEditors/NeedArtifactForm", () => ({
  NeedArtifactForm: () => <div data-testid="need-artifact-form-stub" />,
}));

vi.mock("../components/NeedsEditors/NeedList", () => ({
  NeedList: () => <div data-testid="need-list-stub" />,
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
  requirementsApi: {
    create: vi.fn(),
    delete: vi.fn(),
  },
}));

vi.mock("../api/architecture", () => ({
  architectureApi: { listAll: vi.fn().mockResolvedValue([]) },
}));

vi.mock("../api/tracelinks", () => ({
  tracelinksApi: {
    listForArtifact: vi.fn().mockResolvedValue({ results: [], count: 0, next: null, previous: null }),
    create: vi.fn().mockResolvedValue({}),
    delete: vi.fn().mockResolvedValue(undefined),
  },
}));

vi.mock("../api/artifactRefs", () => ({
  resolveArtifactRefs: vi.fn().mockResolvedValue({}),
}));

// Merge fix (traceability-semantik x attribute-definition, 2026-09-10):
// CreateTraceLinkDialog (mounted inside TraceLinkPanel, which this tree
// pulls in transitively) now reads the link-type catalog via useLinkTypes()
// — needs a provider-free mock here, same pattern as every other
// non-dialog-focused test that renders it incidentally (see
// NeedsEditors.test.tsx). This file was created after that pattern was
// established elsewhere, so it never picked it up.
vi.mock("../context/LinkTypeContext", () => ({
  useLinkTypes: () => ({
    linkTypes: [],
    isLoading: false,
    error: null,
    reload: vi.fn(),
    creatableLinkTypes: [],
    definitionFor: () => undefined,
    isAllowedPair: () => false,
    labelFor: (key: string) => key,
  }),
}));

// Must import AFTER vi.mock
import NeedsEditors from "../components/NeedsEditors/NeedsEditors";
import { stakeholderNeedApi } from "../api/stakeholder-need";
import { requirementsApi } from "../api/requirements";
import { tracelinksApi } from "../api/tracelinks";

const DRAFTS = [
  {
    title: "SysReq A",
    description: "Beschreibung A",
    rationale: "weil A",
    suggested_parent_id: "need-001",
  },
  {
    title: "SysReq B",
    description: "Beschreibung B",
    rationale: "weil B",
    suggested_parent_id: "need-001",
  },
];

const clickDerive = async () => {
  const btn = await screen.findByRole("button", { name: /Ableiten/i });
  await userEvent.click(btn);
};

describe("NeedsEditors — AI derive feedback (REQ-008)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(tracelinksApi.listForArtifact).mockResolvedValue({ results: [], count: 0, next: null, previous: null });
  });

  it("shows error message with role=alert when AI derive fails (REQ-008 B1)", async () => {
    vi.mocked(stakeholderNeedApi.deriveRequirements).mockRejectedValue({
      error: { message: "KI nicht verfügbar" },
    });

    render(<NeedsEditors />);
    await clickDerive();

    const status = await screen.findByTestId("need-derive-status");
    expect(status).toHaveAttribute("role", "alert");
    expect(status.textContent).toContain("KI nicht verfügbar");
  });

  it("shows status message with role=status while AI derive is loading (REQ-008 B1)", async () => {
    vi.mocked(stakeholderNeedApi.deriveRequirements).mockReturnValue(new Promise(() => {}));

    render(<NeedsEditors />);
    await clickDerive();

    await waitFor(() => {
      const status = screen.getByTestId("need-derive-status");
      expect(status).toHaveAttribute("role", "status");
      expect(status.textContent).toContain("KI-Ableitung wird gestartet");
    });
  });
});

describe("NeedsEditors — AI derive Draft/Accept (REQ-L2-AI-002)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(tracelinksApi.listForArtifact).mockResolvedValue({ results: [], count: 0, next: null, previous: null });
  });

  it("renders the returned drafts for review instead of a fake success message", async () => {
    vi.mocked(stakeholderNeedApi.deriveRequirements).mockResolvedValue({ drafts: DRAFTS });

    render(<NeedsEditors />);
    await clickDerive();

    expect(await screen.findByTestId("derive-requirements-panel")).toBeInTheDocument();
    expect(screen.getByTestId("derive-requirements-title-0")).toHaveValue("SysReq A");
    expect(screen.getByTestId("derive-requirements-title-1")).toHaveValue("SysReq B");
  });

  it("persists accepted drafts, links them back to the need and refreshes the list", async () => {
    vi.mocked(stakeholderNeedApi.deriveRequirements).mockResolvedValue({ drafts: DRAFTS });
    vi.mocked(requirementsApi.create)
      .mockResolvedValueOnce({ id: "req-a" } as never)
      .mockResolvedValueOnce({ id: "req-b" } as never);

    render(<NeedsEditors />);
    await clickDerive();

    await screen.findByTestId("derive-requirements-panel");
    await userEvent.click(screen.getByTestId("derive-requirements-accept"));

    expect(requirementsApi.create).toHaveBeenCalledTimes(2);
    expect(requirementsApi.create).toHaveBeenCalledWith({
      workspace_id: "ws-001",
      title: "SysReq A",
      description: "Beschreibung A",
    });
    expect(tracelinksApi.create).toHaveBeenCalledWith({
      source_id: "req-a",
      target_id: "art-001",
      link_type: "derives-from",
    });
    expect(tracelinksApi.create).toHaveBeenCalledWith({
      source_id: "req-b",
      target_id: "art-001",
      link_type: "derives-from",
    });
    // Task 23: previously wired to a `onNeedsChanged` prop no call site ever
    // passed — now a plain local `refresh()` call, so this must actually run.
    await waitFor(() => expect(refreshMock).toHaveBeenCalled());
  });

  it("skips drafts the user deselected", async () => {
    vi.mocked(stakeholderNeedApi.deriveRequirements).mockResolvedValue({ drafts: DRAFTS });
    vi.mocked(requirementsApi.create).mockResolvedValue({ id: "req-b" } as never);

    render(<NeedsEditors />);
    await clickDerive();

    await screen.findByTestId("derive-requirements-panel");
    await userEvent.click(screen.getByTestId("derive-requirements-select-0"));
    await userEvent.click(screen.getByTestId("derive-requirements-accept"));

    expect(requirementsApi.create).toHaveBeenCalledTimes(1);
    expect(requirementsApi.create).toHaveBeenCalledWith({
      workspace_id: "ws-001",
      title: "SysReq B",
      description: "Beschreibung B",
    });
  });

  it("reports an empty proposal set instead of claiming success", async () => {
    vi.mocked(stakeholderNeedApi.deriveRequirements).mockResolvedValue({ drafts: [] });

    render(<NeedsEditors />);
    await clickDerive();

    const status = await screen.findByTestId("need-derive-status");
    expect(status.textContent).toContain("Keine Vorschläge");
    expect(screen.queryByTestId("derive-requirements-panel")).not.toBeInTheDocument();
  });
});
