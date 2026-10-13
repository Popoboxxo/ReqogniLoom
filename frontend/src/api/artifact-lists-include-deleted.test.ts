import { beforeEach, describe, expect, it, vi } from "vitest";

const mockGetList = vi.fn();
const mockGetAllPages = vi.fn();

vi.mock("./client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
  getList: (...args: unknown[]) => mockGetList(...args),
  getAllPages: (...args: unknown[]) => mockGetAllPages(...args),
  extractErrorMessage: (err: unknown) => String(err),
}));

import { adrsApi } from "./adrs";
import { risksApi } from "./risks";
import { issuesApi } from "./issues";
import { testcasesApi } from "./testcases";
import { stakeholderNeedApi } from "./stakeholder-need";
import { architectureApi } from "./architecture";

const WORKSPACE = "11111111-1111-1111-1111-111111111111";

function emptyPage() {
  return { results: [], count: 0, next: null, previous: null };
}

describe("artifact list wrappers expose include_deleted (D6)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetList.mockResolvedValue(emptyPage());
    mockGetAllPages.mockResolvedValue([]);
  });

  it("adrsApi.listAll forwards include_deleted only when asked", async () => {
    await adrsApi.listAll(WORKSPACE);
    expect(mockGetAllPages.mock.calls[0][1]).toEqual({ workspace_id: WORKSPACE });

    await adrsApi.listAll(WORKSPACE, true);
    expect(mockGetAllPages.mock.calls[1][1]).toMatchObject({
      workspace_id: WORKSPACE,
      include_deleted: "true",
    });
  });

  it("risksApi.listAll forwards include_deleted only when asked", async () => {
    await risksApi.listAll(WORKSPACE, true);
    expect(mockGetAllPages.mock.calls[0][0]).toBe("/risks/");
    expect(mockGetAllPages.mock.calls[0][1]).toMatchObject({
      include_deleted: "true",
    });

    await risksApi.listAll(WORKSPACE);
    expect(mockGetAllPages.mock.calls[1][1]).not.toHaveProperty("include_deleted");
  });

  it("issuesApi.listAll forwards include_deleted only when asked", async () => {
    await issuesApi.listAll(WORKSPACE, true);
    expect(mockGetAllPages.mock.calls[0][1]).toMatchObject({
      include_deleted: "true",
    });
  });

  it("testcasesApi.listAll forwards include_deleted only when asked", async () => {
    await testcasesApi.listAll(WORKSPACE, true);
    expect(mockGetAllPages.mock.calls[0][1]).toMatchObject({
      include_deleted: "true",
    });
  });

  it("stakeholderNeedApi.listAll forwards include_deleted only when asked", async () => {
    await stakeholderNeedApi.listAll(WORKSPACE, true);
    expect(mockGetAllPages.mock.calls[0][0]).toBe(
      `/workspaces/${WORKSPACE}/needs/`,
    );
    expect(mockGetAllPages.mock.calls[0][1]).toMatchObject({
      include_deleted: "true",
    });
  });

  it("architectureApi.listAll forwards include_deleted only when asked", async () => {
    await architectureApi.listAll(WORKSPACE, true);
    expect(mockGetList.mock.calls[0][0]).toBe("/architecture/");
    expect(mockGetList.mock.calls[0][1]).toMatchObject({
      workspace_id: WORKSPACE,
      include_deleted: "true",
    });

    await architectureApi.listAll(WORKSPACE);
    expect(mockGetList.mock.calls[1][1]).not.toHaveProperty("include_deleted");
  });
});
