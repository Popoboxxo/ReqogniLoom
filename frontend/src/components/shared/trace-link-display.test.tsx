/**
 * trace-link-display.test.tsx
 *
 * Unit tests for the TraceLinkDisplay shared component (REQ-002).
 *
 * Covers:
 *   - Renders backend-supplied title (source_title / target_title)
 *   - Falls back to truncated UUID when no title supplied
 *   - Renders link_type badge via getLinkTypeLabel
 *   - Renders delete button only when onDelete prop is provided
 *   - Calls onDelete with link.id when delete is clicked
 *   - data-testid attributes are present (E2E contract)
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { TraceLinkDisplay } from "./trace-link-display";
import type { TraceLink, UUID } from "../../types";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const mockNavigate = vi.fn();
vi.mock("react-router-dom", () => ({
  useNavigate: () => mockNavigate,
}));

vi.mock("../../utils/artifactRoutes", () => ({
  getArtifactRoute: (type: string, id: string) => `/mock/${type}/${id}`,
}));

vi.mock("../../constants/traceLinkLabels", () => ({
  getLinkTypeLabel: (lt: string) => `label:${lt}`,
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const SOURCE_ID = "aaaaaaaa-0000-0000-0000-000000000001" as UUID;
const TARGET_ID = "bbbbbbbb-0000-0000-0000-000000000002" as UUID;
const LINK_ID = "cccccccc-0000-0000-0000-000000000003" as UUID;

function makeLink(overrides: Partial<TraceLink> = {}): TraceLink {
  return {
    id: LINK_ID,
    source_id: SOURCE_ID,
    target_id: TARGET_ID,
    link_type: "satisfies",
    version: 1,
    created_at: "2026-01-01T00:00:00Z",
    source_title: "Source Requirement",
    target_title: "Target Architecture",
    source_type: "Requirement",
    target_type: "ArchitectureElement",
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("TraceLinkDisplay (REQ-002)", () => {
  beforeEach(() => {
    mockNavigate.mockReset();
  });

  describe("title resolution", () => {
    it("displays backend-supplied target_title when current artifact is source", () => {
      const link = makeLink();
      render(<TraceLinkDisplay link={link} currentArtifactId={SOURCE_ID} />);

      expect(screen.getByTestId("trace-link-display-title")).toHaveTextContent(
        "Target Architecture"
      );
    });

    it("displays backend-supplied source_title when current artifact is target", () => {
      const link = makeLink();
      render(<TraceLinkDisplay link={link} currentArtifactId={TARGET_ID} />);

      expect(screen.getByTestId("trace-link-display-title")).toHaveTextContent(
        "Source Requirement"
      );
    });

    it("falls back to truncated UUID when target_title is empty string", () => {
      const link = makeLink({ target_title: "" });
      render(<TraceLinkDisplay link={link} currentArtifactId={SOURCE_ID} />);

      // First 8 chars of TARGET_ID + ellipsis
      expect(screen.getByTestId("trace-link-display-title")).toHaveTextContent(
        `${TARGET_ID.slice(0, 8)}…`
      );
    });

    it("falls back to truncated UUID when title fields are absent", () => {
      const {
        source_title: _source_title,
        target_title: _target_title,
        source_type: _source_type,
        target_type: _target_type,
        ...rest
      } = makeLink();
      const link = rest as TraceLink;
      render(<TraceLinkDisplay link={link} currentArtifactId={SOURCE_ID} />);

      expect(screen.getByTestId("trace-link-display-title")).toHaveTextContent(
        `${TARGET_ID.slice(0, 8)}…`
      );
    });
  });

  describe("badge", () => {
    it("renders link_type label in badge via getLinkTypeLabel", () => {
      const link = makeLink();
      render(<TraceLinkDisplay link={link} currentArtifactId={SOURCE_ID} />);

      expect(screen.getByTestId("trace-link-display-badge")).toHaveTextContent(
        "label:satisfies"
      );
    });
  });

  describe("delete button", () => {
    it("does not render delete button when onDelete is not provided", () => {
      const link = makeLink();
      render(<TraceLinkDisplay link={link} currentArtifactId={SOURCE_ID} />);

      expect(
        screen.queryByTestId("trace-link-display-delete")
      ).not.toBeInTheDocument();
    });

    it("renders delete button when onDelete is provided", () => {
      const link = makeLink();
      const onDelete = vi.fn();
      render(
        <TraceLinkDisplay
          link={link}
          currentArtifactId={SOURCE_ID}
          onDelete={onDelete}
        />
      );

      expect(
        screen.getByTestId("trace-link-display-delete")
      ).toBeInTheDocument();
    });

    it("calls onDelete with link.id when delete button is clicked", () => {
      const link = makeLink();
      const onDelete = vi.fn();
      render(
        <TraceLinkDisplay
          link={link}
          currentArtifactId={SOURCE_ID}
          onDelete={onDelete}
        />
      );

      fireEvent.click(screen.getByTestId("trace-link-display-delete"));
      expect(onDelete).toHaveBeenCalledOnce();
      expect(onDelete).toHaveBeenCalledWith(LINK_ID);
    });
  });

  describe("data-testid with custom prefix", () => {
    it("uses testIdPrefix to build data-testid attributes", () => {
      const link = makeLink();
      render(
        <TraceLinkDisplay
          link={link}
          currentArtifactId={SOURCE_ID}
          testIdPrefix="custom-prefix"
        />
      );

      expect(screen.getByTestId("custom-prefix-item")).toBeInTheDocument();
      expect(screen.getByTestId("custom-prefix-badge")).toBeInTheDocument();
      expect(screen.getByTestId("custom-prefix-title")).toBeInTheDocument();
    });
  });

  describe("container element", () => {
    it("renders as li element with -item testid", () => {
      const link = makeLink();
      const { container } = render(
        <TraceLinkDisplay link={link} currentArtifactId={SOURCE_ID} />
      );

      const li = container.querySelector("li");
      expect(li).toBeInTheDocument();
      expect(li).toHaveAttribute("data-testid", "trace-link-display-item");
    });
  });
});
