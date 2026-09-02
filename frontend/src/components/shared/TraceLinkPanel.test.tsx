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
import { resolveArtifactRefs } from "../../api/artifactRefs";

vi.mock("../../api/tracelinks", () => ({
  tracelinksApi: {
    listForArtifact: vi.fn().mockResolvedValue({ results: [], count: 0 }),
    create: vi.fn(),
    delete: vi.fn(),
  },
}));

vi.mock("../../api/artifactRefs", () => ({
  resolveArtifactRefs: vi.fn(async (ids: string[]) =>
    Object.fromEntries(
      ids.map((id) => [id, { title: "Neighbour", route: `/requirements/entity-of-${id}` }])
    )
  ),
}));

vi.mock("../../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "ws-1", default_link_type: "derives-from" } }),
}));

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>(
    "react-router-dom"
  );
  return { ...actual, useNavigate: () => mockNavigate };
});

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
    vi.mocked(resolveArtifactRefs).mockClear();
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
      expect(vi.mocked(resolveArtifactRefs)).toHaveBeenCalledWith([NEIGHBOUR_ID]);
    });
    // The panel's own id is an *entity* id — resolving it would be the
    // wrong-id-space request #512 removed.
    const requested = vi.mocked(resolveArtifactRefs).mock.calls.flatMap((c) => c[0]);
    expect(requested).not.toContain(ENTITY_ID);
  });

  /**
   * #414: the backend title is still preferred for the *label*, but the panel
   * must resolve the endpoint anyway, because the **route** can only come from
   * the id-space bridge. The old code derived it as `/<type>/<artifact-id>`,
   * which 404s — a link row with a title but a broken target is worse than one
   * without a title.
   */
  it("[#414] still resolves for the route when the backend supplied a title", async () => {
    vi.mocked(resolveArtifactRefs).mockClear();
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

    // Backend title wins as the label ...
    await waitFor(() => {
      expect(screen.getByText("Resolved by backend")).toBeInTheDocument();
    });
    // ... while the route comes from the resolver, so the row is navigable.
    expect(vi.mocked(resolveArtifactRefs)).toHaveBeenCalledWith([NEIGHBOUR_ID]);
    expect(screen.getByTestId("trace-link-open-link-1")).toBeInTheDocument();
  });

  /**
   * #414: the route rendered for a neighbour must be the one the resolver
   * returned (entity id space), never `/<type>/<neighbour artifact id>`.
   */
  it("[#414] navigates to the resolved entity route, not the artifact id", async () => {
    vi.mocked(resolveArtifactRefs).mockClear();
    vi.mocked(tracelinksApi.listForArtifact).mockResolvedValueOnce({
      results: [link({ source_id: ENTITY_ID, target_id: NEIGHBOUR_ID })],
      count: 1,
    } as never);

    render(
      <MemoryRouter>
        <TraceLinkPanel workspaceId="ws-1" artifactId={ENTITY_ID} />
      </MemoryRouter>
    );

    const openBtn = await screen.findByTestId("trace-link-open-link-1");
    fireEvent.click(openBtn);

    // The mock maps <id> -> /requirements/entity-of-<id>; navigating to
    // /requirements/<NEIGHBOUR_ID> would be the #414 regression.
    expect(mockNavigate).toHaveBeenCalledWith(`/requirements/entity-of-${NEIGHBOUR_ID}`);
    expect(mockNavigate).not.toHaveBeenCalledWith(`/requirements/${NEIGHBOUR_ID}`);
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

/**
 * UI-P3 — a soft-deleted artifact kept showing up as a live, clickable,
 * fully-titled trace-link neighbour.
 *
 * The backend deliberately *preserves* a TraceLink when one of its endpoints
 * is soft-deleted ("TraceLinks are preserved for audit trail purposes",
 * `AdrService.delete_adr`), so `GET /tracelinks/?artifact_id=` keeps returning
 * it. `ArtifactService.resolve_artifact_titles` now reports the endpoint's
 * lifecycle state via `source_is_outdated`/`target_is_outdated`; this panel
 * must render such a row as dead and must not count it as a live relation.
 */
describe("TraceLinkPanel — soft-deleted endpoints (UI-P3)", () => {
  const ENTITY_ID = "11111111-1111-1111-1111-111111111111";
  const DEAD_ID = "22222222-2222-2222-2222-222222222222";
  const LIVE_ID = "44444444-4444-4444-4444-444444444444";
  const DEAD_LINK = "55555555-5555-5555-5555-555555555555";
  const LIVE_LINK = "66666666-6666-6666-6666-666666666666";

  const base = {
    link_type: "derives-from",
    version: 1,
    created_at: "2026-08-29T00:00:00Z",
    source_title: "",
    source_type: "",
  };

  /** Downstream link (panel artifact is the source) to a deleted ADR. */
  const deadLink = {
    ...base,
    id: DEAD_LINK,
    source_id: ENTITY_ID,
    target_id: DEAD_ID,
    target_title: "Deleted ADR",
    target_type: "Adr",
    target_is_outdated: true,
  };

  const liveLink = {
    ...base,
    id: LIVE_LINK,
    source_id: ENTITY_ID,
    target_id: LIVE_ID,
    target_title: "Live ADR",
    target_type: "Adr",
    target_is_outdated: false,
  };

  it("marks the row and drops the navigation link for a deleted endpoint", async () => {
    await i18n.changeLanguage("de");
    vi.mocked(tracelinksApi.listForArtifact).mockResolvedValueOnce({
      results: [deadLink],
      count: 1,
    } as never);

    render(
      <MemoryRouter>
        <TraceLinkPanel workspaceId="ws-1" artifactId={ENTITY_ID} />
      </MemoryRouter>
    );

    expect(
      await screen.findByTestId(`trace-link-outdated-badge-${DEAD_LINK}`)
    ).toHaveTextContent("Gelöscht");
    // The title is still shown — dropping it would only degrade the row to a
    // raw uuid stub and hide *why* the link looks odd.
    expect(screen.getByTestId(`trace-link-label-${DEAD_LINK}`)).toHaveTextContent(
      "Deleted ADR"
    );
    // …but it must not be navigable: every detail route filters outdated rows
    // out, so the link would 404.
    expect(
      screen.queryByTestId(`trace-link-open-${DEAD_LINK}`)
    ).not.toBeInTheDocument();
  });

  it("excludes deleted endpoints from the live relation counter", async () => {
    vi.mocked(tracelinksApi.listForArtifact).mockResolvedValueOnce({
      results: [deadLink, liveLink],
      count: 2,
    } as never);

    render(
      <MemoryRouter>
        <TraceLinkPanel workspaceId="ws-1" artifactId={ENTITY_ID} />
      </MemoryRouter>
    );

    // Two outgoing links, one of them dead -> the badge must read 1, not 2.
    const counter = await screen.findByTestId("trace-link-downstream-count");
    expect(counter).toHaveTextContent("1");
    // Both rows stay rendered: the dead link is audit-trail evidence.
    expect(screen.getByTestId(`trace-link-outdated-${DEAD_LINK}`)).toBeInTheDocument();
    expect(screen.getByTestId(`trace-link-open-${LIVE_LINK}`)).toBeInTheDocument();
  });

  it("treats a pre-UI-P3 payload without the flag as live", async () => {
    vi.mocked(tracelinksApi.listForArtifact).mockResolvedValueOnce({
      results: [{ ...liveLink, target_is_outdated: undefined }],
      count: 1,
    } as never);

    render(
      <MemoryRouter>
        <TraceLinkPanel workspaceId="ws-1" artifactId={ENTITY_ID} />
      </MemoryRouter>
    );

    expect(await screen.findByTestId(`trace-link-open-${LIVE_LINK}`)).toBeInTheDocument();
    expect(
      screen.queryByTestId(`trace-link-outdated-badge-${LIVE_LINK}`)
    ).not.toBeInTheDocument();
  });
});
