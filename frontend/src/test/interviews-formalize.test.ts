/**
 * R2F-003 regression — `formalize()` return type and consumer narrowing.
 *
 * `interviewsApi.formalize()` used to be typed as `Promise<SingleFormalizeResult>`
 * even when called with a confirmed multi-proposal, forcing
 * `InterviewChatPane` to cast to `MultiFormalizeResult` and read
 * `result.created` off every response — `undefined` for a single-kind
 * payload, which was then forwarded to `onFormalized`. The API now exposes
 * the union (via overloads that keep the single-argument caller typed as
 * `SingleFormalizeResult`), and the pane narrows on `"created" in result`.
 *
 * Both mock shapes below are typed WITHOUT any `as unknown as` cast; this
 * file compiling is part of the regression.
 */
import { beforeEach, describe, expect, it, vi, expectTypeOf } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { createElement, type ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";

vi.mock("../api/interviews", () => ({
  interviewsApi: { chat: vi.fn(), propose: vi.fn(), formalize: vi.fn() },
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

import {
  interviewsApi,
  type InterviewState,
  type MultiFormalizeResult,
  type ProposalItem,
  type SingleFormalizeResult,
} from "../api/interviews";
import { InterviewChatPane } from "../components/InterviewWidget/InterviewChatPane";

// Type-level check: the declared return type is the union, so consumers must
// narrow instead of casting. (tsconfig.build excludes tests, but vitest still
// evaluates this expression; the source-side guarantee is checked by tsc.)
expectTypeOf<ReturnType<typeof interviewsApi.formalize>>().toEqualTypeOf<
  Promise<SingleFormalizeResult | MultiFormalizeResult>
>();

const proposal: ProposalItem[] = [
  { type: "Requirement", title: "Login", fields: {}, links: [] },
];

function makeInterview(): InterviewState {
  return {
    id: "s1",
    status: "in_progress",
    session_kind: "multi",
    collected_fields: {},
    missing_fields: [],
    grounding_snapshot: { candidates: [] },
    transcript: [],
  };
}

function renderPane(ui: ReactElement) {
  return render(createElement(MemoryRouter, null, ui));
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(interviewsApi.propose).mockResolvedValue({ proposal });
});

describe("InterviewChatPane / formalize result shapes (R2F-003)", () => {
  it("handles a multi-kind result: shows created artifacts and forwards them", async () => {
    const onFormalized = vi.fn();
    const created = [{ artifact_id: "a1", artifact_type: "Requirement" }];
    // No cast: the typed API accepts the multi shape on a confirmed proposal.
    vi.mocked(interviewsApi.formalize).mockResolvedValue({
      created,
      status: "completed",
    });

    renderPane(
      createElement(InterviewChatPane, {
        interview: makeInterview(),
        onStateChange: vi.fn(),
        onFormalized,
      })
    );

    fireEvent.click(await screen.findByTestId("interview-multi-confirm"));
    expect(await screen.findByTestId("interview-multi-result")).toBeInTheDocument();
    expect(onFormalized).toHaveBeenCalledWith(created);
  });

  it("handles a single-kind result without crashing or forwarding undefined", async () => {
    const onFormalized = vi.fn();
    // No cast: the typed API also accepts the single shape.
    vi.mocked(interviewsApi.formalize).mockResolvedValue({
      resulting_artifact_ids: ["a1"],
      status: "completed",
    });

    renderPane(
      createElement(InterviewChatPane, {
        interview: makeInterview(),
        onStateChange: vi.fn(),
        onFormalized,
      })
    );

    fireEvent.click(await screen.findByTestId("interview-multi-confirm"));
    // The anomalous shape must not produce a result summary from `.created`
    // (which is undefined) nor hand `undefined` to the callback.
    await vi.waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(screen.queryByTestId("interview-multi-result")).not.toBeInTheDocument();
    expect(onFormalized).not.toHaveBeenCalled();
  });
});
