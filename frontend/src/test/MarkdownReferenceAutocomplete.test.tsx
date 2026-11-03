/**
 * F3-T9 — `[[` autocomplete in the shared markdown editor.
 *
 * Drives the real editor with a controlled harness: typing `[[` opens the
 * listbox, clicking or pressing Enter inserts the *stored* token through
 * `references/insert/` (so the usage trace link exists, I-1), and Escape
 * closes the popup without changing the text.
 */

import { useState } from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "../i18n/index";

vi.mock("../context/WorkspaceContext", () => ({
  useWorkspace: () => ({
    activeWorkspace: { id: "ws-1", glossary_reference_mode: "pinned" },
  }),
}));

vi.mock("../api/glossary", () => ({
  glossaryApi: {
    list: vi.fn(),
    insertReference: vi.fn(),
    resolveReferences: vi.fn(),
    upgradeReferencesToHead: vi.fn(),
  },
}));

import { MarkdownPreview } from "../components/RequirementEditors/MarkdownPreview";
import { glossaryApi } from "../api/glossary";

const listMock = glossaryApi.list as ReturnType<typeof vi.fn>;
const insertMock = glossaryApi.insertReference as ReturnType<typeof vi.fn>;

const TERM = {
  id: "term-1",
  workspace_id: "ws-1",
  term: "Trace",
  definition: "A link between artifacts",
  synonyms: [],
  global_uuid: "00000000-0000-0000-0000-000000000001",
  version: 2,
};

function Harness({ onValue }: { onValue?: (value: string) => void }): JSX.Element {
  const [value, setValue] = useState("");
  return (
    <MarkdownPreview
      id="md-body"
      value={value}
      artifactId="art-1"
      onChange={(next) => {
        setValue(next);
        onValue?.(next);
      }}
    />
  );
}

describe("MarkdownPreview — [[ reference autocomplete (F3-T9)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listMock.mockResolvedValue([TERM]);
    insertMock.mockResolvedValue({
      token: `[[glossary:${TERM.global_uuid}@2]]`,
      global_uuid: TERM.global_uuid,
      term: TERM.term,
      definition: TERM.definition,
      version: 2,
      link_type: "references",
      mode: "pinned",
    });
  });

  it("opens the listbox and inserts the token on click", async () => {
    const onValue = vi.fn();
    render(<Harness onValue={onValue} />);

    await userEvent.type(screen.getByTestId("md-body-textarea"), "See [[[[Tra");
    await waitFor(() =>
      expect(screen.getByTestId("md-reference-suggestions")).toBeInTheDocument()
    );

    await userEvent.click(
      screen.getByTestId(`md-reference-option-${TERM.global_uuid}`)
    );

    await waitFor(() =>
      expect(insertMock).toHaveBeenCalledWith(
        "ws-1",
        "art-1",
        TERM.global_uuid
      )
    );
    await waitFor(() =>
      expect(onValue).toHaveBeenLastCalledWith(
        `See [[glossary:${TERM.global_uuid}@2]]`
      )
    );
    expect(screen.queryByTestId("md-reference-suggestions")).not.toBeInTheDocument();
  });

  it("inserts the highlighted suggestion with Enter", async () => {
    const onValue = vi.fn();
    render(<Harness onValue={onValue} />);

    await userEvent.type(screen.getByTestId("md-body-textarea"), "[[[[Tra");
    await waitFor(() =>
      expect(screen.getByTestId("md-reference-suggestions")).toBeInTheDocument()
    );
    await userEvent.keyboard("{Enter}");

    await waitFor(() =>
      expect(onValue).toHaveBeenLastCalledWith(
        `[[glossary:${TERM.global_uuid}@2]]`
      )
    );
  });

  it("closes the popup on Escape without changing the text", async () => {
    const onValue = vi.fn();
    render(<Harness onValue={onValue} />);

    await userEvent.type(screen.getByTestId("md-body-textarea"), "[[[[Tra");
    await waitFor(() =>
      expect(screen.getByTestId("md-reference-suggestions")).toBeInTheDocument()
    );
    await userEvent.keyboard("{Escape}");

    expect(screen.queryByTestId("md-reference-suggestions")).not.toBeInTheDocument();
    expect(insertMock).not.toHaveBeenCalled();
    expect(onValue).toHaveBeenLastCalledWith("[[Tra");
  });
});
