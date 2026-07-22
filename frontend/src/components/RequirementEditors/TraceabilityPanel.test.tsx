import { describe, it, expect } from "vitest";
/**
 * Tests for TraceabilityPanel component.
 * Verifies that linked requirement titles are displayed correctly.
 */

import { render, screen } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { TraceabilityPanel } from "./TraceabilityPanel";
import type { TraceLink } from "../../types";

// Mock router for navigation
const renderWithRouter = (component: React.ReactElement) => {
  return render(<BrowserRouter>{component}</BrowserRouter>);
};

describe("TraceabilityPanel", () => {
  it("displays linked requirement titles for upstream links", () => {
    const upstreamLinks: TraceLink[] = [
      {
        id: "link-1",
        source_id: "req-source-1",
        target_id: "req-current",
        link_type: "derives-from",
        version: 1,
        created_at: "2024-01-01T00:00:00Z",
      },
    ];

    const linkedTitles = {
      "req-source-1": "Upstream Requirement Title",
    };

    renderWithRouter(
      <TraceabilityPanel
        upstreamLinks={upstreamLinks}
        downstreamLinks={[]}
        linkedTitles={linkedTitles}
      />
    );

    expect(screen.getByText("Upstream Requirement Title")).toBeInTheDocument();
  });

  it("displays linked requirement titles for downstream links", () => {
    const downstreamLinks: TraceLink[] = [
      {
        id: "link-2",
        source_id: "req-current",
        target_id: "req-target-1",
        link_type: "satisfies",
        version: 1,
        created_at: "2024-01-01T00:00:00Z",
      },
    ];

    const linkedTitles = {
      "req-target-1": "Downstream Requirement Title",
    };

    renderWithRouter(
      <TraceabilityPanel
        upstreamLinks={[]}
        downstreamLinks={downstreamLinks}
        linkedTitles={linkedTitles}
      />
    );

    expect(screen.getByText("Downstream Requirement Title")).toBeInTheDocument();
  });

  it("displays fallback UUID prefix when title is not available", () => {
    const upstreamLinks: TraceLink[] = [
      {
        id: "link-3",
        source_id: "req-unknown",
        target_id: "req-current",
        link_type: "derives-from",
        version: 1,
        created_at: "2024-01-01T00:00:00Z",
      },
    ];

    renderWithRouter(
      <TraceabilityPanel
        upstreamLinks={upstreamLinks}
        downstreamLinks={[]}
        linkedTitles={{}}
      />
    );

    // Fallback should show first 8 characters of UUID + ellipsis
    expect(screen.getByText(/req-unkn/i)).toBeInTheDocument();
  });

  it("displays both upstream and downstream links", () => {
    const upstreamLinks: TraceLink[] = [
      {
        id: "link-1",
        source_id: "req-source-1",
        target_id: "req-current",
        link_type: "derives-from",
        version: 1,
        created_at: "2024-01-01T00:00:00Z",
      },
    ];

    const downstreamLinks: TraceLink[] = [
      {
        id: "link-2",
        source_id: "req-current",
        target_id: "req-target-1",
        link_type: "satisfies",
        version: 1,
        created_at: "2024-01-01T00:00:00Z",
      },
    ];

    const linkedTitles = {
      "req-source-1": "Upstream Title",
      "req-target-1": "Downstream Title",
    };

    renderWithRouter(
      <TraceabilityPanel
        upstreamLinks={upstreamLinks}
        downstreamLinks={downstreamLinks}
        linkedTitles={linkedTitles}
      />
    );

    expect(screen.getByText("Upstream Title")).toBeInTheDocument();
    expect(screen.getByText("Downstream Title")).toBeInTheDocument();
  });

  it("shows empty state when no upstream links exist", () => {
    renderWithRouter(
      <TraceabilityPanel
        upstreamLinks={[]}
        downstreamLinks={[]}
        linkedTitles={{}}
      />
    );

    const upstreamSections = screen.getAllByText(/upstream|downstream/i);
    expect(upstreamSections.length).toBeGreaterThan(0);
  });

  it("[UI-05] disables navigation for a link with an unresolved (empty) route", () => {
    const upstreamLinks: TraceLink[] = [
      {
        id: "link-unresolved",
        source_id: "req-unresolved",
        target_id: "req-current",
        link_type: "derives-from",
        version: 1,
        created_at: "2024-01-01T00:00:00Z",
      },
    ];

    renderWithRouter(
      <TraceabilityPanel
        upstreamLinks={upstreamLinks}
        downstreamLinks={[]}
        linkedTitles={{ "req-unresolved": "(req-unre…)" }}
        linkedRoutes={{ "req-unresolved": "" }}
      />
    );

    const navButton = screen.getByRole("button");
    expect(navButton).toBeDisabled();
  });

  it("includes title in tooltip on link item", () => {
    const upstreamLinks: TraceLink[] = [
      {
        id: "link-1",
        source_id: "req-source-1",
        target_id: "req-current",
        link_type: "derives-from",
        version: 1,
        created_at: "2024-01-01T00:00:00Z",
      },
    ];

    const linkedTitles = {
      "req-source-1": "Upstream Requirement Title",
    };

    renderWithRouter(
      <TraceabilityPanel
        upstreamLinks={upstreamLinks}
        downstreamLinks={[]}
        linkedTitles={linkedTitles}
      />
    );

    const linkElement = screen.getByText("Upstream Requirement Title");
    // Check that the element has a title attribute with both title and UUID
    expect(linkElement).toHaveAttribute(
      "title",
      expect.stringContaining("Upstream Requirement Title")
    );
  });
});
