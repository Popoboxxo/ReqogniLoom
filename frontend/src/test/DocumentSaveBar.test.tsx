/**
 * R6.1 — batch save for the document reading view (plan
 * 2026-11-15-document-view-on-document.md).
 *
 * The bar itself is presentational, so every case is exercised through the
 * pair that actually ships: `useDocumentDrafts` (draft store + the one bulk
 * request) and `<DocumentSaveBar>` (counter, save-all, discard).
 *
 * What matters here is the failure behaviour, not the happy path alone: a
 * rejected batch is all-or-nothing server-side, so the surface must keep every
 * draft, mark what the server blamed, and leave "Save all" reachable instead of
 * pretending the edit landed.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "../i18n/index";

const { READING } = vi.hoisted(() => ({
  READING: {
    id: "doc-1",
    artifact_id: "art-1",
    uid: "DOC-001",
    title: "Architecture guide",
    kind: "Guide" as const,
    description: "How the system is put together.",
    body: "# Overview\n\nFirst chapter.",
    doc_date: "2026-11-02",
    version: 4,
    status: "Entwurf",
    frozen_at: null as string | null,
    frozen_fields: [] as string[],
    editable_fields: ["title", "description", "body"],
    fields: [
      { name: "title", value: "Architecture guide", editable: true, locked: null },
      {
        name: "description",
        value: "How the system is put together.",
        editable: true,
        locked: null,
      },
      { name: "body", value: "# Overview", editable: true, locked: null },
    ],
    capabilities: { can_write: true, read_only_reason: null as string | null },
    chapters: [],
    projection: {
      projection_mode: "none",
      source_path: "",
      projected_sha256: "",
    },
  },
}));

vi.mock("../api/documents", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/documents")>();
  return {
    ...actual,
    documentsApi: { ...actual.documentsApi, updateField: vi.fn() },
  };
});

vi.mock("../api/artifacts", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/artifacts")>();
  return {
    ...actual,
    artifactsApi: { ...actual.artifactsApi, bulkUpdate: vi.fn() },
  };
});

import {
  useDocumentDrafts,
  type DocumentDraftsResult,
} from "../components/Documents/useDocumentDrafts";
import { DocumentSaveBar } from "../components/Documents/DocumentSaveBar";
import { artifactsApi } from "../api/artifacts";
import type { DocumentReading } from "../types";

const bulkUpdate = artifactsApi.bulkUpdate as ReturnType<typeof vi.fn>;

const reading = READING as unknown as DocumentReading;

/**
 * The shipping composition: the hook owns drafts and the request, the bar owns
 * the affordances. The button row mutates drafts the way the field editors do.
 */
function Harness(): JSX.Element {
  const drafts: DocumentDraftsResult = useDocumentDrafts(reading, {
    workspaceId: "ws-001",
  });
  return (
    <div>
      <button
        type="button"
        data-testid="edit-title"
        onClick={() => drafts.setDraft("title", "Renamed guide")}
      >
        edit title
      </button>
      <button
        type="button"
        data-testid="edit-description"
        onClick={() => drafts.setDraft("description", "Rewritten description.")}
      >
        edit description
      </button>
      <button
        type="button"
        data-testid="revert-title"
        onClick={() => drafts.setDraft("title", "Architecture guide")}
      >
        revert title
      </button>

      <DocumentSaveBar
        dirtyCount={drafts.dirtyCount}
        conflicts={drafts.conflicts}
        saving={drafts.saving}
        error={drafts.saveError}
        onSaveAll={() => {
          void drafts.saveAll();
        }}
        onDiscard={drafts.resetAll}
      />

      <p data-testid="draft-state">
        {drafts.drafts.map((draft) => `${draft.field}:${draft.status}`).join(",")}
      </p>
      <p data-testid="draft-version">{drafts.version}</p>
    </div>
  );
}

describe("DocumentSaveBar (R6.1)", () => {
  beforeEach(() => {
    bulkUpdate.mockReset();
  });

  it("save_all_sends_one_request_with_all_entries", async () => {
    bulkUpdate.mockResolvedValue({
      updated: [{ artifact_id: "art-1", version: 5 }],
      errors: [],
    });
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(screen.getByTestId("edit-title"));
    await user.click(screen.getByTestId("edit-description"));
    await user.click(screen.getByTestId("document-save-all"));

    await waitFor(() => expect(bulkUpdate).toHaveBeenCalledTimes(1));
    expect(bulkUpdate).toHaveBeenCalledWith("ws-001", [
      {
        artifact_id: "art-1",
        expected_version: 4,
        fields: {
          title: "Renamed guide",
          description: "Rewritten description.",
        },
      },
    ]);
    // One request for the whole batch, and the version follows the response.
    await waitFor(() =>
      expect(screen.getByTestId("draft-version")).toHaveTextContent("5")
    );
    expect(screen.getByTestId("draft-state")).toHaveTextContent(
      "title:clean,description:clean"
    );
  });

  it("conflict_keeps_all_drafts_and_marks_the_artifact", async () => {
    bulkUpdate.mockRejectedValue({
      error: {
        code: "CONFLICT",
        message: "The document changed in the meantime.",
        details: [],
      },
    });
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(screen.getByTestId("edit-title"));
    await user.click(screen.getByTestId("edit-description"));
    await user.click(screen.getByTestId("document-save-all"));

    // The batch is rolled back server-side: nothing may look saved.
    await waitFor(() =>
      expect(screen.getByTestId("draft-state")).toHaveTextContent(
        "title:conflict,description:conflict"
      )
    );
    expect(
      screen.getByTestId("document-save-bar-conflicts")
    ).toHaveTextContent("2");
    expect(screen.getByTestId("document-save-bar-error")).toHaveTextContent(
      "The document changed in the meantime."
    );
    // Still retryable after a reload — never silently dropped.
    expect(screen.getByTestId("document-save-all")).toBeEnabled();
    expect(screen.getByTestId("document-discard")).toBeEnabled();
  });

  it("discard_clears_drafts_without_request", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(screen.getByTestId("edit-title"));
    expect(screen.getByTestId("document-save-all")).toBeEnabled();

    await user.click(screen.getByTestId("document-discard"));

    expect(screen.getByTestId("draft-state")).toBeEmptyDOMElement();
    expect(screen.getByTestId("document-save-all")).toBeDisabled();
    expect(bulkUpdate).not.toHaveBeenCalled();
  });

  it("dirty_counter_matches_changed_fields", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    expect(screen.getByText("0 changed fields")).toBeInTheDocument();
    await user.click(screen.getByTestId("edit-title"));
    expect(screen.getByText("1 changed fields")).toBeInTheDocument();
    await user.click(screen.getByTestId("edit-description"));
    expect(screen.getByText("2 changed fields")).toBeInTheDocument();

    // Typing a value back to the stored one is not a change.
    await user.click(screen.getByTestId("revert-title"));
    expect(screen.getByText("1 changed fields")).toBeInTheDocument();
  });

  it("save_all_is_disabled_without_changes", () => {
    render(<Harness />);

    expect(screen.getByTestId("document-save-all")).toBeDisabled();
    expect(screen.getByTestId("document-discard")).toBeDisabled();
  });

  it("field_level_errors_from_response_are_mapped", async () => {
    bulkUpdate.mockRejectedValue({
      errors: [
        {
          index: 0,
          artifact_id: "art-1",
          code: "FIELD_FROZEN",
          message: "The title is frozen after release.",
          field: "title",
        },
      ],
    });
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(screen.getByTestId("edit-title"));
    await user.click(screen.getByTestId("edit-description"));
    await user.click(screen.getByTestId("document-save-all"));

    await waitFor(() =>
      expect(screen.getByTestId("draft-state")).toHaveTextContent(
        "title:error,description:dirty"
      )
    );
    expect(screen.getByTestId("document-save-bar-error")).toHaveTextContent(
      "The title is frozen after release."
    );
    // Nothing was written: both drafts are still there.
    expect(screen.getByTestId("document-save-all")).toBeEnabled();
  });
});
