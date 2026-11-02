/**
 * F3-T9 — dead inline-reference hint (DOC-P7 / I-5).
 *
 * The anchor register has no REST read route in this task, so the hint derives
 * its verdict from the same resolver the editor uses: an unresolved token is a
 * dead reference. A resolution failure must stay silent, never block content.
 */

import { describe, it, expect, vi, beforeEach, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { i18n } from "../i18n/index";

vi.mock("../api/glossary", () => ({
  glossaryApi: {
    list: vi.fn(),
    insertReference: vi.fn(),
    resolveReferences: vi.fn(),
    upgradeReferencesToHead: vi.fn(),
  },
}));

import { InlineReferenceHints } from "../components/WorkItems/InlineReferenceHints";
import { glossaryApi } from "../api/glossary";

const resolveMock = glossaryApi.resolveReferences as ReturnType<typeof vi.fn>;

const TOKEN = "[[glossary:00000000-0000-0000-0000-000000000001@1]]";

describe("InlineReferenceHints (F3-T9)", () => {
  beforeAll(async () => {
    await i18n.changeLanguage("de");
  });

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders nothing for text without a reference token", () => {
    const { container } = render(
      <InlineReferenceHints text="Plain text" workspaceId="ws-1" />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("counts resolved references without a warning", async () => {
    resolveMock.mockResolvedValue({
      mode: "pinned",
      has_drift: false,
      references: [
        {
          global_uuid: "00000000-0000-0000-0000-000000000001",
          requested_revision: 1,
          resolved_revision: 1,
          head_revision: 1,
          term: "Trace",
          definition: "A link",
          resolved: true,
          drift: false,
        },
      ],
    });

    render(<InlineReferenceHints text={TOKEN} workspaceId="ws-1" />);

    await waitFor(() =>
      expect(screen.getByTestId("inline-reference-hints-count")).toHaveTextContent(
        "Inline-Verweise: 1"
      )
    );
    expect(screen.queryByTestId("inline-reference-hints-dead")).not.toBeInTheDocument();
  });

  it("flags an unresolved token as a dead reference (DOC-P7)", async () => {
    resolveMock.mockResolvedValue({
      mode: "pinned",
      has_drift: false,
      references: [
        {
          global_uuid: "00000000-0000-0000-0000-000000000001",
          requested_revision: 1,
          resolved_revision: 1,
          head_revision: 1,
          term: "Trace",
          definition: "A link",
          resolved: false,
          drift: false,
        },
      ],
    });

    render(<InlineReferenceHints text={TOKEN} workspaceId="ws-1" />);

    await waitFor(() =>
      expect(screen.getByTestId("inline-reference-hints-dead")).toHaveTextContent(
        "DOC-P7"
      )
    );
  });
});
