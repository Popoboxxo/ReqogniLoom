/**
 * Comments on artifacts (Menschen-im-System spec §4).
 *
 * Comments hang on the generic Artifact, so this wrapper takes an artifact id
 * for every one of the ten artifact kinds — there is no per-kind variant.
 */

import { apiClient } from "./client";
import type { UUID } from "../types";

/** Wire format returned by the backend (snake_case). */
interface CommentWire {
  id: string;
  artifact_id: string;
  text: string;
  author_id: string | null;
  author_display: string | null;
  resolved: boolean;
  resolved_by_id: string | null;
  resolved_at: string | null;
  created_at: string;
}

export interface Comment {
  id: UUID;
  artifactId: UUID;
  text: string;
  authorId: UUID | null;
  authorDisplay: string | null;
  resolved: boolean;
  resolvedById: UUID | null;
  resolvedAt: string | null;
  createdAt: string;
}

export interface ListCommentsOptions {
  /** Default true — pass false to show only open comments. */
  includeResolved?: boolean;
}

function toComment(wire: CommentWire): Comment {
  return {
    id: wire.id,
    artifactId: wire.artifact_id,
    text: wire.text,
    authorId: wire.author_id,
    authorDisplay: wire.author_display,
    resolved: wire.resolved,
    resolvedById: wire.resolved_by_id,
    resolvedAt: wire.resolved_at,
    createdAt: wire.created_at,
  };
}

export const commentsApi = {
  /** List an artifact's comments, oldest first. */
  async list(artifactId: UUID, options: ListCommentsOptions = {}): Promise<Comment[]> {
    const suffix = options.includeResolved === false ? "?include_resolved=false" : "";
    const rows = await apiClient.get<CommentWire[]>(
      `/artifacts/${artifactId}/comments/${suffix}`
    );
    return rows.map(toComment);
  },

  /** Add a comment to an artifact. */
  async create(artifactId: UUID, text: string): Promise<Comment> {
    return toComment(
      await apiClient.post<CommentWire>(`/artifacts/${artifactId}/comments/`, { text })
    );
  },

  /** Mark a comment resolved. */
  async resolve(commentId: UUID): Promise<Comment> {
    return toComment(await apiClient.post<CommentWire>(`/comments/${commentId}/resolve/`, {}));
  },

  /** Delete a comment (author or admin only — the backend enforces it). */
  async remove(commentId: UUID): Promise<void> {
    await apiClient.delete<void>(`/comments/${commentId}/`);
  },
};
