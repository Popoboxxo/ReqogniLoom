/**
 * #1266 — MarkdownPreview renders version-bound glossary references.
 *
 * Pins: the token is resolved through the API, shown as a highlighted mark
 * with the resolved version + drift flag, and the "raise to head" bulk action
 * rewrites the field value. The stored token text is never altered by the
 * preview itself.
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

vi.mock("react-i18next", () => {
  const t = (key: string, fallback?: string): string => fallback ?? key;
  return { useTranslation: () => ({ t, i18n: { language: "de" } }) };
});

let workspaceMode = "pinned";
vi.mock("../../context/WorkspaceContext", () => ({
  useWorkspace: () => ({
    activeWorkspace: { id: "ws-1", name: "WS", glossary_reference_mode: workspaceMode },
  }),
}));

vi.mock("../../api/glossary", () => ({
  glossaryApi: {
    list: vi.fn().mockResolvedValue([]),
    resolveReferences: vi.fn(),
    insertReference: vi.fn(),
    upgradeReferencesToHead: vi.fn(),
  },
}));

import { MarkdownPreview } from "./MarkdownPreview";
import { glossaryApi } from "../../api/glossary";

const UUID = "11111111-1111-1111-1111-111111111111";

function mockResolve(overrides: Partial<Record<string, unknown>> = {}) {
  vi.mocked(glossaryApi.resolveReferences).mockResolvedValue({
    mode: "pinned",
    has_drift: false,
    references: [
      {
        global_uuid: UUID,
        requested_revision: 1,
        resolved_revision: 1,
        head_revision: 1,
        term: "Autopilot",
        definition: "self-driving",
        resolved: true,
        drift: false,
        ...overrides,
      },
    ],
  });
}

describe("MarkdownPreview glossary references (#1266)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    workspaceMode = "pinned";
    mockResolve();
  });

  it("resolves a token and shows the term with its version", async () => {
    render(
      <MarkdownPreview
        value={`see [[glossary:${UUID}@1]] here`}
        onChange={vi.fn()}
      />
    );
    fireEvent.click(screen.getByTestId("md-preview-btn"));

    const mark = await screen.findByTestId("glossary-reference-mark");
    expect(mark).toHaveTextContent("Autopilot");
    expect(mark).toHaveAttribute("data-version", "1");
    expect(mark).toHaveAttribute("data-drift", "false");
    expect(glossaryApi.resolveReferences).toHaveBeenCalledWith(
      "ws-1",
      `see [[glossary:${UUID}@1]] here`
    );
  });

  it("flags drift and offers a bulk raise-to-head action", async () => {
    vi.mocked(glossaryApi.resolveReferences).mockResolvedValue({
      mode: "pinned",
      has_drift: true,
      references: [
        {
          global_uuid: UUID,
          requested_revision: 1,
          resolved_revision: 1,
          head_revision: 3,
          term: "Autopilot",
          definition: "self-driving",
          resolved: true,
          drift: true,
        },
      ],
    });
    const onChange = vi.fn();
    vi.mocked(glossaryApi.upgradeReferencesToHead).mockResolvedValue({
      text: `see [[glossary:${UUID}@3]] here`,
      upgraded: 1,
    });

    render(
      <MarkdownPreview value={`see [[glossary:${UUID}@1]] here`} onChange={onChange} />
    );
    fireEvent.click(screen.getByTestId("md-preview-btn"));

    const mark = await screen.findByTestId("glossary-reference-mark");
    expect(mark).toHaveAttribute("data-drift", "true");

    fireEvent.click(await screen.findByTestId("glossary-drift-upgrade"));
    await waitFor(() =>
      expect(glossaryApi.upgradeReferencesToHead).toHaveBeenCalledWith(
        "ws-1",
        `see [[glossary:${UUID}@1]] here`
      )
    );
    expect(onChange).toHaveBeenCalledWith(`see [[glossary:${UUID}@3]] here`);
  });

  it("marks an unresolvable token instead of dropping it", async () => {
    vi.mocked(glossaryApi.resolveReferences).mockResolvedValue({
      mode: "pinned",
      has_drift: false,
      references: [
        {
          global_uuid: UUID,
          requested_revision: null,
          resolved_revision: 0,
          head_revision: 0,
          term: "",
          definition: "",
          resolved: false,
          drift: false,
        },
      ],
    });

    render(<MarkdownPreview value={`ghost [[glossary:${UUID}]]`} onChange={vi.fn()} />);
    fireEvent.click(screen.getByTestId("md-preview-btn"));

    await waitFor(() =>
      expect(screen.getByTestId("glossary-reference-unresolved")).toBeInTheDocument()
    );
    expect(screen.getByTestId("glossary-reference-unresolved")).toHaveTextContent(UUID);
  });

  it("does not call the resolver when the text carries no token", () => {
    render(<MarkdownPreview value="plain text" onChange={vi.fn()} />);
    fireEvent.click(screen.getByTestId("md-preview-btn"));
    expect(glossaryApi.resolveReferences).not.toHaveBeenCalled();
  });
});
