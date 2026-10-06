import type { AppState } from "../state";

// Shared across InterviewListView/InterviewFormView/ReqogniLoomPanel/
// ConnectedView tests -- every one of them exercises the "already connected"
// slice of AppState, so a single baseline avoids each file re-declaring the
// same literal (and every new AppState field having to be added in several
// places at once).
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
    memoryEntries: [],
    memoryDigest: null,
    memoryAnswer: null,
    memoryDegraded: false,
    memoryDetail: null,
    memoryLoading: false,
    memoryError: null,
    memoryLoaded: false,
    captureEnabled: false,
    pendingCapture: null,
    captureBusy: false,
    captureError: null,
    ...overrides,
  };
}
