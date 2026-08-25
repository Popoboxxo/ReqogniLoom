/**
 * Co-located tests for the interviews API wrapper (interview-management web
 * widget plan, Task 4). Mirrors the `apiClient`/`getList` mocking convention
 * used by `stakeholder-need.test.ts` / `diagrams.test.ts` — a plain mock
 * object per method (not `vi.mock`'s `importOriginal`, which no sibling
 * `src/api/*.test.ts` file in this codebase uses).
 *
 * The "multi-mode" describe group covers multi-artifact-interview plan
 * Task 8: `start()` gains `session_kind`, `formalize()` gains an optional
 * `confirmed_proposal`, and `propose()` fetches the pending proposal.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { interviewsApi } from "./interviews";

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockGetList = vi.fn();

vi.mock("./client", () => ({
  apiClient: {
    get: (...args: unknown[]) => mockGet(...args),
    post: (...args: unknown[]) => mockPost(...args),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
  getList: (...args: unknown[]) => mockGetList(...args),
}));

const WS = "11111111-1111-1111-1111-111111111111";
const SESSION = "s-1";

const STATE_FIXTURE = {
  id: SESSION,
  status: "in_progress",
  phase: "elicitation",
  collected_fields: {},
  missing_fields: [],
  grounding_snapshot: { candidates: [] },
  transcript: [],
};

describe("interviewsApi", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("start POSTs artifact_type, workspace_id and default session_kind", async () => {
    mockPost.mockResolvedValue(STATE_FIXTURE);

    const result = await interviewsApi.start(WS, "Requirement");

    expect(mockPost).toHaveBeenCalledWith("/interviews/", {
      artifact_type: "Requirement",
      workspace_id: WS,
      session_kind: "single",
    });
    expect(result.id).toBe(SESSION);
  });

  it("list passes status as a query param via getList", async () => {
    mockGetList.mockResolvedValue({ results: [], count: 0, next: null, previous: null });

    await interviewsApi.list(WS, "in_progress");

    expect(mockGetList).toHaveBeenCalledWith("/interviews/", {
      workspace_id: WS,
      status: "in_progress",
    });
  });

  it("list omits the status param when not given", async () => {
    mockGetList.mockResolvedValue({ results: [], count: 0, next: null, previous: null });

    await interviewsApi.list(WS);

    expect(mockGetList).toHaveBeenCalledWith("/interviews/", { workspace_id: WS });
  });

  it("get GETs /interviews/{id}/", async () => {
    mockGet.mockResolvedValue({
      id: SESSION,
      workspace_id: WS,
      artifact_type: "Requirement",
      status: "in_progress",
    });

    const result = await interviewsApi.get(SESSION);

    expect(mockGet).toHaveBeenCalledWith(`/interviews/${SESSION}/`);
    expect(result.id).toBe(SESSION);
  });

  it("getState GETs /interviews/{id}/state/", async () => {
    mockGet.mockResolvedValue(STATE_FIXTURE);

    const result = await interviewsApi.getState(SESSION);

    expect(mockGet).toHaveBeenCalledWith(`/interviews/${SESSION}/state/`);
    expect(result.phase).toBe("elicitation");
  });

  it("answer POSTs field and value", async () => {
    mockPost.mockResolvedValue({
      ...STATE_FIXTURE,
      collected_fields: { title: "SSO login" },
    });

    const result = await interviewsApi.answer(SESSION, "title", "SSO login");

    expect(mockPost).toHaveBeenCalledWith(`/interviews/${SESSION}/answer/`, {
      field: "title",
      value: "SSO login",
    });
    expect(result.collected_fields.title).toBe("SSO login");
  });

  it("groundingContext GETs /interviews/{id}/grounding/", async () => {
    const snapshot = { candidates: [{ artifact_id: "a-1", title: "Existing", score: 0.9 }] };
    mockGet.mockResolvedValue(snapshot);

    const result = await interviewsApi.groundingContext(SESSION);

    expect(mockGet).toHaveBeenCalledWith(`/interviews/${SESSION}/grounding/`);
    expect(result.candidates).toHaveLength(1);
  });

  it("formalize POSTs to /interviews/{id}/formalize/ with an empty body", async () => {
    mockPost.mockResolvedValue({ resulting_artifact_ids: ["req-1"], status: "completed" });

    const result = await interviewsApi.formalize(SESSION);

    expect(mockPost).toHaveBeenCalledWith(`/interviews/${SESSION}/formalize/`, {});
    expect(result.status).toBe("completed");
  });

  it("chat POSTs message to /interviews/{id}/chat/", async () => {
    mockPost.mockResolvedValue({ reply: "Got it.", state: STATE_FIXTURE });

    const result = await interviewsApi.chat(SESSION, "hello");

    expect(mockPost).toHaveBeenCalledWith(`/interviews/${SESSION}/chat/`, {
      message: "hello",
    });
    expect(result.reply).toBe("Got it.");
  });
});

describe("interviewsApi multi-mode (plan Task 8)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("start() sends session_kind and passes null artifact_type for multi", async () => {
    mockPost.mockResolvedValue(STATE_FIXTURE);

    await interviewsApi.start(WS, null, "multi");

    expect(mockPost).toHaveBeenCalledWith("/interviews/", {
      workspace_id: WS,
      artifact_type: null,
      session_kind: "multi",
    });
  });

  it("formalize() sends confirmed_proposal when given", async () => {
    mockPost.mockResolvedValue({ created: [], status: "completed" });

    const proposal = [
      { type: "StakeholderNeed", title: "N", fields: { title: "N" }, links: [] },
    ];
    await interviewsApi.formalize(SESSION, proposal);

    expect(mockPost).toHaveBeenCalledWith(`/interviews/${SESSION}/formalize/`, {
      confirmed_proposal: proposal,
    });
  });

  it("formalize() without argument posts {} (backward compatible)", async () => {
    mockPost.mockResolvedValue({ resulting_artifact_ids: [], status: "completed" });

    await interviewsApi.formalize(SESSION);

    expect(mockPost).toHaveBeenCalledWith(`/interviews/${SESSION}/formalize/`, {});
  });

  it("propose() fetches the pending proposal", async () => {
    mockGet.mockResolvedValue({ proposal: null });

    const result = await interviewsApi.propose(SESSION);

    expect(mockGet).toHaveBeenCalledWith(`/interviews/${SESSION}/propose/`);
    expect(result.proposal).toBeNull();
  });
});
