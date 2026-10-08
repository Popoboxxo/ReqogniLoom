/**
 * suggestionKeys — FE review round 2, F1.
 *
 * `kind` is sent to the server, so it must be part of the TanStack Query key.
 * When it was omitted, two consumers with different kinds shared one cache
 * entry and one rendered the other's rows. These are pure key-shape
 * assertions — cheap and independent of a rendered hook.
 */

import { describe, expect, it } from "vitest";
import { suggestionKeys } from "./useSuggestionsData";

describe("suggestionKeys.list", () => {
  it("includes kind so different kind filters never share a cache entry", () => {
    const traceLink = suggestionKeys.list("ws-1", "open", "trace_link");
    const artifactCreate = suggestionKeys.list(
      "ws-1",
      "open",
      "artifact_create",
    );

    expect(traceLink).not.toEqual(artifactCreate);
    expect(traceLink).toContain("trace_link");
    expect(artifactCreate).toContain("artifact_create");
  });

  it("distinguishes an omitted kind filter from a specific one", () => {
    expect(suggestionKeys.list("ws-1", "open")).not.toEqual(
      suggestionKeys.list("ws-1", "open", "trace_link"),
    );
  });
});
