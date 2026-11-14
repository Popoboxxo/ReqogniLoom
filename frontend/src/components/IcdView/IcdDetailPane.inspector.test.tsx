/**
 * IcdDetailPane — the inspector mount (#1762 / M6).
 *
 * The pane used to be a `2fr 1fr` grid whose right track held the stacked
 * stacked sidebar plus a separate linked-elements panel. Since M6 the
 * shared `InspectorShell` is the right column and is the **only** place a
 * trace link is readable (spec §2.3 rule 5 for spine-less kinds).
 *
 * The comments tab is keyed on the backing Artifact UUID (`artifact_id`,
 * #1075/#1763). A legacy ICD without one gets three tabs — no comments tab,
 * no request, no error banner (spec §4.3).
 */
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import type { IcdDetail } from "../../api/icds";
import { IcdDetailPane } from "./IcdDetailPane";
import * as commentsModule from "../../api/comments";
import * as tracelinksModule from "../../api/tracelinks";
import * as icdsModule from "../../api/icds";

vi.mock("../../api/comments");
vi.mock("../../api/tracelinks");
vi.mock("../../api/icds");
vi.mock("../../api/interviews", () => ({
  interviewsApi: { getProvenance: vi.fn().mockResolvedValue({ session_id: null }) },
}));
vi.mock("../../context/WorkspaceContext", () => ({
  useWorkspace: () => ({
    activeWorkspace: { id: "ws-001", name: "WS", default_link_type: "references" },
  }),
}));
vi.mock("../../context/LinkTypeContext", () => ({
  useLinkTypes: () => ({
    linkTypes: [{ key: "references", definition: { label: {}, allowed_pairs: [] } }],
    creatableLinkTypes: [],
    isLoading: false,
    error: null,
    reload: vi.fn(),
    definitionFor: () => undefined,
    isAllowedPair: () => true,
    labelFor: (key: string) => key,
  }),
}));
vi.mock("../WorkflowStatusEditor", () => ({ WorkflowStatusEditor: () => null }));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, second?: unknown): string => {
      if (typeof second === "string") return second;
      if (second && typeof second === "object" && "defaultValue" in second) {
        return String((second as { defaultValue: unknown }).defaultValue);
      }
      return key;
    },
  }),
}));

const DETAIL: IcdDetail = {
  id: "icd-entity-1",
  // #1075: the backing Artifact id the comments route accepts.
  artifact_id: "artifact-icd-1",
  name: "NavSub ↔ GroundControl RF Link",
  workspace_id: "ws-001",
  source_element_id: "arch-1",
  target_element_id: "arch-2",
  current_version: null,
  created_at: "2026-03-01T00:00:00Z",
  version: 4,
  direction: "unidirectional",
  interface_type: "data",
  semantic_description: "RF link",
  preconditions: [],
  postconditions: [],
  invariants: [],
};

function setViewport(width: number): void {
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    writable: true,
    value: width,
  });
}

function renderPane(detail: IcdDetail): ReturnType<typeof render> {
  return render(
    <MemoryRouter>
      <IcdDetailPane
        detail={detail}
        allICDs={[]}
        artifactLabel={(id) => id}
        onSelectIcd={() => undefined}
        showNewVersion={false}
        setShowNewVersion={() => undefined}
        formError={null}
        setFormError={() => undefined}
        isSaving={false}
        onNewVersion={() => undefined}
        nvDirection="unidirectional"
        setNvDirection={() => undefined}
        nvInterfaceType=""
        setNvInterfaceType={() => undefined}
        nvContract=""
        setNvContract={() => undefined}
        nvPre=""
        setNvPre={() => undefined}
        nvPost=""
        setNvPost={() => undefined}
        nvInv=""
        setNvInv={() => undefined}
      />
    </MemoryRouter>,
  );
}

describe("IcdDetailPane — inspector mount (#1762 M6)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    window.history.replaceState({}, "", "/icds/icd-entity-1");
    setViewport(1440);
    vi.mocked(icdsModule.icdsApi.versions).mockResolvedValue([]);
    vi.mocked(icdsModule.icdsApi.diff).mockResolvedValue({
      from_version: 0,
      to_version: 1,
      changes: [],
    } as never);
    vi.mocked(commentsModule.commentsApi.list).mockResolvedValue([]);
    vi.mocked(tracelinksModule.tracelinksApi.listForArtifact).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    } as never);
  });

  it("mounts one shell as the right column with four tabs and no separate linked-elements panel", () => {
    renderPane(DETAIL);

    expect(screen.getByTestId("inspector-shell")).toBeInTheDocument();
    expect(screen.getByTestId("inspector-tab-version")).toBeInTheDocument();
    expect(screen.getByTestId("inspector-tab-diff")).toBeInTheDocument();
    expect(screen.getByTestId("inspector-tab-links")).toBeInTheDocument();
    expect(screen.getByTestId("inspector-tab-comments")).toBeInTheDocument();
    // The former linked-elements block is gone — one trace surface only.
    expect(screen.queryByTestId("icd-linked-elements")).not.toBeInTheDocument();
  });

  it("keys the comments tab on the backing Artifact UUID", async () => {
    renderPane(DETAIL);

    screen.getByTestId("inspector-tab-comments").click();

    await waitFor(() => {
      expect(commentsModule.commentsApi.list).toHaveBeenCalledWith("artifact-icd-1");
    });
    expect(commentsModule.commentsApi.list).not.toHaveBeenCalledWith("icd-entity-1");
  });

  it("renders three tabs for a legacy ICD without a backing Artifact", () => {
    renderPane({ ...DETAIL, artifact_id: null });

    expect(screen.getByTestId("inspector-tab-links")).toBeInTheDocument();
    expect(screen.queryByTestId("inspector-tab-comments")).not.toBeInTheDocument();
    expect(commentsModule.commentsApi.list).not.toHaveBeenCalled();
  });
});
