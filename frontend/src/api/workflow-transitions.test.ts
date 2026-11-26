/**
 * P1.9 (M-13) — Document/WorkItem on the generic transition contract.
 *
 * `DocumentViewSet` and `WorkItemViewSet` (backend/rest_api/views_entity_core.py)
 * both mix in `WorkflowTransitionsMixin`, so they serve the same
 * `GET/POST /{resource}/{id}/transitions/` pair as every other workflow type.
 * These tests pin the three things that make the sharing safe:
 *   1. the resource path comes from the shared `RESOURCE_PATH` table,
 *   2. the generic `transition()` sends `expected_version` only when defined,
 *   3. the specialised wrappers (`documentsApi`, `workItemsApi`) keep their
 *      exact previous request bodies while now going through the shared helper.
 *
 * `listByStatus` is intentionally NOT exercised for "document"/"work-item":
 * their list endpoints ignore `?status=` (status is a row field there), so the
 * parameter is narrowed to `StatusFilterableArtifactType` and such a call is a
 * *compile* error rather than a silently unfiltered result.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";

const mockGet = vi.fn();
const mockPost = vi.fn();

vi.mock("./client", () => ({
  apiClient: {
    get: (...args: unknown[]) => mockGet(...args),
    post: (...args: unknown[]) => mockPost(...args),
    patch: vi.fn(),
    delete: vi.fn(),
  },
  getList: vi.fn(),
  // documents.ts / workItems.ts import this at module level; the transition
  // wrappers under test never reach it.
  getAllPages: vi.fn(),
}));

import {
  postWorkflowTransition,
  workflowTransitionsApi,
} from "./workflow-transitions";
import type { DocumentWorkflowArtifactType } from "./workflow-transitions";
import { documentsApi } from "./documents";
import { workItemsApi } from "./workItems";

const DOC_ID = "11111111-1111-1111-1111-111111111111";
const ITEM_ID = "22222222-2222-2222-2222-222222222222";

const DOCUMENT_TRANSITIONS = {
  current_state: "draft",
  version: 4,
  states: ["draft", "released"],
  allowed_transitions: [],
  proposed_by: null,
};

describe("workflowTransitionsApi — document/work-item routes (P1.9)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("GETs /documents/<id>/transitions/ for a document", async () => {
    mockGet.mockResolvedValue(DOCUMENT_TRANSITIONS);

    const resp = await workflowTransitionsApi.getTransitions("document", DOC_ID);

    expect(mockGet).toHaveBeenCalledWith(`/documents/${DOC_ID}/transitions/`);
    expect(resp.current_state).toBe("draft");
  });

  it("GETs /work-items/<id>/transitions/ for a work item", async () => {
    mockGet.mockResolvedValue({ ...DOCUMENT_TRANSITIONS, current_state: "open" });

    await workflowTransitionsApi.getTransitions("work-item", ITEM_ID);

    expect(mockGet).toHaveBeenCalledWith(`/work-items/${ITEM_ID}/transitions/`);
  });

  it("POSTs target_state/change_reason/credential without expected_version", async () => {
    mockPost.mockResolvedValue({
      id: DOC_ID,
      previous_state: "draft",
      new_state: "released",
    });

    await workflowTransitionsApi.transition(
      "document",
      DOC_ID,
      "released",
      "sign-off"
    );

    expect(mockPost).toHaveBeenCalledWith(`/documents/${DOC_ID}/transitions/`, {
      target_state: "released",
      change_reason: "sign-off",
      credential: "",
    });
    expect(mockPost.mock.calls[0][1]).not.toHaveProperty("expected_version");
  });

  it("POSTs expected_version only when it is provided", async () => {
    mockPost.mockResolvedValue({
      id: DOC_ID,
      previous_state: "draft",
      new_state: "released",
      version: 5,
    });

    await workflowTransitionsApi.transition(
      "document",
      DOC_ID,
      "released",
      "",
      "",
      4
    );

    expect(mockPost).toHaveBeenCalledWith(`/documents/${DOC_ID}/transitions/`, {
      target_state: "released",
      change_reason: "",
      credential: "",
      expected_version: 4,
    });
  });

  it.each<[DocumentWorkflowArtifactType, string, string]>([
    ["document", DOC_ID, "documents"],
    ["work-item", ITEM_ID, "work-items"],
  ])(
    "takes the %s path from the shared resource table",
    async (type, id, segment) => {
      mockGet.mockResolvedValue(DOCUMENT_TRANSITIONS);
      mockPost.mockResolvedValue({ id, previous_state: "a", new_state: "b" });

      await workflowTransitionsApi.getTransitions(type, id);
      await postWorkflowTransition(type, id, { target_state: "a" });

      expect(mockGet).toHaveBeenCalledWith(`/${segment}/${id}/transitions/`);
      expect(mockPost).toHaveBeenCalledWith(`/${segment}/${id}/transitions/`, {
        target_state: "a",
      });
    }
  );
});

describe("documentsApi.transition (P1.9 delegation)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("keeps the exact body and resolves {version, document}", async () => {
    const payload = { version: 6, document: { id: DOC_ID, version: 6 } };
    mockPost.mockResolvedValue({
      id: DOC_ID,
      previous_state: "draft",
      new_state: "released",
      ...payload,
    });

    const result = await documentsApi.transition(DOC_ID, "released", {
      changeReason: "ccb",
      credential: "123456",
      expectedVersion: 5,
    });

    expect(mockPost).toHaveBeenCalledWith(`/documents/${DOC_ID}/transitions/`, {
      target_state: "released",
      change_reason: "ccb",
      credential: "123456",
      expected_version: 5,
    });
    expect(result.version).toBe(6);
    expect(result.document).toEqual(payload.document);
  });

  it("omits expected_version when the caller does not pass one", async () => {
    mockPost.mockResolvedValue({
      id: DOC_ID,
      previous_state: "draft",
      new_state: "released",
      version: 1,
      document: { id: DOC_ID },
    });

    await documentsApi.transition(DOC_ID, "released");

    expect(mockPost.mock.calls[0][1]).toEqual({
      target_state: "released",
      change_reason: "",
      credential: "",
    });
  });
});

describe("workItemsApi.transition (P1.9 delegation)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("keeps blocked_reason/actor/expected_version in the body", async () => {
    const result = {
      id: ITEM_ID,
      previous_state: "in_progress",
      new_state: "blocked",
      version: 3,
      work_item: { id: ITEM_ID },
    };
    mockPost.mockResolvedValue(result);

    const resp = await workItemsApi.transition(ITEM_ID, "blocked", {
      changeReason: "waiting for review",
      expectedVersion: 2,
      blockedReason: "review pending",
      actor: "agent-1",
    });

    expect(mockPost).toHaveBeenCalledWith(
      `/work-items/${ITEM_ID}/transitions/`,
      {
        target_state: "blocked",
        change_reason: "waiting for review",
        credential: "",
        blocked_reason: "review pending",
        expected_version: 2,
        actor: "agent-1",
      }
    );
    expect(resp).toEqual(result);
  });

  it("sends only the mandatory fields when no options are passed", async () => {
    mockPost.mockResolvedValue({
      id: ITEM_ID,
      previous_state: "open",
      new_state: "in_progress",
      version: 1,
      work_item: { id: ITEM_ID },
    });

    await workItemsApi.transition(ITEM_ID, "in_progress");

    expect(mockPost.mock.calls[0][1]).toEqual({
      target_state: "in_progress",
      change_reason: "",
      credential: "",
    });
  });
});
