/**
 * ARCH-L1-001 ReactFrontend — Actor API (Attribut v3 WS2, #936, spec section 4).
 *
 * The ``actor`` attribute type stores one of two wire value forms (the exact
 * shape ``ActorService.validate_actor_value`` accepts server-side):
 *
 * - internal  ``{"kind": "user", "id": "<user-or-actor-uuid>"}``
 * - external  ``{"kind": "external", "name": "<display name>"}``
 * - multiple  ``{"multiple": true, "items": [<entry>, ...]}`` (attribute
 *   property ``multiple`` selects the shape; the picker emits it verbatim)
 *
 * Where the candidates come from
 * ------------------------------
 * There is **no REST route for the ``Actor`` table**: ``backend/application/
 * actor_service.py`` is Layer-2 only and the only REST surface an actor could
 * read is the workspace-member directory (``GET /api/v1/workspaces/{id}/
 * members/``, ``WorkspaceMembersView``), which is readable by any active
 * member (unlike the tenant-admin-only ``GET /api/v1/users/`` the legacy
 * ``UserPicker`` uses). ``ActorService.resolve_reference`` accepts a ``User``
 * id as well as an ``Actor`` id ("user-or-actor-uuid"), creating the actor on
 * demand, so the member's ``user_id`` is a valid wire ``id``.
 *
 * External actors need no dedicated create route either: the write adapter
 * (``ArtifactAttributeGateway.resolve_actor_write_value`` -> ``ActorService.
 * get_or_create_external``) materializes the actor from the ``{"kind":
 * "external", "name"}`` value on save. That is why the picker stores the wire
 * form directly instead of pre-creating a row — the value it emits is exactly
 * what the backend accepts.
 *
 * The functions here are the single adapter between the workspace-member
 * directory and that wire vocabulary, so the picker never has to know the
 * member payload shape.
 */

import {
  workspaceMembersApi,
  type WorkspaceMember,
} from "./workspace-members";
import type { ActorValue } from "../types";

// The wire vocabulary lives in the canonical shared types module; re-exported
// here so every consumer of the actor API has one import site.
export type { ActorValue };

/** One searchable actor candidate derived from the member directory. */
export interface ActorCandidate {
  /** Wire ``id``: a ``User`` id resolves to its ``Actor`` on demand. */
  id: string;
  /** Human label used for display and case-insensitive search. */
  name: string;
  email: string;
}

function toCandidate(member: WorkspaceMember): ActorCandidate {
  // ``display_name`` is optional on the wire (a user may have neither first
  // nor last name); fall back to the username before the email, mirroring the
  // legacy UserPicker's own fallback order.
  const name = (member.display_name || member.username || member.email || "").trim();
  return {
    id: String(member.user_id),
    name: name || member.email || String(member.user_id),
    email: member.email ?? "",
  };
}

export const actorsApi = {
  /**
   * List the pickable internal actor candidates of a workspace.
   *
   * Reuses the workspace-member directory (the only member-readable listing
   * route) instead of the tenant-admin-only ``GET /users/``. Non-members get a
   * 403, which the caller surfaces as its own error state rather than an empty
   * picker (same reasoning as ``UserPicker``'s ``lookupFailed``).
   */
  async list(workspaceId: string): Promise<ActorCandidate[]> {
    const members = await workspaceMembersApi.list(workspaceId);
    return members.map(toCandidate);
  },
};
