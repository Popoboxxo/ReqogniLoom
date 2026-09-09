/**
 * ARCH-L1-001 ReactFrontend — RequirementEditors unit test.
 *
 * leaf_id: COMP-RF-003 (RequirementEditors)
 * req_id:  REQ-L2-RF-003 (Requirements-Editor with Inline-Editing and Markdown),
 *          REQ-L3-RF003-001 (Inline-Editing — Title, Description, Category),
 *          REQ-L3-RF003-002 (Workflow-State-Anzeige + Transition),
 *          REQ-L3-RF003-003 (TraceabilityPanel),
 *          REQ-L1-040 (Resizable split-pane divider, analog ArchitectureEditors)
 *
 * Acceptance criterion (REQ-L2-RF-003 AC):
 *   Unit-Test: Render RequirementEditor with Mock-Requirement →
 *   alle Felder sichtbar und editierbar.
 *
 * REST mocked: requirementsApi.list, requirementsApi.update, tracelinksApi.listForArtifact
 */

import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
// Task 25: RequirementEditors now renders RequirementArtifactForm, whose
// FieldShell reads `i18n.language` directly (`helpText()`, FieldShell.tsx) —
// without the real i18next singleton initialised, `language` is `undefined`
// and `.startsWith()` throws. Same import ArchitectureEditors.test.tsx
// already relies on (Task 24).
import "../i18n/index";

// ---------------------------------------------------------------------------
// Mock API modules
// ---------------------------------------------------------------------------

// R2/T1 (systemaudit 2026-09-02): mutable so individual tests can simulate a
// non-editor session (see the role-gate describe block below) without
// re-declaring this whole apiClient mock — mirrors the `nextListResult`
// pattern in SidebarNavigation.test.tsx.
let mockAuthRoles: string[] = ["admin"];

vi.mock("../api/client", async (importActual) => ({
  ...(await importActual<typeof import("../api/client")>()),
  getList: vi.fn().mockResolvedValue({ results: [], count: 0 }),
  extractErrorMessage: vi.fn().mockReturnValue("Error"),
  // #340: NOT stubbed on purpose — the create/delete handlers under test must
  // be exercised against the real extraction logic, so a test that shows the
  // server's own message really proves the envelope is read correctly.
  setAuthToken: vi.fn(),
  setUnauthorizedHandler: vi.fn(),
  apiClient: {
    get: vi.fn((path?: string) =>
      Promise.resolve(
        path === "/auth/me/"
          ? {
              user: {
                id: "u-1",
                username: "tester",
                email: "t@x.test",
                first_name: "",
                last_name: "",
                is_active: true,
                tenant_id: "t-1",
                roles: mockAuthRoles,
              },
              tenant_id: "t-1",
              roles: mockAuthRoles,
            }
          : {}
      )
    ),
    post: vi.fn().mockResolvedValue({}),
    put: vi.fn().mockResolvedValue({}),
    patch: vi.fn().mockResolvedValue({}),
    delete: vi.fn().mockResolvedValue({}),
  },
}));

vi.mock("../api/requirements", () => ({
  requirementsApi: {
    list: vi.fn(),
    listAll: vi.fn().mockResolvedValue([]),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    get: vi.fn(),
    versions: vi.fn().mockResolvedValue([]),
    diff: vi.fn().mockResolvedValue({ fields: [], unchanged: [] }),
    // REQ-143: workflow transitions endpoint mocks (RequirementForm loads these).
    getTransitions: vi.fn().mockResolvedValue({
      current_state: "approved",
      states: ["draft", "approved", "deprecated"],
      allowed_transitions: [],
    }),
    transition: vi.fn().mockResolvedValue({}),
    // REQ-008: AI decompose endpoint mock
    aiDecomposeNextLevel: vi.fn().mockResolvedValue({
      drafts: [],
      parent_requirement_id: "req-001",
    }),
  },
}));

vi.mock("../api/tracelinks", () => ({
  tracelinksApi: {
    list: vi.fn(),
    listForArtifact: vi.fn(),
    create: vi.fn(),
    delete: vi.fn(),
    // Task 3.3: <TraceSpine>'s useDerivationChain calls impact() on mount —
    // without a mock this throws synchronously and gets swallowed into the
    // hook's own error state, stealing the extractErrorMessage() mock queue
    // from unrelated save-error assertions below.
    impact: vi.fn().mockResolvedValue([]),
  },
}));

vi.mock("../api/traceability", () => ({
  traceabilityApi: {
    resolve: vi.fn().mockResolvedValue([]),
  },
}));

vi.mock("../api/workspaces", () => ({
  workspacesApi: {
    list: vi.fn(),
    downloadPdfReport: vi.fn(),
  },
}));

vi.mock("../api/testcases", () => ({
  testcasesApi: {
    list: vi.fn(),
  },
}));

// Task 25: RequirementEditors now renders RequirementArtifactForm, which
// resolves its field set from the attribute-definition API — see the
// identical mock/rationale in ArchitectureEditors.test.tsx (Task 24).
// `getWorkspace`'s resolved value is set once in the shared `beforeEach`
// below via `REQ_DEFINITION`; `vi.clearAllMocks()` clears call history, not
// the implementation, so this one setup covers every describe block in the
// file.
vi.mock("../api/attribute-definitions", () => ({
  attributeDefinitionsApi: { getWorkspace: vi.fn() },
}));

// Stub the shared ArtifactInspector so the RightSidebar shell is countable.
// Preserves the rest of the barrel (VersionPanel, types, ...) via importActual
// and only replaces RightSidebar with a marker. This lets the test assert that
// the Inspector is rendered exactly ONCE at container level (REQ-TBD:
// remove duplicate ArtifactInspector rendering in editor components).
vi.mock("../components/shared/ArtifactInspector", async (importActual) => {
  const actual =
    await importActual<typeof import("../components/shared/ArtifactInspector")>();
  return {
    ...actual,
    RightSidebar: () => <div data-testid="artifact-inspector" />,
  };
});

// Must import AFTER vi.mock
import RequirementEditors from "../components/RequirementEditors/RequirementEditors";
import { requirementsApi } from "../api/requirements";
import { tracelinksApi } from "../api/tracelinks";
import { testcasesApi } from "../api/testcases";
import { workspacesApi } from "../api/workspaces";
import { attributeDefinitionsApi } from "../api/attribute-definitions";
import { AuthProvider } from "../context/AuthContext";
import { WorkspaceProvider } from "../context/WorkspaceContext";
import { ThemeProvider } from "../context/ThemeContext";
import { getWorkflowStatusLabel } from "../utils/workflowStatus";

// jsdom in this test runtime does not provide window.localStorage (Node's
// --localstorage-file experimental flag is not set), which ThemeProvider
// (now a WorkspaceProvider dependency, #568 phase 1) reads synchronously on
// mount. Polyfill a minimal in-memory implementation so it does not throw.
function installLocalStorageStub(): void {
  const store = new Map<string, string>();
  Object.defineProperty(window, "localStorage", {
    configurable: true,
    value: {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => void store.set(key, value),
      removeItem: (key: string) => void store.delete(key),
      clear: () => store.clear(),
    },
  });
}
installLocalStorageStub();

// ---------------------------------------------------------------------------
// Mock data
// ---------------------------------------------------------------------------

const MOCK_REQUIREMENT = {
  id: "req-001",
  workspace_id: "ws-001",
  title: "User Authentication",
  description: "## Auth\nSystem shall authenticate users.",
  category: "functional",
  status: "approved",
  change_reason: "",
  version: 1,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

// Task 25: minimal attribute definition — just enough for
// RequirementArtifactForm to render the `title` field these tests assert on
// (the load-signal / save-button / field-error interactions below only ever
// touch `title`), same minimal-fixture convention ArchitectureEditors.test.tsx
// uses (Task 24).
function reqAttr(over: Record<string, unknown>) {
  return {
    kind: "core", widget_key: null, fields: [], options: [], required: false,
    visible: true, locked: false, editable: true, section: "general", order: 1,
    label: { de: "", en: "" }, help_text: { de: "", en: "" }, default: null,
    validation: {}, ai_elicit: false, export: true, audience: "basic", ...over,
  };
}
const REQ_DEFINITION = {
  item_type: "Requirement",
  preset: "standard",
  is_customized: false,
  version: 1,
  attributes: [reqAttr({ name: "title", type: "text", required: true, order: 1 })],
};

// ---------------------------------------------------------------------------
// Render helper
// ---------------------------------------------------------------------------

function renderEditor(requirementId?: string): ReturnType<typeof render> {
  sessionStorage.setItem("reqflow_token", "test-token");

  const path = requirementId ? `/requirements/${requirementId}` : "/requirements";
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <AuthProvider>
          <ThemeProvider>
            <WorkspaceProvider>
              <Routes>
                <Route path="/requirements" element={<RequirementEditors />} />
                <Route path="/requirements/:id" element={<RequirementEditors />} />
              </Routes>
            </WorkspaceProvider>
          </ThemeProvider>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

// R2/T1: file-wide default so every pre-existing describe block below (none
// of which touch mockAuthRoles) keeps running as an editor/admin session —
// only the role-gate block further down overrides it, per-test.
//
// Task 25: also the one place `attributeDefinitionsApi.getWorkspace`'s
// resolved value is set — `vi.clearAllMocks()` (used by every nested
// `beforeEach` below) clears call history, not the mock implementation, so
// this single file-wide default covers every describe block without each one
// needing its own copy.
beforeEach(() => {
  mockAuthRoles = ["admin"];
  vi.mocked(attributeDefinitionsApi.getWorkspace).mockResolvedValue(REQ_DEFINITION as any);
});

describe("RequirementEditors (COMP-RF-003 / REQ-L2-RF-003)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();

    // Default mock implementations
    vi.mocked(requirementsApi.list).mockResolvedValue({
      results: [MOCK_REQUIREMENT],
      count: 1,
    } as any);
    vi.mocked(requirementsApi.listAll).mockResolvedValue([MOCK_REQUIREMENT] as any);

    vi.mocked(requirementsApi.get).mockResolvedValue(MOCK_REQUIREMENT);

    vi.mocked(tracelinksApi.listForArtifact).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    });

    vi.mocked(testcasesApi.list).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    });
  });

  // -------------------------------------------------------------------------
  // REQ-L1-040 — Resizable split-pane divider tests
  // -------------------------------------------------------------------------

  it("renders split-pane divider for resizing (REQ-L1-040 — enable split-pane resizing)", async () => {
    renderEditor(MOCK_REQUIREMENT.id);

    await waitFor(() => {
      const divider = screen.getByTestId("splitview-divider");
      expect(divider).toBeInTheDocument();
      expect(divider).toHaveStyle("cursor: col-resize");
    });
  });

  // -------------------------------------------------------------------------
  // REQ-TBD — ArtifactInspector must render exactly ONCE
  //
  // Regression guard: RequirementEditors (container) AND RequirementForm
  // (detail form) both used to render the shared RightSidebar, producing two
  // Inspector bars side by side in the requirements mask. The Inspector must
  // live at the container level only.
  // -------------------------------------------------------------------------

  // -------------------------------------------------------------------------
  // REQ-008 — AI-derive button in Anforderungen view
  // -------------------------------------------------------------------------

  it("renders AI-derive button (✨ Ableiten) in RequirementEditors (REQ-008)", async () => {
    renderEditor(MOCK_REQUIREMENT.id);

    await waitFor(() => {
      expect(screen.getByTestId("artifact-field-title")).toBeInTheDocument();
    });

    // AI-derive button must be present in the ReqTraceLinkPanel header
    expect(screen.getByTestId("req-ai-derive-btn")).toBeInTheDocument();
  });

  // Issue #311: zero drafts used to render the *success* message — both
  // branches of the status ternary were literally identical, so "the AI
  // returned nothing" was indistinguishable from "derivation worked".
  it("reports an empty AI derivation as a problem, not as success (issue #311)", async () => {
    const user = userEvent.setup();
    vi.mocked(requirementsApi.aiDecomposeNextLevel).mockResolvedValue({
      drafts: [],
      parent_requirement_id: MOCK_REQUIREMENT.id,
      note: "The LLM returned an empty list.",
    });
    renderEditor(MOCK_REQUIREMENT.id);

    await waitFor(() => {
      expect(screen.getByTestId("req-ai-derive-btn")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("req-ai-derive-btn"));

    const status = await screen.findByTestId("req-ai-derive-status");
    await waitFor(() => {
      expect(status).toHaveAttribute("role", "alert");
    });
    expect(status.textContent ?? "").toMatch(/aiDeriveEmpty|proposed no|keine/i);
  });

  it("reports a non-empty AI derivation as success (issue #311)", async () => {
    const user = userEvent.setup();
    vi.mocked(requirementsApi.aiDecomposeNextLevel).mockResolvedValue({
      drafts: [
        {
          title: "Child requirement",
          description: "d",
          rationale: "r",
          suggested_arch_element_id: null,
        },
      ],
      parent_requirement_id: MOCK_REQUIREMENT.id,
    });
    renderEditor(MOCK_REQUIREMENT.id);

    await waitFor(() => {
      expect(screen.getByTestId("req-ai-derive-btn")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("req-ai-derive-btn"));

    const status = await screen.findByTestId("req-ai-derive-status");
    await waitFor(() => {
      expect(status).toHaveAttribute("role", "status");
    });
  });

  it("renders the ArtifactInspector exactly once — no duplicate RightSidebar (REQ-TBD)", async () => {
    renderEditor(MOCK_REQUIREMENT.id);

    // Wait until the detail form has loaded the requirement (title field).
    await waitFor(() => {
      expect(screen.getByTestId("artifact-field-title")).toBeInTheDocument();
    });

    // Exactly one Inspector instance — not zero (missing), not two (duplicate).
    expect(screen.getAllByTestId("artifact-inspector")).toHaveLength(1);
  });

  // -------------------------------------------------------------------------
  // REQ-009 — Validation error messages on save failure
  // -------------------------------------------------------------------------

  it("shows field-specific error message on save failure instead of generic fallback (REQ-009)", async () => {
    // Task 25: RequirementArtifactForm routes a rejected save through
    // ArtifactForm's own `fieldErrorsFromException`, which prefers the
    // structured `error.details` array over the flattened `message` — the
    // per-field message therefore renders WITHOUT the "Title: " prefix, next
    // to the field itself (`FieldShell`'s own `role="alert"` span), not as a
    // page-level banner. `extractErrorMessage` is not exercised here since
    // `details` alone already yields a non-empty field-error map.
    const fieldErrorText = "This field may not be blank.";
    vi.mocked(requirementsApi.update).mockRejectedValueOnce({
      error: {
        code: "VALIDATION_ERROR",
        message: "Validation failed.",
        details: [{ field: "title", errors: [fieldErrorText] }],
      },
    });

    renderEditor(MOCK_REQUIREMENT.id);

    await waitFor(() => {
      expect(screen.getByTestId("artifact-form-save")).toBeInTheDocument();
    });

    await userEvent.click(screen.getByTestId("artifact-form-save"));

    await waitFor(() => {
      const alert = screen.getByRole("alert");
      expect(alert).toBeInTheDocument();
      expect(alert).toHaveTextContent(fieldErrorText);
    });
  });
});

// ---------------------------------------------------------------------------
// Task 3.1 — ArtifactRow list rows + EmptyState empty/no-match distinction
// ---------------------------------------------------------------------------

describe("RequirementEditors Task 3.1 (ArtifactRow / EmptyState)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();

    vi.mocked(requirementsApi.list).mockResolvedValue({
      results: [MOCK_REQUIREMENT],
      count: 1,
    } as any);
    vi.mocked(requirementsApi.listAll).mockResolvedValue([MOCK_REQUIREMENT] as any);
    vi.mocked(requirementsApi.get).mockResolvedValue(MOCK_REQUIREMENT);

    vi.mocked(tracelinksApi.listForArtifact).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    });

    vi.mocked(testcasesApi.list).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    });
  });

  it("renders each requirement as an ArtifactRow with id, status and title", async () => {
    renderEditor();

    await waitFor(() => {
      expect(screen.getByTestId(`req-row-${MOCK_REQUIREMENT.id}`)).toBeInTheDocument();
    });
    const row = screen.getByTestId(`req-row-${MOCK_REQUIREMENT.id}`);
    expect(row).toHaveTextContent(MOCK_REQUIREMENT.title);
    // GH-453: the badge renders the human-readable *label*, not the raw API
    // value — `status="approved"` shows as "Approved". The raw value stays the
    // filter/compare key (see utils/workflowStatus).
    expect(screen.getByTestId(`req-row-${MOCK_REQUIREMENT.id}-status`)).toHaveTextContent(
      getWorkflowStatusLabel(MOCK_REQUIREMENT.status)
    );
  });

  it("shows the empty variant with a create action when there are no requirements at all", async () => {
    vi.mocked(requirementsApi.list).mockResolvedValue({ results: [], count: 0 } as any);
    vi.mocked(requirementsApi.listAll).mockResolvedValue([]);
    renderEditor();

    await waitFor(() => {
      expect(screen.getByTestId("req-list-empty")).toBeInTheDocument();
    });
    expect(screen.getByTestId("req-list-empty-create")).toBeInTheDocument();
    expect(screen.queryByTestId("req-list-no-match")).not.toBeInTheDocument();
  });

  it("shows the no-match variant with only a reset-filters action when the filter matches nothing", async () => {
    renderEditor();
    await waitFor(() => {
      expect(screen.getByTestId(`req-row-${MOCK_REQUIREMENT.id}`)).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.type(screen.getByTestId("req-list-search-input"), "no such requirement title");

    await waitFor(() => {
      expect(screen.getByTestId("req-list-no-match")).toBeInTheDocument();
    });
    expect(screen.getByTestId("req-list-no-match-reset-filters")).toBeInTheDocument();
    expect(screen.queryByTestId("req-list-empty")).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// GitHub #339 / #340 — the UI must never swallow a server rejection
//
// Both issues share one root cause: the list-level write handlers in
// RequirementEditors caught their rejection into `console.error` and had no
// UI surface at all, so a rejected create/delete was indistinguishable from a
// no-op. Every sibling artifact container (Need/Risk/TestCase/Adr/Issue)
// already rendered a `createError`; Requirements was the one that did not.
// ---------------------------------------------------------------------------

describe("RequirementEditors — server validation errors are visible (#339/#340)", () => {
  /** The exact 400 body the free-text guard produces for markup in a title. */
  const XSS_REJECTION = {
    error: {
      code: "VALIDATION_ERROR",
      message: "Validation failed.",
      details: [
        {
          field: "title",
          errors: [
            "contains disallowed content: HTML markup is not permitted in free-text fields.",
          ],
        },
      ],
    },
  };

  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();

    vi.mocked(requirementsApi.list).mockResolvedValue({
      results: [MOCK_REQUIREMENT],
      count: 1,
    } as any);
    vi.mocked(requirementsApi.listAll).mockResolvedValue([MOCK_REQUIREMENT] as any);
    vi.mocked(requirementsApi.get).mockResolvedValue(MOCK_REQUIREMENT);
    vi.mocked(tracelinksApi.listForArtifact).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    });
    vi.mocked(testcasesApi.list).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    });
  });

  it("renders the server's rejection reason when a create is refused", async () => {
    vi.mocked(requirementsApi.create).mockRejectedValueOnce(XSS_REJECTION);
    const user = userEvent.setup();
    renderEditor();

    await waitFor(() =>
      expect(screen.getByTestId("create-req-btn")).toBeInTheDocument()
    );
    await user.click(screen.getByTestId("create-req-btn"));
    await user.type(
      screen.getByTestId("req-new-title-input"),
      "<script>alert(1)</script>"
    );
    await user.click(screen.getByTestId("req-new-save-btn"));

    const alert = await screen.findByTestId("req-create-error");
    expect(alert).toHaveAttribute("role", "alert");
    expect(alert).toHaveTextContent(
      "HTML markup is not permitted in free-text fields."
    );
  });

  it("keeps the create form (and the typed title) open after a refused create", async () => {
    vi.mocked(requirementsApi.create).mockRejectedValueOnce(XSS_REJECTION);
    const user = userEvent.setup();
    renderEditor();

    await waitFor(() =>
      expect(screen.getByTestId("create-req-btn")).toBeInTheDocument()
    );
    await user.click(screen.getByTestId("create-req-btn"));
    await user.type(screen.getByTestId("req-new-title-input"), "<b>x</b>");
    await user.click(screen.getByTestId("req-new-save-btn"));

    await screen.findByTestId("req-create-error");
    // Nothing was lost: the user can correct the title in place.
    expect(screen.getByTestId("req-new-title-input")).toHaveValue("<b>x</b>");
  });

  it("clears the create error once the user starts correcting the title", async () => {
    vi.mocked(requirementsApi.create).mockRejectedValueOnce(XSS_REJECTION);
    const user = userEvent.setup();
    renderEditor();

    await waitFor(() =>
      expect(screen.getByTestId("create-req-btn")).toBeInTheDocument()
    );
    await user.click(screen.getByTestId("create-req-btn"));
    await user.type(screen.getByTestId("req-new-title-input"), "<b>x</b>");
    await user.click(screen.getByTestId("req-new-save-btn"));
    await screen.findByTestId("req-create-error");

    await user.type(screen.getByTestId("req-new-title-input"), "y");

    await waitFor(() =>
      expect(screen.queryByTestId("req-create-error")).not.toBeInTheDocument()
    );
  });

  it("falls back to localised copy when the rejection carries no message", async () => {
    vi.mocked(requirementsApi.create).mockRejectedValueOnce({ weird: true });
    const user = userEvent.setup();
    renderEditor();

    await waitFor(() =>
      expect(screen.getByTestId("create-req-btn")).toBeInTheDocument()
    );
    await user.click(screen.getByTestId("create-req-btn"));
    await user.type(screen.getByTestId("req-new-title-input"), "Fine title");
    await user.click(screen.getByTestId("req-new-save-btn"));

    const alert = await screen.findByTestId("req-create-error");
    // Never an "[object Object]" dump — the container's own i18n key wins.
    expect(alert.textContent).not.toContain("object Object");
    expect(alert.textContent?.trim().length).toBeGreaterThan(0);
  });

  // -----------------------------------------------------------------------
  // BUG-02 (SYSTEMAUDIT_2026-08-18 §4): the create dialog accepted an empty
  // title. The form used to silently substitute the placeholder copy
  // ("New Requirement" / "Neue Anforderung") for a blank/whitespace-only
  // input and submit that — no error, no block, no way for the user to tell
  // their (missing) input was ignored. Title is a required field; the form
  // must refuse to submit instead of quietly inventing content.
  // -----------------------------------------------------------------------

  it("disables the save button while the title is empty (BUG-02)", async () => {
    const user = userEvent.setup();
    renderEditor();

    await waitFor(() =>
      expect(screen.getByTestId("create-req-btn")).toBeInTheDocument()
    );
    await user.click(screen.getByTestId("create-req-btn"));

    expect(screen.getByTestId("req-new-save-btn")).toBeDisabled();
    expect(requirementsApi.create).not.toHaveBeenCalled();
  });

  it("keeps the save button disabled for a whitespace-only title and never calls the API (BUG-02)", async () => {
    const user = userEvent.setup();
    renderEditor();

    await waitFor(() =>
      expect(screen.getByTestId("create-req-btn")).toBeInTheDocument()
    );
    await user.click(screen.getByTestId("create-req-btn"));
    await user.type(screen.getByTestId("req-new-title-input"), "   ");

    expect(screen.getByTestId("req-new-save-btn")).toBeDisabled();

    // Guard against a future regression that removes `disabled` but still
    // wires the click handler permissively: submitting the form directly
    // must still be a no-op.
    const form = screen.getByTestId("create-req-form");
    fireEvent.submit(form);
    expect(requirementsApi.create).not.toHaveBeenCalled();
  });

  it("enables the save button once a non-blank title is typed and creates with the typed title verbatim (BUG-02)", async () => {
    vi.mocked(requirementsApi.create).mockResolvedValueOnce({
      ...MOCK_REQUIREMENT,
      id: "req-002",
      title: "Real title",
    } as any);
    const user = userEvent.setup();
    renderEditor();

    await waitFor(() =>
      expect(screen.getByTestId("create-req-btn")).toBeInTheDocument()
    );
    await user.click(screen.getByTestId("create-req-btn"));
    expect(screen.getByTestId("req-new-save-btn")).toBeDisabled();

    await user.type(screen.getByTestId("req-new-title-input"), "Real title");
    expect(screen.getByTestId("req-new-save-btn")).toBeEnabled();

    await user.click(screen.getByTestId("req-new-save-btn"));

    await waitFor(() => {
      expect(requirementsApi.create).toHaveBeenCalledWith(
        expect.objectContaining({ title: "Real title" })
      );
    });
  });

  it("surfaces a refused list-level action in the page banner", async () => {
    // The PDF export is the reachable list-level action on this page (the
    // list's own delete confirmation is currently unreachable — its
    // `setConfirmDeleteId` has no caller, tracked separately). It used to
    // fail with a console.error and no download, i.e. invisibly.
    vi.mocked(workspacesApi.downloadPdfReport).mockRejectedValueOnce({
      error: {
        code: "PERMISSION_DENIED",
        message: "You do not have permission to perform this action.",
        details: [],
      },
    });
    const user = userEvent.setup();
    renderEditor();

    // UI-consistency P1: the PDF export is a rare action and now lives in the
    // page header's overflow menu (same as Architecture's export/decompose
    // entries), so it has to be opened before the item exists in the DOM.
    await waitFor(() =>
      expect(screen.getByTestId("page-header-overflow-trigger")).toBeEnabled()
    );
    await user.click(screen.getByTestId("page-header-overflow-trigger"));

    await waitFor(() =>
      expect(screen.getByTestId("export-pdf-btn")).toBeEnabled()
    );
    await user.click(screen.getByTestId("export-pdf-btn"));

    const alert = await screen.findByTestId("req-action-error");
    expect(alert).toHaveAttribute("role", "alert");
    expect(alert).toHaveTextContent(
      "You do not have permission to perform this action."
    );
  });
});

// ---------------------------------------------------------------------------
// GitHub #811 — a rejected delete must not look like a successful one
//
// RequirementList's confirm dialog used to call `onDelete` and close itself
// unconditionally in the same tick, without waiting for the (async) result.
// A server rejection (e.g. the extended preset's mandatory `change_reason`
// on delete) therefore closed the dialog and left the row in place with no
// visible sign anything had gone wrong beyond a message the dialog-close
// covered up. This suite reproduces the exact rejection from the issue and
// proves the dialog now stays open, the requirement stays in the list, and
// the failure is visible.
// ---------------------------------------------------------------------------

describe("RequirementEditors — delete flow surfaces server rejections (#811)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();

    vi.mocked(requirementsApi.list).mockResolvedValue({
      results: [MOCK_REQUIREMENT],
      count: 1,
    } as any);
    vi.mocked(requirementsApi.listAll).mockResolvedValue([MOCK_REQUIREMENT] as any);
    vi.mocked(requirementsApi.get).mockResolvedValue(MOCK_REQUIREMENT);
    vi.mocked(tracelinksApi.listForArtifact).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    });
    vi.mocked(testcasesApi.list).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    });
  });

  it("keeps the dialog open, shows the server error, and leaves the requirement listed on a rejected delete", async () => {
    vi.mocked(requirementsApi.delete).mockRejectedValueOnce({
      error: {
        code: "VALIDATION_ERROR",
        message: "change_reason is required by preset policy.",
      },
    });
    const user = userEvent.setup();
    renderEditor();

    await waitFor(() =>
      expect(screen.getByTestId(`req-row-${MOCK_REQUIREMENT.id}`)).toBeInTheDocument()
    );

    await user.click(screen.getByTestId(`req-row-delete-${MOCK_REQUIREMENT.id}`));
    await waitFor(() =>
      expect(screen.getByTestId("req-delete-dialog")).toBeInTheDocument()
    );

    await user.click(screen.getByTestId("req-confirm-delete-btn"));

    const alert = await screen.findByTestId("req-action-error");
    expect(alert).toHaveAttribute("role", "alert");
    expect(alert).toHaveTextContent("change_reason is required by preset policy.");

    // The dialog must NOT have closed itself just because onDelete settled.
    expect(screen.getByTestId("req-delete-dialog")).toBeInTheDocument();
    // No optimistic removal: the requirement is still in the list.
    expect(screen.getByTestId(`req-row-${MOCK_REQUIREMENT.id}`)).toBeInTheDocument();
  });

  it("closes the dialog and clears the row on a successful delete (control case)", async () => {
    vi.mocked(requirementsApi.delete).mockResolvedValueOnce(undefined);
    vi.mocked(requirementsApi.list).mockResolvedValueOnce({
      results: [MOCK_REQUIREMENT],
      count: 1,
    } as any).mockResolvedValue({ results: [], count: 0 } as any);
    vi.mocked(requirementsApi.listAll)
      .mockResolvedValueOnce([MOCK_REQUIREMENT] as any)
      .mockResolvedValue([]);
    const user = userEvent.setup();
    renderEditor();

    await waitFor(() =>
      expect(screen.getByTestId(`req-row-${MOCK_REQUIREMENT.id}`)).toBeInTheDocument()
    );

    await user.click(screen.getByTestId(`req-row-delete-${MOCK_REQUIREMENT.id}`));
    await waitFor(() =>
      expect(screen.getByTestId("req-delete-dialog")).toBeInTheDocument()
    );
    await user.click(screen.getByTestId("req-confirm-delete-btn"));

    await waitFor(() =>
      expect(screen.queryByTestId("req-delete-dialog")).not.toBeInTheDocument()
    );
    expect(requirementsApi.delete).toHaveBeenCalledWith(MOCK_REQUIREMENT.id, undefined);
  });
});

/**
 * BUG-11 (Systemaudit 2026-08-18, §4, Mittel) — the create-requirement form
 * only ever had a title input; `description` and `category` are ordinary
 * `requirementsApi.create()` fields (backend already accepts them) but had
 * no editor at all, so every requirement started life with an empty
 * description and no category, forcing an immediate follow-up edit.
 */
describe("RequirementEditors — create form has description/category fields (BUG-11)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    vi.mocked(requirementsApi.list).mockResolvedValue({
      results: [MOCK_REQUIREMENT],
      count: 1,
    } as any);
    vi.mocked(requirementsApi.listAll).mockResolvedValue([MOCK_REQUIREMENT] as any);
    vi.mocked(requirementsApi.get).mockResolvedValue(MOCK_REQUIREMENT);
    vi.mocked(tracelinksApi.listForArtifact).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    });
    vi.mocked(testcasesApi.list).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    });
  });

  it("sends the typed description and category alongside the title on create", async () => {
    vi.mocked(requirementsApi.create).mockResolvedValueOnce({
      ...MOCK_REQUIREMENT,
      id: "req-new",
    } as any);
    const user = userEvent.setup();
    renderEditor();

    await waitFor(() =>
      expect(screen.getByTestId("create-req-btn")).toBeInTheDocument()
    );
    await user.click(screen.getByTestId("create-req-btn"));

    await user.type(screen.getByTestId("req-new-title-input"), "New Req");
    await user.type(
      screen.getByTestId("req-new-description-input"),
      "Some description"
    );
    await user.selectOptions(
      screen.getByTestId("req-new-category-select"),
      "functional"
    );
    await user.click(screen.getByTestId("req-new-save-btn"));

    await waitFor(() =>
      expect(requirementsApi.create).toHaveBeenCalledWith(
        expect.objectContaining({
          title: "New Req",
          description: "Some description",
          category: "functional",
        })
      )
    );
  });
});

// ---------------------------------------------------------------------------
// GitHub #800 — focus trap / Tab order in the create dialog
//
// Root cause: the title input carried both `autoFocus` (native, queued-task
// timing per the HTML autofocus processing model) and the Dialog's
// `initialFocusRef` (synchronous, runs in a passive effect) — two competing
// focus-management mechanisms on the same element that could resolve in
// either order. In real-browser QA this misdirected initial focus onto the
// description field, and the Dialog's close button being first in DOM order
// put a destructive, unconfirmed action in the middle of the keyboard Tab
// flow. Fixed by removing the redundant `autoFocus` (RequirementEditors.tsx)
// and excluding the close button from the Tab cycle via `tabIndex={-1}`
// (shared Dialog.tsx, so all five create dialogs benefit).
// ---------------------------------------------------------------------------

describe("RequirementEditors — create dialog focus order (#800)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    vi.mocked(requirementsApi.list).mockResolvedValue({
      results: [MOCK_REQUIREMENT],
      count: 1,
    } as any);
    vi.mocked(requirementsApi.listAll).mockResolvedValue([MOCK_REQUIREMENT] as any);
    vi.mocked(requirementsApi.get).mockResolvedValue(MOCK_REQUIREMENT);
    vi.mocked(tracelinksApi.listForArtifact).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    });
    vi.mocked(testcasesApi.list).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    });
  });

  it("focuses the title field — not the description — right after opening", async () => {
    const user = userEvent.setup();
    renderEditor();

    await waitFor(() =>
      expect(screen.getByTestId("create-req-btn")).toBeInTheDocument()
    );
    await user.click(screen.getByTestId("create-req-btn"));

    expect(document.activeElement).toBe(screen.getByTestId("req-new-title-input"));
  });

  it("tabs through the form fields before ever reaching the close button", async () => {
    const user = userEvent.setup();
    renderEditor();

    await waitFor(() =>
      expect(screen.getByTestId("create-req-btn")).toBeInTheDocument()
    );
    await user.click(screen.getByTestId("create-req-btn"));

    // Title has a value from the moment the dialog opens onward, so Save
    // becomes reachable as a real (non-disabled) Tab stop too — type it
    // first to exercise the *full* field order, not a truncated one.
    await user.type(screen.getByTestId("req-new-title-input"), "New Req");
    expect(document.activeElement).toBe(screen.getByTestId("req-new-title-input"));

    await user.tab();
    expect(document.activeElement).toBe(screen.getByTestId("req-new-description-input"));

    await user.tab();
    expect(document.activeElement).toBe(screen.getByTestId("req-new-category-select"));

    await user.tab();
    expect(document.activeElement).toBe(screen.getByTestId("req-new-cancel-btn"));

    await user.tab();
    expect(document.activeElement).toBe(screen.getByTestId("req-new-save-btn"));

    // Issue #800: the ×-close button must never be a Tab stop — Tab from
    // the last field wraps straight back to the first one, not through ×.
    await user.tab();
    expect(document.activeElement).toBe(screen.getByTestId("req-new-title-input"));
    expect(document.activeElement).not.toBe(screen.getByTestId("req-new-dialog-close"));
  });
});

// ---------------------------------------------------------------------------
// R2/T1 (systemaudit 2026-09-02): role-gated write controls
//
// A live audit found that a "viewer" role saw the "Testfall generieren"
// trigger and the ✨ "Ableiten" button (REQ-008) here — only the server
// rejected the actual write. Both must be genuinely absent from the DOM for
// a viewer, not merely disabled ("nicht gerendert, nicht nur deaktiviert").
// Save/Delete/Status-ändern (owned by RequirementForm/RequirementList) are
// covered by their own colocated role-gate tests.
// ---------------------------------------------------------------------------

describe("RequirementEditors — role-gated write controls (R2/T1)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();

    vi.mocked(requirementsApi.list).mockResolvedValue({
      results: [MOCK_REQUIREMENT],
      count: 1,
    } as any);
    vi.mocked(requirementsApi.listAll).mockResolvedValue([MOCK_REQUIREMENT] as any);
    vi.mocked(requirementsApi.get).mockResolvedValue(MOCK_REQUIREMENT);

    vi.mocked(tracelinksApi.listForArtifact).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    });

    vi.mocked(testcasesApi.list).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    });
  });

  it("does not render 'Testfall generieren' or the Ableiten button for a viewer", async () => {
    mockAuthRoles = ["viewer"];
    renderEditor(MOCK_REQUIREMENT.id);

    await waitFor(() => {
      expect(screen.getByTestId("artifact-field-title")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("req-derive-testcase-btn")).not.toBeInTheDocument();
    expect(screen.queryByTestId("req-ai-derive-btn")).not.toBeInTheDocument();
  });

  it("renders 'Testfall generieren' and the Ableiten button for an editor", async () => {
    mockAuthRoles = ["editor"];
    renderEditor(MOCK_REQUIREMENT.id);

    await waitFor(() => {
      expect(screen.getByTestId("artifact-field-title")).toBeInTheDocument();
    });
    expect(screen.getByTestId("req-derive-testcase-btn")).toBeInTheDocument();
    expect(screen.getByTestId("req-ai-derive-btn")).toBeInTheDocument();
  });

  // Final review: the route's PageHeader primary action ("New Requirement")
  // was the last ungated create trigger on this route.
  it("does not render the 'New Requirement' primary action for a viewer", async () => {
    mockAuthRoles = ["viewer"];
    renderEditor(MOCK_REQUIREMENT.id);

    await waitFor(() => {
      expect(screen.getByTestId("artifact-field-title")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("create-req-btn")).not.toBeInTheDocument();
  });

  it("renders the 'New Requirement' primary action for an editor", async () => {
    mockAuthRoles = ["editor"];
    renderEditor(MOCK_REQUIREMENT.id);

    await waitFor(() => {
      expect(screen.getByTestId("create-req-btn")).toBeInTheDocument();
    });
  });
});
