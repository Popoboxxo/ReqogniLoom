/**
 * ARCH-L1-001 ReactFrontend — RequirementTreeNode load-failure recovery (UI-58).
 *
 * leaf_id: COMP-RF-001 (RequirementEditors)
 * req_id:  REQ-L2-RF-030 (generic reusable frontend components)
 *
 * The audit reported "no retry after a child load error". The failure was
 * worse than that: the catch block wrote `setChildNodes([])`, and `[]` is
 * indistinguishable from "loaded, no children" for the `childNodes === null`
 * guard in `toggle`. Collapsing and re-expanding therefore took the
 * already-loaded path, so a single transient 500 left that node permanently
 * empty until a full page reload.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import { RequirementTreeNode } from "./RequirementTreeNode";
import { tracelinksApi } from "../../api/tracelinks";
import { i18n } from "../../i18n/index";

vi.mock("../../api/tracelinks", () => ({
  tracelinksApi: { listForArtifact: vi.fn() },
}));

const listForArtifact = vi.mocked(tracelinksApi.listForArtifact);

const ROOT_ARTIFACT_ID = "11111111-1111-1111-1111-111111111111";
const CHILD_ARTIFACT_ID = "22222222-2222-2222-2222-222222222222";

function renderNode(): void {
  render(
    <MemoryRouter>
      <RequirementTreeNode
        workspaceId="ws-1"
        node={{
          artifactId: ROOT_ARTIFACT_ID,
          title: "Root requirement",
          artifactType: "Requirement",
        }}
        depth={0}
      />
    </MemoryRouter>,
  );
}

describe("RequirementTreeNode load-failure recovery (UI-58)", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en");
    listForArtifact.mockReset();
  });

  afterEach(() => cleanup());

  it("offers a retry that re-fetches and renders the children", async () => {
    const user = userEvent.setup();
    listForArtifact
      .mockRejectedValueOnce({ error: { message: "Backend unavailable" } })
      .mockResolvedValueOnce({
        results: [
          {
            id: "link-1",
            link_type: "decomposes",
            source_id: ROOT_ARTIFACT_ID,
            source_title: "Root requirement",
            source_type: "Requirement",
            target_id: CHILD_ARTIFACT_ID,
            target_title: "Child requirement",
            target_type: "Requirement",
          },
        ],
      } as never);

    renderNode();
    await user.click(screen.getByTestId("req-tree-toggle"));

    const error = await screen.findByTestId("req-tree-error");
    expect(error).toHaveTextContent("Backend unavailable");

    await user.click(screen.getByTestId("req-tree-retry"));

    await waitFor(() => expect(screen.queryByTestId("req-tree-error")).not.toBeInTheDocument());
    expect(await screen.findByText("Child requirement")).toBeInTheDocument();
    expect(listForArtifact).toHaveBeenCalledTimes(2);
  });

  it("re-fetches on re-expand instead of caching the failure as an empty node", async () => {
    const user = userEvent.setup();
    listForArtifact
      .mockRejectedValueOnce({ error: { message: "Backend unavailable" } })
      .mockResolvedValueOnce({ results: [] } as never);

    renderNode();
    const toggle = screen.getByTestId("req-tree-toggle");

    await user.click(toggle);
    await screen.findByTestId("req-tree-error");

    await user.click(toggle); // collapse
    await user.click(toggle); // re-expand

    await waitFor(() => expect(listForArtifact).toHaveBeenCalledTimes(2));
    expect(await screen.findByTestId("req-tree-empty")).toBeInTheDocument();
  });
});
