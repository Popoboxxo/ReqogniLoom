/**
 * F3-T9 — `[[` autocomplete grammar and ranking.
 *
 * The editor inserts the canonical stored token; the trigger helper only
 * decides when the popup may open. These cases pin the boundary so typing a
 * completed `[[glossary:…]]` token or a bracket in prose never re-opens it.
 */

import { describe, it, expect } from "vitest";

import {
  filterReferenceSuggestions,
  findReferenceTrigger,
} from "../components/WorkItems/referenceAutocomplete";
import type { GlossaryTerm } from "../types";

function term(overrides: Partial<GlossaryTerm>): GlossaryTerm {
  return {
    id: "t-1",
    workspace_id: "ws-1",
    term: "Trace",
    definition: "A link",
    synonyms: [],
    global_uuid: "00000000-0000-0000-0000-000000000001",
    version: 2,
    ...overrides,
  };
}

describe("findReferenceTrigger", () => {
  it("detects an open trigger and its query", () => {
    expect(findReferenceTrigger("Text [[Tra", 10)).toEqual({
      start: 5,
      query: "Tra",
    });
  });

  it("does not trigger once the token is closed", () => {
    const closed = "[[glossary:00000000-0000-0000-0000-000000000001@1]]";
    expect(findReferenceTrigger(closed, closed.length)).toBeNull();
  });

  it("ignores brackets separated by a newline", () => {
    expect(findReferenceTrigger("[[\nterm", 7)).toBeNull();
  });

  it("ignores a caret outside the value", () => {
    expect(findReferenceTrigger("abc", 99)).toBeNull();
  });
});

describe("filterReferenceSuggestions", () => {
  const terms = [
    term({ term: "Trace", synonyms: ["Link"] }),
    term({
      id: "t-2",
      term: "Baseline",
      global_uuid: "00000000-0000-0000-0000-000000000002",
    }),
    term({ id: "t-3", term: "Unlinked", global_uuid: undefined }),
  ];

  it("matches by name, synonym and abbreviation", () => {
    expect(filterReferenceSuggestions(terms, "tra").map((t) => t.term)).toEqual([
      "Trace",
    ]);
    expect(filterReferenceSuggestions(terms, "link").map((t) => t.term)).toEqual([
      "Trace",
    ]);
  });

  it("offers every referencable term for an empty query", () => {
    expect(filterReferenceSuggestions(terms, "").map((t) => t.term)).toEqual([
      "Trace",
      "Baseline",
    ]);
  });

  it("never offers a term without a global uuid", () => {
    expect(filterReferenceSuggestions(terms, "unlinked")).toEqual([]);
  });
});
