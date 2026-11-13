import type { AppState, RequirementFormState } from "../state";
import type { Requirement } from "../api";

// Shared across InterviewListView/InterviewFormView/ReqogniLoomPanel tests --
// every one of them exercises the "already connected, viewing interviews"
// slice of AppState, so a single baseline avoids each file re-declaring the
// same 11-field literal (and every new AppState field having to be added
// in three places at once).
export function makeAppState(overrides: Partial<AppState> = {}): AppState {
  return {
    view: "interviews",
    connection: { baseUrl: "https://x", apiKey: "k", workspaceId: "ws-1" },
    workspaceName: "WS",
    pendingCredentials: null,
    pendingWorkspaces: [],
    connectError: null,
    connecting: false,
    activeInterview: null,
    interviewList: [],
    interviewError: null,
    interviewBusy: false,
    requirements: [],
    requirementsPage: 1,
    requirementsNext: null,
    requirementsPrevious: null,
    requirementsCount: 0,
    requirementsSearch: "",
    activeRequirement: null,
    requirementForm: null,
    requirementError: null,
    requirementBusy: false,
    ...overrides,
  };
}

// Full read-side requirement payload (Phase H / #1701): the views render
// `uid`, `status`, `tier_name`, `level`, `level_source` and `suspect`, so a
// fixture missing any of them would pass for the wrong reason.
export function makeRequirement(overrides: Partial<Requirement> = {}): Requirement {
  return {
    id: "req-1",
    artifact_id: "art-1",
    global_uuid: "art-1",
    workspace_id: "ws-1",
    parent_id: null,
    uid: "REQ-1",
    title: "Login must work",
    description: "Users sign in with SSO.",
    acceptance_criteria: "A valid token grants access.",
    category: "security",
    type: "SyReq",
    complexity_fibonacci: 3,
    verification_method: "Test",
    level: 2,
    tier_key: "system",
    tier_name: "System",
    released_tier_key: null,
    level_source: "derived",
    allocation_intent: "unassigned",
    status: "draft",
    suspect: false,
    atomicity_warning: null,
    version: 7,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-02T00:00:00Z",
    ...overrides,
  };
}

export function makeRequirementForm(overrides: Partial<RequirementFormState> = {}): RequirementFormState {
  return {
    mode: "create",
    values: { title: "", description: "", acceptance_criteria: "", category: "", type: "SyReq" },
    fieldErrors: {},
    changeReason: "",
    ...overrides,
  };
}
