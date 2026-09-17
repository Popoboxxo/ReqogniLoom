import type { AppState } from "../state";

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
    ...overrides,
  };
}
