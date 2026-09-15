import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";

vi.mock("../../../api/comments", () => ({
  commentsApi: {
    list: vi.fn(),
    create: vi.fn(),
    resolve: vi.fn(),
    remove: vi.fn(),
  },
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string, fallback?: string) => fallback ?? key }),
}));

import { commentsApi } from "../../../api/comments";
import { CommentPanel } from "./CommentPanel";

const comment = {
  id: "c1",
  artifactId: "a1",
  text: "needs a rationale",
  authorId: "u1",
  authorDisplay: "alice",
  resolved: false,
  resolvedById: null,
  resolvedAt: null,
  createdAt: "2026-09-04T10:00:00Z",
};

describe("CommentPanel", () => {
  beforeEach(() => {
    vi.mocked(commentsApi.list).mockReset().mockResolvedValue([comment]);
    vi.mocked(commentsApi.create).mockReset().mockResolvedValue(comment);
    vi.mocked(commentsApi.resolve).mockReset().mockResolvedValue({ ...comment, resolved: true });
    vi.mocked(commentsApi.remove).mockReset().mockResolvedValue(undefined);
  });

  it("loads and renders the artifact's comments", async () => {
    render(<CommentPanel kind="requirement" artifactId="a1" />);

    expect(await screen.findByText("needs a rationale")).toBeInTheDocument();
    expect(commentsApi.list).toHaveBeenCalledWith("a1");
  });

  it("shows an empty state when there are no comments", async () => {
    vi.mocked(commentsApi.list).mockResolvedValue([]);

    render(<CommentPanel kind="requirement" artifactId="a1" />);

    expect(await screen.findByTestId("comment-panel-empty")).toBeInTheDocument();
  });

  it("creates a comment and clears the input", async () => {
    const user = userEvent.setup();
    render(<CommentPanel kind="requirement" artifactId="a1" />);
    await screen.findByText("needs a rationale");

    const input = screen.getByTestId("comment-panel-input");
    await user.type(input, "another one");
    await user.click(screen.getByTestId("comment-panel-submit"));

    await waitFor(() => expect(commentsApi.create).toHaveBeenCalledWith("a1", "another one"));
    await waitFor(() => expect(input).toHaveValue(""));
  });

  it("disables submit while the input is empty", async () => {
    render(<CommentPanel kind="requirement" artifactId="a1" />);
    await screen.findByText("needs a rationale");

    expect(screen.getByTestId("comment-panel-submit")).toBeDisabled();
  });

  it("resolves a comment", async () => {
    const user = userEvent.setup();
    render(<CommentPanel kind="requirement" artifactId="a1" />);
    await screen.findByText("needs a rationale");

    await user.click(screen.getByTestId("comment-panel-resolve-c1"));

    await waitFor(() => expect(commentsApi.resolve).toHaveBeenCalledWith("c1"));
  });

  it("asks for confirmation before deleting", async () => {
    const user = userEvent.setup();
    render(<CommentPanel kind="requirement" artifactId="a1" />);
    await screen.findByText("needs a rationale");

    await user.click(screen.getByTestId("comment-panel-delete-c1"));
    expect(screen.getByTestId("comment-delete-dialog")).toBeInTheDocument();
    expect(commentsApi.remove).not.toHaveBeenCalled();

    await user.click(screen.getByTestId("comment-delete-confirm"));
    await waitFor(() => expect(commentsApi.remove).toHaveBeenCalledWith("c1"));
  });

  it("closes the dialog on the success path", async () => {
    const user = userEvent.setup();
    render(<CommentPanel kind="requirement" artifactId="a1" />);
    await screen.findByText("needs a rationale");

    await user.click(screen.getByTestId("comment-panel-delete-c1"));
    await user.click(screen.getByTestId("comment-delete-confirm"));

    await waitFor(() =>
      expect(screen.queryByTestId("comment-delete-dialog")).not.toBeInTheDocument()
    );
  });

  it("shows an error when loading fails", async () => {
    vi.mocked(commentsApi.list).mockRejectedValue(new Error("boom"));

    render(<CommentPanel kind="requirement" artifactId="a1" />);

    expect(await screen.findByTestId("comment-panel-error")).toBeInTheDocument();
  });
});
