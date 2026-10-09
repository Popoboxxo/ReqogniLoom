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
        // #1089: the success text must name WHERE the new artefacts are
        // reviewable, otherwise the accepted drafts are effectively invisible.
        "needs.deriveCreated":
          "Angelegt zur Prüfung unter „Freigaben“ → „Nur KI-Vorschläge“: {{count}}",
        "actions.deriveAi": "KI-Ableitung",
        "actions.derivingAi": "KI-Ableitung läuft…",
        "deriveRequirements.title": "Systemanforderungen (Entwurf)",
        "deriveRequirements.accept": "Ausgewählte anlegen",
        "deriveRequirements.accepting": "Wird angelegt...",
        "deriveRequirements.acceptedHint":
          "KI-Vorschlag zur Prüfung unter „Freigaben“ → „Nur KI-Vorschläge“",
        "deriveRequirements.reviewRequired": `Kein prüfbarer KI-Vorschlag: ${opts?.reason ?? ""}`,
        "deriveRequirements.discard": "Verwerfen",
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
    acceptDerivedRequirements: vi.fn(),
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

/** A 201 accept body as the server sends it (issue #1095). */
const acceptResult = (overrides: Record<string, unknown> = {}) => ({
  count: 2,
  created: [
    { id: "req-a", status: "proposed", trace_link_id: "tl-a", proposal: {} },
    { id: "req-b", status: "proposed", trace_link_id: "tl-b", proposal: {} },
  ],
  proposal: {
    state: "proposed",
    is_proposal: true,
    supported: true,
    proposed_by: "ai-derivation",
    label: "ai-derivation",
    reason: "",
  },
  ...overrides,
});

const clickDerive = async () => {
  // Issue #927: the AI trigger is "KI-Ableitung" (the manual derive is
  // "Ableiten"), so match the AI label explicitly.
  const btn = await screen.findByRole("button", { name: /KI-Ableitung/i });
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

  // Issue #1095 / #1089: the persist step moved server-side. The panel must
  // NOT go back to `requirementsApi.create` (a `user` principal seeds `draft`,
  // so the artefact never reaches the pending-review queue) nor build the
  // `derives-from` TraceLink itself (the server writes it). Both are asserted
  // as *not called* — that is the regression this change exists to pin.
  it("persists accepted drafts through the server endpoint and never via requirementsApi.create", async () => {
    vi.mocked(stakeholderNeedApi.deriveRequirements).mockResolvedValue({ drafts: DRAFTS });
    vi.mocked(stakeholderNeedApi.acceptDerivedRequirements).mockResolvedValue(
      acceptResult() as never
    );

    render(<NeedsEditors />);
    await clickDerive();

    await screen.findByTestId("derive-requirements-panel");
    await userEvent.click(screen.getByTestId("derive-requirements-accept"));

    await waitFor(() =>
      expect(stakeholderNeedApi.acceptDerivedRequirements).toHaveBeenCalledTimes(1)
    );
    // The need's PK (not its artifact id) plus the selected drafts, verbatim.
    expect(stakeholderNeedApi.acceptDerivedRequirements).toHaveBeenCalledWith("need-001", [
      {
        title: "SysReq A",
        description: "Beschreibung A",
        rationale: "weil A",
      },
      {
        title: "SysReq B",
        description: "Beschreibung B",
        rationale: "weil B",
      },
    ]);
    expect(requirementsApi.create).not.toHaveBeenCalled();
    expect(requirementsApi.delete).not.toHaveBeenCalled();
    expect(tracelinksApi.create).not.toHaveBeenCalled();
    // Task 23: previously wired to a `onNeedsChanged` prop no call site ever
    // passed — now a plain local `refresh()` call, so this must actually run.
    await waitFor(() => expect(refreshMock).toHaveBeenCalled());
  });

  it("points the user at the review surface after a successful accept (#1089)", async () => {
    vi.mocked(stakeholderNeedApi.deriveRequirements).mockResolvedValue({ drafts: DRAFTS });
    vi.mocked(stakeholderNeedApi.acceptDerivedRequirements).mockResolvedValue(
      acceptResult() as never
    );

    render(<NeedsEditors />);
    await clickDerive();

    await screen.findByTestId("derive-requirements-panel");
    await userEvent.click(screen.getByTestId("derive-requirements-accept"));

    // "created and linked" said nothing about WHERE — the reason the accepted
    // drafts were effectively invisible.
    await waitFor(() => {
      const status = screen.getByTestId("need-derive-status");
      expect(status.textContent).toContain("„Freigaben“");
      expect(status.textContent).toContain("„Nur KI-Vorschläge“");
    });
  });

  it("skips drafts the user deselected", async () => {
    vi.mocked(stakeholderNeedApi.deriveRequirements).mockResolvedValue({ drafts: DRAFTS });
    vi.mocked(stakeholderNeedApi.acceptDerivedRequirements).mockResolvedValue(
      acceptResult({ count: 1 }) as never
    );

    render(<NeedsEditors />);
    await clickDerive();

    await screen.findByTestId("derive-requirements-panel");
    await userEvent.click(screen.getByTestId("derive-requirements-select-0"));
    await userEvent.click(screen.getByTestId("derive-requirements-accept"));

    await waitFor(() =>
      expect(stakeholderNeedApi.acceptDerivedRequirements).toHaveBeenCalledWith("need-001", [
        {
          title: "SysReq B",
          description: "Beschreibung B",
          rationale: "weil B",
        },
      ])
    );
  });

  it("surfaces the server's validation message verbatim (e.g. a minimal-preset workspace)", async () => {
    vi.mocked(stakeholderNeedApi.deriveRequirements).mockResolvedValue({ drafts: DRAFTS });
    vi.mocked(stakeholderNeedApi.acceptDerivedRequirements).mockRejectedValue({
      error: { message: "This workspace cannot create reviewable AI proposals: no 'proposed' state." },
    });

    render(<NeedsEditors />);
    await clickDerive();

    await screen.findByTestId("derive-requirements-panel");
    await userEvent.click(screen.getByTestId("derive-requirements-accept"));

    const errorBox = await screen.findByTestId("derive-requirements-error");
    expect(errorBox).toHaveAttribute("role", "alert");
    expect(errorBox.textContent).toContain(
      "This workspace cannot create reviewable AI proposals: no 'proposed' state."
    );
    // Nothing was persisted, so no success status may replace the error.
    expect(screen.queryByTestId("need-derive-status")).toBeNull();
    expect(refreshMock).not.toHaveBeenCalled();
  });

  it("reports a plain draft (is_proposal=false) with the server's reason instead of claiming success", async () => {
    vi.mocked(stakeholderNeedApi.deriveRequirements).mockResolvedValue({ drafts: DRAFTS });
    vi.mocked(stakeholderNeedApi.acceptDerivedRequirements).mockResolvedValue(
      acceptResult({
        proposal: {
          state: "draft",
          is_proposal: false,
          supported: false,
          proposed_by: "",
          label: "",
          reason: "no 'proposed' state in the resolved graph",
        },
      }) as never
    );

    render(<NeedsEditors />);
    await clickDerive();

    await screen.findByTestId("derive-requirements-panel");
    await userEvent.click(screen.getByTestId("derive-requirements-accept"));

    const errorBox = await screen.findByTestId("derive-requirements-error");
    expect(errorBox.textContent).toContain("no 'proposed' state in the resolved graph");
    expect(screen.queryByTestId("need-derive-status")).toBeNull();
    expect(refreshMock).not.toHaveBeenCalled();
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
