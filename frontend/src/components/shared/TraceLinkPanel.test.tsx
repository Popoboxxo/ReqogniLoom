/**
 * Regression coverage for #421 — the panel header ("Trace Links") and the
 * upstream/downstream column headings ("Incoming"/"Outgoing") stayed
 * English in the German UI because the `tracelinks.*` i18n namespace never
 * existed in de.json/en.json; `t(key, englishDefault)` silently fell back
 * to the (English) default on every render, in either language.
 *
 * Uses the real i18n resources (not a mocked `t`) so this actually
 * exercises the JSON translation files, not just the component's default
 * fallback strings.
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { i18n } from "../../i18n/index";
import { TraceLinkPanel } from "./TraceLinkPanel";
import { tracelinksApi } from "../../api/tracelinks";
import { resolveArtifactRef } from "../../api/artifactRefs";

vi.mock("../../api/tracelinks", () => ({
  tracelinksApi: {
    listForArtifact: vi.fn().mockResolvedValue({ results: [], count: 0 }),
    create: vi.fn(),
    delete: vi.fn(),
  },
}));

vi.mock("../../api/artifactRefs", () => ({
  resolveArtifactRef: vi
    .fn()
    .mockResolvedValue({ title: "Neighbour", route: "/requirements/x" }),
}));

vi.mock("../../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "ws-1", default_link_type: "derives-from" } }),
}));

describe("TraceLinkPanel — i18n (#421)", () => {
  it("renders the German panel title and column headings, not the English defaults", async () => {
    await i18n.changeLanguage("de");

    render(
      <MemoryRouter>
        <TraceLinkPanel workspaceId="ws-1" artifactId="art-1" />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText("Trace-Links")).toBeInTheDocument();
    });
    expect(screen.getByText("Eingehend")).toBeInTheDocument();
    expect(screen.getByText("Ausgehend")).toBeInTheDocument();
    expect(screen.queryByText("Incoming")).not.toBeInTheDocument();
    expect(screen.queryByText("Outgoing")).not.toBeInTheDocument();
  });
});

/**
 * Regression coverage for #512 — "UI calls a dead endpoint:
 * GET /api/v1/artifacts/{id}/ -> 404 on the Architecture detail page".
 *
 * The editors pass their *entity* id (ArchitectureElement.id) as
 * `artifactId`. GET /tracelinks/?artifact_id=<id> resolves that internally
 * but echoes the id back verbatim as this link's own endpoint
 * (rest_api/views.py::_neighbor_to_dict), so the response mixes one entity
 * id with Artifact ids for the neighbours. The panel used to resolve *both*
 * endpoints of every link, which meant one guaranteed 404 per panel load —
 * for a title that renderLinkItem never displays, since it only ever shows
 * the other end of the link.
 */
describe("TraceLinkPanel — artifact ref resolution (#512)", () => {
  const ENTITY_ID = "11111111-1111-1111-1111-111111111111";
  const NEIGHBOUR_ID = "22222222-2222-2222-2222-222222222222";

  const link = (overrides: Record<string, unknown>) => ({
    id: "link-1",
    link_type: "derives-from",
    version: 1,
    created_at: "2026-08-14T00:00:00Z",
    source_title: "",
    target_title: "",
    source_type: "",
    target_type: "",
    ...overrides,
  });

  it("resolves only the other endpoint, never the artifact the panel is on", async () => {
    vi.mocked(resolveArtifactRef).mockClear();
    vi.mocked(tracelinksApi.listForArtifact).mockResolvedValueOnce({
      // upstream: the panel's own artifact is the target
      results: [link({ source_id: NEIGHBOUR_ID, target_id: ENTITY_ID })],
      count: 1,
    } as never);

    render(
      <MemoryRouter>
        <TraceLinkPanel workspaceId="ws-1" artifactId={ENTITY_ID} />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(vi.mocked(resolveArtifactRef)).toHaveBeenCalledWith(NEIGHBOUR_ID);
    });
    expect(vi.mocked(resolveArtifactRef)).not.toHaveBeenCalledWith(ENTITY_ID);
    expect(vi.mocked(resolveArtifactRef)).toHaveBeenCalledTimes(1);
  });

  it("does not resolve anything the backend already supplied a title for", async () => {
    vi.mocked(resolveArtifactRef).mockClear();
    vi.mocked(tracelinksApi.listForArtifact).mockResolvedValueOnce({
      // downstream: the panel's own artifact is the source
      results: [
        link({
          source_id: ENTITY_ID,
          target_id: NEIGHBOUR_ID,
          target_title: "Resolved by backend",
          target_type: "Requirement",
        }),
      ],
      count: 1,
    } as never);

    render(
      <MemoryRouter>
        <TraceLinkPanel workspaceId="ws-1" artifactId={ENTITY_ID} />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText("Resolved by backend")).toBeInTheDocument();
    });
    expect(vi.mocked(resolveArtifactRef)).not.toHaveBeenCalled();
  });
});

/**
 * Regression coverage for systemaudit 2026-08-29 Bug 1 — deleting a trace
 * link via this shared panel (used by ADR/Architecture/Issue/Needs/Risk
 * editors) skipped confirmation entirely and called the delete API directly
 * on click. This must go through a ConfirmDialog first, matching
 * ReqTraceLinkPanel's already-correct pattern (UI-09).
 */
describe("TraceLinkPanel — delete confirmation (systemaudit Bug 1)", () => {
  const ENTITY_ID = "11111111-1111-1111-1111-111111111111";
  const NEIGHBOUR_ID = "22222222-2222-2222-2222-222222222222";
  const LINK_ID = "33333333-3333-3333-3333-333333333333";

  const link = (overrides: Record<string, unknown> = {}) => ({
    id: LINK_ID,
    source_id: ENTITY_ID,
    target_id: NEIGHBOUR_ID,
    link_type: "derives-from",
    version: 1,
    created_at: "2026-08-14T00:00:00Z",
    source_title: "",
    target_title: "Neighbour",
    source_type: "",
    target_type: "Requirement",
    ...overrides,
  });

  it("does not call delete on click — shows a ConfirmDialog instead", async () => {
    vi.mocked(tracelinksApi.delete).mockClear();
    vi.mocked(tracelinksApi.listForArtifact).mockResolvedValueOnce({
      results: [link()],
      count: 1,
    } as never);

    render(
      <MemoryRouter>
        <TraceLinkPanel workspaceId="ws-1" artifactId={ENTITY_ID} />
      </MemoryRouter>
    );

    const deleteBtn = await screen.findByTestId(`trace-link-delete-${LINK_ID}`);
    fireEvent.click(deleteBtn);

    expect(
      await screen.findByTestId("tracelink-panel-delete-confirm")
    ).toBeInTheDocument();
    expect(vi.mocked(tracelinksApi.delete)).not.toHaveBeenCalled();
  });

  it("calls delete with the real TraceLink id only after confirming", async () => {
    vi.mocked(tracelinksApi.delete).mockClear();
    vi.mocked(tracelinksApi.delete).mockResolvedValueOnce(undefined as never);
    vi.mocked(tracelinksApi.listForArtifact)
      .mockResolvedValueOnce({ results: [link()], count: 1 } as never)
      .mockResolvedValueOnce({ results: [], count: 0 } as never);

    render(
      <MemoryRouter>
        <TraceLinkPanel workspaceId="ws-1" artifactId={ENTITY_ID} />
      </MemoryRouter>
    );

    const deleteBtn = await screen.findByTestId(`trace-link-delete-${LINK_ID}`);
    fireEvent.click(deleteBtn);

    const confirmBtn = await screen.findByTestId(
      "tracelink-panel-delete-confirm-confirm"
    );
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(vi.mocked(tracelinksApi.delete)).toHaveBeenCalledWith(LINK_ID);
    });
  });

  it("cancelling the dialog leaves the link untouched", async () => {
    vi.mocked(tracelinksApi.delete).mockClear();
    vi.mocked(tracelinksApi.listForArtifact).mockResolvedValueOnce({
      results: [link()],
      count: 1,
    } as never);

    render(
      <MemoryRouter>
        <TraceLinkPanel workspaceId="ws-1" artifactId={ENTITY_ID} />
      </MemoryRouter>
    );

    const deleteBtn = await screen.findByTestId(`trace-link-delete-${LINK_ID}`);
    fireEvent.click(deleteBtn);

    const cancelBtn = await screen.findByTestId(
      "tracelink-panel-delete-confirm-cancel"
    );
    fireEvent.click(cancelBtn);

    await waitFor(() => {
      expect(
        screen.queryByTestId("tracelink-panel-delete-confirm")
      ).not.toBeInTheDocument();
    });
    expect(vi.mocked(tracelinksApi.delete)).not.toHaveBeenCalled();
  });
});
